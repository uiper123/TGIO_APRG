from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from remote_ssh_desktop.common.config import parse_screen
from remote_ssh_desktop.common.logging_setup import setup_logging
from remote_ssh_desktop.server.session import SessionConfig, SessionWorker
from remote_ssh_desktop.version import __version__

LOG = setup_logging("remote-ssh-desktop.server")


def session_root(session_id: str) -> Path:
    return Path.home() / ".cache" / "remote-ssh-desktop" / session_id


def state_path(session_id: str) -> Path:
    return session_root(session_id) / "session.json"


def read_state(session_id: str) -> dict[str, object] | None:
    path = state_path(session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_states() -> list[dict[str, object]]:
    root = Path.home() / ".cache" / "remote-ssh-desktop"
    states: list[dict[str, object]] = []
    if not root.exists():
        return states
    for path in root.glob("*/session.json"):
        with contextlib.suppress(Exception):
            states.append(json.loads(path.read_text(encoding="utf-8")))
    return states


def pid_alive(pid: object) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def active_session_count() -> int:
    return sum(1 for state in list_states() if pid_alive(state.get("pid")))


def socket_alive(path: str) -> bool:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        sock.connect(path)
        return True
    except Exception:
        return False
    finally:
        sock.close()


def spawn_worker(args: argparse.Namespace, session_id: str) -> dict[str, object]:
    if active_session_count() >= args.max_sessions:
        raise RuntimeError(f"session limit reached: {args.max_sessions}")
    cmd = [
        sys.executable,
        "-m",
        "remote_ssh_desktop.server.main",
        "--worker",
        "--session-id",
        session_id,
        "--screen",
        args.screen,
        "--fps",
        str(args.fps),
        "--quality",
        str(args.quality),
        "--idle-timeout",
        str(args.idle_timeout),
        "--clipboard-max-bytes",
        str(args.clipboard_max_bytes),
    ]
    if args.persistent:
        cmd.append("--persistent")
    if args.no_clipboard:
        cmd.append("--no-clipboard")
    if args.desktop_command:
        cmd.extend(["--desktop-command", args.desktop_command])
    if args.shared_folder:
        cmd.extend(["--shared-folder", args.shared_folder])
    LOG.info("starting session worker %s", session_id)
    env = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[2])
    existing_pythonpath = env.get("PYTHONPATH", "")
    if source_root not in existing_pythonpath.split(os.pathsep):
        env["PYTHONPATH"] = source_root if not existing_pythonpath else source_root + os.pathsep + existing_pythonpath
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
        cwd=str(Path.home()),
    )
    for _ in range(150):
        state = read_state(session_id)
        if state and state.get("socket_path") and Path(str(state["socket_path"])).exists():
            return state
        time.sleep(0.1)
    raise RuntimeError("worker did not start")


def ensure_worker(args: argparse.Namespace, session_id: str) -> dict[str, object]:
    state = read_state(session_id)
    if state and state.get("socket_path") and socket_alive(str(state["socket_path"])):
        return state
    if args.resume and not state:
        raise RuntimeError("no existing session to resume")
    return spawn_worker(args, session_id)


def bridge_stdio(socket_path: str) -> None:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(socket_path)
        stop = threading.Event()

        def stdin_to_socket() -> None:
            try:
                while not stop.is_set():
                    data = os.read(0, 65536)
                    if not data:
                        break
                    sock.sendall(data)
            except Exception:
                pass
            finally:
                with contextlib.suppress(Exception):
                    sock.shutdown(socket.SHUT_WR)
                stop.set()

        def socket_to_stdout() -> None:
            try:
                while not stop.is_set():
                    data = sock.recv(65536)
                    if not data:
                        break
                    os.write(1, data)
            except Exception:
                pass
            finally:
                stop.set()

        threads = [
            threading.Thread(target=stdin_to_socket, daemon=True),
            threading.Thread(target=socket_to_stdout, daemon=True),
        ]
        for thread in threads:
            thread.start()
        while not stop.is_set():
            time.sleep(0.05)


def stop_session(session_id: str) -> bool:
    state = read_state(session_id)
    if not state:
        return False
    pid = state.get("pid")
    if not pid_alive(pid):
        return False
    os.kill(int(pid), signal.SIGTERM)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Remote graphical desktop over SSH")
    parser.add_argument("--proxy", action="store_true", help="compatibility flag for the documented remote command")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--list-sessions", action="store_true")
    parser.add_argument("--stop-session", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--screen", default="1920x1080")
    parser.add_argument("--fps", type=int, default=18)
    parser.add_argument("--quality", type=int, default=80)
    parser.add_argument("--persistent", action="store_true")
    parser.add_argument("--idle-timeout", type=int, default=300)
    parser.add_argument("--max-sessions", type=int, default=8)
    parser.add_argument("--desktop-command", default="")
    parser.add_argument("--shared-folder", default="")
    parser.add_argument("--no-clipboard", action="store_true")
    parser.add_argument("--clipboard-max-bytes", type=int, default=1_000_000)
    parser.add_argument("--log-file", default="")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.version:
        print(f"remote-ssh-desktop-server {__version__}")
        return
    global LOG
    LOG = setup_logging("remote-ssh-desktop.server", args.log_file or None, args.verbose)
    if args.list_sessions:
        print(json.dumps(list_states(), ensure_ascii=False, indent=2))
        return
    if args.stop_session:
        raise SystemExit(0 if stop_session(args.stop_session) else 1)
    session_id = args.session_id or os.environ.get("REMOTE_SSH_DESKTOP_SESSION") or os.urandom(6).hex()
    if args.worker:
        worker = SessionWorker(
            SessionConfig(
                session_id=session_id,
                screen_size=parse_screen(args.screen),
                fps=args.fps,
                quality=args.quality,
                persistent=args.persistent,
                idle_timeout=args.idle_timeout,
                desktop_command=args.desktop_command or None,
                shared_folder=args.shared_folder or None,
                clipboard_enabled=not args.no_clipboard,
                clipboard_max_bytes=args.clipboard_max_bytes,
            )
        )
        asyncio.run(worker.run())
        return
    state = ensure_worker(args, session_id)
    bridge_stdio(str(state["socket_path"]))


if __name__ == "__main__":
    main()
