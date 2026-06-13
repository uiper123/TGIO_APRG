block_cipher = None

a = Analysis([
    "remote_ssh_desktop/server/main.py",
], pathex=["."], binaries=[], datas=[], hiddenimports=[], hookspath=[], runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="remote-ssh-desktop-server", console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="remote-ssh-desktop-server")
