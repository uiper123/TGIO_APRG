from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from remote_ssh_desktop.version import __version__

Checker = Callable[[list[str], int], tuple[int, str, str]]


@dataclass(slots=True)
class DiagnosticCheck:
    name: str
    ok: bool
    severity: str
    message: str
    detail: str = ""


@dataclass(slots=True)
class DiagnosticReport:
    generated_at: str
    app_version: str
    platform: str
    python: str
    checks: list[DiagnosticCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok or check.severity != "error" for check in self.checks)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _run(cmd: list[str], timeout: int = 5) -> tuple[int, str, str]:
    completed = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _command_check(name: str, command: str, args: list[str] | None = None, *, severity: str = "error", checker: Checker = _run) -> DiagnosticCheck:
    path = shutil.which(command)
    if not path:
        return DiagnosticCheck(name, False, severity, f"missing command: {command}", f"Install '{command}' on the remote Linux host.")
    try:
        code, stdout, stderr = checker([path, *(args or ["--version"])], 5)
    except Exception as exc:
        return DiagnosticCheck(name, False, severity, f"{command} failed to run", str(exc))
    output = stdout or stderr
    if code not in {0, 1} and not output:
        return DiagnosticCheck(name, False, severity, f"{command} exited with {code}", stderr)
    return DiagnosticCheck(name, True, severity, f"found {command}: {path}", output.splitlines()[0] if output else "")


def _python_module_check(module: str, *, severity: str = "error") -> DiagnosticCheck:
    if importlib.util.find_spec(module) is None:
        return DiagnosticCheck(f"Python module {module}", False, severity, f"missing Python module: {module}", f"Install project requirements so '{module}' is importable.")
    return DiagnosticCheck(f"Python module {module}", True, severity, f"Python module importable: {module}")


def run_diagnostics(checker: Checker = _run, role: str = "client") -> DiagnosticReport:
    checks: list[DiagnosticCheck] = []
    role = role.lower().strip()
    if role not in {"client", "server", "full"}:
        raise ValueError("role must be client, server, or full")
    checks.append(DiagnosticCheck("Python", sys.version_info >= (3, 11), "error", f"Python {platform.python_version()}", "Python 3.11+ is required."))
    module_sets = {
        "client": ("asyncssh", "PIL", "PySide6"),
        "server": ("PIL", "mss", "Xlib"),
        "full": ("asyncssh", "PIL", "mss", "Xlib", "msgpack", "PySide6"),
    }
    for module in module_sets[role]:
        checks.append(_python_module_check(module))
    if platform.system() == "Linux":
        checks.extend(
            [
                _command_check("Xvfb", "Xvfb", ["-help"], checker=checker),
                _command_check("xauth", "xauth", ["-V"], checker=checker),
                _command_check("xclip", "xclip", ["-version"], checker=checker),
                _command_check("xterm", "xterm", ["-version"], checker=checker),
            ]
        )
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or os.environ.get("QT_QPA_PLATFORM")):
            checks.append(DiagnosticCheck("Qt display", False, "warning", "No DISPLAY/WAYLAND_DISPLAY/QT_QPA_PLATFORM set", "GUI startup needs a desktop session, Wayland/X11, or QT_QPA_PLATFORM=offscreen for tests."))
        else:
            checks.append(DiagnosticCheck("Qt display", True, "warning", "Qt display environment is present"))
    else:
        checks.append(DiagnosticCheck("Server platform", True, "warning", "Server-side X11 self-test checks are Linux-only and were skipped on this platform."))
    return DiagnosticReport(_timestamp(), __version__, platform.platform(), platform.python_version(), checks)


def report_to_dict(report: DiagnosticReport) -> dict:
    return {
        "generated_at": report.generated_at,
        "app_version": report.app_version,
        "platform": report.platform,
        "python": report.python,
        "ok": report.ok,
        "checks": [asdict(check) for check in report.checks],
    }


def report_to_json(report: DiagnosticReport) -> str:
    return json.dumps(report_to_dict(report), ensure_ascii=False, indent=2) + "\n"


def report_to_text(report: DiagnosticReport) -> str:
    lines = [
        "Remote SSH Desktop self-test",
        f"Generated: {report.generated_at}",
        f"Version: {report.app_version}",
        f"Platform: {report.platform}",
        f"Python: {report.python}",
        f"Overall: {'PASS' if report.ok else 'FAIL'}",
        "",
    ]
    for check in report.checks:
        mark = "PASS" if check.ok else ("WARN" if check.severity == "warning" else "FAIL")
        lines.append(f"[{mark}] {check.name}: {check.message}")
        if check.detail:
            lines.append(f"      {check.detail}")
    return "\n".join(lines) + "\n"


def save_report(report: DiagnosticReport, path: str | Path) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == ".json":
        target.write_text(report_to_json(report), encoding="utf-8")
    else:
        target.write_text(report_to_text(report), encoding="utf-8")
    return target
