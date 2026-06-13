from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time

import pytest

from remote_ssh_desktop.common.protocol import FRAME_CONTROL, FRAME_VIDEO, PROTOCOL_VERSION, pack_frame, read_frame


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
            writer.close()
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        assert seen_video

    asyncio.run(run_case())
