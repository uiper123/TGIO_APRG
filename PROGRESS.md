# PROGRESS

## Audit — 2026-06-14 cycle 1

### Environment
- Repository cloned to `/home/workspace/Projects/TGIO_APRG` on branch `main`, current base HEAD `1925965`.
- Python venv recreated in `.venv`; `requirements.txt`, `requirements-build.txt`, and `pytest-timeout` installed.
- Debian/X11 packages expected for e2e: `xvfb`, `xauth`, `xclip`, `xterm`, X11/Qt runtime libraries.

### Test baseline
- Current verification after this cycle: `python -m pytest -q -x --timeout=60` → `9 passed`.
- Import/help smoke: `python -m remote_ssh_desktop.crypto.keygen --help`, `QT_QPA_PLATFORM=offscreen timeout 10 python -m remote_ssh_desktop.client.main --help`, `timeout 10 python -m remote_ssh_desktop.server.main --version` → OK.
- Static build-script checks: `bash -n scripts/build_client_linux.sh scripts/build_server_linux.sh`; `--onefile` present in Linux and Windows build scripts → OK.

### Tree reviewed
- `remote_ssh_desktop/client/main.py`: Qt client, SSH transport, clipboard, SFTP file manager.
- `remote_ssh_desktop/server/main.py`: server CLI, persistent worker spawn, session listing/stopping, stdio bridge.
- `remote_ssh_desktop/server/session.py`: X11 worker lifecycle, capture/input/clipboard loops, adaptive quality.
- `remote_ssh_desktop/server/x11.py`: Xvfb/XAUTHORITY/capture/XTEST/xclip helpers.
- `remote_ssh_desktop/common/protocol.py`: framed protocol.
- `remote_ssh_desktop/common/files.py`: SFTP shared-folder jail path normalization.
- `remote_ssh_desktop/crypto/keygen.py`: SSH key generation.
- PyInstaller specs/scripts and `.github/workflows/release.yml`.
- `tests/`: protocol/jail/config/keygen/UI and Xvfb e2e proxy tests.

### Explicit findings

#### TODO/mock/fake/hardcoded/stub scan
- Current scan finds no `TODO`, `FIXME`, `NotImplementedError`, `pass`, `mock`, `dummy`, or hardcoded functional stub in `remote_ssh_desktop/`, `tests/`, `scripts/`, workflow, specs, and docs.
- `xtest.fake_input` occurrences in `server/x11.py` are real XTEST API calls, not fake/mock code.

#### README feature coverage
- Present in code and covered at least partly: SSH-only exec transport, JPEG frame protocol, Xvfb isolated sessions, XAUTHORITY, XTEST input, clipboard via xclip, SFTP browse/upload/download/resume, key generation, protocol tests, Xvfb e2e smoke.
- Present in code but still needs deeper verification: persistent reconnect/resume session lifecycle, idle timeout cleanup, max-session limit, adaptive FPS/quality, clipboard origin loop prevention, transfer cancellation/resume edge cases.
- Release one-file support is present in scripts/workflow, but a real CI artifact download/start check still needs to be done after the next tag/workflow run.
- UI has been modernized in current HEAD, but still needs a product-level pass on file manager polish, toasts/spinners, and resize/Wayland behavior.

## Cycle 1 completed — 2026-06-14

### Done
- Hardened SFTP uploads: `TransportThread.put_file()` now normalizes the destination and creates missing remote parent directories inside the configured jail before resuming/writing.
- Added regression test for recursive remote parent-directory creation with a fake async SFTP backend.
- Replaced silent server proxy/clipboard exception swallowing with debug/exception logging in `server/main.py` and `server/session.py`.
- Updated `CHANGELOG.md`.

### Verified
- `python -m pytest -q -x --timeout=60` → `9 passed`.
- `python -m compileall -q remote_ssh_desktop tests` → OK.
- CLI/help smoke checks for keygen, headless client `--help`, and server `--version` → OK.
- `bash -n` for Linux build scripts → OK.
- Stub scan for functional code/docs/workflow → no remaining `pass`/TODO/mock-style findings other than real `xtest.fake_input` calls.

### Next step
- Continue with one focused gap: add tests for session lifecycle controls (`--persistent`, `--resume`, idle timeout, `--list-sessions`, `--stop-session`) using short-lived Xvfb worker/proxy runs with timeouts, then fix any lifecycle bugs found.

## Cycle 2 completed — 2026-06-14

### Done
- Added live Xvfb lifecycle e2e coverage for persistent session `--list-sessions`, `--resume`, `--stop-session`, and non-persistent idle cleanup.
- Fixed a real resume bug: `ensure_worker()` no longer uses a Unix-socket connect probe that consumed the worker's single current proxy connection before the actual stdio bridge attached.
- Hardened stale session handling: `list_states()` cleans dead/zombie worker state, session counts ignore stale entries, and `--stop-session` waits for SIGTERM cleanup before escalating to SIGKILL and removing stale socket/state files.
- Added SIGTERM/SIGINT handling inside `SessionWorker` so worker shutdown runs the normal cleanup path for Xvfb, desktop process, socket, and non-persistent state.

