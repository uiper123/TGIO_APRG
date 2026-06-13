# Remote SSH Desktop

Python client/server app for remote graphical access over SSH using a custom frame protocol over an SSH exec channel and SFTP for file transfer.

## What it does

- launches a separate X11 session on the server
- streams the desktop as JPEG frames
- sends mouse and keyboard input back to X11
- syncs clipboard text both ways
- transfers files over SFTP on the same SSH connection
- generates SSH key pairs inside the app

## Layout

- `remote_ssh_desktop/client/main.py` — Qt client
- `remote_ssh_desktop/server/main.py` — SSH proxy entrypoint and worker launcher
- `remote_ssh_desktop/server/session.py` — session worker, capture, input, clipboard
- `remote_ssh_desktop/server/x11.py` — Xvfb/X11 helpers
- `remote_ssh_desktop/common/protocol.py` — frame protocol
- `remote_ssh_desktop/crypto/keygen.py` — key generation

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Server host needs:

- `Xvfb`
- `xauth`
- `xclip` recommended for clipboard
- a desktop environment or window manager such as `openbox-session`, `startxfce4`, `fluxbox`, or `xterm`

Optional but recommended on the server:

- `python-xlib`
- `mss`

## Start the server side

The server side runs as a remote command over SSH.

Default command:

```bash
python -m remote_ssh_desktop.server.main --proxy --session-id <id>
```

The first connection starts a detached session worker. Later connections can reuse the same session id to resume.

## Start the client

```bash
python -m remote_ssh_desktop.client.main
```

Fill in:

- host
- port
- username
- password or key path
- remote command
- session id

## SSH key generation

Use the app button, or run:

```bash
python -m remote_ssh_desktop.crypto.keygen --output-dir ~/.ssh
```

Then add the printed public key helper to `authorized_keys` on the server.

## Clipboard

Clipboard sync currently focuses on UTF-8 text. The protocol includes an origin tag to avoid loops.

## File transfer

File transfer uses SFTP over the same SSH connection. The default shared folder is `~/RemoteShared` on the server.

You can also drag local files onto the desktop view to upload them into the shared folder.

## Wayland and X11 on the client

Qt chooses the right backend automatically. On Linux:

- X11: full keyboard and mouse capture works best
- Wayland: global grabs are limited by design; use the on-screen buttons for special keys like Super or Ctrl+Alt+Del

## Build

PyInstaller spec files are included:

- `build_client_windows.spec`
- `build_client_linux.spec`
- `build_server_linux.spec`

Example:

```bash
pyinstaller build_client_linux.spec
pyinstaller build_server_linux.spec
```


## GitHub

This project is ready to push to a GitHub repository once GitHub is connected.
