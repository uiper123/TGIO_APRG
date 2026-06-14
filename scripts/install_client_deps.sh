#!/usr/bin/env bash
# Install Qt/xcb system runtime libraries needed by remote-ssh-desktop Linux client.
# These libraries are loaded at runtime by PySide6/Qt and are NOT bundled in the binary.
# Supports Debian/Ubuntu (apt-get) and Fedora/RHEL (dnf/yum).
set -euo pipefail

echo "Installing remote-ssh-desktop-client Qt/xcb runtime dependencies..."

if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y --no-install-recommends \
        libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 \
        libxcb-render-util0 libxcb-xinerama0 libxcb-xinput0 libxcb-xkb1 \
        libxcb-shape0 libxcb-image0 libxcb-randr0 libxcb-xfixes0 \
        libegl1 libgl1 libdbus-1-3 libfontconfig1
elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y \
        libxcb xcb-util-cursor xcb-util-keysyms xcb-util-image \
        xcb-util-wm xcb-util-renderutil libxkbcommon-x11 \
        mesa-libEGL mesa-libGL dbus-libs fontconfig
elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y \
        libxcb xcb-util-cursor xcb-util-keysyms xcb-util-image \
        xcb-util-wm xcb-util-renderutil libxkbcommon-x11 \
        mesa-libEGL mesa-libGL dbus-libs fontconfig
else
    echo "ERROR: unsupported package manager — install Qt xcb libs manually." >&2
    exit 1
fi

echo "Done. Run the client binary to verify."
