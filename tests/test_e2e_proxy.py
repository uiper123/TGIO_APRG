from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

from remote_ssh_desktop.common.protocol import FRAME_CONTROL, FRAME_VIDEO, PROTOCOL_VERSION, pack_frame, read_frame


async def _close_proxy(proc: subprocess.Popen, writer) -> None:
    writer.close()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(writer.wait_closed(), timeout=2)
    with contextlib.suppress(Exception):
        proc.wait(timeout=5)
    if proc.poll() is None:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)
    if proc.poll() is None:
        proc.kill()


@pytest.mark.skipif(shutil.which("Xvfb") is None or shutil.which("xauth") is None or shutil.which("xterm") is None, reason="X11 test tools unavailable")
def test_proxy_starts_x11_session_and_streams_video():
    async def run_case():
        sid = f"pytest-e2e-{int(time.time() * 1000)}"
        env = os.environ.copy()
        env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "remote_ssh_desktop.server.main",
                "--proxy",
                "--session-id",
                sid,
                "--screen",
                "640x480",
                "--fps",
                "5",
                "--quality",
                "65",
                "--idle-timeout",
                "5",
                "--desktop-command",
                "xterm",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        assert proc.stdin is not None and proc.stdout is not None
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        loop = asyncio.get_running_loop()
        await loop.connect_read_pipe(lambda: protocol, proc.stdout)
        transport, _ = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, proc.stdin)
        writer = asyncio.StreamWriter(transport, protocol, reader, loop)
        writer.write(pack_frame(FRAME_CONTROL, {"t": "hello", "proto": PROTOCOL_VERSION, "codec": "jpeg"}))
        await writer.drain()
        seen_video = False
        try:
            for _ in range(10):
                frame = await asyncio.wait_for(read_frame(reader), timeout=8)
                if frame.kind == FRAME_VIDEO and len(frame.payload) > 100:
                    seen_video = True
                    break
        finally:
            await _close_proxy(proc, writer)
            subprocess.run([sys.executable, "-m", "remote_ssh_desktop.server.main", "--stop-session", sid], env=env, text=True, timeout=10, check=False)
        assert seen_video

    asyncio.run(run_case())


@pytest.mark.skipif(shutil.which("Xvfb") is None or shutil.which("xauth") is None or shutil.which("xterm") is None, reason="X11 test tools unavailable")
def test_persistent_session_can_list_resume_and_stop():
    async def run_case():
        sid = f"pytest-persistent-{int(time.time() * 1000)}"
        env = os.environ.copy()
        env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")

        async def open_proxy(*extra_args):
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "remote_ssh_desktop.server.main",
                    "--proxy",
                    "--session-id",
                    sid,
                    "--screen",
                    "640x480",
                    "--fps",
                    "5",
                    "--quality",
                    "65",
                    "--idle-timeout",
                    "3",
                    "--persistent",
                    "--desktop-command",
                    "xterm",
                    *extra_args,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            assert proc.stdin is not None and proc.stdout is not None
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            loop = asyncio.get_running_loop()
            await loop.connect_read_pipe(lambda: protocol, proc.stdout)
            transport, _ = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, proc.stdin)
            writer = asyncio.StreamWriter(transport, protocol, reader, loop)
            writer.write(pack_frame(FRAME_CONTROL, {"t": "hello", "proto": PROTOCOL_VERSION, "codec": "jpeg"}))
            await writer.drain()
            for _ in range(8):
                frame = await asyncio.wait_for(read_frame(reader), timeout=8)
                if frame.kind == FRAME_VIDEO:
                    break
            return proc, writer

        first_proc, first_writer = await open_proxy()
        await _close_proxy(first_proc, first_writer)
        await asyncio.sleep(0.5)

        listed = subprocess.check_output([sys.executable, "-m", "remote_ssh_desktop.server.main", "--list-sessions"], env=env, text=True, timeout=10)
        states = json.loads(listed)
        assert any(state.get("session_id") == sid and state.get("persistent") for state in states)

        second_proc, second_writer = await open_proxy("--resume")
        await _close_proxy(second_proc, second_writer)

        stop = subprocess.run([sys.executable, "-m", "remote_ssh_desktop.server.main", "--stop-session", sid], env=env, text=True, timeout=10)
        assert stop.returncode == 0
        listed_after = subprocess.check_output([sys.executable, "-m", "remote_ssh_desktop.server.main", "--list-sessions"], env=env, text=True, timeout=10)
        assert sid not in listed_after

    asyncio.run(run_case())


@pytest.mark.skipif(shutil.which("Xvfb") is None or shutil.which("xauth") is None or shutil.which("xterm") is None, reason="X11 test tools unavailable")
def test_nonpersistent_session_cleans_after_idle_timeout():
    async def run_case():
        sid = f"pytest-idle-{int(time.time() * 1000)}"
        env = os.environ.copy()
        env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "remote_ssh_desktop.server.main",
                "--proxy",
                "--session-id",
                sid,
                "--screen",
                "640x480",
                "--fps",
                "5",
                "--quality",
                "65",
                "--idle-timeout",
                "2",
                "--desktop-command",
                "xterm",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        assert proc.stdin is not None and proc.stdout is not None
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        loop = asyncio.get_running_loop()
        await loop.connect_read_pipe(lambda: protocol, proc.stdout)
        transport, _ = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, proc.stdin)
        writer = asyncio.StreamWriter(transport, protocol, reader, loop)
        writer.write(pack_frame(FRAME_CONTROL, {"t": "hello", "proto": PROTOCOL_VERSION, "codec": "jpeg"}))
        await writer.drain()
        for _ in range(8):
            frame = await asyncio.wait_for(read_frame(reader), timeout=8)
            if frame.kind == FRAME_VIDEO:
                break
        await _close_proxy(proc, writer)
        await asyncio.sleep(8)
        listed = subprocess.check_output([sys.executable, "-m", "remote_ssh_desktop.server.main", "--list-sessions"], env=env, text=True, timeout=10)
        assert sid not in listed

    asyncio.run(run_case())
