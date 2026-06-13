from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..common.protocol import FRAME_CLIPBOARD, FRAME_CONTROL, FRAME_INPUT, FRAME_STATS, FRAME_VIDEO, decode_message, pack_frame, read_frame
from .x11 import ClipboardBridge, XInputController, available_desktop_command, capture_frame, ensure_xauthority, find_free_display, launch_desktop, launch_xvfb, make_session_env


@dataclass(slots=True)
class SessionConfig:
    session_id: str
    screen_size: tuple[int, int] = (1920, 1080)
    fps: int = 12
    quality: int = 80
    persistent: bool = True
    idle_timeout: int = 300
    desktop_command: str | None = None
    shared_folder: str | None = None


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
    fps: int = 12
    running: bool = True


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
        return SessionState(session_dir=session_dir, socket_path=session_dir / "proxy.sock", state_path=session_dir / "session.json", quality=config.quality, fps=config.fps)

    def _touch_proxy(self) -> None:
        self.state.last_proxy_seen = time.monotonic()

    def _write_state(self) -> None:
        payload = {
            "session_id": self.config.session_id,
            "socket_path": str(self.state.socket_path),
            "display": self.state.display,
            "xauthority": str(self.state.xauthority) if self.state.xauthority else "",
            "screen_size": list(self.config.screen_size),
            "shared_folder": self.config.shared_folder or str(Path.home() / "RemoteShared"),
            "persistent": self.config.persistent,
            "updated_at": time.time(),
        }
        self.state.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _bootstrap(self) -> None:
        display_num = find_free_display()
        self.state.display = f":{display_num}"
        self.state.xauthority = ensure_xauthority(self.state.session_dir, self.state.display)
        self.state.env = make_session_env(self.state.display, self.state.xauthority)
        self.state.xvfb = launch_xvfb(self.state.display, self.config.screen_size, self.state.xauthority)
        self.state.desktop = launch_desktop(self.state.env, available_desktop_command(self.config.desktop_command))
        os.environ["DISPLAY"] = self.state.display
        os.environ["XAUTHORITY"] = str(self.state.xauthority)
        self.state.xinput = XInputController(self.state.display)
        self.state.clipboard = ClipboardBridge(self.state.env)
        Path(self.config.shared_folder or (Path.home() / "RemoteShared")).mkdir(parents=True, exist_ok=True)
        self._write_state()

    async def run(self) -> None:
        await self._bootstrap()
        with contextlib.suppress(FileNotFoundError):
            if self.state.socket_path.exists():
                self.state.socket_path.unlink()
        self._server = await asyncio.start_unix_server(self._accept_proxy, path=str(self.state.socket_path))
        self._write_state()
        self._tasks = [asyncio.create_task(self._capture_loop()), asyncio.create_task(self._clipboard_loop()), asyncio.create_task(self._watchdog())]
        async with self._server:
            await self._needs_stop.wait()
        await self.shutdown()

    async def _accept_proxy(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self.state.current_writer is not None:
            with contextlib.suppress(Exception):
                self.state.current_writer.close()
        self.state.current_writer = writer
        self._touch_proxy()
        await self._send_control({"t": "session", "session_id": self.config.session_id, "display": self.state.display, "screen": list(self.config.screen_size), "fps": self.state.fps, "quality": self.state.quality, "shared_folder": self.config.shared_folder or str(Path.home() / "RemoteShared"), "persistent": self.config.persistent})
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
        except Exception:
            pass
        finally:
            if self.state.current_writer is writer:
                self.state.current_writer = None
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def _dispatch(self, kind: int, payload: bytes) -> None:
        message = decode_message(payload) if payload else {}
        if kind == FRAME_CONTROL:
            typ = message.get("t")
            if typ == "hello":
                await self._send_control({"t": "hello", "ok": True, "session_id": self.config.session_id})
            elif typ == "ping":
                await self._send_control({"t": "pong", "ts": message.get("ts", time.time())})
        elif kind == FRAME_INPUT:
            await self._handle_input(message)
        elif kind == FRAME_CLIPBOARD:
            await self._handle_clipboard(message)
        elif kind == FRAME_STATS:
            self._apply_stats(message)

    def _apply_stats(self, message: dict[str, Any]) -> None:
        lag = float(message.get("latency_ms", 0.0) or 0.0)
        if lag > 150:
            self.state.quality = max(45, self.state.quality - 5)
            self.state.fps = max(5, self.state.fps - 1)
        elif lag < 60:
            self.state.quality = min(90, self.state.quality + 1)
            self.state.fps = min(max(self.state.fps, 8), 30)

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
        if message.get("format") != "text":
            return
        text = str(message.get("data", ""))
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
                await self._send_frame(FRAME_VIDEO, jpeg)
            delay = max(1.0 / max(self.state.fps, 1) - (time.monotonic() - start), 0.0)
            await asyncio.sleep(delay)

    async def _clipboard_loop(self) -> None:
        while self.state.running:
            try:
                if self.state.clipboard:
                    text = self.state.clipboard.read_text()
                    if text and text != self.state.last_local_clipboard:
                        self.state.last_local_clipboard = text
                        await self._send_frame(FRAME_CLIPBOARD, {"t": "clipboard", "format": "text", "data": text, "origin": "server"})
            except Exception:
                pass
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
