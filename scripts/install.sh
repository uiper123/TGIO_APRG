#!/usr/bin/env bash
# Universal installer for remote-ssh-desktop.
# Usage:
#   Server:  curl -fsSL https://raw.githubusercontent.com/uiper123/TGIO_APRG/main/scripts/install.sh | bash -s server
#   Client:  curl -fsSL https://raw.githubusercontent.com/uiper123/TGIO_APRG/main/scripts/install.sh | bash -s client
#   Both:    curl -fsSL https://raw.githubusercontent.com/uiper123/TGIO_APRG/main/scripts/install.sh | bash
#
# Supports: Debian/Ubuntu/Astra Linux, Arch/Manjaro, ALT Linux, Fedora/RHEL/CentOS, openSUSE.
set -euo pipefail

REPO="uiper123/TGIO_APRG"
COMPONENT="${1:-both}"   # server | client | both
INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"

# ── Detect OS ─────────────────────────────────────────────────────────────
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "${ID:-linux}"
    elif [ "$(uname -s)" = "Darwin" ]; then
        echo "macos"
    else
        echo "linux"
    fi
}

OS_ID=$(detect_os)
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)  ARCH_SUFFIX="x86_64" ;;
    aarch64|arm64) ARCH_SUFFIX="arm64" ;;
    *) echo "ERROR: unsupported architecture: $ARCH" >&2; exit 1 ;;
esac

echo "=== remote-ssh-desktop installer ==="
echo "OS: $OS_ID | Arch: $ARCH_SUFFIX | Component: $COMPONENT"
echo

# ── Get latest release tag ────────────────────────────────────────────────
LATEST=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | grep '"tag_name"' | sed 's/.*"tag_name": "\(.*\)".*/\1/')
if [ -z "$LATEST" ]; then
    echo "ERROR: could not determine latest release. Check internet connection." >&2
    exit 1
fi
echo "Latest release: $LATEST"

# ── Download helper ───────────────────────────────────────────────────────
download_artifact() {
    local name="$1"
    local dest="$2"
    local url="https://github.com/$REPO/releases/download/$LATEST/$name"
    echo "Downloading $name..."
    curl -fsSL -o "$dest" "$url"
    chmod +x "$dest"
    echo "Installed: $dest"
}

# ── Install server ────────────────────────────────────────────────────────
install_server() {
    local artifact="remote-ssh-desktop-server-linux-$ARCH_SUFFIX"
    download_artifact "$artifact" "$INSTALL_DIR/remote-ssh-desktop-server"
    echo
    echo "Installing server system dependencies..."
    install_server_deps
    echo
    echo "Server installed. Verify:"
    echo "  remote-ssh-desktop-server --version"
    echo "  remote-ssh-desktop-server --self-test"
}

# ── Install client ────────────────────────────────────────────────────────
install_client() {
    if [ "$OS_ID" = "macos" ]; then
        echo "macOS client: downloading .app.zip..."
        local artifact="remote-ssh-desktop-client-macos-$ARCH_SUFFIX.zip"
        curl -fsSL -o /tmp/rsd-client.zip "https://github.com/$REPO/releases/download/$LATEST/$artifact" || {
            echo "macOS build not yet available in this release." >&2
            exit 1
        }
        unzip -q /tmp/rsd-client.zip -d /Applications/
        echo "macOS client installed to /Applications/Remote SSH Desktop.app"
    else
        local artifact="remote-ssh-desktop-client-linux-$ARCH_SUFFIX"
        download_artifact "$artifact" "$INSTALL_DIR/remote-ssh-desktop"
        echo
        echo "Installing Qt/xcb runtime dependencies..."
        bash "$(dirname "$0")/install_client_deps.sh" 2>/dev/null || install_client_deps_inline
        echo
        echo "Client installed. Run: remote-ssh-desktop"
    fi
}

# ── Inline client deps (when running piped without scripts/ dir) ──────────
install_client_deps_inline() {
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y --no-install-recommends \
            libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 \
            libxcb-render-util0 libxcb-xinerama0 libegl1 libgl1 libdbus-1-3
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --noconfirm --needed xcb-util-cursor xcb-util-keysyms \
            xcb-util-wm xcb-util-renderutil libxkbcommon-x11 libglvnd
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y xcb-util-cursor xcb-util-keysyms xcb-util-wm \
            xcb-util-renderutil libxkbcommon-x11 mesa-libEGL
    fi
}

# ── Install server system deps ────────────────────────────────────────────
install_server_deps() {
    if command -v apt-get >/dev/null 2>&1; then
        # Detect ALT Linux by checking /etc/altlinux-release or apt-rpm
        if [ -f /etc/altlinux-release ] || (apt-get --version 2>/dev/null | grep -q "apt-rpm"); then
            echo "  Detected: ALT Linux (apt-rpm)"
            sudo apt-get install -y xorg-xvfb xorg-utils xclip xterm
        else
            echo "  Detected: Debian/Ubuntu/Astra Linux"
            sudo apt-get update -y
            sudo apt-get install -y --no-install-recommends xvfb xauth xclip xterm
        fi
    elif command -v pacman >/dev/null 2>&1; then
        echo "  Detected: Arch Linux / Manjaro"
        sudo pacman -S --noconfirm --needed xorg-server-xvfb xorg-xauth xclip xterm
    elif command -v dnf >/dev/null 2>&1; then
        echo "  Detected: Fedora / RHEL"
        sudo dnf install -y xorg-x11-server-Xvfb xorg-x11-xauth xclip xterm
    elif command -v yum >/dev/null 2>&1; then
        echo "  Detected: CentOS / older RHEL"
        sudo yum install -y xorg-x11-server-Xvfb xorg-x11-xauth xclip xterm
    elif command -v zypper >/dev/null 2>&1; then
        echo "  Detected: openSUSE"
        sudo zypper install -y xorg-x11-server xorg-x11-xauth xclip xterm
    else
        echo "  WARNING: unknown package manager. Install manually: xvfb xauth xclip xterm"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"

case "$COMPONENT" in
    server) install_server ;;
    client) install_client ;;
    both)   install_server; echo; install_client ;;
    *)
        echo "Usage: install.sh [server|client|both]" >&2
        exit 1
        ;;
esac

echo
echo "=== Done! ==="
