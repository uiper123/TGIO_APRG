# PROGRESS

## Audit — 2026-06-14 cycle 1

### Environment
- Repository cloned to `/home/workspace/Projects/TGIO_APRG` on branch `main`, HEAD `2793d52`.
- Python venv created in `.venv`; `requirements.txt` and `pytest` installed.
- Debian/X11 packages installed for e2e: `xvfb`, `xauth`, `xclip`, `xterm`, X11/Qt runtime libraries.

### Test baseline
- Initial `python -m pytest -q`: `2 passed, 1 skipped` before installing X11 tools.
- After installing X11 tools: `3 passed` including local Xvfb proxy video stream e2e.

### Tree reviewed
- `remote_ssh_desktop/client/main.py`: Qt client, SSH exec transport, clipboard, SFTP file manager.
- `remote_ssh_desktop/server/main.py`: server CLI, persistent worker spawn, session listing/stopping, stdio bridge.
- `remote_ssh_desktop/server/session.py`: X11 worker lifecycle, capture/input/clipboard loops, adaptive quality.
- `remote_ssh_desktop/server/x11.py`: Xvfb/XAUTHORITY/capture/XTEST/xclip helpers.
- `remote_ssh_desktop/common/protocol.py`: framed protocol.
- `remote_ssh_desktop/common/files.py`: SFTP shared-folder path normalization.
- `remote_ssh_desktop/crypto/keygen.py`: SSH key generation.
- PyInstaller specs/scripts and `.github/workflows/release.yml`.
- `tests/`: protocol/jail tests and Xvfb e2e proxy test.

### Explicit findings

#### TODO/mock/fake/hardcoded/stub scan
- No `TODO`, `FIXME`, `NotImplementedError`, `mock`, `dummy`, or fake-data implementation found in functional code.
- `pass`/silent exception paths found and still need hardening:
  - `remote_ssh_desktop/server/session.py`: `_accept_proxy()` swallows disconnect/read errors; `_clipboard_loop()` swallows clipboard errors.
  - `remote_ssh_desktop/server/main.py`: stdio/socket bridge threads swallow copy errors.
  - These are not feature stubs, but they hide failures from logs.
- `xtest.fake_input` occurrences in `server/x11.py` are real XTEST calls, not fake/mock code.

#### README feature coverage
- Present in code and covered at least partly: SSH-only exec transport, JPEG frame protocol, Xvfb isolated sessions, XAUTHORITY, XTEST input, clipboard via xclip, SFTP browse/upload/download/resume, key generation, protocol tests, Xvfb e2e smoke.
- Present in code but weakly tested/needs deeper verification: persistent reconnect/resume session lifecycle, idle timeout cleanup, max-session limit, adaptive FPS/quality, clipboard origin loop prevention, file-transfer cancellation/resume edge cases.
- README/release mismatch found: release workflow currently packages directories/archives, while the requirement is one single executable asset per OS role.
- UI technically functional but visually unfinished: default widgets, weak validation/error feedback, single global progress bar, no polished theme toggle, no toasts/spinners, file manager is list-only.
- Wayland fallback is implemented via `QT_QPA_PLATFORM=wayland;xcb`, but not tested in CI.

#### Paths that can fail or silently do little
- File manager actions return silently when disconnected or no file selected.
- Connection config parsing can raise on invalid screen text before showing a friendly validation error.
- SFTP upload does not create missing remote parent directories before upload.
- Build scripts do not pass `--onefile` and release workflow re-wraps PyInstaller output directories.

## Cycle 1 plan

Priority scope: improve release correctness and harden the basic path without destabilizing the protocol.

1. Convert PyInstaller build scripts/workflow to real one-file artifacts for Linux client, Linux server, and Windows client.
2. Add version metadata in package code and keep SemVer/CHANGELOG aligned.
3. Add friendly client-side validation before connecting and prevent invalid screen/auth states from throwing raw exceptions.
4. Harden SFTP upload by creating remote parent directories and add tests for jail normalization/resume helpers where feasible.
5. Replace silent server exception swallowing with debug logging where it matters.

Verification for this cycle:
- `python -m pytest -q`
- Xvfb e2e remains green.
- Build-script static check confirms `--onefile` and workflow asset layout points to single files.
- Commit with conventional message if checks pass.

## Cycle 1 result

_Not completed yet._
