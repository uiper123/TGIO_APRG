#!/usr/bin/env bash
# Install system dependencies for remote-ssh-desktop-server on Linux.
# Supports: Debian/Ubuntu/Astra Linux, Arch Linux/Manjaro, ALT Linux,
#           Fedora/RHEL/CentOS, openSUSE.
set -euo pipefail

echo "Installing remote-ssh-desktop-server system dependencies..."

# Detect ALT Linux: apt-rpm uses apt-get but has different package names
is_alt_linux() {
    [ -f /etc/altlinux-release ] || (command -v apt-get >/dev/null 2>&1 && apt-get --version 2>/dev/null | grep -q "apt-rpm")
}

if is_alt_linux; then
    echo "  Package manager: apt-rpm (ALT Linux)"
    echo "  Note: ALT Linux uses different X11 package names than Debian"
    sudo apt-get install -y xorg-xvfb xorg-utils xclip xterm
elif command -v apt-get >/dev/null 2>&1; then
    echo "  Package manager: apt-get (Debian / Ubuntu / Astra Linux)"
    sudo apt-get update -y
    sudo apt-get install -y --no-install-recommends xvfb xauth xclip xterm
elif command -v pacman >/dev/null 2>&1; then
    echo "  Package manager: pacman (Arch Linux / Manjaro)"
    sudo pacman -S --noconfirm --needed xorg-server-xvfb xorg-xauth xclip xterm
elif command -v dnf >/dev/null 2>&1; then
    echo "  Package manager: dnf (Fedora / RHEL / CentOS Stream)"
    sudo dnf install -y xorg-x11-server-Xvfb xorg-x11-xauth xclip xterm
elif command -v yum >/dev/null 2>&1; then
    echo "  Package manager: yum (CentOS / older RHEL)"
    sudo yum install -y xorg-x11-server-Xvfb xorg-x11-xauth xclip xterm
elif command -v zypper >/dev/null 2>&1; then
    echo "  Package manager: zypper (openSUSE)"
    sudo zypper install -y xorg-x11-server xorg-x11-xauth xclip xterm
else
    echo "ERROR: unsupported package manager." >&2
    echo "Install manually: xvfb (Xvfb), xauth, xclip, xterm" >&2
    exit 1
fi

echo "Done. Verify with:"
echo "  Xvfb -help && xauth --version && xclip -version && xterm -version"
echo "  remote-ssh-desktop-server --self-test"
