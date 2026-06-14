# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['remote_ssh_desktop.version', 'Xlib', 'Xlib.ext', 'Xlib.ext.xtest', 'Xlib.ext.xfixes']
hiddenimports += collect_submodules('asyncssh')
hiddenimports += collect_submodules('PIL')
hiddenimports += collect_submodules('mss')
hiddenimports += collect_submodules('remote_ssh_desktop.server')
hiddenimports += collect_submodules('remote_ssh_desktop.common')
hiddenimports += collect_submodules('remote_ssh_desktop.crypto')


a = Analysis(
    ['remote_ssh_desktop/server/main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='remote-ssh-desktop-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
