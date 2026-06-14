from __future__ import annotations

import asyncio
import contextlib
import os
import platform
import shlex
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import asyncssh
from PySide6.QtCore import QPointF, QThread, Qt, Signal, QTimer
from PySide6.QtGui import QAction, QColor, QImage, QKeyEvent, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QStyleFactory,
)

from remote_ssh_desktop.common.diagnostics import report_to_text, run_diagnostics, save_report
from remote_ssh_desktop.common.files import join_remote_jail, normalize_remote_rel
from remote_ssh_desktop.common.protocol import (
    FRAME_CLIPBOARD,
    FRAME_CONTROL,
    FRAME_INPUT,
    FRAME_STATS,
    FRAME_VIDEO,
    PROTOCOL_VERSION,
    decode_message,
    pack_frame,
    read_frame,
)
from remote_ssh_desktop.crypto.keygen import authorized_keys_line, save_keypair
from remote_ssh_desktop.version import __version__
from remote_ssh_desktop.common.profiles import export_profiles, import_profiles, import_ssh_config, load_profiles, save_profiles, validate_profile_name
from remote_ssh_desktop.common.history import clear_history, connection_label, latest_history, load_history, record_connection


QUALITY_PRESETS = {
    "LAN": {"fps": 30, "quality": 90},
    "WAN": {"fps": 18, "quality": 75},
    "Mobile": {"fps": 10, "quality": 55},
}


DEFAULT_REMOTE_COMMAND = (
    "python -m remote_ssh_desktop.server.main --proxy --session-id {session_id} "
    "--screen {screen} --fps {fps} --quality {quality} --idle-timeout {idle_timeout} "
    "{persistent_flag} {clipboard_flag} --clipboard-max-bytes {clipboard_max_bytes} "
    "--shared-folder {shared_folder}"
)


DARK_QSS = """
QMainWindow, QWidget { background: #0f1218; color: #e6edf3; font-family: Inter, Segoe UI, Arial, sans-serif; font-size: 13px; }
QToolBar { background: #151a23; border: 0; border-bottom: 1px solid #273244; spacing: 6px; padding: 8px; }
QToolButton, QPushButton { background: #2563eb; color: white; border: 0; border-radius: 8px; padding: 8px 12px; font-weight: 600; }
QToolButton:hover, QPushButton:hover { background: #3b82f6; }
QToolButton:pressed, QPushButton:pressed { background: #1d4ed8; }
QPushButton[secondary="true"] { background: #243044; color: #d7e1f0; }
QPushButton[secondary="true"]:hover { background: #31415c; }
QLineEdit, QSpinBox, QComboBox { background: #111827; color: #eef4ff; border: 1px solid #334155; border-radius: 8px; padding: 7px 9px; selection-background-color: #2563eb; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #60a5fa; }
QGroupBox { border: 1px solid #263246; border-radius: 14px; margin-top: 14px; padding: 14px; background: #131923; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #93c5fd; }
QTabWidget::pane { border: 1px solid #263246; border-radius: 14px; top: -1px; }
QTabBar::tab { background: #151a23; color: #9fb1c8; border: 1px solid #263246; padding: 10px 18px; border-top-left-radius: 10px; border-top-right-radius: 10px; }
QTabBar::tab:selected { background: #1e293b; color: #ffffff; }
QListWidget { background: #0b1020; border: 1px solid #263246; border-radius: 12px; padding: 6px; }
QListWidget::item { padding: 9px; border-radius: 8px; }
QListWidget::item:selected { background: #1d4ed8; color: #ffffff; }
QProgressBar { background: #111827; border: 1px solid #334155; border-radius: 8px; height: 14px; text-align: center; }
QProgressBar::chunk { background: #22c55e; border-radius: 8px; }
QLabel[muted="true"] { color: #94a3b8; }
QLabel[status="true"] { background: #111827; border: 1px solid #263246; border-radius: 10px; padding: 8px 10px; }
QFrame#remoteDisplay { border: 1px solid #263246; border-radius: 16px; background: #05070d; }
"""

LIGHT_QSS = """
QMainWindow, QWidget { background: #f6f8fb; color: #0f172a; font-family: Inter, Segoe UI, Arial, sans-serif; font-size: 13px; }
QToolBar { background: #ffffff; border: 0; border-bottom: 1px solid #dbe4f0; spacing: 6px; padding: 8px; }
QToolButton, QPushButton { background: #2563eb; color: white; border: 0; border-radius: 8px; padding: 8px 12px; font-weight: 600; }
QToolButton:hover, QPushButton:hover { background: #1d4ed8; }
QPushButton[secondary="true"] { background: #e2e8f0; color: #0f172a; }
QPushButton[secondary="true"]:hover { background: #cbd5e1; }
QLineEdit, QSpinBox, QComboBox { background: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 8px; padding: 7px 9px; selection-background-color: #2563eb; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #2563eb; }
QGroupBox { border: 1px solid #dbe4f0; border-radius: 14px; margin-top: 14px; padding: 14px; background: #ffffff; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #1d4ed8; }
QTabWidget::pane { border: 1px solid #dbe4f0; border-radius: 14px; top: -1px; background: #ffffff; }
QTabBar::tab { background: #eaf0f8; color: #475569; border: 1px solid #dbe4f0; padding: 10px 18px; border-top-left-radius: 10px; border-top-right-radius: 10px; }
QTabBar::tab:selected { background: #ffffff; color: #0f172a; }
QListWidget { background: #ffffff; border: 1px solid #dbe4f0; border-radius: 12px; padding: 6px; }
QListWidget::item { padding: 9px; border-radius: 8px; }
QListWidget::item:selected { background: #2563eb; color: #ffffff; }
QProgressBar { background: #e2e8f0; border: 1px solid #cbd5e1; border-radius: 8px; height: 14px; text-align: center; }
QProgressBar::chunk { background: #16a34a; border-radius: 8px; }
QLabel[muted="true"] { color: #64748b; }
QLabel[status="true"] { background: #ffffff; border: 1px solid #dbe4f0; border-radius: 10px; padding: 8px 10px; }
QFrame#remoteDisplay { border: 1px solid #dbe4f0; border-radius: 16px; background: #0f172a; }
"""


def apply_theme(app: QApplication, theme: str) -> None:
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setStyleSheet(LIGHT_QSS if theme == "light" else DARK_QSS)


def qt_user_role():
    return getattr(getattr(Qt, "ItemDataRole", Qt), "UserRole")


def qt_button(button, left=1, middle=2, right=3) -> int:
    mouse = getattr(Qt, "MouseButton", Qt)
    mapping = {
        getattr(mouse, "LeftButton"): left,
        getattr(mouse, "MiddleButton"): middle,
        getattr(mouse, "RightButton"): right,
    }
    return mapping.get(button, left)


@dataclass(slots=True)
class ClientConfig:
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""
    key_file: str = ""
    key_passphrase: str = ""
    remote_command: str = DEFAULT_REMOTE_COMMAND
    session_id: str = ""
    screen: tuple[int, int] = (1920, 1080)
    fps: int = 18
    quality: int = 80
    persistent: bool = False
    idle_timeout: int = 300
    shared_folder: str = "~/RemoteShared"
    known_hosts: str = ""
    verify_host_key: bool = True
    clipboard_enabled: bool = True
    clipboard_max_bytes: int = 1_000_000
    reconnect_enabled: bool = True
    reconnect_attempts: int = 5
    reconnect_delay: float = 2.0
    proxy_jump: str = ""
    quality_preset: str = "WAN"

    @property
    def screen_text(self) -> str:
        return f"{self.screen[0]}x{self.screen[1]}"

    def format_remote_command(self) -> str:
        return self.remote_command.format(
            session_id=shlex.quote(self.session_id),
            screen=shlex.quote(self.screen_text),
            fps=self.fps,
            quality=self.quality,
            idle_timeout=self.idle_timeout,
            persistent_flag="--persistent" if self.persistent else "",
            clipboard_flag="" if self.clipboard_enabled else "--no-clipboard",
            clipboard_max_bytes=self.clipboard_max_bytes,
            shared_folder=shlex.quote(self.shared_folder),
        )


