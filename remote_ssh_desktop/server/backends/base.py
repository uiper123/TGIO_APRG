"""Abstract base class for session backends."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SessionBackend(ABC):
    """Abstract session backend interface.

    Provides screen capture, input injection, clipboard, and lifecycle
    management for a remote desktop session.  Each concrete subclass
    implements these for a specific OS / display server.
    """

    # ── Lifecycle ────────────────────────────────────────────────────────────

    @abstractmethod
    def check_dependencies(self) -> None:
        """Verify all required system binaries / libraries are present.

        Call this before startup().  Raises RuntimeError with a clear
        message and installation command if anything is missing.
        """

    @abstractmethod
    def startup(
        self,
        session_id: str,
        screen_size: tuple[int, int],
        desktop_command: str | None,
        clipboard_enabled: bool,
        clipboard_max_bytes: int,
    ) -> None:
        """Allocate a display, start the desktop, initialise input subsystem."""

    @abstractmethod
    def shutdown(self) -> None:
        """Terminate processes and release all resources."""

    # ── Video ────────────────────────────────────────────────────────────────

    @abstractmethod
    def capture_frame(self, quality: int) -> tuple[bytes, tuple[int, int]]:
        """Capture the current display as JPEG.

        Returns:
            (jpeg_bytes, (width_px, height_px))
        """

    # ── Input ────────────────────────────────────────────────────────────────

    @abstractmethod
    def inject_mouse_move(self, x: int, y: int) -> None:
        """Move the mouse cursor to absolute position (x, y)."""

    @abstractmethod
    def inject_mouse_button(self, button: int, down: bool) -> None:
        """Press (down=True) or release (down=False) a mouse button (1/2/3)."""

    @abstractmethod
    def inject_scroll(self, dx: int, dy: int) -> None:
        """Scroll: positive dy = scroll up, negative dy = scroll down."""

    @abstractmethod
    def inject_key(self, keysym: str, down: bool, mods: list[str]) -> None:
        """Press or release a key.

        keysym follows X11 naming convention (e.g. 'Return', 'Escape',
        'ctrl', 'a', 'F1').  mods is a list of modifier names:
        'ctrl', 'alt', 'shift', 'super'.
        """

    # ── Clipboard ────────────────────────────────────────────────────────────

    @abstractmethod
    def get_clipboard(self) -> str | None:
        """Read the clipboard as UTF-8 text.  Returns None on failure."""

    @abstractmethod
    def set_clipboard(self, text: str) -> None:
        """Write text to the clipboard."""

    # ── Metadata ─────────────────────────────────────────────────────────────

    @property
    def display_info(self) -> dict[str, Any]:
        """Extra key/value pairs added to the session state file (optional)."""
        return {}

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable backend name for logging (e.g. 'Linux/X11')."""
