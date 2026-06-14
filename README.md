# Remote SSH Desktop

Remote SSH Desktop is a Python client/server application for remote graphical access to isolated Linux X11 sessions over **SSH only**. It does not use VNC/RDP or their libraries. Graphics, input, control, and clipboard events use a custom framed protocol over an SSH exec channel; file transfer uses SFTP over the same SSH connection.

## Features

- SSH-only transport with password or private-key login.
- A new isolated X11 session per connection using `Xvfb`, its own display number, and its own `XAUTHORITY` cookie.
- Session lifecycle controls: persistent reconnectable sessions, idle timeout, concurrent session limit, list/stop session commands.
- Desktop streaming as JPEG frames captured from X11 with `mss`/XShm; hardware cursor is embedded when XFixes is available.
- Adaptive FPS/JPEG quality based on client ping latency and drop reports.
- Mouse movement, buttons, scroll, keyboard keysyms, and modifiers sent from client to server and replayed through XTEST.
- Cross-platform Qt client via PySide6 for Windows and Linux; Linux supports both X11 (`xcb`) and Wayland with XWayland fallback.
- Wayland-safe shortcuts: toolbar buttons for `Ctrl+Alt+Del`, `Super`, and `Esc` because global shortcut grabbing is restricted on Wayland.
- Two-way text clipboard sync through Qt on the client and `xclip` on X11 server, with origin tagging and max-size privacy limits.
- Shared-folder file manager over SFTP: browse, mkdir, upload, download, drag-and-drop upload, progress, cancellation, and resume for partial files.
- Built-in SSH key generation for Ed25519/RSA, optional passphrase, public-key export, and `authorized_keys` helper.
- PyInstaller specs for Windows/Linux client and Linux server.

## Project layout

```text
remote_ssh_desktop/
├── client/main.py          # PySide6 GUI, SSH transport, clipboard, SFTP file manager
├── server/main.py          # SSH exec entrypoint / session proxy / worker launcher
├── server/session.py       # X11 session worker, capture loop, input, clipboard, lifecycle
├── server/x11.py           # Xvfb, XAUTHORITY, XTEST, XFixes cursor, xclip helpers
├── common/protocol.py      # custom frame protocol and versioning
├── common/files.py         # shared-folder jail path normalization
├── common/config.py        # config helpers
├── common/logging_setup.py # logging setup
└── crypto/keygen.py        # SSH key generation
```

## Install from source

