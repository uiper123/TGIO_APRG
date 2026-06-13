from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from .session import SessionConfig, SessionWorker


def state_path(session_id: str) -> Path:
    return Path.home() / ".cache" / "remote-ssh-desktop" / session_id / "session.json"


def read_state(session_id: str) -> dict[str, object] | None:
    path = state_path(session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


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
    ]
    if args.persistent:
        cmd.append("--persistent")
    if args.desktop_command:
        cmd.extend(["--desktop-command", args.desktop_command])
    if args.shared_folder:
        cmd.extend(["--shared-folder", args.shared_folder])
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True, cwd=str(Path.home()))
    for _ in range(120):
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

        threads = [threading.Thread(target=stdin_to_socket, daemon=True), threading.Thread(target=socket_to_stdout, daemon=True)]
        for thread in threads:
            thread.start()
        while not stop.is_set():
            time.sleep(0.05)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Remote graphical desktop over SSH")
    parser.add_argument("--proxy", action="store_true", help="compatibility flag for the documented remote command")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--screen", default="1920x1080")
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--quality", type=int, default=80)
    parser.add_argument("--persistent", action="store_true")
    parser.add_argument("--idle-timeout", type=int, default=300)
    parser.add_argument("--desktop-command", default="")
    parser.add_argument("--shared-folder", default="")
    return parser


def parse_screen(screen: str) -> tuple[int, int]:
    width, height = screen.lower().split("x", 1)
    return int(width), int(height)


def main() -> None:
    args = build_parser().parse_args()
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
            )
        )
        asyncio.run(worker.run())
        return
    state = ensure_worker(args, session_id)
    bridge_stdio(str(state["socket_path"]))


if __name__ == "__main__":
    main()
