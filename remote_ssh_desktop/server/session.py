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
    FRAME_AUDIO,
    FRAME_STATS,
    FRAME_VIDEO,
    FLAG_DELTA,
    PROTOCOL_VERSION,
    SUPPORTED_CODECS,
    control_error,
    decode_message,
    pack_frame,
    read_frame,
)
from remote_ssh_desktop.server.backends.base import SessionBackend

LOG = logging.getLogger("remote-ssh-desktop.server.session")


# ── Delta encoding helpers ───────────────────────────────────────────────────

_BLOCK_SIZE = 64  # pixels per block side; 64×64 = 4096 pixels each

def _split_blocks(img, width: int, height: int, quality: int = 80) -> dict[int, tuple[bytes, bytes]]:
    """Split a decoded RGB image into (block_jpeg, block_hash) by 64x64 tile index.

    Returns a dict mapping tile_index -> (jpeg_bytes, blake2b_hash).
    Tiles are indexed row-major (tile 0 = top-left); columns = ceil(width / 64).
    The tile size and grid layout MUST stay in sync with the client compositor.
    """
    from io import BytesIO
    result: dict[int, tuple[bytes, bytes]] = {}
    cols = (width  + _BLOCK_SIZE - 1) // _BLOCK_SIZE
    rows = (height + _BLOCK_SIZE - 1) // _BLOCK_SIZE
    q = max(20, min(95, int(quality)))
    for row in range(rows):
        for col in range(cols):
            x0 = col * _BLOCK_SIZE
            y0 = row * _BLOCK_SIZE
            x1 = min(x0 + _BLOCK_SIZE, width)
            y1 = min(y0 + _BLOCK_SIZE, height)
            tile = img.crop((x0, y0, x1, y1))
            buf = BytesIO()
            tile.save(buf, format="JPEG", quality=q, optimize=True)
            jpeg = buf.getvalue()
            h = hashlib.blake2b(jpeg, digest_size=8).digest()
            result[row * cols + col] = (jpeg, h)
    return result


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
    current_writer: asyncio.StreamWriter | None = None
    last_proxy_seen: float = 0.0
    last_local_clipboard: str = ""
    last_remote_clipboard: str = ""
    last_frame_digest: bytes = b""
    quality: int = 80
    fps: int = 18
    frames_sent: int = 0
    frames_seq: int = 0
    # Delta encoding: per-block hashes from the previous frame
    prev_block_hashes: dict[int, bytes] = field(default_factory=dict)
    running: bool = True
    client_ready: bool = False


