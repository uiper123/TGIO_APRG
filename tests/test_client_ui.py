from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from remote_ssh_desktop.client.main import MainWindow, TransportThread, ClientConfig, apply_theme, qt_user_role
from remote_ssh_desktop.common.history import record_connection
from remote_ssh_desktop.version import __version__


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    apply_theme(instance, "dark")
    return instance


def test_main_window_constructs_with_modern_controls(app, tmp_path, monkeypatch):
    monkeypatch.setenv("REMOTE_SSH_DESKTOP_PROFILES", str(tmp_path / "profiles.json"))
    monkeypatch.setenv("REMOTE_SSH_DESKTOP_HISTORY", str(tmp_path / "history.json"))
    window = MainWindow()
    try:
        assert __version__ in window.windowTitle()
        assert window.tabs.count() == 3
        assert window.theme_combo.count() == 2
        assert window.status.text().startswith("●")
        assert window.display.objectName() == "remoteDisplay"
        assert window.profile_combo.objectName() == "profileCombo"
        assert window.proxy_jump_edit.objectName() == "proxyJumpEdit"
        assert window.recent_list.objectName() == "recentConnectionsList"
        assert window.quick_connect_button.text() == "Quick Connect"
        assert window.self_test_button.text() == "Run self-test"
        assert window.diagnostics_output.toPlainText().startswith("Self-test has not been run")
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
            "fps": 10,
            "quality": 55,
            "quality_preset": "Mobile",
            "proxy_jump": "bastion",
        })
        cfg = window.config()
        assert cfg.host == "server.example"
        assert cfg.port == 2200
        assert cfg.username == "alice"
        assert cfg.screen == (1366, 768)
        assert cfg.fps == 10
        assert cfg.quality == 55
        assert cfg.quality_preset == "Mobile"
        assert cfg.proxy_jump == "bastion"
    finally:
        window.close()


def test_recent_history_appears_and_can_be_applied(app, tmp_path, monkeypatch):
    monkeypatch.setenv("REMOTE_SSH_DESKTOP_PROFILES", str(tmp_path / "profiles.json"))
    history_path = tmp_path / "history.json"
    monkeypatch.setenv("REMOTE_SSH_DESKTOP_HISTORY", str(history_path))
    record_connection(
        "prod",
        {"host": "prod.example", "port": 2222, "username": "alice", "screen": [1280, 720], "key_file": "~/.ssh/id_rsd"},
        history_path,
    )

    window = MainWindow()
    try:
        assert window.recent_list.count() == 1
        item = window.recent_list.item(0)
        assert "prod" in item.text()
        assert "alice@prod.example:2222" in item.text()
        window.apply_history_entry(item.data(qt_user_role()))
        cfg = window.config()
        assert cfg.host == "prod.example"
        assert cfg.port == 2222
        assert cfg.username == "alice"
        assert cfg.screen == (1280, 720)
    finally:
        window.close()


def test_self_test_ui_runs_and_exports(app, tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("REMOTE_SSH_DESKTOP_PROFILES", str(tmp_path / "profiles.json"))
    monkeypatch.setenv("REMOTE_SSH_DESKTOP_HISTORY", str(tmp_path / "history.json"))
    window = MainWindow()
    try:
        window.run_self_test()
        assert "Remote SSH Desktop self-test" in window.diagnostics_output.toPlainText()
        assert window.export_self_test_button.isEnabled()
    finally:
        window.close()


def test_quality_presets_apply_and_custom_changes(app, tmp_path, monkeypatch):
    monkeypatch.setenv("REMOTE_SSH_DESKTOP_PROFILES", str(tmp_path / "profiles.json"))
    monkeypatch.setenv("REMOTE_SSH_DESKTOP_HISTORY", str(tmp_path / "history.json"))
    window = MainWindow()
    try:
        window.quality_preset_combo.setCurrentText("LAN")
        assert window.fps_edit.value() == 30
        assert window.quality_edit.value() == 90
        window.quality_edit.setValue(88)
        assert window.quality_preset_combo.currentText() == "Custom"
    finally:
        window.close()
