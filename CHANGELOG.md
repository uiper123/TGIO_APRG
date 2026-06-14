# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/) and the
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Multi-platform CI release pipeline (Linux/Windows/macOS x86_64+arm64)
- PyInstaller spec files for client (Linux/Windows/macOS) and server (Linux)
- PyPI publish workflow for tagged releases
- SHA-256 checksums for all release artifacts
- Auto-generated release notes with changelog bullets and artifact table
- Release checklist issue template
- SFTP uploads now create missing remote parent directories before resuming/writing files.
- Regression coverage for recursive SFTP parent-directory creation.
- Xvfb e2e coverage for persistent session list/resume/stop and non-persistent idle cleanup.
- Connection profile manager with searchable saved profiles, JSON import/export, and non-secret profile storage.
- `~/.ssh/config` import for simple `Host` entries with `HostName`, `User`, `Port`, `IdentityFile`, and `ProxyJump`.
- ProxyJump/bastion support via the client `ProxyJump` field.
- Client CLI `--profile NAME` and `--connect` for shortcut/script launches.
- Quick Connect and recent-connection history with one-click reconnect, history clearing, capped non-secret storage, and CLI `--last`/`--recent`.
- Client/server self-test diagnostics for Python modules, Linux X11 tools, Qt display environment, JSON/text export, and client Diagnostics tab.
- Live localhost OpenSSH e2e coverage for the Qt transport, remote X11 session startup, SFTP upload/download, and clipboard propagation.
- Quality presets (`LAN`, `WAN`, `Mobile`, `Custom`) for FPS/JPEG settings with profile/history persistence and live server updates.
- `New Window` client action for multiple simultaneous connections, preloading the selected profile in the new client instance.
- Active connection label with target/session id and uptime in the Desktop status area.

### Changed
- Server proxy and clipboard loops now log disconnect/clipboard failures instead of silently swallowing them.
- Session listing/limits now ignore stale zombie worker states, and `--stop-session` waits for cleanup before returning.

### Fixed
- Reconnect/resume no longer consumes the worker Unix socket with a health-check probe before the real proxy bridge connects.
- Client remote process streams are now opened in binary mode so framed protocol bytes survive AsyncSSH stdio transport unchanged.

### Notes
- Cut the first release with `git tag -s v0.1.0 -m "v0.1.0" && git push origin v0.1.0`
