#!/usr/bin/env bash
# Builds the Linux server binary using PyInstaller.

set -euo pipefail
export RSD_KIND=server
exec "$(dirname "$0")/build_client_linux.sh" "$@"
