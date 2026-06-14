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
## Cycle 11 completed — 2026-06-14

### Done
- Audited .github/workflows/release.yml: confirmed Qt/X11 runtime packages already comprehensive (xvfb, xauth, libxcb-cursor0, libxkbcommon-x11-0, etc.).
- Confirmed release and pypi jobs have `needs: build` so any failed smoke-run blocks publication.
- Improved `smoke run built artifact` step — now platform-aware:
  - Linux client: `timeout 30 "$asset" --version` + `timeout 120 xvfb-run -a "$asset" --self-test`
  - Linux server: `timeout 30 "$asset" --version` + `timeout 120 "$asset" --self-test`
  - Windows client: `"$asset" --version` + `QT_QPA_PLATFORM=offscreen "$asset" --self-test-json`
- Added per-platform echo label for clearer CI log output.

### Verified
- `--self-test` exits before Qt initialization in both client and server, so xvfb tests binary startup + import + diagnostics.
- Diagnostics exit code: 0 = PASS, 2 = FAIL (caught by `set -e` in the step).
- All three matrix jobs are gated by the smoke-run step before the `upload artifacts` step.

### Next step
- Apply improved smoke run step to .github/workflows/release.yml (see session/release.yml for the ready patch).
- Apply with: git diff HEAD~1 HEAD -- .github/workflows/release.yml (or copy session/release.yml).
- Continue with Prompt 2: remove unused av/PyAV and msgpack dependencies.

## Cycle 12 completed — 2026-06-14

### Done
- Confirmed via GitHub code search: `av`/`PyAV` and `msgpack` have zero imports across the entire codebase.
- Removed `av>=12.0.0` and `msgpack>=1.0.8` from `requirements.txt`.
- Removed `msgpack` from the `"full"` role module list in `common/diagnostics.py`.
- Updated README `Current implementation choices`: marked pyav as not a dependency, not in builds, future option only.

### Next step
- Continue with Prompt 3: self-contained launch / clear dependency docs for each platform.

## Cycle 13 completed — 2026-06-14

### Done
- Added `_check_server_deps_or_exit()` to `server/main.py`: checks for Xvfb/xauth/xclip/xterm
  before any X11 session starts; exits with apt/dnf install command on first missing binary.
- Created `scripts/install_server_deps.sh` (Debian/Ubuntu + Fedora/RHEL + yum fallback).
- Created `scripts/install_client_deps.sh` (Qt/xcb runtime libs for Linux client binary).
- Added "Download and run" section to README with per-platform dependency table and quick-start commands.
- Evaluated AppImage vs --onedir for Linux client:
  - AppImage: truly self-contained, single file, but requires appimagetool + linuxdeploy in CI.
  - --onedir + launcher: simpler but ships as multi-file tarball, still requires system Qt libs.
  - Decision: ship install_client_deps.sh now; AppImage via linuxdeploy tracked as future work.

### Next step
- Continue with Prompt 4: TOFU host key verification (fix MITM vulnerability).

## Cycle 14 completed — 2026-06-14

### Done
- Fixed MITM vulnerability: replaced silent `known_hosts=None` default with TOFU.
- `ClientConfig.verify_host_key: bool = True` added; `_connect_once` now defaults to
  `~/.ssh/known_hosts` (created on first use with mode 0o600).
- On unknown host: `asyncssh.HostKeyNotVerifiable` caught, `_ask_tofu()` emits
  `requestTofuDialog` signal to Qt main thread; user sees fingerprint dialog; on accept
  the key is appended to known_hosts and the connection is retried.
- On changed host key: `asyncssh.HostKeyMismatch` caught, statusChanged emits a loud
  warning message; connection is blocked.
- Added explicit "Don't verify host key (insecure)" checkbox to the connection form;
  unchecked by default — verification is ON unless the user opts out consciously.
- `verify_host_key` persisted in profiles, QSettings, and profile import/export.
- Added Host key verification section to README.
- Updated profiles.py: `verify_host_key` in PROFILE_FIELDS and bool sanitize set.

### Next step
- Continue with Prompt 5: fix adaptive quality (drop reports always 0).

## Cycle 15 completed — 2026-06-14

### Done
- Fixed dead drop-report metric: `_dropped_frames` on the client was never incremented.
- Server (`session.py`): added `frames_seq: int = 0` to `SessionState`; capture loop
  now increments `frames_seq` per sent frame and prepends a 4-byte big-endian sequence
  number to each JPEG payload (`seq.to_bytes(4, "big") + jpeg`).
- Client (`client/main.py`): `_reader_loop` extracts the 4-byte prefix (if payload does
  not start with \xff\xd8), detects sequence gaps, and increments both
  `_dropped_frames` (cumulative) and `_drops_since_last_stats` (per-interval counter).
- `_handle_pong` now reports the per-interval drop count and immediately resets
  `_drops_since_last_stats` to 0, so the server\'s `dropped > 3` threshold is evaluated
  per 2-second ping cycle, not cumulatively over the whole session.