### Verified
- `python -m pytest -q tests/test_e2e_proxy.py -x --timeout=60` → `3 passed`.
- `python -m pytest -q -x --timeout=60` → `11 passed`.
- `python -m compileall -q remote_ssh_desktop tests` → OK.
- Post-test process scan for `remote_ssh_desktop`, `Xvfb`, and `xterm` → no leftovers.

### Next step
- Continue with the next live-verification gap: clipboard/input/file-transfer e2e over a real local SSH server, or, if SSH daemon setup is unavailable, add isolated tests for clipboard anti-loop/UTF-8/limit behavior and transfer resume/cancel edge cases.

## Cycle 3 completed — 2026-06-14

### Done
- Added a real connection profile manager: searchable profile dropdown, Save/Delete, JSON import/export, and non-secret storage at `~/.config/remote-ssh-desktop/profiles.json` or `REMOTE_SSH_DESKTOP_PROFILES`.
- Added `~/.ssh/config` import for simple `Host` blocks (`HostName`, `User`, `Port`, `IdentityFile`, `ProxyJump`) while ignoring wildcard hosts.
- Added ProxyJump/bastion support through AsyncSSH tunnel configuration and a dedicated GUI field.
- Added client CLI shortcuts: `--profile NAME` preloads a saved profile; `--profile NAME --connect` starts connecting after the Qt event loop opens.
- Updated README and CHANGELOG.

### Verified
- `python -m pytest -q tests/test_profiles.py tests/test_client_ui.py -x --timeout=60` → `8 passed`.
- `python -m pytest -q -x --timeout=60` → `16 passed`.

### Next step
- Continue with Quick Connect/history/recent profiles, or first-run diagnostics/self-test for local/server dependencies (`Xvfb`, `xauth`, `xclip`, `xterm`, Qt runtime) with clear UI feedback.

## Cycle 4 completed — 2026-06-14

### Done
- Added separate recent-connection history storage at `~/.config/remote-ssh-desktop/history.json` with `REMOTE_SSH_DESKTOP_HISTORY` override, schema versioning, sanitization, deduplication, newest-first sorting, and a 20-entry cap.
- Added Quick Connect UI: toolbar action, Recent list, connect-selected/double-click reconnect, and Clear history button.
- Saved history only after a successful session hello, keeping passwords/key passphrases out of profiles/history.
- Added client CLI aliases `--last` / `--recent` to load and immediately connect to the most recent saved connection.
- Updated README and CHANGELOG.

### Verified
- Installed required headless Qt/X11 runtime packages in the test environment (`libegl1`, Qt xcb helpers, `xvfb`, `xauth`, `xclip`, `xterm`).
- `python -m compileall -q remote_ssh_desktop tests` → OK.
- `QT_QPA_PLATFORM=offscreen timeout 120 python -m pytest -q tests/test_history.py tests/test_client_ui.py -x --timeout=60` → `8 passed`.
- `QT_QPA_PLATFORM=offscreen timeout 120 python -m pytest -q -x --timeout=60` → `20 passed`.
- `QT_QPA_PLATFORM=offscreen timeout 20 python -m remote_ssh_desktop.client.main --help` → OK, shows `--last, --recent`.

### Next step
- Continue with Cycle 4 second priority: first-run self-test / diagnostics for client/server dependencies (`Xvfb`, `xauth`, `xclip`, `xterm`, Qt runtime, Python, asyncssh), with UI report/export, CLI `--self-test`, mocked tests for missing dependencies, then update PROGRESS/CHANGELOG/README and commit.

## Cycle 5 completed — 2026-06-14

### Done
- Added shared self-test diagnostics module with text/JSON serialization and report saving.
- Added client CLI `--self-test` / `--self-test-json`, toolbar Self-test action, Diagnostics tab, and report export.
- Added server CLI `--self-test`, `--self-test-json`, and `--self-test-output` so remote hosts can be checked before launching an X11 session.
- Diagnostics cover Python 3.11+, required Python modules, Linux X11 commands (`Xvfb`, `xauth`, `xclip`, `xterm`), and Qt display environment.
- Added diagnostics unit tests and UI coverage.
- Updated README and CHANGELOG.

### Verified
- `python -m compileall -q remote_ssh_desktop tests` → OK.
- `QT_QPA_PLATFORM=offscreen timeout 120 python -m pytest -q tests/test_diagnostics.py tests/test_client_ui.py -x --timeout=60` → `9 passed`.
- `QT_QPA_PLATFORM=offscreen timeout 120 python -m pytest -q -x --timeout=60` → `24 passed`.
- `QT_QPA_PLATFORM=offscreen timeout 30 python -m remote_ssh_desktop.client.main --self-test` → PASS.
- `QT_QPA_PLATFORM=offscreen timeout 30 python -m remote_ssh_desktop.server.main --self-test-json` → valid JSON, PASS.

