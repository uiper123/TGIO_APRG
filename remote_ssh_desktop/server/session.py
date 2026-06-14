from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from remote_ssh_desktop.common.protocol import (
    FRAME_CLIPBOARD,
    FRAME_CONTROL,
    FRAME_INPUT,
    FRAME_STATS,
    FRAME_VIDEO,
    PROTOCOL_VERSION,
    SUPPORTED_CODECS,
    control_error,
    decode_message,
    pack_frame,
    read_frame,
)
from remote_ssh_desktop.server.x11 import (
    ClipboardBridge,
    XInputController,
    available_desktop_command,
    capture_frame,
    ensure_xauthority,
    find_free_display,
    launch_desktop,
    launch_xvfb,
    make_session_env,
    wait_for_x,
)

LOG = logging.getLogger("remote-ssh-desktop.server.session")


@dataclass(slots=True)
class SessionConfig:
    session_id: str
    screen_size: tuple[int, int] = (1920, 1080)
    fps: int = 18
    quality: int = 80
    persistent: bool = False
    idle_timeout: int = 300
    desktop_command: str | None = None
    shared_folder: str | None = None
    clipboard_enabled: bool = True
    clipboard_max_bytes: int = 1_000_000


@dataclass(slots=True)
class SessionState:
    session_dir: Path
    socket_path: Path
    state_path: Path
    display: str = ""
    xauthority: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    xinput: XInputController | None = None
    clipboard: ClipboardBridge | None = None
    xvfb: subprocess.Popen[str] | None = None
    desktop: subprocess.Popen[str] | None = None
    current_writer: asyncio.StreamWriter | None = None
    last_proxy_seen: float = 0.0
    last_local_clipboard: str = ""
    last_remote_clipboard: str = ""
    last_frame_digest: bytes = b""
    quality: int = 80
    fps: int = 18
    frames_sent: int = 0
    running: bool = True
    client_ready: bool = False


