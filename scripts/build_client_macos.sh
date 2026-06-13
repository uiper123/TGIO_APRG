#!/usr/bin/env bash
# Builds the macOS client binary using PyInstaller.

set -euo pipefail
KIND="${RSD_KIND:-client}"
NAME="${RSD_NAME:-remote-ssh-desktop.app}"
PROJECT_ROOT="${PROJECT_ROOT:-$PWD}"
DIST="$PROJECT_ROOT/dist"
BUILD="$PROJECT_ROOT/build"

rm -rf "$DIST" "$BUILD"
mkdir -p "$DIST"

ENTRY="remote_ssh_desktop/client/main.py"
ARGS=(
  --noconfirm --clean
  --name "$NAME"
  --osx-bundle-identifier org.remote-ssh-desktop.client
  --distpath "$DIST"
  --workpath "$BUILD"
  --specpath "$PROJECT_ROOT"
  --windowed
  --collect-submodules PySide6
  --collect-submodules asyncssh
  --collect-submodules PIL
  --collect-submodules mss
  --collect-submodules remote_ssh_desktop
  --hidden-import PIL.ImageQt
  "$ENTRY"
)

pyinstaller "${ARGS[@]}"
echo "build complete: $DIST"
