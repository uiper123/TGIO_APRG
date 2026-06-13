from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncssh
from PySide6.QtCore import QPointF, QThread, Qt, Signal
from PySide6.QtGui import QAction, QColor, QImage, QKeyEvent, QKeySequence, QPainter
from PySide6.QtWidgets import QApplication, QCheckBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSpinBox, QTabWidget, QToolBar, QVBoxLayout, QWidget

from ..common.protocol import FRAME_CLIPBOARD, FRAME_CONTROL, FRAME_INPUT, FRAME_STATS, FRAME_VIDEO, decode_message, pack_frame, read_frame
from ..crypto.keygen import save_keypair


@dataclass(slots=True)
class ClientConfig:
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""
    key_file: str = ""
    key_passphrase: str = ""
    remote_command: str = "python -m remote_ssh_desktop.server.main --proxy --session-id {session_id}"
    session_id: str = ""
    screen: tuple[int, int] = (1920, 1080)
    persistent: bool = True
    shared_folder: str = ""
    known_hosts: str = ""


class TransportThread(QThread):
    videoFrame = Signal(bytes)
    statusChanged = Signal(str)
    sessionInfo = Signal(dict)
    clipboardReceived = Signal(str)
    disconnected = Signal(str)

    def __init__(self, config: ClientConfig):
        super().__init__()
        self.config = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._submit_queue: asyncio.Queue[bytes] | None = None
        self._running = True
        self._conn = None
        self._proc = None
        self._sftp = None

    def run(self) -> None:
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._connect())
        except Exception as exc:
            self.disconnected.emit(str(exc))
        finally:
            if self._loop is not None:
                with contextlib.suppress(Exception):
                    self._loop.close()
                self._loop = None

    def submit_frame(self, kind: int, message: dict[str, Any] | bytes | str) -> None:
        if self._loop is None or self._submit_queue is None:
            return
        raw = pack_frame(kind, message)
        self._loop.call_soon_threadsafe(self._submit_queue.put_nowait, raw)

    def run_coro(self, coro):
        if self._loop is None:
            raise RuntimeError("transport not started")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

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
                self.videoFrame.emit(frame.payload)
            elif frame.kind == FRAME_CONTROL:
                message = decode_message(frame.payload)
                if message.get("t") == "session":
                    self.sessionInfo.emit(message)
            elif frame.kind == FRAME_CLIPBOARD:
                message = decode_message(frame.payload)
                if message.get("format") == "text":
                    self.clipboardReceived.emit(str(message.get("data", "")))

    async def _connect(self) -> None:
        self._submit_queue = asyncio.Queue()
        kwargs: dict[str, Any] = {
            "host": self.config.host,
            "port": self.config.port,
            "username": self.config.username or None,
            "known_hosts": self.config.known_hosts or None,
        }
        if self.config.password:
            kwargs["password"] = self.config.password
        if self.config.key_file:
            kwargs["client_keys"] = [self.config.key_file]
            if self.config.key_passphrase:
                kwargs["passphrase"] = self.config.key_passphrase
        self._conn = await asyncssh.connect(**kwargs)
        cmd = self.config.remote_command.format(session_id=self.config.session_id)
        self._proc = await self._conn.create_process(cmd)
        self._sftp = await self._conn.start_sftp_client()
        self.statusChanged.emit("connected")
        hello = {
            "t": "hello",
            "proto": 1,
            "codec": "jpeg",
            "view": list(self.config.screen),
            "user": self.config.username,
            "auth": "key" if self.config.key_file else "password",
            "new_session": not bool(self.config.session_id),
            "geometry": list(self.config.screen),
            "persistent": self.config.persistent,
            "shared_folder": self.config.shared_folder,
            "session_id": self.config.session_id,
        }
        self.submit_frame(FRAME_CONTROL, hello)
        writer_task = asyncio.create_task(self._writer_loop(self._proc.stdin))
        reader_task = asyncio.create_task(self._reader_loop(self._proc.stdout))
        done, pending = await asyncio.wait({writer_task, reader_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()

    async def listdir(self, path: str):
        if self._sftp is None:
            raise RuntimeError("SFTP not ready")
        return await self._sftp.listdir_attr(path)

    async def put(self, local_path: str, remote_path: str):
        if self._sftp is None:
            raise RuntimeError("SFTP not ready")
        return await self._sftp.put(local_path, remote_path)

    async def get(self, remote_path: str, local_path: str):
        if self._sftp is None:
            raise RuntimeError("SFTP not ready")
        return await self._sftp.get(remote_path, local_path)


class AsyncTask(QThread):
    success = Signal(object)
    failure = Signal(str)

    def __init__(self, transport: TransportThread, coro):
        super().__init__()
        self.transport = transport
        self.coro = coro

    def run(self) -> None:
        try:
            result = self.transport.run_coro(self.coro).result()
        except Exception as exc:
            self.failure.emit(str(exc))
        else:
            self.success.emit(result)


class RemoteDisplayWidget(QFrame):
    inputMessage = Signal(dict)
    localFilesDropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
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
        scaled = self._image.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
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
        mapped = self._map_point(event.position())
        if mapped:
            button = {Qt.LeftButton: 1, Qt.MiddleButton: 2, Qt.RightButton: 3}.get(event.button(), 1)
            self.inputMessage.emit({"t": "mouse_move", "x": mapped[0], "y": mapped[1]})
            self.inputMessage.emit({"t": "mouse_btn", "button": button, "down": True})

    def mouseReleaseEvent(self, event):
        button = {Qt.LeftButton: 1, Qt.MiddleButton: 2, Qt.RightButton: 3}.get(event.button(), 1)
        self.inputMessage.emit({"t": "mouse_btn", "button": button, "down": False})

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
    mods = []
    state = event.modifiers()
    if state & Qt.ControlModifier:
        mods.append("ctrl")
    if state & Qt.AltModifier:
        mods.append("alt")
    if state & Qt.ShiftModifier:
        mods.append("shift")
    if state & Qt.MetaModifier:
        mods.append("super")
    return mods


def qt_key_to_keysym(event: QKeyEvent) -> str:
    key = event.key()
    text = event.text()
    if text and len(text) == 1:
        return text
    mapping = {
        Qt.Key_Return: "Return",
        Qt.Key_Enter: "Return",
        Qt.Key_Escape: "Escape",
        Qt.Key_Backspace: "BackSpace",
        Qt.Key_Tab: "Tab",
        Qt.Key_Delete: "Delete",
        Qt.Key_Home: "Home",
        Qt.Key_End: "End",
        Qt.Key_PageUp: "Page_Up",
        Qt.Key_PageDown: "Page_Down",
        Qt.Key_Left: "Left",
        Qt.Key_Right: "Right",
        Qt.Key_Up: "Up",
        Qt.Key_Down: "Down",
        Qt.Key_Space: "space",
        Qt.Key_Super_L: "Super_L",
        Qt.Key_Super_R: "Super_R",
        Qt.Key_Control: "Control_L",
        Qt.Key_Alt: "Alt_L",
        Qt.Key_Shift: "Shift_L",
    }
    return mapping.get(key, QKeySequence(key).toString() or "")


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
        self.passphrase.setEchoMode(QLineEdit.Password)
        self.bits = QSpinBox()
        self.bits.setRange(1024, 8192)
        self.bits.setValue(3072)
        self.status = QLabel("")
        btn = QPushButton("Generate")
        btn.clicked.connect(self.generate)
        layout.addRow("Kind", self.kind)
        layout.addRow("Output dir", self.out_dir)
        layout.addRow("Name", self.name)
        layout.addRow("Passphrase", self.passphrase)
        layout.addRow("RSA bits", self.bits)
        layout.addRow(btn)
        layout.addRow(self.status)

    def generate(self):
        try:
            private_path, public_path = save_keypair(Path(self.out_dir.text()).expanduser(), self.name.text().strip() or "id_remote_ssh_desktop", self.kind.text().strip().lower(), passphrase=self.passphrase.text() or None, bits=self.bits.value())
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.status.setText(f"Saved {private_path} and {public_path}")
        self.generated.emit(str(private_path), str(public_path))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Remote SSH Desktop")
        self.transport: TransportThread | None = None
        self._tasks: list[QThread] = []
        self._clipboard_from_remote = False
        self._last_remote_clipboard = ""
        self._build_ui()
        self._load_defaults()

    def _build_ui(self):
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        connect_action = QAction("Connect", self)
        connect_action.triggered.connect(self.connect_session)
        toolbar.addAction(connect_action)
        disconnect_action = QAction("Disconnect", self)
        disconnect_action.triggered.connect(self.disconnect_session)
        toolbar.addAction(disconnect_action)
        key_action = QAction("Generate key", self)
        key_action.triggered.connect(self.open_keygen)
        toolbar.addAction(key_action)
        ctrl_alt_del_action = QAction("Ctrl+Alt+Del", self)
        ctrl_alt_del_action.triggered.connect(lambda: self.send_combo(["ctrl", "alt"], "Delete"))
        toolbar.addAction(ctrl_alt_del_action)
        super_action = QAction("Super", self)
        super_action.triggered.connect(lambda: self.send_key("Super_L"))
        toolbar.addAction(super_action)
        esc_action = QAction("Esc", self)
        esc_action.triggered.connect(lambda: self.send_key("Escape"))
        toolbar.addAction(esc_action)

        self.tabs = QTabWidget()
        self.session_tab = QWidget()
        self.files_tab = QWidget()
        self.tabs.addTab(self.session_tab, "Session")
        self.tabs.addTab(self.files_tab, "Files")
        self.setCentralWidget(self.tabs)

        session_layout = QVBoxLayout(self.session_tab)
        box = QGroupBox("Connection")
        form = QFormLayout(box)
        self.host_edit = QLineEdit()
        self.port_edit = QSpinBox(); self.port_edit.setRange(1, 65535); self.port_edit.setValue(22)
        self.user_edit = QLineEdit()
        self.password_edit = QLineEdit(); self.password_edit.setEchoMode(QLineEdit.Password)
        self.key_edit = QLineEdit()
        self.key_pass_edit = QLineEdit(); self.key_pass_edit.setEchoMode(QLineEdit.Password)
        self.remote_command_edit = QLineEdit("python -m remote_ssh_desktop.server.main --proxy --session-id {session_id}")
        self.session_id_edit = QLineEdit(uuid.uuid4().hex[:12])
        self.screen_edit = QLineEdit("1920x1080")
        self.shared_folder_edit = QLineEdit(str(Path.home() / "RemoteShared"))
        self.known_hosts_edit = QLineEdit("")
        self.persistent_check = QCheckBox("Persistent session")
        self.persistent_check.setChecked(True)
        for label, widget in [("Host", self.host_edit), ("Port", self.port_edit), ("Username", self.user_edit), ("Password", self.password_edit), ("Private key", self.key_edit), ("Key passphrase", self.key_pass_edit), ("Remote command", self.remote_command_edit), ("Session id", self.session_id_edit), ("Screen", self.screen_edit), ("Shared folder", self.shared_folder_edit), ("Known hosts", self.known_hosts_edit)]:
            form.addRow(label, widget)
        form.addRow(self.persistent_check)
        session_layout.addWidget(box)

        self.display = RemoteDisplayWidget()
        self.display.inputMessage.connect(self.send_input_message)
        self.display.localFilesDropped.connect(self.upload_local_files)
        session_layout.addWidget(self.display, 1)
        self.status = QLabel("Disconnected")
        session_layout.addWidget(self.status)
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.local_clipboard_changed)

        files_layout = QVBoxLayout(self.files_tab)
        row = QHBoxLayout()
        self.remote_path_edit = QLineEdit(str(Path.home() / "RemoteShared"))
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_files)
        self.upload_button = QPushButton("Upload…")
        self.upload_button.clicked.connect(self.upload_file_dialog)
        self.download_button = QPushButton("Download…")
        self.download_button.clicked.connect(self.download_file_dialog)
        for widget in [QLabel("Remote path"), self.remote_path_edit, self.refresh_button, self.upload_button, self.download_button]:
            row.addWidget(widget)
        files_layout.addLayout(row)
        self.file_list = QListWidget()
        files_layout.addWidget(self.file_list, 1)

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

    def config(self) -> ClientConfig:
        screen = tuple(int(part) for part in self.screen_edit.text().lower().split("x", 1))
        return ClientConfig(host=self.host_edit.text().strip(), port=self.port_edit.value(), username=self.user_edit.text().strip(), password=self.password_edit.text(), key_file=self.key_edit.text().strip(), key_passphrase=self.key_pass_edit.text(), remote_command=self.remote_command_edit.text().strip(), session_id=self.session_id_edit.text().strip() or uuid.uuid4().hex[:12], screen=screen, persistent=self.persistent_check.isChecked(), shared_folder=self.shared_folder_edit.text().strip(), known_hosts=self.known_hosts_edit.text().strip())

    def connect_session(self):
        if self.transport and self.transport.isRunning():
            return
        cfg = self.config()
        self.session_id_edit.setText(cfg.session_id)
        self.transport = TransportThread(cfg)
        self.transport.videoFrame.connect(self.display.setFrame)
        self.transport.sessionInfo.connect(self.handle_session_info)
        self.transport.clipboardReceived.connect(self.handle_remote_clipboard)
        self.transport.statusChanged.connect(self.status.setText)
        self.transport.disconnected.connect(self.handle_disconnect)
        self.transport.start()
        self.status.setText("Connecting…")
        self._save_defaults()

    def disconnect_session(self):
        if self.transport:
            self.transport._running = False
            self.status.setText("Disconnecting…")

    def handle_disconnect(self, message: str):
        self.status.setText(message)

    def handle_session_info(self, info: dict):
        screen = info.get("screen")
        if isinstance(screen, list) and len(screen) == 2:
            self.display.setServerSize((int(screen[0]), int(screen[1])))
        folder = info.get("shared_folder")
        if folder:
            self.remote_path_edit.setText(str(folder))
        self.refresh_files()

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
        if self._clipboard_from_remote:
            self._clipboard_from_remote = False
            return
        text = self.clipboard.text()
        if text and text != self._last_remote_clipboard and self.transport:
            self.transport.submit_frame(FRAME_CLIPBOARD, {"t": "clipboard", "format": "text", "data": text, "origin": "client"})

    def handle_remote_clipboard(self, text: str):
        if text and text != self.clipboard.text():
            self._clipboard_from_remote = True
            self._last_remote_clipboard = text
            self.clipboard.setText(text)

    def open_keygen(self):
        self.key_dialog = KeyGenDialog()
        self.key_dialog.setWindowModality(Qt.ApplicationModal)
        self.key_dialog.show()

    def _run_file_task(self, coro, on_success):
        if not self.transport:
            return
        task = AsyncTask(self.transport, coro)
        task.success.connect(on_success)
        task.failure.connect(lambda e: QMessageBox.critical(self, "File transfer", e))
        self._tasks.append(task)
        task.start()

    def refresh_files(self):
        if self.transport:
            self._run_file_task(self.transport.listdir(self.remote_path_edit.text().strip() or "."), self._display_remote_files)

    def _display_remote_files(self, entries):
        self.file_list.clear()
        for entry in entries:
            name = getattr(entry, "filename", None) or getattr(entry, "longname", "")
            size = getattr(entry, "st_size", 0)
            item = QListWidgetItem(f"{name}  ({size} bytes)")
            item.setData(Qt.UserRole, name)
            self.file_list.addItem(item)

    def upload_file_dialog(self):
        local_path, _ = QFileDialog.getOpenFileName(self, "Upload file")
        if local_path:
            self.upload_local_files([local_path])

    def upload_local_files(self, paths: list[str]):
        if not self.transport:
            return
        remote_dir = self.remote_path_edit.text().strip() or "."
        for path in paths:
            remote_path = f"{remote_dir.rstrip('/')}/{Path(path).name}"
            self._run_file_task(self.transport.put(path, remote_path), lambda _: self.refresh_files())

    def download_file_dialog(self):
        item = self.file_list.currentItem()
        if not item or not self.transport:
            return
        remote_name = item.data(Qt.UserRole)
        remote_dir = self.remote_path_edit.text().strip() or "."
        remote_path = f"{remote_dir.rstrip('/')}/{remote_name}"
        local_path, _ = QFileDialog.getSaveFileName(self, "Download file", remote_name)
        if local_path:
            self._run_file_task(self.transport.get(remote_path, local_path), lambda _: None)


def main() -> None:
    app = QApplication([])
    window = MainWindow()
    window.resize(1400, 1000)
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
