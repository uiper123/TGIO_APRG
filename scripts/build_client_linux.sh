#!/usr/bin/env bash
# Builds the Linux client binary using PyInstaller.
# Environment variables:
#   RSD_KIND   - "client" (default) or "server"
#   RSD_NAME   - output name; default "remote-ssh-desktop" or "remote-ssh-desktop-server"
#   PROJECT_ROOT - the project root; defaults to current directory

set -euo pipefail

KIND="${RSD_KIND:-client}"
if [[ "$KIND" == "server" ]]; then
  NAME="${RSD_NAME:-remote-ssh-desktop-server}"
  ENTRY="remote_ssh_desktop/server/main.py"
else
  NAME="${RSD_NAME:-remote-ssh-desktop}"
  ENTRY="remote_ssh_desktop/client/main.py"
fi
PROJECT_ROOT="${PROJECT_ROOT:-$PWD}"
DIST="$PROJECT_ROOT/dist"
BUILD="$PROJECT_ROOT/build"

rm -rf "$DIST" "$BUILD"
mkdir -p "$DIST"

ARGS=(
  --noconfirm --clean
  --name "$NAME"
  --distpath "$DIST"
  --workpath "$BUILD"
  --specpath "$PROJECT_ROOT"
)
if [[ "$KIND" == "client" ]]; then
  ARGS+=(--windowed)
else
  ARGS+=(--console)
fi
ARGS+=(
  --collect-submodules PySide6
  --collect-submodules asyncssh
  --collect-submodules PIL
  --collect-submodules mss
  --collect-submodules remote_ssh_desktop
  --hidden-import PIL.ImageQt
  "$ENTRY"
)

echo "PyInstaller ${ARGS[*]}"
pyinstaller "${ARGS[@]}"

echo "build complete: $DIST"