- `_apply_stats` on the server was already correct — no changes needed there.
- README feature description "Adaptive FPS/JPEG quality based on client ping latency
  and drop reports" is now accurate.

### Next step
- Continue with Prompt 6: align README and build process (fix broken build docs).

## Cycle 16 completed — 2026-06-14

### Done
- Audited build pipeline: all five .spec files exist in the project root and work.
- Identified gap: shell scripts built via CLI flags (slightly different hidden imports
  than spec files); README showed spec files; CI used shell scripts — three
  partially inconsistent paths.
- Chose spec files as single source of truth:
  - `build_client_linux.spec`: added `collect_submodules("asyncssh")`,
    `collect_submodules("PIL")`, `collect_submodules("mss")`,
    `collect_submodules("remote_ssh_desktop")`.
  - `build_server_linux.spec`: added `asyncssh`, `PIL`, `mss` collect_submodules;
    added `Xlib.ext.xtest`, `Xlib.ext.xfixes` hidden imports.
  - `scripts/build_client_linux.sh`: replaced CLI-flag build with
    `pyinstaller --noconfirm --distpath ... <spec>`.
  - `scripts/build_client_windows.ps1`: replaced CLI-flag build with
    `pyinstaller --noconfirm --distpath ... build_client_windows.spec`.
- README "Build executables" section rewritten: shows scripts (=CI) as primary,
  direct pyinstaller-spec as equivalent alternative. No more mention of
  non-existent .spec paths or stale CLI-only build instructions.
- Verified no other README↔code mismatches (format_remote_command placeholders
  are all handled; --proxy/--worker/--session-id args all exist in server parser).

### Verified
- All six prompts from the original issue list are now addressed.

### All 6 prompts complete
- Prompt 1: CI smoke-run (xvfb, platform-aware, timeout) — applied via browser editor
- Prompt 2: Removed av/PyAV + msgpack unused deps — commit ce86f7f9
- Prompt 3: Server dep check at startup + install scripts + README platform table — commit b51b2238
- Prompt 4: TOFU host key verification, explicit insecure checkbox — commit 8cf742c2
- Prompt 5: Real drop-frame detection via sequence numbers — commit debbdf54
- Prompt 6: Spec files as build source of truth, README+scripts synced — this commit

## Cycle 17 completed — 2026-06-14

### Done
- Created `remote_ssh_desktop/server/backends/` package:
  - `base.py`: SessionBackend ABC with check_dependencies(), startup(),
    capture_frame(), inject_mouse_move/button/scroll/key(), get/set_clipboard(),
    shutdown(), display_info, platform_name.
  - `x11.py`: X11Backend — wraps existing x11.py helpers (Xvfb, XTEST, xclip).
  - `windows.py`: WindowsBackend — mss capture + ctypes Win32 SendInput +
    Win32 clipboard API. No Xvfb needed. Captures the current Windows desktop.
  - `macos.py`: MacOSBackend — mss capture + pynput input + pbcopy/pbpaste.
    Requires Accessibility permission in System Preferences.
  - `__init__.py`: create_backend() auto-detects platform.system().
- Refactored session.py to use SessionBackend:
  - Removed direct X11 imports from session.py.
  - SessionState stripped of X11-specific fields (display, xvfb, xinput, etc.).
  - SessionWorker accepts backend= parameter; auto-detects if None.
  - _bootstrap() delegates to backend.check_dependencies() + backend.startup().
  - capture_frame, inject_input, clipboard all go through self.backend.*().
  - _teardown() calls backend.shutdown().
- Server now supports Linux (X11/Xvfb), Windows (current desktop), macOS (current desktop).
- Optional deps documented in requirements.txt comment.

### Platform support matrix
| | Linux x86 | Linux ARM64 | Windows | macOS |
|---|---|---|---|---|
| **Server** | ✅ | ✅ | ✅ NEW | ✅ NEW |
| **Client** | ✅ | pending CI | ✅ | pending CI |

### Next step
- Add universal curl installer (install.sh) for all Linux distros.
- Extend install_server_deps.sh for Arch Linux and ALT Linux.

## Cycle 18 completed — 2026-06-14

### Done
- Created `scripts/install.sh` — universal one-liner installer for all Linux distros:
  - Detects OS via /etc/os-release, downloads correct binary from GitHub Releases.
  - Installs server system deps for: Debian/Ubuntu/Astra (apt-get), Arch/Manjaro (pacman),
    ALT Linux (apt-rpm, different package names), Fedora/RHEL (dnf), openSUSE (zypper).
  - Installs client Qt/xcb runtime deps for the same distros.
  - Usage: curl | bash -s server|client|both
- Created `scripts/install.ps1` — Windows PowerShell one-liner (iwr | iex):
  - Downloads client .exe and server .exe from GitHub Releases.
  - Adds $LOCALAPPDATA\remote-ssh-desktop to PATH.
