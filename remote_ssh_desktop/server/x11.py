from __future__ import annotations

import contextlib
import os
import secrets
import shutil
import subprocess
import time
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
    from Xlib.ext import xtest, xfixes
except Exception:
    X = None
    XK = None
    xdisplay = None
    xtest = None
    xfixes = None


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
    if shutil.which("xauth") is None:
        raise RuntimeError("xauth is required to create an isolated X11 cookie")
    session_dir.mkdir(parents=True, exist_ok=True)
    xauth_path = session_dir / "Xauthority"
    cookie = secrets.token_hex(16)
    subprocess.run(["xauth", "-f", str(xauth_path), "add", display, ".", cookie], check=True)
    os.chmod(xauth_path, 0o600)
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
    raise RuntimeError("no supported desktop/window-manager command found; install xterm, openbox, fluxbox, i3, or xfce")


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


def make_session_env(display: str, xauthority: Path, home: Path | None = None, user: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["DISPLAY"] = display
    env["XAUTHORITY"] = str(xauthority)
    if home:
        env["HOME"] = str(home)
    if user:
        env["USER"] = user
        env["LOGNAME"] = user
    return env


def wait_for_x(display: str, timeout: float = 5.0) -> None:
    if xdisplay is None:
        time.sleep(0.3)
        return
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            d = xdisplay.Display(display)
            d.close()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"X server {display} did not become ready: {last_error}")


def _overlay_cursor(img: Image.Image, display_name: str) -> None:
    if xdisplay is None or xfixes is None:
        return
    d = None
    try:
        d = xdisplay.Display(display_name)
        cursor = d.xfixes_get_cursor_image(d.screen().root)
        width = int(getattr(cursor, "width", 0) or 0)
        height = int(getattr(cursor, "height", 0) or 0)
        data = getattr(cursor, "cursor_image", None)
        if width <= 0 or height <= 0 or not data:
            return
        raw = bytearray()
        for argb in data:
            a = (int(argb) >> 24) & 0xFF
            r = (int(argb) >> 16) & 0xFF
            g = (int(argb) >> 8) & 0xFF
            b = int(argb) & 0xFF
            raw.extend((r, g, b, a))
        cursor_img = Image.frombytes("RGBA", (width, height), bytes(raw))
        x = int(getattr(cursor, "x", 0) or 0) - int(getattr(cursor, "xhot", 0) or 0)
        y = int(getattr(cursor, "y", 0) or 0) - int(getattr(cursor, "yhot", 0) or 0)
        img.paste(cursor_img, (x, y), cursor_img)
    except Exception:
        return
    finally:
        if d is not None:
            with contextlib.suppress(Exception):
                d.close()


def capture_frame(display: str, quality: int = 80, embed_cursor: bool = True) -> tuple[bytes, tuple[int, int]]:
    if mss is None:
        raise RuntimeError("mss is required for X11 screen capture")
    old_display = os.environ.get("DISPLAY")
    os.environ["DISPLAY"] = display
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            if embed_cursor:
                _overlay_cursor(img, display)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=max(20, min(95, quality)), optimize=True)
            return buf.getvalue(), (shot.width, shot.height)
    finally:
        if old_display is None:
            os.environ.pop("DISPLAY", None)
        else:
            os.environ["DISPLAY"] = old_display


class XInputController:
    def __init__(self, display_name: str):
        if xdisplay is None or xtest is None or X is None:
            raise RuntimeError("python-xlib with XTEST support is required for input emulation")
        self.display = xdisplay.Display(display_name)
        self.root = self.display.screen().root

    def _keysym(self, name: str) -> int:
        if XK is None:
            return 0
        if len(name) == 1:
            return XK.string_to_keysym(name)
        aliases = {" ": "space", "Esc": "Escape", "PgUp": "Page_Up", "PgDown": "Page_Down"}
        return XK.string_to_keysym(aliases.get(name, name))

    def _keycode(self, name: str) -> int:
        sym = self._keysym(name)
        if not sym:
            return 0
        return self.display.keysym_to_keycode(sym)

    def mouse_move(self, x: int, y: int) -> None:
        self.root.warp_pointer(max(0, int(x)), max(0, int(y)))
        self.display.sync()

    def mouse_button(self, button: int, down: bool) -> None:
        xtest.fake_input(self.display, X.ButtonPress if down else X.ButtonRelease, int(button))
        self.display.sync()

    def scroll(self, dx: int, dy: int) -> None:
        for _ in range(abs(int(dy))):
            button = 4 if dy > 0 else 5
            self.mouse_button(button, True)
            self.mouse_button(button, False)
        for _ in range(abs(int(dx))):
            button = 6 if dx > 0 else 7
            self.mouse_button(button, True)
            self.mouse_button(button, False)

    def key(self, keysym: str, down: bool, mods: Iterable[str] = ()) -> None:
        modmap = {"ctrl": "Control_L", "control": "Control_L", "alt": "Alt_L", "shift": "Shift_L", "super": "Super_L", "meta": "Super_L"}
        pressed: list[int] = []
        for mod in mods:
            code = self._keycode(modmap.get(str(mod).lower(), str(mod)))
            if code:
                pressed.append(code)
                xtest.fake_input(self.display, X.KeyPress, code)
        code = self._keycode(keysym)
        if code:
            xtest.fake_input(self.display, X.KeyPress if down else X.KeyRelease, code)
        for code in reversed(pressed):
            xtest.fake_input(self.display, X.KeyRelease, code)
        self.display.sync()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.display.close()


class ClipboardBridge:
    def __init__(self, env: dict[str, str], max_bytes: int = 1_000_000):
        self.env = env
        self.max_bytes = max_bytes
        self._owner: subprocess.Popen[str] | None = None

    def read_text(self, selection: str = "clipboard") -> str | None:
        if shutil.which("xclip") is None:
            return None
        proc = subprocess.run(
            ["xclip", "-selection", selection, "-out"],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=False,
            check=False,
            timeout=2,
        )
        if proc.returncode != 0 or len(proc.stdout) > self.max_bytes:
            return None
        return proc.stdout.decode("utf-8", errors="replace")

    def write_text(self, text: str, selection: str = "clipboard") -> None:
        if shutil.which("xclip") is None:
            return
        if len(text.encode("utf-8")) > self.max_bytes:
            return
        if self._owner and self._owner.poll() is None:
            with contextlib.suppress(Exception):
                self._owner.terminate()
        self._owner = subprocess.Popen(
            ["xclip", "-selection", selection, "-in"],
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        with contextlib.suppress(Exception):
            self._owner.communicate(text, timeout=2)