### Next step
- Continue with live local SSH e2e: spin up an isolated `sshd`, connect the Qt transport over localhost, verify session hello/frame flow plus SFTP upload/download/clipboard behavior, then fix any real transport issues found.

## Cycle 6 completed — 2026-06-14

### Done
- Added a live localhost OpenSSH integration test that generates temporary host/user keys, starts isolated `sshd`, connects `TransportThread` over AsyncSSH, launches the real server proxy with Xvfb/xterm, and verifies session hello + JPEG frame delivery.
- Extended the same e2e test to exercise SFTP upload/download through the actual client transport and OpenSSH SFTP subsystem.
- Verified clipboard write-through from client protocol frame into the remote X11 clipboard with `xclip`.
- Fixed a real transport bug: `TransportThread` now calls `create_process(..., encoding=None)` so protocol frames remain binary bytes instead of passing through text stdio handling.
- Updated CHANGELOG.

### Verified
- `python -m compileall -q remote_ssh_desktop tests/test_e2e_ssh.py` → OK.
- `QT_QPA_PLATFORM=offscreen timeout 180 python -m pytest -q tests/test_e2e_ssh.py -x -s --timeout=120` → `1 passed`.
- Post-test process scan for project `remote_ssh_desktop`, Xvfb, xterm, and test sshd → no project leftovers.

### Next step
- Continue down backlog with UX/product features: quality presets (LAN/WAN/Mobile), multi-session tabs/windows, richer file-manager actions, then repeat full tests + commit + push.

## Cycle 7 completed — 2026-06-14

### Done
- Added client Quality preset selector with `LAN`, `WAN`, `Mobile`, and `Custom`.
- `LAN` maps to 30 FPS / JPEG 90, `WAN` to 18 FPS / JPEG 75, and `Mobile` to 10 FPS / JPEG 55.
- Manual FPS/JPEG edits switch the selector to `Custom`.
- Quality preset now persists through profiles/history and current config payloads.
- Live preset/FPS/JPEG changes send `set_quality` control frames to the connected server.
- Updated README and CHANGELOG.

### Verified
- `QT_QPA_PLATFORM=offscreen timeout 120 python -m pytest -q tests/test_profiles.py tests/test_client_ui.py -x --timeout=60` → `11 passed`.

### Next step
- Continue with multi-session UX: tab/window workflow, clearer active-connection labeling, and release artifact validation.

## Cycle 8 completed — 2026-06-14

### Done
- Added toolbar **New Window** action for multiple simultaneous connections.
- New client instances preload the selected saved profile via `--profile` when available, while leaving the current connection untouched.
- Added UI regression coverage for the new-window launch command.
- Updated README and CHANGELOG.

### Verified
- `python -m compileall -q remote_ssh_desktop tests` → OK.
- `QT_QPA_PLATFORM=offscreen timeout 120 python -m pytest -q tests/test_client_ui.py -x --timeout=60` → `8 passed`.

### Next step
- Continue with active connection/session status polish, then artifact build/run verification.

## Cycle 9 completed — 2026-06-14

### Done
- Added an active connection label in the Desktop status area showing target host, session id, and uptime.
- Reset uptime on disconnect and refresh the label from the existing stats timer.
- Added UI regression coverage for session-info label updates.
- Updated CHANGELOG.

### Verified
- `QT_QPA_PLATFORM=offscreen timeout 120 python -m pytest -q tests/test_client_ui.py -x --timeout=60` → `9 passed`.

### Next step
- Continue with release artifact build/run validation: build Linux server/client one-file binaries locally where feasible, run `--version`/`--self-test`/help smoke checks, then commit/push any packaging fixes.

## Cycle 10 completed — 2026-06-14

### Done
- Made diagnostics role-aware (`client`, `server`, `full`) so frozen server builds do not fail on client-only PySide6 and frozen client runs do not require server-only X11 capture modules.
- Wired client CLI/UI self-test to `role="client"` and server self-test to `role="server"`.
- Built the Linux server one-file PyInstaller artifact locally.
- Verified the downloaded/built standalone Linux server artifact launches and reports self-test PASS.
- Updated CHANGELOG.

### Verified
- `python -m compileall -q remote_ssh_desktop tests` → OK.
- `QT_QPA_PLATFORM=offscreen timeout 120 python -m pytest -q -x --timeout=120` → `29 passed`.
- `PROJECT_ROOT="$PWD" RSD_KIND=server RSD_NAME=remote-ssh-desktop-server bash scripts/build_server_linux.sh` → produced `dist/remote-ssh-desktop-server`.
- `./dist/remote-ssh-desktop-server --version` → `remote-ssh-desktop-server 0.1.0`.
- `QT_QPA_PLATFORM=offscreen timeout 60 ./dist/remote-ssh-desktop-server --self-test` → `Overall: PASS`.

### Next step
- Continue with Linux client one-file build/run validation and CI release artifact download verification once a tagged workflow artifact exists.