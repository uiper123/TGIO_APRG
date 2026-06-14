"""Windows session backend: mss screen capture + ctypes SendInput + Win32 clipboard.

No virtual display is needed on Windows — the backend captures the current
interactive desktop session and injects input via the Win32 API.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
from io import BytesIO
from typing import Any

from remote_ssh_desktop.server.backends.base import SessionBackend


# ── Win32 constants ──────────────────────────────────────────────────────────

MOUSEEVENTF_LEFTDOWN   = 0x0002
MOUSEEVENTF_LEFTUP     = 0x0004
MOUSEEVENTF_RIGHTDOWN  = 0x0008
MOUSEEVENTF_RIGHTUP    = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP   = 0x0040
MOUSEEVENTF_WHEEL      = 0x0800
MOUSEEVENTF_HWHEEL     = 0x1000

KEYEVENTF_KEYUP        = 0x0002
WHEEL_DELTA            = 120
CF_UNICODETEXT         = 13
GMEM_MOVEABLE          = 0x0002

# X11 keysym → Windows Virtual Key code
_VK_MAP: dict[str, int] = {
    "Return": 0x0D, "Escape": 0x1B, "Tab": 0x09, "BackSpace": 0x08,
    "Delete": 0x2E, "Insert": 0x2D,
    "Left": 0x25, "Right": 0x27, "Up": 0x26, "Down": 0x28,
    "Home": 0x24, "End": 0x23, "Page_Up": 0x21, "Page_Down": 0x22,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "space": 0x20, "Print": 0x2C, "Pause": 0x13, "Caps_Lock": 0x14,
    "Num_Lock": 0x90, "Scroll_Lock": 0x91,
    "Control_L": 0x11, "Control_R": 0x11,
    "Alt_L": 0x12,    "Alt_R": 0x12,
    "Shift_L": 0x10,  "Shift_R": 0x10,
    "Super_L": 0x5B,  "Super_R": 0x5C,
}

_MOD_MAP: dict[str, str] = {
    "ctrl": "Control_L", "control": "Control_L",
    "alt": "Alt_L", "shift": "Shift_L",
    "super": "Super_L", "meta": "Super_L",
}


def _vk(keysym: str) -> int:
    vk = _VK_MAP.get(keysym, 0)
    if not vk and len(keysym) == 1:
        vk = ctypes.windll.user32.VkKeyScanW(ord(keysym)) & 0xFF
    return vk


class WindowsBackend(SessionBackend):
    """Windows session backend — captures the current interactive desktop."""

    platform_name = "Windows"

    def __init__(self) -> None:
        self._user32 = None
        self._kernel32 = None

    def check_dependencies(self) -> None:
        import platform
        if platform.system() != "Windows":
            raise RuntimeError("WindowsBackend requires Windows")
        try:
            import mss  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                f"Missing dependency: {exc}.\n"
                "Install via: pip install mss Pillow"
            ) from exc

    def startup(
        self,
        session_id: str,
        screen_size: tuple[int, int],
        desktop_command: str | None,
        clipboard_enabled: bool,
        clipboard_max_bytes: int,
    ) -> None:
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
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
        if self._user32:
            self._user32.SetCursorPos(int(x), int(y))

    def inject_mouse_button(self, button: int, down: bool) -> None:
        if not self._user32:
            return
        btn_flags = {1: (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
                     2: (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
                     3: (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)}
        if button not in btn_flags:
            return
        flag = btn_flags[button][0 if down else 1]
        self._user32.mouse_event(flag, 0, 0, 0, 0)

    def inject_scroll(self, dx: int, dy: int) -> None:
        if not self._user32:
            return
        if dy != 0:
            self._user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(dy) * WHEEL_DELTA, 0)
        if dx != 0:
            self._user32.mouse_event(MOUSEEVENTF_HWHEEL, 0, 0, int(dx) * WHEEL_DELTA, 0)

    def inject_key(self, keysym: str, down: bool, mods: list[str]) -> None:
        if not self._user32:
            return
        flags = 0 if down else KEYEVENTF_KEYUP
        pressed: list[int] = []
        for mod in mods:
            mvk = _vk(_MOD_MAP.get(str(mod).lower(), str(mod)))
            if mvk:
                pressed.append(mvk)
                self._user32.keybd_event(mvk, 0, 0, 0)
        vk = _vk(keysym)
        if vk:
            self._user32.keybd_event(vk, 0, flags, 0)
        for mvk in reversed(pressed):
            self._user32.keybd_event(mvk, 0, KEYEVENTF_KEYUP, 0)

    def get_clipboard(self) -> str | None:
        if not (self._user32 and self._kernel32):
            return None
        try:
            if not self._user32.OpenClipboard(None):
                return None
            try:
                handle = self._user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return None
                ptr = self._kernel32.GlobalLock(handle)
                if not ptr:
                    return None
                try:
                    return ctypes.wstring_at(ptr)
                finally:
                    self._kernel32.GlobalUnlock(handle)
            finally:
                self._user32.CloseClipboard()
        except Exception:
            return None

    def set_clipboard(self, text: str) -> None:
        if not (self._user32 and self._kernel32):
            return
        try:
            encoded = (text + "\0").encode("utf-16-le")
            handle = self._kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
            if not handle:
                return
            ptr = self._kernel32.GlobalLock(handle)
            if not ptr:
                self._kernel32.GlobalFree(handle)
                return
            ctypes.memmove(ptr, encoded, len(encoded))
            self._kernel32.GlobalUnlock(handle)
            if self._user32.OpenClipboard(None):
                self._user32.EmptyClipboard()
                self._user32.SetClipboardData(CF_UNICODETEXT, handle)
                self._user32.CloseClipboard()
        except Exception:
            pass

    def shutdown(self) -> None:
        pass  # No virtual display to terminate

    @property
    def display_info(self) -> dict[str, Any]:
        return {"platform": "windows"}