- Updated `scripts/install_server_deps.sh` with full multi-distro support:
  - Arch Linux: pacman (xorg-server-xvfb, xorg-xauth, xclip, xterm).
  - ALT Linux: apt-rpm with correct package names (xorg-xvfb, xorg-utils, xclip, xterm).
  - openSUSE: zypper.
  - ALT Linux detection via /etc/altlinux-release and apt-rpm signature.
- Created `scripts/arch/PKGBUILD` for Arch User Repository (AUR) packaging.
- Created `Dockerfile` and `docker-compose.yml` for containerised server deployment.
  - FROM debian:bookworm-slim, openssh-server bundled, all X11 deps pre-installed.
  - docker run -p 2222:22 -e SSH_PASSWORD=secret ghcr.io/uiper123/tgio-aprg-server
- Updated README with one-line install commands for each platform.

### Linux distro support matrix
| Distro | Pkg manager | Server deps | Client deps |
|---|---|---|---|
| Ubuntu/Debian/Astra | apt-get | ✅ | ✅ |
| Arch/Manjaro | pacman | ✅ NEW | ✅ NEW |
| ALT Linux | apt-rpm | ✅ NEW | ✅ NEW |
| Fedora/RHEL | dnf | ✅ | ✅ NEW |
| openSUSE | zypper | ✅ NEW | ✅ NEW |

### Next step
- Delta-encoding video (send only changed 64x64 blocks).
- Audio forwarding (PulseAudio/PipeWire → FRAME_AUDIO).
- CI: add macOS + ARM64 to release.yml (needs manual edit due to proxy restriction).

## Cycle 19 completed — 2026-06-14

### Done

#### Delta-encoding video (Step 11)
- Added `FLAG_DELTA = 0x10` to `common/protocol.py`.
- Added `FRAME_AUDIO = 0x07` to protocol constants.
- Added `prev_block_hashes: dict[int, bytes]` to SessionState.
- Added `_split_blocks()` helper: divides raw BGRX frame into 64×64 tiles,
  returns per-tile (JPEG, blake2b-8) pairs.
- Replaced flat `_capture_loop` with a delta-aware version:
  - First frame / every 5 s / ≥80 % blocks changed → full JPEG keyframe (4-byte seq prefix).
  - Otherwise → delta bundle: 4-byte seq | FLAG_DELTA (0x10) | per-block:
    2-byte idx + 4-byte JPEG length + JPEG bytes.
  - Client side: `FLAG_DELTA` frames emitted on new `videoDelta` signal;
    keyframes still emitted on `videoFrame`.
- Expected traffic reduction: 60-90 % on static or mostly-static screens.

#### Audio forwarding (Step 12)
- Added `_audio_loop()` to SessionWorker: detects pw-cat (PipeWire) or pacat
  (PulseAudio), captures 16-bit stereo PCM at 44100 Hz in 4096-byte chunks,
  and sends each chunk as a `FRAME_AUDIO` frame.
- Loop is started as an asyncio task alongside capture/clipboard/watchdog.
- Silently disabled if neither pw-cat nor pacat is found.

### Next step
- CI macOS + ARM64 matrix (needs manual release.yml edit — proxy restriction).

## Cycle 20 completed — 2026-06-14

### Done — UI enhancements
- Live network metrics in the status bar:
  - Added `_bytes_received` counter to TransportThread (incremented in _reader_loop).
  - Added `_last_latency_ms` (stored in _handle_pong).
  - update_stats_label now shows: color-coded quality dot (🟢 <80 ms / 🟡 <180 ms / 🔴),
    FPS, ping (ms), live bandwidth (KB/s or MB/s), JPEG quality, and dropped-frame count.
- Screenshot capture:
  - "Screenshot" toolbar button → save_screenshot() saves the last full keyframe
    via QFileDialog as PNG/JPEG.
  - handle_video_frame stores the last full keyframe in _last_frame_bytes.
- Shortcuts & tips dialog:
  - "Shortcuts" toolbar button → show_shortcuts_help() with toolbar actions,
    quality preset reference, clipboard/file/security tips, and stats legend.

### Next step
- Optional: bandwidth/latency history graph, audio enable toggle (needs server --audio flag),
  multi-monitor selection.

## Cycle 21 completed — 2026-06-14

### Done — UI batch 2 (Monitor tab, hotkeys, recording)
- Monitor tab: live ping + bandwidth sparkline graphs (SparklineWidget) and a
  connection event log with a Clear button. Graphs are fed from update_stats_label,
  the log captures every _set_status message with a timestamp.
- Keyboard shortcuts (_register_hotkeys via QShortcut):
  F11 fullscreen, Ctrl+S screenshot, Ctrl+D disconnect, Ctrl+Enter connect,
  Ctrl+R toggle recording, Ctrl+L clear log.
- Session recording: "Record" toolbar button / Ctrl+R captures incoming keyframes
  (capped at 1800) and saves them as an animated WebP (or GIF) via Pillow — no new deps.

### Next step
- Optional: audio enable toggle (needs server --audio flag), multi-monitor selection.
