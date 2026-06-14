"""Platform-specific session backends for remote-ssh-desktop server.

Each backend provides screen capture, input injection, and clipboard
access for a specific OS. The correct backend is selected automatically
based on platform.system() at server startup.
"""
from remote_ssh_desktop.server.backends.base import SessionBackend
from remote_ssh_desktop.server.backends.x11 import X11Backend
from remote_ssh_desktop.server.backends.windows import WindowsBackend
from remote_ssh_desktop.server.backends.macos import MacOSBackend

__all__ = ["SessionBackend", "X11Backend", "WindowsBackend", "MacOSBackend"]


def create_backend() -> "SessionBackend":
    """Auto-detect the current platform and return the appropriate backend."""
    import platform
    system = platform.system()
    if system == "Linux":
        return X11Backend()
    if system == "Windows":
        return WindowsBackend()
    if system == "Darwin":
        return MacOSBackend()
    raise RuntimeError(
        f"Unsupported platform: {system!r}. "
        "Supported platforms: Linux (X11/Xvfb), Windows, macOS (Darwin)."
    )