class TransportThread(QThread):
    videoFrame = Signal(bytes)
    statusChanged = Signal(str)
    sessionInfo = Signal(dict)
    clipboardReceived = Signal(str)
    disconnected = Signal(str)
    transferProgress = Signal(str, int, int)
    requestTofuDialog = Signal(str, str, str, object)  # host, key_type, fingerprint, callback

    def __init__(self, config: ClientConfig):
        super().__init__()
        self.config = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._submit_queue: asyncio.Queue[bytes] | None = None
        self._running = True
        self._conn: asyncssh.SSHClientConnection | None = None
        self._proc = None
        self._sftp = None
        self._remote_shared_root = config.shared_folder
        self._last_pings: dict[float, float] = {}
        self._frames_seen = 0
        self._dropped_frames = 0
        self._active_transfers: set[str] = set()
        self._cancelled_transfers: set[str] = set()

    def run(self) -> None:
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._run_with_reconnect())
        except Exception as exc:
            self.disconnected.emit(str(exc))
        finally:
            if self._loop is not None:
                self._loop.close()
                self._loop = None

    def stop(self) -> None:
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self.close()))

    def cancel_transfers(self) -> None:
        self._cancelled_transfers.update(self._active_transfers)

    def _check_cancelled(self, transfer_id: str) -> None:
        if transfer_id in self._cancelled_transfers:
            self._cancelled_transfers.discard(transfer_id)
            raise RuntimeError("transfer cancelled")

    def submit_frame(self, kind: int, message: dict[str, Any] | bytes | str) -> None:
        if self._loop is None or self._submit_queue is None or not self._running:
            return
        raw = pack_frame(kind, message)
        self._loop.call_soon_threadsafe(self._submit_queue.put_nowait, raw)

    def run_coro(self, coro):
        if self._loop is None:
            raise RuntimeError("transport not started")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def _run_with_reconnect(self) -> None:
        attempts = max(1, self.config.reconnect_attempts if self.config.reconnect_enabled else 1)
        for attempt in range(1, attempts + 1):
            if not self._running:
                return
            try:
                await self._connect_once()
            except Exception as exc:
                if not self._running:
                    return
                if attempt >= attempts:
                    raise
                self.statusChanged.emit(f"reconnecting after error: {exc}")
                await asyncio.sleep(self.config.reconnect_delay)
            else:
                return

    async def _writer_loop(self, writer) -> None:
        assert self._submit_queue is not None
        while self._running:
            raw = await self._submit_queue.get()
            writer.write(raw)
            await writer.drain()

    async def _reader_loop(self, reader) -> None:
        while self._running:
            frame = await read_frame(reader)
            if frame.kind == FRAME_VIDEO:
                self._frames_seen += 1
                self.videoFrame.emit(frame.payload)
            elif frame.kind == FRAME_CONTROL:
                message = decode_message(frame.payload) if frame.payload else {}
                t = message.get("t")
                if t == "session":
                    root = message.get("shared_folder")
                    if root:
                        self._remote_shared_root = str(root)
                    self.sessionInfo.emit(message)
                elif t == "pong":
                    await self._handle_pong(message)
                elif t == "error":
                    self.statusChanged.emit(f"server error: {message.get('message', message)}")
            elif frame.kind == FRAME_CLIPBOARD:
                message = decode_message(frame.payload) if frame.payload else {}
                if message.get("format") == "text":
                    self.clipboardReceived.emit(str(message.get("data", "")))

    async def _ping_loop(self) -> None:
        while self._running:
            ts = time.time()
            self._last_pings[ts] = time.monotonic()
            self.submit_frame(FRAME_CONTROL, {"t": "ping", "ts": ts})
            await asyncio.sleep(2.0)

    async def _handle_pong(self, message: dict[str, Any]) -> None:
        ts = float(message.get("ts", 0.0) or 0.0)
        sent_at = self._last_pings.pop(ts, None)
        if sent_at is None:
            return
        latency_ms = int((time.monotonic() - sent_at) * 1000)
        self.submit_frame(FRAME_STATS, {"t": "stats", "latency_ms": latency_ms, "dropped": self._dropped_frames})
        self.statusChanged.emit(f"connected — {latency_ms} ms")

    def update_quality(self, fps: int, quality: int) -> None:
        self.config.fps = max(1, min(60, int(fps)))
        self.config.quality = max(20, min(95, int(quality)))
        self.submit_frame(FRAME_CONTROL, {"t": "set_quality", "fps": self.config.fps, "quality": self.config.quality})

    async def _ask_tofu(self, host: str, key_type: str, fingerprint: str) -> bool:
        """Emit requestTofuDialog on the Qt main thread and await the user's decision."""
        import asyncio
        loop = asyncio.get_event_loop()
        future: asyncio.Future[bool] = loop.create_future()

        def _callback(accepted: bool) -> None:
            loop.call_soon_threadsafe(future.set_result, accepted)

        self.requestTofuDialog.emit(host, key_type, fingerprint, _callback)
        return await future

    async def _connect_once(self) -> None:
        self._submit_queue = asyncio.Queue(maxsize=128)
        kwargs: dict[str, Any] = {
            "host": self.config.host,
            "port": self.config.port,
            "username": self.config.username or None,
        }
        # ── Host-key verification (TOFU) ──────────────────────────────────
        if not self.config.verify_host_key:
            kwargs["known_hosts"] = None  # user explicitly disabled — insecure
        else:
            _kh = self.config.known_hosts.strip() if self.config.known_hosts else ""
            kh_path = Path(_kh).expanduser() if _kh else Path.home() / ".ssh" / "known_hosts"
            kh_path.parent.mkdir(parents=True, exist_ok=True)
            if not kh_path.exists():
                kh_path.touch(mode=0o600)
            kwargs["known_hosts"] = str(kh_path)
        if self.config.password:
            kwargs["password"] = self.config.password
        if self.config.key_file:
            kwargs["client_keys"] = [self.config.key_file]
            if self.config.key_passphrase:
                kwargs["passphrase"] = self.config.key_passphrase
        if self.config.proxy_jump:
            kwargs["tunnel"] = self.config.proxy_jump
        self.statusChanged.emit("connecting\u2026")
        try:
            self._conn = await asyncssh.connect(**kwargs)
        except asyncssh.HostKeyNotVerifiable as _exc:
            # Unknown host — TOFU: ask user before adding to known_hosts
            _srv_key = getattr(_exc, "key", None)
            _fingerprint = _srv_key.get_fingerprint() if _srv_key else "unavailable"
            _key_type = _srv_key.get_algorithm() if _srv_key else "unknown"
            _accepted = await self._ask_tofu(self.config.host, _key_type, _fingerprint)
            if not _accepted:
                raise ConnectionError(
                    f"Host key for {self.config.host!r} not accepted by user"
                ) from _exc
            if _srv_key is not None:
                _kh_path = Path(str(kwargs.get("known_hosts") or Path.home() / ".ssh" / "known_hosts"))
                try:
                    _entry = asyncssh.export_known_hosts({self.config.host: [_srv_key]})
                    with open(_kh_path, "a", encoding="utf-8") as _fh:
                        _fh.write(_entry)
                except Exception as _we:
                    LOG.warning("Could not save host key to known_hosts: %s", _we)
            self._conn = await asyncssh.connect(**kwargs)
        except asyncssh.HostKeyMismatch:
            self.statusChanged.emit(
                f"\u26a0\ufe0f HOST KEY CHANGED for {self.config.host!r}! "
                "This may indicate a man-in-the-middle attack. "
                "If the server was rebuilt, remove the old entry from your known_hosts."
            )
            raise
        cmd = self.config.format_remote_command()
        self._proc = await self._conn.create_process(cmd, encoding=None)
        self._sftp = await self._conn.start_sftp_client()
        self.statusChanged.emit("connected")
        hello = {
            "t": "hello",
            "proto": PROTOCOL_VERSION,
            "codec": "jpeg",
            "view": list(self.config.screen),
            "user": self.config.username,
            "auth": "key" if self.config.key_file else "password",
            "new_session": not bool(self.config.session_id),
            "geometry": list(self.config.screen),
            "persistent": self.config.persistent,
            "shared_folder": self.config.shared_folder,
            "session_id": self.config.session_id,
            "clipboard_enabled": self.config.clipboard_enabled,
        }
        self.submit_frame(FRAME_CONTROL, hello)
        tasks = {
            asyncio.create_task(self._writer_loop(self._proc.stdin)),
            asyncio.create_task(self._reader_loop(self._proc.stdout)),
            asyncio.create_task(self._ping_loop()),
        }
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc:
                raise exc

    def remote_path(self, relative: str = "") -> str:
        return join_remote_jail(self._remote_shared_root, relative)

    async def listdir(self, relative: str):
        if self._sftp is None:
            raise RuntimeError("SFTP not ready")
        entries = []
        for entry in await self._sftp.listdir_attr(self.remote_path(relative)):
            name = getattr(entry, "filename", "")
            attrs = getattr(entry, "attrs", entry)
            entries.append(
                SimpleNamespace(
                    filename=name,
                    size=int(getattr(attrs, "size", getattr(attrs, "st_size", 0)) or 0),
                    permissions=int(getattr(attrs, "permissions", getattr(attrs, "st_mode", 0)) or 0),
                )
            )
        return entries

    async def mkdir(self, relative: str):
        if self._sftp is None:
            raise RuntimeError("SFTP not ready")
        with contextlib.suppress(Exception):
            await self._sftp.mkdir(self.remote_path(relative))

    async def ensure_remote_parent_dirs(self, remote_relative: str) -> None:
        if self._sftp is None:
            raise RuntimeError("SFTP not ready")
        parent = Path(normalize_remote_rel(remote_relative)).parent
        if parent.as_posix() in {"", "."}:
            return
        current = Path("")
        for part in parent.parts:
            if part in {"", "."}:
                continue
            current = current / part
            with contextlib.suppress(Exception):
                await self._sftp.mkdir(self.remote_path(current.as_posix()))

    async def put_file(self, local_path: str, remote_relative: str, transfer_id: str):
        if self._sftp is None:
            raise RuntimeError("SFTP not ready")
        self._active_transfers.add(transfer_id)
        try:
            local = Path(local_path)
            remote_relative = normalize_remote_rel(remote_relative)
            remote = self.remote_path(remote_relative)
            await self.ensure_remote_parent_dirs(remote_relative)
            size = local.stat().st_size
            sent = 0
            with contextlib.suppress(Exception):
                attrs = await self._sftp.stat(remote)
                sent = min(int(getattr(attrs, "size", getattr(attrs, "st_size", 0)) or 0), size)
            mode = "ab" if sent else "wb"
            async with self._sftp.open(remote, mode) as dst:
                with local.open("rb") as src:
                    src.seek(sent)
                    self.transferProgress.emit(transfer_id, sent, size)
                    while True:
                        self._check_cancelled(transfer_id)
                        chunk = src.read(1024 * 256)
                        if not chunk:
                            break
                        await dst.write(chunk)
                        sent += len(chunk)
                        self.transferProgress.emit(transfer_id, sent, size)
            self.submit_frame(FRAME_CONTROL, {"t": "file_put_done", "path": remote_relative, "size": size})
        finally:
            self._active_transfers.discard(transfer_id)

    async def get_file(self, remote_relative: str, local_path: str, transfer_id: str):
        if self._sftp is None:
            raise RuntimeError("SFTP not ready")
        self._active_transfers.add(transfer_id)
        try:
            remote = self.remote_path(remote_relative)
            attrs = await self._sftp.stat(remote)
            size = int(getattr(attrs, "size", getattr(attrs, "st_size", 0)) or 0)
            local = Path(local_path)
            got = local.stat().st_size if local.exists() else 0
            if got > size:
                got = 0
            mode = "ab" if got else "wb"
            async with self._sftp.open(remote, "rb") as src:
                if got:
                    src.seek(got)
                with local.open(mode) as dst:
                    self.transferProgress.emit(transfer_id, got, size)
                    while True:
                        self._check_cancelled(transfer_id)
                        chunk = await src.read(1024 * 256)
                        if not chunk:
                            break
                        dst.write(chunk)
                        got += len(chunk)
                        self.transferProgress.emit(transfer_id, got, size)
        finally:
            self._active_transfers.discard(transfer_id)

    async def close(self) -> None:
        self._running = False
        if self._proc is not None:
            with contextlib.suppress(Exception):
                self._proc.stdin.write_eof()
        if self._conn is not None:
            self._conn.close()
            with contextlib.suppress(Exception):
                await self._conn.wait_closed()


