"""macOS session backend: mss screen capture + pynput input + pbcopy/pbpaste clipboard.

Requires Accessibility permission to be granted to the terminal / app:
  System Preferences → Privacy & Security → Accessibility → enable your terminal.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

from remote_ssh_desktop.server.backends.base import SessionBackend


# X11 keysym → pynput key names
_PYNPUT_MAP: dict[str, str] = {
    "Return": "enter", "Escape": "esc", "Tab": "tab",
    "BackSpace": "backspace", "Delete": "delete", "Insert": "insert",
    "Left": "left", "Right": "right", "Up": "up", "Down": "down",
    "Home": "home", "End": "end", "Page_Up": "page_up", "Page_Down": "page_down",
    "F1": "f1", "F2": "f2", "F3": "f3", "F4": "f4",
    "F5": "f5", "F6": "f6", "F7": "f7", "F8": "f8",
    "F9": "f9", "F10": "f10", "F11": "f11", "F12": "f12",
    "space": "space", "Caps_Lock": "caps_lock",
    "Control_L": "ctrl_l", "Control_R": "ctrl_r",
    "Alt_L": "alt_l",     "Alt_R": "alt_r",
    "Shift_L": "shift_l", "Shift_R": "shift_r",
    "Super_L": "cmd",     "Super_R": "cmd_r",
}

_MOD_MAP: dict[str, str] = {
    "ctrl": "Control_L", "control": "Control_L",
    "alt": "Alt_L", "shift": "Shift_L",
    "super": "Super_L", "meta": "Super_L",
}


class MacOSBackend(SessionBackend):
    """macOS session backend — captures the current desktop display."""

    platform_name = "macOS"

    def __init__(self) -> None:
        self._mouse = None
        self._keyboard = None
        self._clipboard_enabled = True
        self._clipboard_max_bytes = 1_000_000

    def check_dependencies(self) -> None:
        import platform
        if platform.system() != "Darwin":
            raise RuntimeError("MacOSBackend requires macOS")
        missing: list[str] = []
        try:
            import mss  # noqa: F401
        except ImportError:
            missing.append("mss")
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            missing.append("Pillow")
        try:
            import pynput  # noqa: F401
        except ImportError:
            missing.append("pynput")
        if missing:
            raise RuntimeError(
                f"Missing dependencies: {', '.join(missing)}.\n"
                "Install via: pip install " + " ".join(missing) + "\n\n"
                "Also grant Accessibility permission in:\n"
                "  System Preferences → Privacy & Security → Accessibility"
            )

    def startup(
        self,
        session_id: str,
        screen_size: tuple[int, int],
        desktop_command: str | None,
        clipboard_enabled: bool,
        clipboard_max_bytes: int,
    ) -> None:
        from pynput import mouse, keyboard
        self._mouse = mouse.Controller()
        self._keyboard = keyboard.Controller()
        self._clipboard_enabled = clipboard_enabled
        self._clipboard_max_bytes = clipboard_max_bytes
        if desktop_command:
            import subprocess
            subprocess.Popen(desktop_command, shell=True)

    def capture_frame(self, quality: int) -> tuple[bytes, tuple[int, int]]:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=max(20, min(95, quality)), optimize=True)
        return buf.getvalue(), (shot.width, shot.height)

    def inject_mouse_move(self, x: int, y: int) -> None:
        if self._mouse:
            self._mouse.position = (int(x), int(y))

    def inject_mouse_button(self, button: int, down: bool) -> None:
        if not self._mouse:
            return
        from pynput.mouse import Button
        btn = {1: Button.left, 2: Button.middle, 3: Button.right}.get(button, Button.left)
        if down:
            self._mouse.press(btn)
        else:
            self._mouse.release(btn)

    def inject_scroll(self, dx: int, dy: int) -> None:
        if self._mouse:
            self._mouse.scroll(int(dx), int(dy))

    def inject_key(self, keysym: str, down: bool, mods: list[str]) -> None:
        if not self._keyboard:
            return
        from pynput import keyboard as kb

        def _to_key(name: str):
            pname = _PYNPUT_MAP.get(name)
            if pname:
                return getattr(kb.Key, pname, None)
            if len(name) == 1:
                return kb.KeyCode.from_char(name)
            return None

        pressed = []
        for mod in mods:
            mkey = _to_key(_MOD_MAP.get(str(mod).lower(), str(mod)))
            if mkey:
                pressed.append(mkey)
                self._keyboard.press(mkey)

        key = _to_key(keysym)
        if key:
            if down:
                self._keyboard.press(key)
            else:
                self._keyboard.release(key)

        for mkey in reversed(pressed):
            self._keyboard.release(mkey)

    def get_clipboard(self) -> str | None:
        if not self._clipboard_enabled:
            return None
        import subprocess
        try:
            proc = subprocess.run(
                ["pbpaste"], capture_output=True, timeout=2, check=False
            )
            text = proc.stdout.decode("utf-8", errors="replace")
            if len(text.encode()) > self._clipboard_max_bytes:
                return None
            return text
        except Exception:
            return None

    def set_clipboard(self, text: str) -> None:
        if not self._clipboard_enabled:
            return
        if len(text.encode()) > self._clipboard_max_bytes:
            return
        import subprocess
        try:
            subprocess.run(
                ["pbcopy"], input=text.encode("utf-8"),
                check=False, timeout=2
            )
        except Exception:
            pass

    def shutdown(self) -> None:
        pass  # No virtual display to terminate

    @property
    def display_info(self) -> dict[str, Any]:
        return {"platform": "macos"}
