from __future__ import annotations

import contextlib
import os
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable

from PIL import Image

try:
    import mss
except Exception:
    mss = None

try:
    from Xlib import X, XK, display as xdisplay
    from Xlib.ext import xtest
except Exception:
    X = None
    XK = None
    xdisplay = None
    xtest = None


@dataclass(slots=True)
class X11Resources:
    display: str
    xauthority: Path
    xvfb: subprocess.Popen[str] | None
    desktop: subprocess.Popen[str] | None


def find_free_display(start: int = 100, end: int = 220) -> int:
    for num in range(start, end):
        if not Path(f"/tmp/.X{num}-lock").exists() and not Path(f"/tmp/.X11-unix/X{num}").exists():
            return num
    raise RuntimeError("no free X11 display found")


def ensure_xauthority(session_dir: Path, display: str) -> Path:
    session_dir.mkdir(parents=True, exist_ok=True)
    xauth_path = session_dir / "Xauthority"
    cookie = secrets.token_hex(16)
    subprocess.run(["xauth", "-f", str(xauth_path), "add", display, ".", cookie], check=True)
    return xauth_path


def launch_xvfb(display: str, size: tuple[int, int], xauthority: Path) -> subprocess.Popen[str]:
    if shutil.which("Xvfb") is None:
        raise RuntimeError("Xvfb is required on the server")
    width, height = size
    return subprocess.Popen(
        ["Xvfb", display, "-screen", "0", f"{width}x{height}x24", "-auth", str(xauthority), "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )


def available_desktop_command(custom: str | None = None) -> str:
    if custom:
        return custom
    for candidate in ("startxfce4", "openbox-session", "fluxbox", "i3", "xterm"):
        if shutil.which(candidate):
            return candidate
    return "xterm"


def launch_desktop(env: dict[str, str], command: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        command,
        shell=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )


def make_session_env(display: str, xauthority: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["DISPLAY"] = display
    env["XAUTHORITY"] = str(xauthority)
    return env


def capture_frame(display: str, quality: int = 80) -> tuple[bytes, tuple[int, int]]:
    old_display = os.environ.get("DISPLAY")
    os.environ["DISPLAY"] = display
    try:
        if mss is None:
            img = Image.new("RGB", (1280, 720), color=(25, 25, 28))
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            return buf.getvalue(), img.size
        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            return buf.getvalue(), (shot.width, shot.height)
    finally:
        if old_display is None:
            os.environ.pop("DISPLAY", None)
        else:
            os.environ["DISPLAY"] = old_display


class XInputController:
    def __init__(self, display_name: str):
        self._enabled = xdisplay is not None
        self.display = xdisplay.Display(display_name) if self._enabled else None
        self.root = self.display.screen().root if self._enabled else None

    def _keysym(self, name: str) -> int:
        if not self._enabled or XK is None:
            return 0
        sym = XK.string_to_keysym(name)
        if sym == 0 and len(name) == 1:
            sym = XK.string_to_keysym(name.upper())
        return sym

    def _keycode(self, name: str) -> int:
        sym = self._keysym(name)
        if not sym or not self.display:
            return 0
        return self.display.keysym_to_keycode(sym)

    def mouse_move(self, x: int, y: int) -> None:
        if self.root is None:
            return
        self.root.warp_pointer(x, y)
        self.display.sync()

    def mouse_button(self, button: int, down: bool) -> None:
        if not self._enabled or xtest is None or X is None:
            return
        xtest.fake_input(self.display, X.ButtonPress if down else X.ButtonRelease, button)
        self.display.sync()

    def scroll(self, dx: int, dy: int) -> None:
        for _ in range(abs(dy)):
            btn = 4 if dy > 0 else 5
            self.mouse_button(btn, True)
            self.mouse_button(btn, False)
        for _ in range(abs(dx)):
            btn = 6 if dx > 0 else 7
            self.mouse_button(btn, True)
            self.mouse_button(btn, False)

    def key(self, keysym: str, down: bool, mods: Iterable[str] = ()) -> None:
        if not self._enabled or xtest is None or X is None:
            return
        modmap = {"ctrl": "Control_L", "control": "Control_L", "alt": "Alt_L", "shift": "Shift_L", "super": "Super_L", "meta": "Super_L"}
        pressed: list[int] = []
        for mod in mods:
            code = self._keycode(modmap.get(mod.lower(), mod))
            if code:
                pressed.append(code)
                xtest.fake_input(self.display, X.KeyPress, code)
        code = self._keycode(keysym)
        if code:
            xtest.fake_input(self.display, X.KeyPress if down else X.KeyRelease, code)
        for code in reversed(pressed):
            xtest.fake_input(self.display, X.KeyRelease, code)
        self.display.sync()


class ClipboardBridge:
    def __init__(self, env: dict[str, str]):
        self.env = env

    def read_text(self, selection: str = "clipboard") -> str | None:
        if shutil.which("xclip") is None:
            return None
        proc = subprocess.run(
            ["xclip", "-selection", selection, "-out"],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=2,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout

    def write_text(self, text: str, selection: str = "clipboard") -> None:
        if shutil.which("xclip") is None:
            return
        proc = subprocess.Popen(
            ["xclip", "-selection", selection],
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        with contextlib.suppress(Exception):
            proc.communicate(text, timeout=2)