class AsyncTask(QThread):
    success = Signal(object)
    failure = Signal(str)

    def __init__(self, transport: TransportThread, coro_factory: Callable[[], Any]):
        super().__init__()
        self.transport = transport
        self.coro_factory = coro_factory

    def run(self) -> None:
        try:
            result = self.transport.run_coro(self.coro_factory()).result()
        except Exception as exc:
            self.failure.emit(str(exc))
        else:
            self.success.emit(result)


class RemoteDisplayWidget(QFrame):
    inputMessage = Signal(dict)
    localFilesDropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self._image = QImage()
        self._server_size = (1920, 1080)

    def setServerSize(self, size: tuple[int, int]) -> None:
        self._server_size = size
        self.update()

    def setFrame(self, jpeg_bytes: bytes) -> None:
        image = QImage.fromData(jpeg_bytes, "JPEG")
        if not image.isNull():
            self._image = image
            self.update()

    def _image_rect(self):
        if self._image.isNull():
            return None
        from PySide6.QtCore import QRect
        scaled = self._image.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return QRect((self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled.width(), scaled.height())

    def _map_point(self, pos: QPointF):
        rect = self._image_rect()
        if rect is None or not rect.contains(pos.toPoint()):
            return None
        sx = (pos.x() - rect.x()) / max(rect.width(), 1)
        sy = (pos.y() - rect.y()) / max(rect.height(), 1)
        return int(sx * self._server_size[0]), int(sy * self._server_size[1])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(15, 15, 18))
        if not self._image.isNull():
            rect = self._image_rect()
            if rect is not None:
                painter.drawImage(rect, self._image)

    def mousePressEvent(self, event):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        mapped = self._map_point(event.position())
        if mapped:
            self.inputMessage.emit({"t": "mouse_move", "x": mapped[0], "y": mapped[1]})
            self.inputMessage.emit({"t": "mouse_btn", "button": qt_button(event.button()), "down": True})

    def mouseReleaseEvent(self, event):
        self.inputMessage.emit({"t": "mouse_btn", "button": qt_button(event.button()), "down": False})

    def mouseMoveEvent(self, event):
        mapped = self._map_point(event.position())
        if mapped:
            self.inputMessage.emit({"t": "mouse_move", "x": mapped[0], "y": mapped[1]})

    def wheelEvent(self, event):
        delta = event.angleDelta()
        self.inputMessage.emit({"t": "scroll", "dx": int(delta.x() / 120), "dy": int(delta.y() / 120)})

    def keyPressEvent(self, event: QKeyEvent):
        if not event.isAutoRepeat():
            self.inputMessage.emit({"t": "key", "keysym": qt_key_to_keysym(event), "down": True, "mods": qt_modifiers(event)})

    def keyReleaseEvent(self, event: QKeyEvent):
        if not event.isAutoRepeat():
            self.inputMessage.emit({"t": "key", "keysym": qt_key_to_keysym(event), "down": False, "mods": qt_modifiers(event)})

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.localFilesDropped.emit(paths)


def qt_modifiers(event: QKeyEvent) -> list[str]:
    mods: list[str] = []
    state = event.modifiers()
    km = getattr(Qt, "KeyboardModifier", Qt)
    if state & km.ControlModifier:
        mods.append("ctrl")
    if state & km.AltModifier:
        mods.append("alt")
    if state & km.ShiftModifier:
        mods.append("shift")
    if state & km.MetaModifier:
        mods.append("super")
    return mods


