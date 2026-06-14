from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from remote_ssh_desktop.client.main import MainWindow, apply_theme
from remote_ssh_desktop.version import __version__


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    apply_theme(instance, "dark")
    return instance


def test_main_window_constructs_with_modern_controls(app):
    window = MainWindow()
    try:
        assert __version__ in window.windowTitle()
        assert window.tabs.count() == 2
        assert window.theme_combo.count() == 2
        assert window.status.text().startswith("●")
        assert window.display.objectName() == "remoteDisplay"
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
