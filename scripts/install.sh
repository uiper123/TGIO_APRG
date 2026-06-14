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

# (No GitHub release lookup needed — we install the package from git via pip.)

# ── Install server ────────────────────────────────────────────────────────
install_server() {
    echo "Installing server system dependencies..."
    install_server_deps
    echo
    ensure_python
    echo "Installing the server package (pip from git)..."
    pip_install_pkg
    echo
    echo "Server installed. Verify:"
    echo "  remote-ssh-desktop-server --self-test"
    echo "  (or: python3 -m remote_ssh_desktop.server.main --self-test)"
}

# ── Install client ────────────────────────────────────────────────────────
install_client() {
    if [ "$OS_ID" = "macos" ]; then
        echo "macOS client: installing via pip..."
        ensure_python
        pip_install_pkg
    else
        echo "Installing Qt/xcb runtime dependencies..."
        install_client_deps_inline
        echo
        ensure_python
        echo "Installing the client package (pip from git)..."
        pip_install_pkg
        echo
        echo "Client installed. Run: remote-ssh-desktop"
        echo "  (or: python3 -m remote_ssh_desktop.client.main)"
    fi
}

# ── Ensure python3 + pip + git + curl ─────────────────────────────────────
ensure_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        echo "  Installing python3 + pip + git..."
        if command -v apt-get >/dev/null 2>&1; then
            sudo apt-get install -y python3 python3-pip git curl
        elif command -v pacman >/dev/null 2>&1; then
            sudo pacman -S --noconfirm --needed python python-pip git curl
        elif command -v dnf >/dev/null 2>&1; then
            sudo dnf install -y python3 python3-pip git curl
        elif command -v zypper >/dev/null 2>&1; then
            sudo zypper install -y python3 python3-pip git curl
        else
            echo "  WARNING: install python3, pip, git, and curl manually." >&2
        fi
    fi
    if ! python3 -m pip --version >/dev/null 2>&1; then
        command -v apt-get >/dev/null 2>&1 && sudo apt-get install -y python3-pip || true
    fi
}

# ── pip install the package from git (PEP 668 aware) ──────────────────────
pip_install_pkg() {
    local spec="git+https://github.com/$REPO.git@main"
    python3 -m pip install --user --upgrade "$spec"         || python3 -m pip install --user --break-system-packages --upgrade "$spec"
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) : ;;
        *) echo "  NOTE: add ~/.local/bin to your PATH so the launchers are found:"
           echo "        echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc" ;;
    esac
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