def qt_key_to_keysym(event: QKeyEvent) -> str:
    key = event.key()
    text = event.text()
    if text and len(text) == 1 and not event.modifiers() & getattr(Qt, "KeyboardModifier", Qt).ControlModifier:
        return text
    k = getattr(Qt, "Key", Qt)
    mapping = {
        k.Key_Return: "Return",
        k.Key_Enter: "Return",
        k.Key_Escape: "Escape",
        k.Key_Backspace: "BackSpace",
        k.Key_Tab: "Tab",
        k.Key_Delete: "Delete",
        k.Key_Home: "Home",
        k.Key_End: "End",
        k.Key_PageUp: "Page_Up",
        k.Key_PageDown: "Page_Down",
        k.Key_Left: "Left",
        k.Key_Right: "Right",
        k.Key_Up: "Up",
        k.Key_Down: "Down",
        k.Key_Space: "space",
        k.Key_Super_L: "Super_L",
        k.Key_Super_R: "Super_R",
        k.Key_Control: "Control_L",
        k.Key_Alt: "Alt_L",
        k.Key_Shift: "Shift_L",
    }
    return mapping.get(key, QKeySequence(key).toString() or text or "")


class KeyGenDialog(QWidget):
    generated = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Generate SSH key pair")
        layout = QFormLayout(self)
        self.kind = QLineEdit("ed25519")
        self.out_dir = QLineEdit(str(Path.home() / ".ssh"))
        self.name = QLineEdit("id_remote_ssh_desktop")
        self.passphrase = QLineEdit("")
        self.passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.bits = QSpinBox()
        self.bits.setRange(2048, 8192)
        self.bits.setValue(3072)
        self.status = QLabel("")
        self.helper = QLineEdit("")
        self.helper.setReadOnly(True)
        btn = QPushButton("Generate")
        btn.clicked.connect(self.generate)
        layout.addRow("Kind (ed25519/rsa)", self.kind)
        layout.addRow("Output dir", self.out_dir)
        layout.addRow("Name", self.name)
        layout.addRow("Passphrase", self.passphrase)
        layout.addRow("RSA bits", self.bits)
        layout.addRow(btn)
        layout.addRow("authorized_keys", self.helper)
        layout.addRow(self.status)

    def generate(self):
        try:
            private_path, public_path = save_keypair(
                Path(self.out_dir.text()).expanduser(),
                self.name.text().strip() or "id_remote_ssh_desktop",
                self.kind.text().strip().lower(),
                passphrase=self.passphrase.text() or None,
                bits=self.bits.value(),
            )
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.helper.setText(authorized_keys_line(public_path))
        self.status.setText(f"Saved {private_path} and {public_path}")
        self.generated.emit(str(private_path), str(public_path))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Remote SSH Desktop {__version__}")
        self.transport: TransportThread | None = None
        self._tasks: list[QThread] = []
        self._profiles: dict[str, dict[str, Any]] = {}
        self._history: list[dict[str, Any]] = []
        self._pending_history_profile: dict[str, Any] | None = None
        self._pending_history_name = ""
        self._clipboard_from_remote = False
        self._last_remote_clipboard = ""
        self._remote_rel = ""
        self._remote_root = "~/RemoteShared"
        self._frames_rendered = 0
        self._last_frame_sample = time.monotonic()
        self._last_frame_count = 0
        self._connection_started_at = 0.0
        self._connection_label = "—"
        self._child_windows: list[MainWindow] = []
        self._build_ui()
        self._load_defaults()
        self._load_profiles()
        self._load_history()
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self.update_stats_label)
        self._stats_timer.start(1000)

    def _secondary(self, button: QPushButton) -> QPushButton:
        button.setProperty("secondary", "true")
        return button

    def _set_status(self, text: str, busy: bool = False) -> None:
        self.status.setText(("⏳ " if busy else "● ") + text)

    def _build_ui(self):
        toolbar = QToolBar("Remote controls")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for text, handler in [
            ("Connect", self.connect_session),
            ("Quick Connect", self.quick_connect),
            ("New Window", self.open_new_window),
            ("Disconnect", self.disconnect_session),
            ("Fullscreen", self.toggle_fullscreen),
            ("Generate key", self.open_keygen),
            ("Self-test", self.run_self_test),
            ("Ctrl+Alt+Del", lambda: self.send_combo(["ctrl", "alt"], "Delete")),
            ("Super", lambda: self.send_key("Super_L")),
            ("Esc", lambda: self.send_key("Escape")),
        ]:
            action = QAction(text, self)
            action.triggered.connect(handler)
            toolbar.addAction(action)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        self.theme_combo.currentTextChanged.connect(lambda value: apply_theme(QApplication.instance(), value.lower()))
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Theme"))
        toolbar.addWidget(self.theme_combo)

        self.tabs = QTabWidget()
        self.session_tab = QWidget()
        self.files_tab = QWidget()
        self.diagnostics_tab = QWidget()
        self.tabs.addTab(self.session_tab, "Desktop")
        self.tabs.addTab(self.files_tab, "Files")
        self.tabs.addTab(self.diagnostics_tab, "Diagnostics")
        self.setCentralWidget(self.tabs)

        session_layout = QVBoxLayout(self.session_tab)
        session_layout.setContentsMargins(14, 14, 14, 14)
        session_layout.setSpacing(12)
        hero = QLabel("SSH-only isolated X11 desktop — no VNC/RDP, encrypted transport, SFTP shared folder.")
        hero.setProperty("muted", "true")
        session_layout.addWidget(hero)
        box = QGroupBox("Connection")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.host_edit = QLineEdit()
        self.port_edit = QSpinBox(); self.port_edit.setRange(1, 65535); self.port_edit.setValue(22)
        self.user_edit = QLineEdit()
        self.password_edit = QLineEdit(); self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit = QLineEdit()
        self.key_pass_edit = QLineEdit(); self.key_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.remote_command_edit = QLineEdit(DEFAULT_REMOTE_COMMAND)
        self.session_id_edit = QLineEdit(uuid.uuid4().hex[:12])
        self.screen_edit = QLineEdit("1920x1080")
        self.shared_folder_edit = QLineEdit("~/RemoteShared")
        self.known_hosts_edit = QLineEdit("")
        self.verify_host_key_check = QCheckBox("Don't verify host key (insecure — disables MITM protection)")
        self.proxy_jump_edit = QLineEdit("")
        self.proxy_jump_edit.setPlaceholderText("Optional: bastion host alias or user@host")
        self.proxy_jump_edit.setObjectName("proxyJumpEdit")
        self.quality_preset_combo = QComboBox()
        self.quality_preset_combo.addItems([*QUALITY_PRESETS.keys(), "Custom"])
        self.quality_preset_combo.setCurrentText("WAN")
        self.quality_preset_combo.currentTextChanged.connect(self.apply_quality_preset)
        self.quality_preset_combo.setObjectName("qualityPresetCombo")
        self.fps_edit = QSpinBox(); self.fps_edit.setRange(1, 60); self.fps_edit.setValue(QUALITY_PRESETS["WAN"]["fps"])
        self.quality_edit = QSpinBox(); self.quality_edit.setRange(20, 95); self.quality_edit.setValue(QUALITY_PRESETS["WAN"]["quality"])
        self.fps_edit.valueChanged.connect(lambda _=None: self.mark_quality_custom())
        self.quality_edit.valueChanged.connect(lambda _=None: self.mark_quality_custom())
        self.idle_timeout_edit = QSpinBox(); self.idle_timeout_edit.setRange(5, 86400); self.idle_timeout_edit.setValue(300)
        self.clipboard_max_edit = QSpinBox(); self.clipboard_max_edit.setRange(1024, 100_000_000); self.clipboard_max_edit.setValue(1_000_000)
        self.persistent_check = QCheckBox("Persistent session")
        self.clipboard_check = QCheckBox("Sync clipboard")
        self.clipboard_check.setChecked(True)
        self.reconnect_check = QCheckBox("Auto reconnect")
        self.reconnect_check.setChecked(True)
        self.profile_combo = QComboBox()
        self.profile_combo.setObjectName("profileCombo")
        self.profile_combo.setEditable(False)
        self.profile_combo.currentTextChanged.connect(self.load_selected_profile)
        self.profile_search_edit = QLineEdit()
        self.profile_search_edit.setPlaceholderText("Search profiles")
        self.profile_search_edit.textChanged.connect(self.refresh_profile_combo)
        profile_row = QHBoxLayout()
        self.save_profile_button = self._secondary(QPushButton("Save profile"))
        self.save_profile_button.clicked.connect(self.save_current_profile)
        self.delete_profile_button = self._secondary(QPushButton("Delete"))
        self.delete_profile_button.clicked.connect(self.delete_current_profile)
        self.import_profile_button = self._secondary(QPushButton("Import JSON"))
        self.import_profile_button.clicked.connect(self.import_profiles_dialog)
        self.export_profile_button = self._secondary(QPushButton("Export JSON"))
        self.export_profile_button.clicked.connect(self.export_profiles_dialog)
        self.ssh_config_button = self._secondary(QPushButton("Import ~/.ssh/config"))
        self.ssh_config_button.clicked.connect(self.import_ssh_config_dialog)
        for widget in [self.profile_combo, self.profile_search_edit, self.save_profile_button, self.delete_profile_button, self.import_profile_button, self.export_profile_button, self.ssh_config_button]:
            profile_row.addWidget(widget)
        form.addRow("Profiles", profile_row)
        recent_box = QVBoxLayout()
        self.recent_list = QListWidget()
        self.recent_list.setObjectName("recentConnectionsList")
        self.recent_list.setMaximumHeight(118)
        self.recent_list.itemDoubleClicked.connect(self.connect_recent_item)
        recent_buttons = QHBoxLayout()
        self.quick_connect_button = QPushButton("Quick Connect")
        self.quick_connect_button.clicked.connect(self.quick_connect)
        self.connect_recent_button = self._secondary(QPushButton("Connect selected"))
        self.connect_recent_button.clicked.connect(self.connect_selected_recent)
        self.clear_history_button = self._secondary(QPushButton("Clear history"))
        self.clear_history_button.clicked.connect(self.clear_recent_history)
        for widget in [self.quick_connect_button, self.connect_recent_button, self.clear_history_button]:
            recent_buttons.addWidget(widget)
        recent_box.addWidget(self.recent_list)
        recent_box.addLayout(recent_buttons)
        form.addRow("Recent", recent_box)
        for label, widget in [
            ("Host", self.host_edit), ("Port", self.port_edit), ("Username", self.user_edit),
            ("Password", self.password_edit), ("Private key", self.key_edit), ("Key passphrase", self.key_pass_edit),
            ("Remote command", self.remote_command_edit), ("Session id", self.session_id_edit), ("Screen", self.screen_edit),
            ("Quality preset", self.quality_preset_combo), ("FPS", self.fps_edit), ("JPEG quality", self.quality_edit), ("Idle timeout", self.idle_timeout_edit),
            ("Shared folder", self.shared_folder_edit), ("Known hosts", self.known_hosts_edit), ("ProxyJump", self.proxy_jump_edit),
            ("Clipboard max bytes", self.clipboard_max_edit),
        ]:
            form.addRow(label, widget)
        form.addRow(self.persistent_check)
        form.addRow(self.clipboard_check)
        form.addRow(self.reconnect_check)
        form.addRow(self.verify_host_key_check)
        session_layout.addWidget(box)

        self.display = RemoteDisplayWidget()
        self.display.setObjectName("remoteDisplay")
        self.display.inputMessage.connect(self.send_input_message)
        self.display.localFilesDropped.connect(self.upload_local_files)
        session_layout.addWidget(self.display, 1)
        status_row = QHBoxLayout()
        self.status = QLabel("● Disconnected")
        self.status.setProperty("status", "true")
        self.connection_label = QLabel("Target — · uptime —")
        self.connection_label.setProperty("muted", "true")
        self.stats = QLabel("FPS 0 · ping — · quality —")
        self.stats.setProperty("muted", "true")
        status_row.addWidget(self.status, 1)
        status_row.addWidget(self.connection_label)
        status_row.addWidget(self.stats)
        session_layout.addLayout(status_row)
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.local_clipboard_changed)

        files_layout = QVBoxLayout(self.files_tab)
        files_layout.setContentsMargins(14, 14, 14, 14)
        files_layout.setSpacing(12)
        row = QHBoxLayout()
        self.remote_path_edit = QLineEdit("")
        self.remote_path_edit.setPlaceholderText("Relative path inside shared folder")
        self.refresh_button = self._secondary(QPushButton("Refresh"))
        self.refresh_button.clicked.connect(self.refresh_files)
        self.up_button = self._secondary(QPushButton("Up"))
        self.up_button.clicked.connect(self.go_up)
        self.mkdir_button = self._secondary(QPushButton("Mkdir"))
        self.mkdir_button.clicked.connect(self.mkdir_remote)
        self.upload_button = QPushButton("Upload…")
        self.upload_button.clicked.connect(self.upload_file_dialog)
        self.download_button = self._secondary(QPushButton("Download…"))
        self.download_button.clicked.connect(self.download_file_dialog)
        self.cancel_transfer_button = self._secondary(QPushButton("Cancel transfer"))
        self.cancel_transfer_button.clicked.connect(self.cancel_transfers)
        for widget in [QLabel("Shared relative path"), self.remote_path_edit, self.up_button, self.refresh_button, self.mkdir_button, self.upload_button, self.download_button, self.cancel_transfer_button]:
            row.addWidget(widget)
        files_layout.addLayout(row)
        self.file_list = QListWidget()
        self.file_list.itemDoubleClicked.connect(self.open_file_item)
        files_layout.addWidget(self.file_list, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        files_layout.addWidget(self.progress)

        diagnostics_layout = QVBoxLayout(self.diagnostics_tab)
        diagnostics_layout.setContentsMargins(14, 14, 14, 14)
        diagnostics_layout.setSpacing(12)
        diagnostics_intro = QLabel("Run a local dependency self-test before connecting or export the report for support.")
        diagnostics_intro.setProperty("muted", "true")
        diagnostics_layout.addWidget(diagnostics_intro)
        diagnostics_buttons = QHBoxLayout()
        self.self_test_button = QPushButton("Run self-test")
        self.self_test_button.clicked.connect(self.run_self_test)
        self.export_self_test_button = self._secondary(QPushButton("Export report…"))
        self.export_self_test_button.clicked.connect(self.export_self_test_report)
        self.export_self_test_button.setEnabled(False)
        diagnostics_buttons.addWidget(self.self_test_button)
        diagnostics_buttons.addWidget(self.export_self_test_button)
        diagnostics_buttons.addStretch(1)
        diagnostics_layout.addLayout(diagnostics_buttons)
        self.diagnostics_output = QTextEdit()
        self.diagnostics_output.setReadOnly(True)
        self.diagnostics_output.setPlainText("Self-test has not been run yet.")
        diagnostics_layout.addWidget(self.diagnostics_output, 1)
        self._last_diagnostic_report = None

    def run_self_test(self):
        report = run_diagnostics(role="client")
        self._last_diagnostic_report = report
        text = report_to_text(report)
        self.diagnostics_output.setPlainText(text)
        self.export_self_test_button.setEnabled(True)
        self.tabs.setCurrentWidget(self.diagnostics_tab)
        self._set_status("Self-test passed" if report.ok else "Self-test found issues")

    def export_self_test_report(self):
        report = self._last_diagnostic_report or run_diagnostics(role="client")
        path, _ = QFileDialog.getSaveFileName(self, "Export self-test report", "remote-ssh-desktop-self-test.txt", "Text files (*.txt);;JSON files (*.json);;All files (*)")
        if not path:
            return
        try:
            saved = save_report(report, path)
        except Exception as exc:
            QMessageBox.critical(self, "Self-test", str(exc))
            return
        self._set_status(f"Self-test report saved: {saved}")

    def apply_quality_preset(self, name: str) -> None:
        preset = QUALITY_PRESETS.get(name)
        if not preset:
            return
        self.fps_edit.blockSignals(True)
        self.quality_edit.blockSignals(True)
        self.fps_edit.setValue(preset["fps"])
        self.quality_edit.setValue(preset["quality"])
        self.fps_edit.blockSignals(False)
        self.quality_edit.blockSignals(False)
        self.send_quality_update()
        self._set_status(f"Quality preset: {name}")

    def mark_quality_custom(self) -> None:
        if hasattr(self, "quality_preset_combo"):
            preset = QUALITY_PRESETS.get(self.quality_preset_combo.currentText())
            if not preset or preset["fps"] != self.fps_edit.value() or preset["quality"] != self.quality_edit.value():
                self.quality_preset_combo.blockSignals(True)
                self.quality_preset_combo.setCurrentText("Custom")
                self.quality_preset_combo.blockSignals(False)
        self.send_quality_update()

    def send_quality_update(self) -> None:
        if self.transport and self.transport.isRunning():
            self.transport.update_quality(self.fps_edit.value(), self.quality_edit.value())

    def validate_config(self) -> bool:
        errors: list[str] = []
        if not self.host_edit.text().strip():
            errors.append("Host is required")
        if not self.user_edit.text().strip():
            errors.append("Username is required")
        if not self.password_edit.text() and not self.key_edit.text().strip():
            errors.append("Use a password or a private key")
        try:
            width, height = (int(part) for part in self.screen_edit.text().lower().replace(" ", "").split("x", 1))
            if width < 320 or height < 240:
                errors.append("Screen must be at least 320x240")
        except Exception:
            errors.append("Screen must look like 1920x1080")
        if self.key_edit.text().strip() and not Path(self.key_edit.text().strip()).expanduser().exists():
            errors.append("Private key file does not exist")
        if errors:
            QMessageBox.warning(self, "Connection settings", "\n".join(errors))
            self._set_status("Fix connection settings")
            return False
        return True

    def update_stats_label(self) -> None:
        now = time.monotonic()
        elapsed = max(now - self._last_frame_sample, 0.001)
        frames = self._frames_rendered - self._last_frame_count
        fps = frames / elapsed
        self._last_frame_sample = now
        self._last_frame_count = self._frames_rendered
        transport = self.transport
        quality = getattr(getattr(transport, "config", None), "quality", "—") if transport else "—"
        self.stats.setText(f"FPS {fps:.1f} · quality {quality} · session {self.session_id_edit.text().strip() or '—'}")
        if hasattr(self, "connection_label"):
            if self._connection_started_at:
                uptime = int(time.monotonic() - self._connection_started_at)
                mins, secs = divmod(uptime, 60)
                uptime_text = f"{mins}m {secs:02d}s"
            else:
                uptime_text = "—"
            self.connection_label.setText(f"Target {self._connection_label} · uptime {uptime_text}")

    def _load_defaults(self):
        from PySide6.QtCore import QSettings
        settings = QSettings("remote-ssh-desktop", "client")
        self.host_edit.setText(settings.value("host", ""))
        self.port_edit.setValue(int(settings.value("port", 22)))
        self.user_edit.setText(settings.value("username", ""))
        self.key_edit.setText(settings.value("key_file", ""))
        self.remote_command_edit.setText(settings.value("remote_command", self.remote_command_edit.text()))
        self.shared_folder_edit.setText(settings.value("shared_folder", self.shared_folder_edit.text()))
        self.session_id_edit.setText(settings.value("session_id", self.session_id_edit.text()))
        self.known_hosts_edit.setText(settings.value("known_hosts", ""))
        self.verify_host_key_check.setChecked(not settings.value("verify_host_key", True, type=bool))

    def _save_defaults(self):
        from PySide6.QtCore import QSettings
        settings = QSettings("remote-ssh-desktop", "client")
        settings.setValue("host", self.host_edit.text())
        settings.setValue("port", self.port_edit.value())
        settings.setValue("username", self.user_edit.text())
        settings.setValue("key_file", self.key_edit.text())
        settings.setValue("remote_command", self.remote_command_edit.text())
        settings.setValue("shared_folder", self.shared_folder_edit.text())
        settings.setValue("session_id", self.session_id_edit.text())
        settings.setValue("known_hosts", self.known_hosts_edit.text())
        settings.setValue("verify_host_key", not self.verify_host_key_check.isChecked())

    def _load_profiles(self):
        try:
            self._profiles = load_profiles()
        except Exception as exc:
            self._profiles = {}
            self._set_status(f"Profiles unavailable: {exc}")
        self.refresh_profile_combo()

    def _load_history(self):
        try:
            self._history = load_history()
        except Exception as exc:
            self._history = []
            self._set_status(f"History unavailable: {exc}")
        self.refresh_history_ui()

    def refresh_history_ui(self):
        if not hasattr(self, "recent_list"):
            return
        self.recent_list.clear()
        for entry in self._history:
            item = QListWidgetItem(connection_label(entry))
            item.setData(qt_user_role(), entry)
            self.recent_list.addItem(item)

    def _current_profile_name(self) -> str:
        name = self.profile_combo.currentText() if hasattr(self, "profile_combo") else ""
        return name if name in self._profiles else ""

    def _remember_successful_connection(self) -> None:
        profile = self._pending_history_profile or self.current_profile_payload()
        name = self._pending_history_name or self._current_profile_name()
        try:
            self._history = record_connection(name, profile)
        except Exception as exc:
            self._set_status(f"Connected, but history was not saved: {exc}")
            return
        self.refresh_history_ui()
        self._pending_history_profile = None
        self._pending_history_name = ""

    def apply_history_entry(self, entry: dict[str, Any]) -> None:
        profile = entry.get("profile")
        if isinstance(profile, dict):
            self.apply_profile(profile)
            name = str(entry.get("profile_name", ""))
            if name in self._profiles:
                self.profile_combo.blockSignals(True)
                self.profile_combo.setCurrentText(name)
                self.profile_combo.blockSignals(False)

    def connect_recent_item(self, item: QListWidgetItem) -> None:
        entry = item.data(qt_user_role())
        if isinstance(entry, dict):
            self.apply_history_entry(entry)
            self.connect_session()

    def connect_selected_recent(self) -> None:
        item = self.recent_list.currentItem()
        if item:
            self.connect_recent_item(item)

    def quick_connect(self) -> None:
        entry = self._history[0] if self._history else None
        if entry:
            self.apply_history_entry(entry)
            self.connect_session()
            return
        name = self._current_profile_name()
        if name:
            self.apply_profile(self._profiles[name])
            self.connect_session()
            return
        self._set_status("No recent connection or selected profile for Quick Connect")

    def clear_recent_history(self) -> None:
        clear_history()
        self._history = []
        self.refresh_history_ui()
        self._set_status("Connection history cleared")

    def refresh_profile_combo(self):
        if not hasattr(self, "profile_combo"):
            return
        current = self.profile_combo.currentText()
        query = self.profile_search_edit.text().strip().lower() if hasattr(self, "profile_search_edit") else ""
        names = [name for name in sorted(self._profiles) if not query or query in name.lower() or query in str(self._profiles[name].get("host", "")).lower()]
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem("Select profile…")
        self.profile_combo.addItems(names)
        if current in names:
            self.profile_combo.setCurrentText(current)
        self.profile_combo.blockSignals(False)

    def current_profile_payload(self) -> dict[str, Any]:
        cfg = self.config()
        return {
            "host": cfg.host,
            "port": cfg.port,
            "username": cfg.username,
            "key_file": cfg.key_file,
            "remote_command": cfg.remote_command,
            "session_id": cfg.session_id,
            "screen": list(cfg.screen),
            "fps": cfg.fps,
            "quality": cfg.quality,
            "quality_preset": cfg.quality_preset,
            "persistent": cfg.persistent,
            "idle_timeout": cfg.idle_timeout,
            "shared_folder": cfg.shared_folder,
            "known_hosts": cfg.known_hosts,
            "clipboard_enabled": cfg.clipboard_enabled,
            "clipboard_max_bytes": cfg.clipboard_max_bytes,
            "reconnect_enabled": cfg.reconnect_enabled,
            "reconnect_attempts": cfg.reconnect_attempts,
            "reconnect_delay": cfg.reconnect_delay,
            "proxy_jump": cfg.proxy_jump,
        }

    def apply_profile(self, profile: dict[str, Any]) -> None:
        self.host_edit.setText(str(profile.get("host", "")))
        self.port_edit.setValue(int(profile.get("port", 22) or 22))
        self.user_edit.setText(str(profile.get("username", "")))
        self.key_edit.setText(str(profile.get("key_file", "")))
        self.remote_command_edit.setText(str(profile.get("remote_command", DEFAULT_REMOTE_COMMAND)))
        self.session_id_edit.setText(str(profile.get("session_id", self.session_id_edit.text())))
        screen = profile.get("screen", [1920, 1080])
        if isinstance(screen, (list, tuple)) and len(screen) == 2:
            self.screen_edit.setText(f"{int(screen[0])}x{int(screen[1])}")
        elif isinstance(screen, str):
            self.screen_edit.setText(screen)
        preset = str(profile.get("quality_preset", "Custom"))
        self.quality_preset_combo.blockSignals(True)
        self.fps_edit.blockSignals(True)
        self.quality_edit.blockSignals(True)
        self.quality_preset_combo.setCurrentText(preset if preset in QUALITY_PRESETS else "Custom")
        self.fps_edit.setValue(int(profile.get("fps", QUALITY_PRESETS["WAN"]["fps"]) or QUALITY_PRESETS["WAN"]["fps"]))
        self.quality_edit.setValue(int(profile.get("quality", QUALITY_PRESETS["WAN"]["quality"]) or QUALITY_PRESETS["WAN"]["quality"]))
        self.fps_edit.blockSignals(False)
        self.quality_edit.blockSignals(False)
        self.quality_preset_combo.blockSignals(False)
        self.idle_timeout_edit.setValue(int(profile.get("idle_timeout", 300) or 300))
        self.shared_folder_edit.setText(str(profile.get("shared_folder", "~/RemoteShared")))
        self.known_hosts_edit.setText(str(profile.get("known_hosts", "")))
        self.verify_host_key_check.setChecked(not bool(profile.get("verify_host_key", True)))
        self.clipboard_max_edit.setValue(int(profile.get("clipboard_max_bytes", 1_000_000) or 1_000_000))
        self.persistent_check.setChecked(bool(profile.get("persistent", False)))
        self.clipboard_check.setChecked(bool(profile.get("clipboard_enabled", True)))
        self.reconnect_check.setChecked(bool(profile.get("reconnect_enabled", True)))
        self.proxy_jump_edit.setText(str(profile.get("proxy_jump", "")))
        self._set_status("Profile loaded")

    def load_selected_profile(self, name: str) -> None:
        if name in self._profiles:
            self.apply_profile(self._profiles[name])

    def save_current_profile(self):
        default = self.profile_combo.currentText() if self.profile_combo.currentText() in self._profiles else self.host_edit.text().strip()
        name, ok = QInputDialog.getText(self, "Save connection profile", "Profile name", text=default)
        if not ok:
            return
        try:
            clean = validate_profile_name(name)
            self._profiles[clean] = self.current_profile_payload()
            path = save_profiles(self._profiles)
        except Exception as exc:
            QMessageBox.critical(self, "Profiles", str(exc))
            return
        self.refresh_profile_combo()
        self.profile_combo.setCurrentText(clean)
        self._pending_history_name = clean
        self._set_status(f"Profile saved: {path}")

    def delete_current_profile(self):
        name = self.profile_combo.currentText()
        if name not in self._profiles:
            return
        if QMessageBox.question(self, "Delete profile", f"Delete profile '{name}'?") != QMessageBox.StandardButton.Yes:
            return
        self._profiles.pop(name, None)
        save_profiles(self._profiles)
        self.refresh_profile_combo()
        self._set_status("Profile deleted")

    def import_profiles_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import profiles JSON", "", "JSON files (*.json);;All files (*)")
        if not path:
            return
        try:
            self._profiles = import_profiles(path)
        except Exception as exc:
            QMessageBox.critical(self, "Profiles", str(exc))
            return
        self.refresh_profile_combo()
        self._set_status("Profiles imported")

    def export_profiles_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export profiles JSON", "remote-ssh-desktop-profiles.json", "JSON files (*.json);;All files (*)")
        if not path:
            return
        try:
            export_profiles(self._profiles, path)
        except Exception as exc:
            QMessageBox.critical(self, "Profiles", str(exc))
            return
        self._set_status("Profiles exported")

    def import_ssh_config_dialog(self):
        try:
            imported = import_ssh_config()
            if not imported:
                self._set_status("No importable SSH config hosts found")
                return
            self._profiles.update(imported)
            save_profiles(self._profiles)
        except Exception as exc:
            QMessageBox.critical(self, "Profiles", str(exc))
            return
        self.refresh_profile_combo()
        self._set_status(f"Imported {len(imported)} SSH config profile(s)")

    def config(self) -> ClientConfig:
        screen = tuple(int(part) for part in self.screen_edit.text().lower().replace(" ", "").split("x", 1))
        return ClientConfig(
            host=self.host_edit.text().strip(), port=self.port_edit.value(), username=self.user_edit.text().strip(),
            password=self.password_edit.text(), key_file=self.key_edit.text().strip(), key_passphrase=self.key_pass_edit.text(),
            remote_command=self.remote_command_edit.text().strip(), session_id=self.session_id_edit.text().strip() or uuid.uuid4().hex[:12],
            screen=(int(screen[0]), int(screen[1])), fps=self.fps_edit.value(), quality=self.quality_edit.value(),
            quality_preset=self.quality_preset_combo.currentText(),
            persistent=self.persistent_check.isChecked(), idle_timeout=self.idle_timeout_edit.value(),
            shared_folder=self.shared_folder_edit.text().strip(), known_hosts=self.known_hosts_edit.text().strip(),
            verify_host_key=not self.verify_host_key_check.isChecked(),
            clipboard_enabled=self.clipboard_check.isChecked(), clipboard_max_bytes=self.clipboard_max_edit.value(),
            reconnect_enabled=self.reconnect_check.isChecked(),
            proxy_jump=self.proxy_jump_edit.text().strip(),
        )

    def connect_session(self):
        if self.transport and self.transport.isRunning():
            return
        if not self.validate_config():
            return
        cfg = self.config()
        self.session_id_edit.setText(cfg.session_id)
        self._connection_started_at = 0.0
        self._connection_label = f"{cfg.username}@{cfg.host}:{cfg.port}" if cfg.username else f"{cfg.host}:{cfg.port}"
        self._pending_history_profile = self.current_profile_payload()
        self._pending_history_name = self._current_profile_name()
        self.transport = TransportThread(cfg)
        self.transport.videoFrame.connect(self.handle_video_frame)
        self.transport.sessionInfo.connect(self.handle_session_info)
        self.transport.clipboardReceived.connect(self.handle_remote_clipboard)
        self.transport.statusChanged.connect(lambda text: self._set_status(text, "connecting" in text.lower() or "reconnecting" in text.lower()))
        self.transport.disconnected.connect(self.handle_disconnect)
        self.transport.transferProgress.connect(self.handle_transfer_progress)
        self.transport.requestTofuDialog.connect(self._show_tofu_dialog)
        self.transport.start()
        self._set_status("Connecting…", busy=True)
        self._save_defaults()

    def _show_tofu_dialog(self, host: str, key_type: str, fingerprint: str, callback) -> None:
        """Show a TOFU dialog asking the user to trust an unknown host key."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Unknown Host Key")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText(
            f"The host key for <b>{host}</b> is not in your known_hosts file.\n\n"
            f"Key type: {key_type}\n"
            f"Fingerprint (SHA256):\n  {fingerprint}\n\n"
            "Do you trust this server and want to connect?"
        )
        msg.setInformativeText(
            "If you trust this server, click Trust and the key will be saved "
            "to your known_hosts for future connections without prompting."
        )
        accept_btn = msg.addButton("Trust and Connect", QMessageBox.ButtonRole.YesRole)
        msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(accept_btn)
        msg.exec()
        callback(msg.clickedButton() is accept_btn)

    def disconnect_session(self):
        if self.transport:
            self.transport.stop()
            self._set_status("Disconnecting…", busy=True)


    def open_new_window(self):
        if getattr(sys, "frozen", False):
            args = [sys.executable]
        else:
            args = [sys.executable, "-m", "remote_ssh_desktop.client.main"]
        profile = self._current_profile_name()
        if profile:
            args.extend(["--profile", profile])
        try:
            subprocess.Popen(args, close_fds=True)
        except Exception as exc:
            QMessageBox.critical(self, "New window", str(exc))
            return
        self._set_status("New client window opened" + (f" with profile: {profile}" if profile else ""))

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def handle_video_frame(self, jpeg_bytes: bytes) -> None:
        self._frames_rendered += 1
        self.display.setFrame(jpeg_bytes)

    def handle_disconnect(self, message: str):
        self._connection_started_at = 0.0
        self._set_status(message or "Disconnected")

    def handle_session_info(self, info: dict):
        screen = info.get("screen")
        if isinstance(screen, list) and len(screen) == 2:
            self.display.setServerSize((int(screen[0]), int(screen[1])))
        folder = info.get("shared_folder")
        if folder:
            self._remote_root = str(folder)
        self.refresh_files()
        self._remember_successful_connection()
        if not self._connection_started_at:
            self._connection_started_at = time.monotonic()
        target = f"{self.user_edit.text().strip()}@{self.host_edit.text().strip()}:{self.port_edit.value()}" if self.user_edit.text().strip() else f"{self.host_edit.text().strip()}:{self.port_edit.value()}"
        self._connection_label = f"{target} / {info.get('session_id', self.session_id_edit.text().strip() or '—')}"
        self.update_stats_label()
        self._set_status("Connected")

    def send_input_message(self, message: dict):
        if self.transport:
            self.transport.submit_frame(FRAME_INPUT, message)

    def send_key(self, keysym: str):
        self.send_input_message({"t": "key", "keysym": keysym, "down": True, "mods": []})
        self.send_input_message({"t": "key", "keysym": keysym, "down": False, "mods": []})

    def send_combo(self, mods: list[str], keysym: str):
        self.send_input_message({"t": "key", "keysym": keysym, "down": True, "mods": mods})
        self.send_input_message({"t": "key", "keysym": keysym, "down": False, "mods": mods})

    def local_clipboard_changed(self):
        if not self.clipboard_check.isChecked():
            return
        if self._clipboard_from_remote:
            self._clipboard_from_remote = False
            return
        text = self.clipboard.text()
        if text and text != self._last_remote_clipboard and self.transport:
            if len(text.encode("utf-8")) <= self.clipboard_max_edit.value():
                self.transport.submit_frame(FRAME_CLIPBOARD, {"t": "clipboard", "format": "text", "data": text, "origin": "client"})

    def handle_remote_clipboard(self, text: str):
        if self.clipboard_check.isChecked() and text and text != self.clipboard.text():
            self._clipboard_from_remote = True
            self._last_remote_clipboard = text
            self.clipboard.setText(text)

    def open_keygen(self):
        self.key_dialog = KeyGenDialog()
        self.key_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.key_dialog.show()

    def _run_file_task(self, coro_factory: Callable[[], Any], on_success: Callable[[Any], None] | None = None):
        if not self.transport:
            return
        task = AsyncTask(self.transport, coro_factory)
        if on_success:
            task.success.connect(on_success)
        task.failure.connect(lambda e: QMessageBox.critical(self, "File transfer", e))
        self._tasks.append(task)
        task.start()

    def current_rel(self) -> str:
        return normalize_remote_rel(self.remote_path_edit.text())

    def refresh_files(self):
        if self.transport:
            self._remote_rel = self.current_rel()
            self._run_file_task(lambda: self.transport.listdir(self._remote_rel), self._display_remote_files)

    def _display_remote_files(self, entries):
        self.file_list.clear()
        for entry in sorted(entries, key=lambda e: getattr(e, "filename", "")):
            name = getattr(entry, "filename", None) or getattr(entry, "longname", "")
            size = getattr(entry, "size", getattr(entry, "st_size", 0))
            perms = getattr(entry, "permissions", 0)
            is_dir = bool(perms & 0o040000)
            item = QListWidgetItem(f"{'📁' if is_dir else '📄'} {name}  ({size} bytes)")
            item.setData(qt_user_role(), {"name": name, "is_dir": is_dir})
            self.file_list.addItem(item)

    def open_file_item(self, item: QListWidgetItem):
        data = item.data(qt_user_role())
        if isinstance(data, dict) and data.get("is_dir"):
            self.remote_path_edit.setText(normalize_remote_rel(f"{self.current_rel()}/{data['name']}"))
            self.refresh_files()

    def go_up(self):
        rel = Path(self.current_rel()).parent.as_posix()
        self.remote_path_edit.setText("" if rel == "." else rel)
        self.refresh_files()

    def mkdir_remote(self):
        name, ok = QInputDialog.getText(self, "Create remote folder", "Folder name")
        if not ok or not name.strip():
            return
        folder = Path(name.strip()).name
        target = normalize_remote_rel(f"{self.current_rel()}/{folder}")
        self._run_file_task(lambda: self.transport.mkdir(target), lambda _: self.refresh_files())

    def cancel_transfers(self):
        if self.transport:
            self.transport.cancel_transfers()
            self._set_status("Transfer cancellation requested")

    def upload_file_dialog(self):
        local_path, _ = QFileDialog.getOpenFileName(self, "Upload file")
        if local_path:
            self.upload_local_files([local_path])

    def upload_local_files(self, paths: list[str]):
        if not self.transport:
            return
        for path in paths:
            rel = normalize_remote_rel(f"{self.current_rel()}/{Path(path).name}")
            transfer_id = uuid.uuid4().hex[:8]
            self._run_file_task(lambda p=path, r=rel, tid=transfer_id: self.transport.put_file(p, r, tid), lambda _: self.refresh_files())

    def download_file_dialog(self):
        item = self.file_list.currentItem()
        if not item or not self.transport:
            return
        data = item.data(qt_user_role())
        if not isinstance(data, dict) or data.get("is_dir"):
            return
        remote_rel = normalize_remote_rel(f"{self.current_rel()}/{data['name']}")
        local_path, _ = QFileDialog.getSaveFileName(self, "Download file", data["name"])
        if local_path:
            transfer_id = uuid.uuid4().hex[:8]
            self._run_file_task(lambda: self.transport.get_file(remote_rel, local_path, transfer_id), lambda _: None)

    def handle_transfer_progress(self, transfer_id: str, done: int, total: int):
        pct = int((done / total) * 100) if total else 0
        self.progress.setValue(max(0, min(100, pct)))
        self._set_status(f"transfer {transfer_id}: {done}/{total}", busy=done < total)


def configure_qt_platform() -> None:
    if platform.system() != "Linux" or os.environ.get("QT_QPA_PLATFORM"):
        return
    if os.environ.get("WAYLAND_DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"
    else:
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def main() -> None:
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Remote SSH Desktop client")
    parser.add_argument("--profile", default="", help="load a saved connection profile by name")
    parser.add_argument("--connect", action="store_true", help="connect immediately after loading --profile")
    parser.add_argument("--last", "--recent", action="store_true", help="load and connect to the most recent connection from history")
    parser.add_argument("--self-test", action="store_true", help="run dependency diagnostics and exit")
    parser.add_argument("--self-test-json", action="store_true", help="print dependency diagnostics as JSON and exit")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    args = parser.parse_args()
    if args.version:
        print(f"remote-ssh-desktop-client {__version__}")
        raise SystemExit(0)
    if args.self_test or args.self_test_json:
        report = run_diagnostics(role="client")
        if args.self_test_json:
            from remote_ssh_desktop.common.diagnostics import report_to_json
            print(report_to_json(report), end="")
        else:
            print(report_to_text(report), end="")
        raise SystemExit(0 if report.ok else 2)
    configure_qt_platform()
    app = QApplication(sys.argv[:1])
    apply_theme(app, "dark")
    window = MainWindow()
    if args.last:
        entry = latest_history()
        if entry:
            window.apply_history_entry(entry)
            QTimer.singleShot(0, window.connect_session)
        else:
            window._set_status("No recent connection in history")
    elif args.profile:
        if args.profile in window._profiles:
            window.profile_combo.setCurrentText(args.profile)
            window.apply_profile(window._profiles[args.profile])
            if args.connect:
                QTimer.singleShot(0, window.connect_session)
        else:
            window._set_status(f"Profile not found: {args.profile}")
    window.resize(1400, 1000)
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
