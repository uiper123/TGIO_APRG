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

### Notes
- Cut the first release with `git tag -s v0.1.0 -m "v0.1.0" && git push origin v0.1.0`
