from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from remote_ssh_desktop.client.main import MainWindow, TransportThread, ClientConfig, apply_theme
from remote_ssh_desktop.version import __version__


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    apply_theme(instance, "dark")
    return instance


def test_main_window_constructs_with_modern_controls(app, tmp_path, monkeypatch):
    monkeypatch.setenv("REMOTE_SSH_DESKTOP_PROFILES", str(tmp_path / "profiles.json"))
    window = MainWindow()
    try:
        assert __version__ in window.windowTitle()
        assert window.tabs.count() == 2
        assert window.theme_combo.count() == 2
        assert window.status.text().startswith("●")
        assert window.display.objectName() == "remoteDisplay"
        assert window.profile_combo.objectName() == "profileCombo"
        assert window.proxy_jump_edit.objectName() == "proxyJumpEdit"
    finally:
        window.close()


def test_connection_validation_reports_missing_required_fields(app, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    window = MainWindow()
    try:
        window.host_edit.setText("")
        window.user_edit.setText("")
        assert not window.validate_config()
        assert "Fix connection settings" in window.status.text()
    finally:
        window.close()


def test_put_file_creates_remote_parent_directories(tmp_path):
    class FakeAttrs:
        size = 0

    class FakeRemoteFile:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def write(self, chunk: bytes):
            return None

    class FakeSFTP:
        def __init__(self):
            self.mkdir_calls = []
            self.open_calls = []

        async def mkdir(self, path: str):
            self.mkdir_calls.append(path)

        async def stat(self, path: str):
            raise FileNotFoundError(path)

        def open(self, path: str, mode: str):
            self.open_calls.append((path, mode))
            return FakeRemoteFile()

    local = tmp_path / "payload.bin"
    local.write_bytes(b"abc")
    transport = TransportThread(ClientConfig(shared_folder="/srv/shared"))
    fake_sftp = FakeSFTP()
    transport._sftp = fake_sftp

    import asyncio
    asyncio.run(transport.put_file(str(local), "nested/deep/payload.bin", "t1"))

    assert fake_sftp.mkdir_calls == ["/srv/shared/nested", "/srv/shared/nested/deep"]
    assert fake_sftp.open_calls == [("/srv/shared/nested/deep/payload.bin", "wb")]


def test_apply_profile_populates_connection_fields(app, tmp_path, monkeypatch):
    monkeypatch.setenv("REMOTE_SSH_DESKTOP_PROFILES", str(tmp_path / "profiles.json"))
    window = MainWindow()
    try:
        window.apply_profile({
            "host": "server.example",
            "port": 2200,
            "username": "alice",
            "key_file": "~/.ssh/id_rsd",
            "screen": [1366, 768],
            "fps": 12,
            "quality": 70,
            "proxy_jump": "bastion",
        })
        cfg = window.config()
        assert cfg.host == "server.example"
        assert cfg.port == 2200
        assert cfg.username == "alice"
        assert cfg.screen == (1366, 768)
        assert cfg.fps == 12
        assert cfg.quality == 70
        assert cfg.proxy_jump == "bastion"
    finally:
        window.close()
