from __future__ import annotations

import getpass
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from remote_ssh_desktop.client.main import ClientConfig, TransportThread, apply_theme
from remote_ssh_desktop.common.protocol import FRAME_CLIPBOARD

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until(predicate, timeout: float = 15.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        time.sleep(interval)
    return False


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    apply_theme(instance, "dark")
    return instance


@pytest.fixture
def local_sshd(tmp_path):
    required = ["sshd", "ssh-keygen", "Xvfb", "xauth", "xterm", "xclip"]
    missing = [name for name in required if shutil.which(name) is None]
    if missing:
        pytest.skip(f"missing tools for local SSH e2e: {', '.join(missing)}")
    sftp_server = Path("/usr/lib/openssh/sftp-server")
    if not sftp_server.exists():
        pytest.skip("OpenSSH sftp-server is unavailable")

    host_key = tmp_path / "ssh_host_ed25519_key"
    user_key = tmp_path / "id_ed25519"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(host_key)], check=True, timeout=10)
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(user_key)], check=True, timeout=10)
    authorized_keys = tmp_path / "authorized_keys"
    authorized_keys.write_text((user_key.with_suffix(".pub")).read_text(encoding="utf-8"), encoding="utf-8")
    authorized_keys.chmod(0o600)

    port = _free_port()
    config = tmp_path / "sshd_config"
    config.write_text(
        "\n".join(
            [
                f"Port {port}",
                "ListenAddress 127.0.0.1",
                f"HostKey {host_key}",
                f"PidFile {tmp_path / 'sshd.pid'}",
                f"AuthorizedKeysFile {authorized_keys}",
                "PasswordAuthentication no",
                "PubkeyAuthentication yes",
                "PermitRootLogin yes",
                "StrictModes no",
                "UsePAM no",
                "LogLevel ERROR",
                f"Subsystem sftp {sftp_server}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    Path("/run/sshd").mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["/usr/sbin/sshd", "-D", "-e", "-f", str(config)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert _wait_until(lambda: _port_open(port), timeout=10), proc.stderr.read() if proc.stderr else "sshd did not start"
        yield {"port": port, "key": user_key, "root": tmp_path}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        try:
            sock.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


@pytest.mark.skipif(sys.platform != "linux", reason="local SSH/X11 e2e is Linux-only")
def test_qt_transport_connects_over_local_ssh_and_exercises_sftp_clipboard(app, local_sshd, tmp_path):
    session_id = f"pytest-ssh-{int(time.time() * 1000)}"
    shared = tmp_path / "shared"
    project_root = Path(__file__).resolve().parents[1]
    remote_command = (
        f"PYTHONPATH={project_root} {sys.executable} -m remote_ssh_desktop.server.main --proxy "
        "--session-id {session_id} --screen {screen} --fps {fps} --quality {quality} "
        "--idle-timeout {idle_timeout} --desktop-command xterm {persistent_flag} {clipboard_flag} "
        "--clipboard-max-bytes {clipboard_max_bytes} --shared-folder {shared_folder}"
    )
    cfg = ClientConfig(
        host="127.0.0.1",
        port=local_sshd["port"],
        username=getpass.getuser(),
        key_file=str(local_sshd["key"]),
        known_hosts="",
        remote_command=remote_command,
        session_id=session_id,
        screen=(640, 480),
        fps=5,
        quality=65,
        idle_timeout=4,
        shared_folder=str(shared),
        reconnect_enabled=False,
    )
    transport = TransportThread(cfg)
    sessions: list[dict] = []
    statuses: list[str] = []
    clipboards: list[str] = []
    frames: list[bytes] = []
    transport.sessionInfo.connect(sessions.append)
    transport.statusChanged.connect(statuses.append)
    transport.clipboardReceived.connect(clipboards.append)
    transport.videoFrame.connect(lambda data: frames.append(bytes(data)))

    try:
        transport.start()
        assert _wait_until(lambda: any(item.get("session_id") == session_id for item in sessions), timeout=35), statuses
        assert _wait_until(lambda: bool(frames), timeout=20), statuses

        local_payload = tmp_path / "payload.txt"
        local_payload.write_text("hello over sftp\n", encoding="utf-8")
        upload = transport.run_coro(transport.put_file(str(local_payload), "nested/payload.txt", "upload-test"))
        upload.result(timeout=20)
        assert (shared / "nested" / "payload.txt").read_text(encoding="utf-8") == "hello over sftp\n"

        download_path = tmp_path / "downloaded.txt"
        download = transport.run_coro(transport.get_file("nested/payload.txt", str(download_path), "download-test"))
        download.result(timeout=20)
        assert download_path.read_text(encoding="utf-8") == "hello over sftp\n"

        transport.submit_frame(FRAME_CLIPBOARD, {"t": "clipboard", "format": "text", "data": "clipboard over ssh", "origin": "client"})
        state_path = Path.home() / ".cache" / "remote-ssh-desktop" / session_id / "session.json"

        def remote_clipboard_ready() -> bool:
            if not state_path.exists():
                return False
            import json

            state = json.loads(state_path.read_text(encoding="utf-8"))
            env = os.environ.copy()
            env["DISPLAY"] = str(state["display"])
            env["XAUTHORITY"] = str(state["xauthority"])
            result = subprocess.run(["xclip", "-selection", "clipboard", "-o"], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
            return result.returncode == 0 and result.stdout == "clipboard over ssh"

        assert _wait_until(remote_clipboard_ready, timeout=15), statuses
    finally:
        transport.stop()
        _wait_until(lambda: not transport.isRunning(), timeout=8)
        subprocess.run([sys.executable, "-m", "remote_ssh_desktop.server.main", "--stop-session", session_id], cwd=project_root, text=True, timeout=10, check=False)
