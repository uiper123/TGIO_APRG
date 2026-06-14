#!/usr/bin/env python
# -*- mode: python ; coding: utf-8 -*-
# Single source of truth for the Linux server build.
# Used by scripts/build_server_linux.sh and CI (release.yml).

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", ".")).resolve()

hidden = (
    collect_submodules("asyncssh")
    + collect_submodules("PIL")
    + collect_submodules("mss")
    + collect_submodules("remote_ssh_desktop")
)
hidden += [
    "Xlib", "Xlib.ext", "Xlib.ext.xtest", "Xlib.ext.xfixes",
    "cryptography", "cryptography.hazmat.primitives.asymmetric",
]
datas = [(str(PROJECT_ROOT / "remote_ssh_desktop" / "version.py"), "remote_ssh_desktop")]

a = Analysis(
    ["remote_ssh_desktop/server/main.py"],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PySide6"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="remote-ssh-desktop-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
