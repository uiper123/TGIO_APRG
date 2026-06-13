#!/usr/bin/env bash
set -euo pipefail

DIST=dist
NAME=remote-ssh-desktop-server
ENTRY=remote_ssh_desktop.server.main

python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r requirements.txt
python3 -m pip install --quiet pyinstaller

pyinstaller \
    --noconfirm \
    --clean \
    --name "$NAME" \
    --console \
    --onefile \
    --paths . \
    --distpath "$DIST" \
    --workpath build/pyi \
    --specpath build/spec \
    "$ENTRY"
