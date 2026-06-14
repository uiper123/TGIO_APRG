from __future__ import annotations

import json

from remote_ssh_desktop.common.diagnostics import report_to_json, report_to_text, run_diagnostics, save_report


def ok_checker(cmd: list[str], timeout: int):
    return 0, f"{cmd[0]} 1.0", ""


def test_diagnostics_report_serializes_with_mocked_commands(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    report = run_diagnostics(checker=ok_checker)
    text = report_to_text(report)
    data = json.loads(report_to_json(report))

    assert report.ok
    assert "Remote SSH Desktop self-test" in text
    assert data["ok"] is True
    assert any(check["name"] == "Xvfb" for check in data["checks"])


def test_diagnostics_missing_command_is_failure(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda command: None if command == "Xvfb" else f"/usr/bin/{command}")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    report = run_diagnostics(checker=ok_checker)

    assert not report.ok
    assert any(check.name == "Xvfb" and not check.ok and check.severity == "error" for check in report.checks)


def test_save_report_writes_text_and_json(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    report = run_diagnostics(checker=ok_checker)

    text_path = save_report(report, tmp_path / "self-test.txt")
    json_path = save_report(report, tmp_path / "self-test.json")

    assert text_path.read_text(encoding="utf-8").startswith("Remote SSH Desktop self-test")
    assert json.loads(json_path.read_text(encoding="utf-8"))["ok"] is True
