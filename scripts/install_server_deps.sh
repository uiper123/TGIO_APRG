#!/usr/bin/env bash
# Install system dependencies for remote-ssh-desktop-server on Linux.
# Supports Debian/Ubuntu (apt-get), Fedora/RHEL (dnf), and older RHEL (yum).
set -euo pipefail

echo "Installing remote-ssh-desktop-server system dependencies..."

if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y --no-install-recommends xvfb xauth xclip xterm
elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y xorg-x11-server-Xvfb xorg-x11-xauth xclip xterm
elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y xorg-x11-server-Xvfb xorg-x11-xauth xclip xterm
else
    echo "ERROR: unsupported package manager — install manually:" >&2
    echo "  xvfb (or Xvfb), xauth, xclip, xterm" >&2
    exit 1
fi

echo "Done. Verify with: Xvfb -help && xauth --version && xclip -version && xterm -version"