```bash
git clone https://github.com/uiper123/TGIO_APRG.git
cd TGIO_APRG
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

Server system packages on Debian/Ubuntu:

```bash
sudo apt-get install -y xvfb xauth xclip xterm libx11-6 libxext6 libxtst6 libxfixes3 libxdamage1
```

For a fuller desktop, install one of these and select it in the client remote command:

```bash
sudo apt-get install -y openbox fluxbox xfce4
```

Client Linux Qt runtime packages may also be needed depending on the distro:

```bash
sudo apt-get install -y libegl1 libopengl0 libxcb-cursor0 libxkbcommon-x11-0 libxcb-xinerama0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-randr0 libxcb-shape0 libxcb-xfixes0
```

## Run

Start the client:

```bash
python -m remote_ssh_desktop.client.main
```

Fill in:

- host / port
- username
- password or private key path
- session id, or keep the generated one
- screen size, FPS, JPEG quality
- shared folder on the server, default `~/RemoteShared`

The default remote command is:

```bash
python -m remote_ssh_desktop.server.main --proxy --session-id {session_id} --screen {screen} --fps {fps} --quality {quality} --idle-timeout {idle_timeout} {persistent_flag} {clipboard_flag} --clipboard-max-bytes {clipboard_max_bytes} --shared-folder {shared_folder}
```

That command runs over SSH as the authenticated system user. Therefore the virtual desktop process, home directory, permissions, and shared folder belong to that SSH user. Each connection gets its own virtual X11 display unless you reconnect to a persistent session id.

## Connection profiles

The client includes a connection profile manager in the Connection panel:

- save multiple host profiles without storing passwords or key passphrases
- search and load profiles from the dropdown
- import/export profiles as JSON
- import simple `~/.ssh/config` `Host` entries, including `HostName`, `User`, `Port`, `IdentityFile`, and `ProxyJump`
- keep a separate recent-connection history for Quick Connect without storing secrets

Profiles are stored by default at `~/.config/remote-ssh-desktop/profiles.json`. Override this location for tests or portable runs with `REMOTE_SSH_DESKTOP_PROFILES=/path/to/profiles.json`.

Recent connections are stored separately at `~/.config/remote-ssh-desktop/history.json`. They contain sanitized connection settings only, are capped to the latest 20 entries, and can be cleared from the GUI. Override the path with `REMOTE_SSH_DESKTOP_HISTORY=/path/to/history.json`.

ProxyJump/bastion hosts are passed through AsyncSSH's tunnel support. Put the bastion alias or `user@host` value in the `ProxyJump` field.

Launch the client with a profile preloaded:

```bash
python -m remote_ssh_desktop.client.main --profile prod
```

To connect immediately after loading the profile:

```bash
python -m remote_ssh_desktop.client.main --profile prod --connect
```

To reconnect to the most recent successful connection:

```bash
python -m remote_ssh_desktop.client.main --last
# or
python -m remote_ssh_desktop.client.main --recent
```

The Desktop tab also has a **Quality preset** selector:

- **LAN** — 30 FPS / JPEG 90 for fast local networks
- **WAN** — 18 FPS / JPEG 75 balanced default
- **Mobile** — 10 FPS / JPEG 55 for slow or metered connections
- Any manual FPS/JPEG change marks the profile as **Custom** and is saved with the profile/history.

The toolbar supports multiple simultaneous connections by opening another client window with **New Window**. If a saved profile is selected, the new window preloads it via `--profile`, so you can connect to a second host/session without interrupting the current one.

## Self-test diagnostics

Before connecting, run the dependency self-test to catch missing local/server prerequisites early:

```bash
remote-ssh-desktop-client --self-test
remote-ssh-desktop-server --self-test
remote-ssh-desktop-server --self-test-json
remote-ssh-desktop-server --self-test-output remote-ssh-desktop-self-test.txt
```

The client also has a **Diagnostics** tab and toolbar **Self-test** action. Reports cover Python version/modules, Linux X11 tools (`Xvfb`, `xauth`, `xclip`, `xterm`), and Qt display environment. Text or JSON reports can be exported for support.

## Server CLI

The server module is normally launched by the client over SSH, but it can be managed manually:

```bash
python -m remote_ssh_desktop.server.main --list-sessions
python -m remote_ssh_desktop.server.main --stop-session <session-id>
python -m remote_ssh_desktop.server.main --proxy --session-id demo --screen 1280x720 --desktop-command xterm
```

Useful options:

- `--persistent` keeps a session alive after disconnect for reconnection.
- `--idle-timeout 300` controls cleanup after disconnect.
- `--max-sessions 8` limits concurrent workers.
- `--no-clipboard` disables clipboard sync.
- `--clipboard-max-bytes 1000000` limits copied text size.
- `--desktop-command openbox-session` or `startxfce4` selects the session desktop.

## SSH keys

From the GUI, click **Generate key**. Or use the CLI:

```bash
python -m remote_ssh_desktop.crypto.keygen --kind ed25519 --output-dir ~/.ssh --name id_remote_ssh_desktop
```

It prints the private/public key paths and a safe helper command to append the public key to `~/.ssh/authorized_keys` on the server.

## Clipboard

Clipboard sync is text/UTF-8 by default. It uses `QClipboard` on the client and `xclip` against the worker's X11 display on the server. Sync messages contain an `origin` field so text received from the other side is not sent back in a loop. Disable it with the GUI checkbox or `--no-clipboard`.

## Shared folder and SFTP jail

The client file manager always works relative to the configured shared folder. Paths are normalized as relative paths before being joined to the shared folder, so UI navigation cannot escape the application-level jail with `..` or absolute paths.

Supported actions:

- browse and refresh
- create folder
- upload file
- download file
- drag local files onto the desktop view to upload
- cancel active transfers
- resume partially transferred files

## Protocol

The custom frame header is exactly six bytes:

```text
+--------+--------+------------------+------------------+
| type   | flags  | length uint32 BE | payload          |
| 1 byte | 1 byte | 4 bytes          | length bytes     |
+--------+--------+------------------+------------------+
```

Types:

- `0x01` control
- `0x02` video
- `0x03` input
- `0x04` clipboard
- `0x05` files/status
- `0x06` stats

Control/input/clipboard payloads are JSON. Video payloads are raw JPEG frames. Large file bytes are transferred through asyncssh SFTP, not through custom frames.

## Linux X11 vs Wayland client notes

Qt chooses its platform plugin automatically. The client sets:

- `QT_QPA_PLATFORM=xcb` on normal Linux X11 sessions.
- `QT_QPA_PLATFORM=wayland;xcb` when `WAYLAND_DISPLAY` is present, so Qt can fall back to XWayland.

Wayland does not allow apps to globally intercept system shortcuts such as `Super` and `Alt+Tab`. Use the toolbar buttons for special keys. Mouse/keyboard capture inside the client window works normally.

## Build executables

Install PyInstaller:

```bash
pip install pyinstaller
```

Linux client:

```bash
pyinstaller build_client_linux.spec
```

Windows client, run on Windows:

```powershell
pyinstaller build_client_windows.spec
```

Linux server:

```bash
pyinstaller build_server_linux.spec
```

## Tests

```bash
python -m pytest -q
```

The test suite includes protocol/jail tests and a local Xvfb end-to-end proxy test when `Xvfb`, `xauth`, and `xterm` are available.

## Current implementation choices

- JPEG is the production codec in this implementation. The dependency list includes `pyav` for future H.264/H.265 work, but H.264 is not enabled by default.
- Authentication is delegated to SSH itself. The remote command runs as the authenticated Linux user, which gives per-user `$HOME`, UID/GID permissions, and independent X11 sessions without requiring a custom root PAM broker process.