class SessionWorker:
    def __init__(self, config: SessionConfig, backend: SessionBackend | None = None):
        self.config = config
        self.state = self._init_state(config)
        # Use provided backend or auto-detect from platform
        if backend is None:
            from remote_ssh_desktop.server.backends import create_backend
            backend = create_backend()
        self.backend = backend
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
        display_info = self.backend.display_info
        payload = {
            "session_id": self.config.session_id,
            "socket_path": str(self.state.socket_path),
            **display_info,
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
        self.backend.check_dependencies()
        self.backend.startup(
            session_id=self.config.session_id,
            screen_size=self.config.screen_size,
            desktop_command=self.config.desktop_command,
            clipboard_enabled=self.config.clipboard_enabled,
            clipboard_max_bytes=self.config.clipboard_max_bytes,
        )
        self.shared_folder.mkdir(parents=True, exist_ok=True)
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
            asyncio.create_task(self._audio_loop(), name="audio"),
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
        if self.config.clipboard_enabled:
            text = self.backend.get_clipboard()
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
                "display": self.backend.display_info.get("display", ""),
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
        typ = message.get("t")
        if typ == "mouse_move":
            self.backend.inject_mouse_move(int(message.get("x", 0)), int(message.get("y", 0)))
        elif typ == "mouse_btn":
            self.backend.inject_mouse_button(int(message.get("button", 1)), bool(message.get("down", True)))
        elif typ == "scroll":
            self.backend.inject_scroll(int(message.get("dx", 0)), int(message.get("dy", 0)))
        elif typ == "key":
            self.backend.inject_key(str(message.get("keysym", "")), bool(message.get("down", True)), message.get("mods", []))

    async def _handle_clipboard(self, message: dict[str, Any]) -> None:
        if not self.config.clipboard_enabled or message.get("format") != "text":
            return
        text = str(message.get("data", ""))
        if len(text.encode("utf-8")) > self.config.clipboard_max_bytes:
            return
        origin = str(message.get("origin", ""))
        if origin == "client" and text != self.state.last_remote_clipboard:
            self.state.last_remote_clipboard = text
            self.backend.set_clipboard(text)
        elif origin != "client" and text != self.state.last_local_clipboard:
            self.state.last_local_clipboard = text
            self.backend.set_clipboard(text)

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
        """Capture frames and stream them with 64x64 block-level delta encoding.

        Each frame is decoded once, split into 64x64 tiles, and only the tiles
        whose JPEG changed since the last sent frame are transmitted.  The client
        composites incoming tiles onto its framebuffer, cutting traffic sharply on
        mostly-static screens.

        A full keyframe (plain JPEG after the 4-byte seq prefix) is sent on the
        first frame, whenever >=80 % of tiles change, and at least every 5 seconds,
        so a freshly-attached or de-synced client can always recover.
        """
        from PIL import Image as _PILImage
        from io import BytesIO as _BytesIO

        last_keyframe = 0.0
        KEYFRAME_INTERVAL = 5.0
        KEYFRAME_THRESHOLD = 0.8
        while self.state.running:
            start = time.monotonic()
            if not self.state.client_ready:
                await asyncio.sleep(0.05)
                continue
            try:
                jpeg_full, (fw, fh) = self.backend.capture_frame(quality=self.state.quality)
            except Exception as exc:
                LOG.debug("capture error: %s", exc)
                await asyncio.sleep(0.5)
                continue
            try:
                img = _PILImage.open(_BytesIO(jpeg_full)).convert("RGB")
                blocks = _split_blocks(img, fw, fh, self.state.quality)
                force_keyframe = (
                    not self.state.prev_block_hashes
                    or (time.monotonic() - last_keyframe) >= KEYFRAME_INTERVAL
                )
                changed = [idx for idx, (_, h) in blocks.items()
                           if h != self.state.prev_block_hashes.get(idx)]
                change_ratio = len(changed) / max(len(blocks), 1)
                if force_keyframe or change_ratio >= KEYFRAME_THRESHOLD:
                    self.state.last_frame_digest = hashlib.blake2b(jpeg_full, digest_size=8).digest()
                    last_keyframe = time.monotonic()
                    self.state.frames_sent += 1
                    self.state.frames_seq += 1
                    seq_prefix = self.state.frames_seq.to_bytes(4, "big")
                    self.state.prev_block_hashes = {idx: h for idx, (_, h) in blocks.items()}
                    await self._send_frame(FRAME_VIDEO, seq_prefix + jpeg_full)
                elif changed:
                    # Delta bundle: 4-byte seq | FLAG_DELTA | per block:
                    #   2-byte block_idx | 4-byte jpeg_len | jpeg_bytes
                    self.state.frames_seq += 1
                    seq_prefix = self.state.frames_seq.to_bytes(4, "big")
                    delta_parts = [seq_prefix, bytes([FLAG_DELTA])]
                    for idx in changed:
                        tile_jpeg, tile_hash = blocks[idx]
                        delta_parts.append(idx.to_bytes(2, "big"))
                        delta_parts.append(len(tile_jpeg).to_bytes(4, "big"))
                        delta_parts.append(tile_jpeg)
                        self.state.prev_block_hashes[idx] = tile_hash
                    self.state.frames_sent += 1
                    await self._send_frame(FRAME_VIDEO, b"".join(delta_parts))
                # else: nothing changed since the last frame — skip
            except Exception as exc:
                LOG.debug("delta capture error: %s", exc)
            delay = max(1.0 / max(self.state.fps, 1) - (time.monotonic() - start), 0.0)
            await asyncio.sleep(delay)

    async def _clipboard_loop(self) -> None:
        while self.state.running:
            if not self.config.clipboard_enabled:
                await asyncio.sleep(1.0)
                continue
            try:
                if self.config.clipboard_enabled:
                    text = self.backend.get_clipboard()
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


    async def _audio_loop(self) -> None:
        """Optionally forward server audio (PulseAudio / PipeWire) to the client.

        This loop is only started when --audio is passed to the server CLI and
        a supported audio backend (pacat / pw-cat) is available.  Audio is sent
        as raw 16-bit little-endian stereo 44100 Hz PCM chunks in FRAME_AUDIO frames.
        The client can play these through QMediaPlayer or pyaudio.
        """
        import shutil
        import subprocess as _sp
        from remote_ssh_desktop.common.protocol import FRAME_AUDIO

        # Prefer pw-cat (PipeWire) then pacat (PulseAudio)
        cmd = None
        if shutil.which("pw-cat"):
            cmd = ["pw-cat", "--record", "--raw", "--rate=44100",
                   "--channels=2", "--format=s16", "-"]
        elif shutil.which("pacat"):
            cmd = ["pacat", "--record", "--raw", "--rate=44100",
                   "--channels=2", "--format=s16le"]
        else:
            LOG.info("audio loop disabled: pw-cat and pacat not found")
            return

        LOG.info("audio loop starting: %s", cmd[0])
        CHUNK = 4096  # bytes per frame (≈23 ms at 44.1 kHz stereo s16)
        try:
            proc = _sp.Popen(
                cmd,
                stdout=_sp.PIPE,
                stderr=_sp.DEVNULL,
                env=getattr(self.backend, "env", None) or None,
            )
            while self.state.running and proc.poll() is None:
                chunk = proc.stdout.read(CHUNK)  # type: ignore[union-attr]
                if not chunk:
                    await asyncio.sleep(0.01)
                    continue
                await self._send_frame(FRAME_AUDIO, chunk)
        except Exception as exc:
            LOG.debug("audio loop error: %s", exc)
        finally:
            with contextlib.suppress(Exception):
                proc.terminate()

    async def shutdown(self) -> None:
        self.state.running = False
        for task in self._tasks:
            task.cancel()
        with contextlib.suppress(Exception):
            self.backend.shutdown()
        with contextlib.suppress(Exception):
            if self.state.socket_path.exists():
                self.state.socket_path.unlink()
        if self.state.state_path.exists() and not self.config.persistent:
            with contextlib.suppress(Exception):
                self.state.state_path.unlink()