class SessionWorker:
    def __init__(self, config: SessionConfig):
        self.config = config
        self.state = self._init_state(config)
        self._writer_lock = asyncio.Lock()
        self._server: asyncio.AbstractServer | None = None
        self._tasks: list[asyncio.Task] = []
        self._needs_stop = asyncio.Event()
        self._touch_proxy()

    def _init_state(self, config: SessionConfig) -> SessionState:
        session_dir = Path.home() / ".cache" / "remote-ssh-desktop" / config.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return SessionState(
            session_dir=session_dir,
            socket_path=session_dir / "proxy.sock",
            state_path=session_dir / "session.json",
            quality=config.quality,
            fps=config.fps,
        )

    @property
    def shared_folder(self) -> Path:
        return Path(self.config.shared_folder or (Path.home() / "RemoteShared")).expanduser().resolve()

    def _touch_proxy(self) -> None:
        self.state.last_proxy_seen = time.monotonic()

    def _write_state(self) -> None:
        payload = {
            "session_id": self.config.session_id,
            "socket_path": str(self.state.socket_path),
            "display": self.state.display,
            "xauthority": str(self.state.xauthority) if self.state.xauthority else "",
            "screen": list(self.config.screen_size),
            "shared_folder": str(self.shared_folder),
            "persistent": self.config.persistent,
            "clipboard_enabled": self.config.clipboard_enabled,
            "updated_at": time.time(),
            "pid": os.getpid(),
            "user": os.environ.get("USER", ""),
            "home": str(Path.home()),
        }
        self.state.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _bootstrap(self) -> None:
        display_num = find_free_display()
        self.state.display = f":{display_num}"
        self.state.xauthority = ensure_xauthority(self.state.session_dir, self.state.display)
        self.state.env = make_session_env(self.state.display, self.state.xauthority, Path.home(), os.environ.get("USER"))
        os.environ["DISPLAY"] = self.state.display
        os.environ["XAUTHORITY"] = str(self.state.xauthority)
        self.state.xvfb = launch_xvfb(self.state.display, self.config.screen_size, self.state.xauthority)
        wait_for_x(self.state.display)
        self.shared_folder.mkdir(parents=True, exist_ok=True)
        self.state.desktop = launch_desktop(self.state.env, available_desktop_command(self.config.desktop_command))
        self.state.xinput = XInputController(self.state.display)
        if self.config.clipboard_enabled:
            self.state.clipboard = ClipboardBridge(self.state.env, max_bytes=self.config.clipboard_max_bytes)
        self._write_state()

    def request_stop(self) -> None:
        self.state.running = False
        self._needs_stop.set()

    async def run(self) -> None:
        await self._bootstrap()
        loop = asyncio.get_running_loop()
        registered_signals: list[signal.Signals] = []
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self.request_stop)
                registered_signals.append(sig)
        try:
            with contextlib.suppress(FileNotFoundError):
                self.state.socket_path.unlink()
            self._server = await asyncio.start_unix_server(self._accept_proxy, path=str(self.state.socket_path))
            self._write_state()
            self._tasks = [
                asyncio.create_task(self._capture_loop(), name="capture"),
                asyncio.create_task(self._clipboard_loop(), name="clipboard"),
                asyncio.create_task(self._watchdog(), name="watchdog"),
            ]
            async with self._server:
                await self._needs_stop.wait()
        finally:
            for sig in registered_signals:
                with contextlib.suppress(Exception):
                    loop.remove_signal_handler(sig)
            await self.shutdown()

    async def _accept_proxy(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self.state.current_writer is not None:
            with contextlib.suppress(Exception):
                self.state.current_writer.close()
        self.state.current_writer = writer
        self.state.client_ready = False
        self._touch_proxy()
        await self._send_session()
        if self.state.clipboard:
            text = self.state.clipboard.read_text()
            if text:
                self.state.last_local_clipboard = text
                await self._send_frame(FRAME_CLIPBOARD, {"t": "clipboard", "format": "text", "data": text, "origin": "server"})
        try:
            while True:
                frame = await read_frame(reader)
                self._touch_proxy()
                await self._dispatch(frame.kind, frame.payload)
        except (asyncio.IncompleteReadError, EOFError, ConnectionError) as exc:
            LOG.debug("proxy disconnected for session %s: %s", self.config.session_id, exc)
        except Exception as exc:
            LOG.exception("proxy failed for session %s: %s", self.config.session_id, exc)
        finally:
            if self.state.current_writer is writer:
                self.state.current_writer = None
                self.state.client_ready = False
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def _send_session(self) -> None:
        await self._send_control(
            {
                "t": "session",
                "session_id": self.config.session_id,
                "display": self.state.display,
                "screen": list(self.config.screen_size),
                "fps": self.state.fps,
                "quality": self.state.quality,
                "codec": "jpeg",
                "cursor": "embedded",
                "shared_folder": str(self.shared_folder),
                "persistent": self.config.persistent,
                "clipboard_enabled": self.config.clipboard_enabled,
            }
        )

    async def _dispatch(self, kind: int, payload: bytes) -> None:
        message = decode_message(payload) if payload else {}
        if kind == FRAME_CONTROL:
            await self._handle_control(message)
        elif kind == FRAME_INPUT:
            await self._handle_input(message)
        elif kind == FRAME_CLIPBOARD:
            await self._handle_clipboard(message)
        elif kind == FRAME_STATS:
            self._apply_stats(message)

    async def _handle_control(self, message: dict[str, Any]) -> None:
        typ = message.get("t")
        if typ == "hello":
            proto = int(message.get("proto", 0) or 0)
            codec = str(message.get("codec", "jpeg"))
            if proto != PROTOCOL_VERSION:
                await self._send_control(control_error("bad_proto", f"expected protocol {PROTOCOL_VERSION}"))
                return
            if codec not in SUPPORTED_CODECS:
                await self._send_control(control_error("bad_codec", f"supported codecs: {sorted(SUPPORTED_CODECS)}"))
                return
            self.state.client_ready = True
            await self._send_control({"t": "hello", "ok": True, "proto": PROTOCOL_VERSION, "session_id": self.config.session_id})
            await self._send_session()
        elif typ == "ping":
            await self._send_control({"t": "pong", "ts": message.get("ts", time.time()), "server_ts": time.time()})
        elif typ == "stats":
            self._apply_stats(message)
        elif typ == "set_quality":
            self.state.quality = max(20, min(95, int(message.get("quality", self.state.quality))))
            self.state.fps = max(1, min(60, int(message.get("fps", self.state.fps))))

    def _apply_stats(self, message: dict[str, Any]) -> None:
        lag = float(message.get("latency_ms", 0.0) or 0.0)
        dropped = int(message.get("dropped", 0) or 0)
        if lag > 180 or dropped > 3:
            self.state.quality = max(35, self.state.quality - 5)
            self.state.fps = max(5, self.state.fps - 2)
        elif lag < 70 and dropped == 0:
            self.state.quality = min(90, self.state.quality + 1)
            self.state.fps = min(30, self.state.fps + 1)

    async def _handle_input(self, message: dict[str, Any]) -> None:
        xinput = self.state.xinput
        if xinput is None:
            return
        typ = message.get("t")
        if typ == "mouse_move":
            xinput.mouse_move(int(message.get("x", 0)), int(message.get("y", 0)))
        elif typ == "mouse_btn":
            xinput.mouse_button(int(message.get("button", 1)), bool(message.get("down", True)))
        elif typ == "scroll":
            xinput.scroll(int(message.get("dx", 0)), int(message.get("dy", 0)))
        elif typ == "key":
            xinput.key(str(message.get("keysym", "")), bool(message.get("down", True)), message.get("mods", []))

    async def _handle_clipboard(self, message: dict[str, Any]) -> None:
        if not self.config.clipboard_enabled or message.get("format") != "text":
            return
        text = str(message.get("data", ""))
        if len(text.encode("utf-8")) > self.config.clipboard_max_bytes:
            return
        origin = str(message.get("origin", ""))
        if origin == "client" and text != self.state.last_remote_clipboard:
            self.state.last_remote_clipboard = text
            if self.state.clipboard:
                self.state.clipboard.write_text(text)
        elif origin != "client" and text != self.state.last_local_clipboard:
            self.state.last_local_clipboard = text
            if self.state.clipboard:
                self.state.clipboard.write_text(text)

    async def _send_control(self, message: dict[str, Any]) -> None:
        await self._send_frame(FRAME_CONTROL, message)

    async def _send_frame(self, kind: int, payload: bytes | dict[str, Any]) -> None:
        writer = self.state.current_writer
        if writer is None:
            return
        raw = pack_frame(kind, payload)
        async with self._writer_lock:
            writer = self.state.current_writer
            if writer is None:
                return
            writer.write(raw)
            try:
                await writer.drain()
            except Exception:
                self.state.current_writer = None

    async def _capture_loop(self) -> None:
        last_sent = 0.0
        while self.state.running:
            start = time.monotonic()
            if not self.state.client_ready:
                await asyncio.sleep(0.05)
                continue
            try:
                jpeg, _ = capture_frame(self.state.display, quality=self.state.quality)
            except Exception:
                await asyncio.sleep(0.5)
                continue
            digest = hashlib.blake2b(jpeg, digest_size=8).digest()
            send = digest != self.state.last_frame_digest or (time.monotonic() - last_sent) > 1.0
            if send:
                self.state.last_frame_digest = digest
                last_sent = time.monotonic()
                self.state.frames_sent += 1
                await self._send_frame(FRAME_VIDEO, jpeg)
            delay = max(1.0 / max(self.state.fps, 1) - (time.monotonic() - start), 0.0)
            await asyncio.sleep(delay)

    async def _clipboard_loop(self) -> None:
        while self.state.running:
            if not self.config.clipboard_enabled:
                await asyncio.sleep(1.0)
                continue
            try:
                if self.state.clipboard:
                    text = self.state.clipboard.read_text()
                    if text and text != self.state.last_local_clipboard:
                        self.state.last_local_clipboard = text
                        await self._send_frame(FRAME_CLIPBOARD, {"t": "clipboard", "format": "text", "data": text, "origin": "server"})
            except Exception as exc:
                LOG.debug("clipboard poll failed for session %s: %s", self.config.session_id, exc, exc_info=True)
            await asyncio.sleep(0.75)

    async def _watchdog(self) -> None:
        grace = self.config.idle_timeout if self.config.persistent else 5
        while self.state.running:
            await asyncio.sleep(2)
            if self.state.current_writer is not None:
                self._touch_proxy()
                continue
            if time.monotonic() - self.state.last_proxy_seen > grace:
                self.state.running = False
                self._needs_stop.set()
                break

    async def shutdown(self) -> None:
        self.state.running = False
        for task in self._tasks:
            task.cancel()
        if self.state.xinput:
            self.state.xinput.close()
        for proc in (self.state.desktop, self.state.xvfb):
            if proc and proc.poll() is None:
                with contextlib.suppress(Exception):
                    proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    with contextlib.suppress(Exception):
                        proc.kill()
        with contextlib.suppress(Exception):
            if self.state.socket_path.exists():
                self.state.socket_path.unlink()
        if self.state.state_path.exists() and not self.config.persistent:
            with contextlib.suppress(Exception):
                self.state.state_path.unlink()
