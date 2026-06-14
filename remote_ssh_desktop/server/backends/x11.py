"""Linux X11 backend using Xvfb, python-xlib, and xclip."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from remote_ssh_desktop.server.backends.base import SessionBackend
from remote_ssh_desktop.server.x11 import (
    ClipboardBridge,
    XInputController,
    available_desktop_command,
    capture_frame as x11_capture_frame,
    ensure_xauthority,
    find_free_display,
    launch_desktop,
    launch_xvfb,
    make_session_env,
    wait_for_x,
)


class X11Backend(SessionBackend):
    """Linux session backend: Xvfb virtual display + XTEST input + xclip clipboard."""

    platform_name = "Linux/X11"

    def __init__(self) -> None:
        self._display: str = ""
        self._xauthority: Path | None = None
        self._env: dict[str, str] = {}
        self._xvfb = None
        self._desktop = None
        self._xinput: XInputController | None = None
        self._clipboard: ClipboardBridge | None = None
        self._screen_size: tuple[int, int] = (1920, 1080)

    def check_dependencies(self) -> None:
        import shutil
        missing = [cmd for cmd in ("Xvfb", "xauth", "xclip", "xterm") if not shutil.which(cmd)]
        if missing:
            missing_str = " ".join(missing)
            raise RuntimeError(
                f"\nERROR: missing required server dependencies: {missing_str}\n"
                "\nInstall on Debian / Ubuntu / Astra Linux:"
                "\n  sudo apt-get install -y xvfb xauth xclip xterm"
                "\n\nInstall on Fedora / RHEL:"
                "\n  sudo dnf install -y xorg-x11-server-Xvfb xorg-x11-xauth xclip xterm"
                "\n\nInstall on Arch Linux:"
                "\n  sudo pacman -S --noconfirm xorg-server-xvfb xorg-xauth xclip xterm"
                "\n\nInstall on ALT Linux:"
                "\n  sudo apt-get install -y xorg-xvfb xorg-utils xclip xterm"
                "\n\nOr use the bundled script:"
                "\n  bash scripts/install_server_deps.sh\n"
            )

    def startup(
        self,
        session_id: str,
        screen_size: tuple[int, int],
        desktop_command: str | None,
        clipboard_enabled: bool,
        clipboard_max_bytes: int,
    ) -> None:
        self._screen_size = screen_size
        session_dir = Path.home() / ".cache" / "remote-ssh-desktop" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        display_num = find_free_display()
        self._display = f":{display_num}"
        self._xauthority = ensure_xauthority(session_dir, self._display)
        self._env = make_session_env(
            self._display, self._xauthority, Path.home(), os.environ.get("USER")
        )
        os.environ["DISPLAY"] = self._display
        os.environ["XAUTHORITY"] = str(self._xauthority)
        self._xvfb = launch_xvfb(self._display, screen_size, self._xauthority)
        wait_for_x(self._display)
        self._desktop = launch_desktop(
            self._env, available_desktop_command(desktop_command)
        )
        self._xinput = XInputController(self._display)
        if clipboard_enabled:
            self._clipboard = ClipboardBridge(self._env, max_bytes=clipboard_max_bytes)

    def capture_frame(self, quality: int) -> tuple[bytes, tuple[int, int]]:
        return x11_capture_frame(self._display, quality=quality, embed_cursor=True)

    def inject_mouse_move(self, x: int, y: int) -> None:
        if self._xinput:
            self._xinput.mouse_move(x, y)

    def inject_mouse_button(self, button: int, down: bool) -> None:
        if self._xinput:
            self._xinput.mouse_button(button, down)

    def inject_scroll(self, dx: int, dy: int) -> None:
        if self._xinput:
            self._xinput.scroll(dx, dy)

    def inject_key(self, keysym: str, down: bool, mods: list[str]) -> None:
        if self._xinput:
            self._xinput.key(keysym, down, mods)

    def get_clipboard(self) -> str | None:
        if self._clipboard:
            return self._clipboard.read_text()
        return None

    def set_clipboard(self, text: str) -> None:
        if self._clipboard:
            self._clipboard.write_text(text)

    def shutdown(self) -> None:
        import contextlib
        import subprocess
        if self._xinput:
            with contextlib.suppress(Exception):
                self._xinput.close()
        for proc in (self._desktop, self._xvfb):
            if proc and proc.poll() is None:
                with contextlib.suppress(Exception):
                    proc.terminate()
                with contextlib.suppress(Exception):
                    proc.wait(timeout=3)
                with contextlib.suppress(Exception):
                    proc.kill()

    @property
    def display_info(self) -> dict[str, Any]:
        return {
            "display": self._display,
            "xauthority": str(self._xauthority) if self._xauthority else "",
        }

    @property
    def env(self) -> dict[str, str]:
        """Session environment (DISPLAY, XAUTHORITY, etc.) for spawning processes."""
        return self._env
