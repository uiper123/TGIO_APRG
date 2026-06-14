from __future__ import annotations

import sys

from remote_ssh_desktop.client.main import main as client_main
from remote_ssh_desktop.version import __version__


def main() -> None:
    if any(arg in {"-V", "--version"} for arg in sys.argv[1:]):
        print(f"remote-ssh-desktop {__version__}")
        return
    client_main()


if __name__ == "__main__":
    main()
