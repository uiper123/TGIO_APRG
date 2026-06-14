#!/usr/bin/env bash
# Builds the Linux client or server binary using the PyInstaller spec file.
# The spec file is the single source of truth for hidden imports and build options.
#
# Environment variables:
#   RSD_KIND     - "client" (default) or "server"
#   PROJECT_ROOT - project root; defaults to current directory

set -euo pipefail

KIND="${RSD_KIND:-client}"
PROJECT_ROOT="${PROJECT_ROOT:-$PWD}"
DIST="$PROJECT_ROOT/dist"
BUILD="$PROJECT_ROOT/build"

if [[ "$KIND" == "server" ]]; then
  SPEC="$PROJECT_ROOT/build_server_linux.spec"
else
  SPEC="$PROJECT_ROOT/build_client_linux.spec"
fi

rm -rf "$DIST" "$BUILD"
mkdir -p "$DIST"

echo "Building $(basename "$SPEC") -> $DIST"
PROJECT_ROOT="$PROJECT_ROOT" pyinstaller --noconfirm --distpath "$DIST" --workpath "$BUILD" "$SPEC"
echo "build complete: $DIST"
