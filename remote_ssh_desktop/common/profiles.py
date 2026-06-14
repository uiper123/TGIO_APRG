from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROFILE_SCHEMA_VERSION = 1
SENSITIVE_FIELDS = {"password", "key_passphrase"}
PROFILE_FIELDS = {
    "host",
    "port",
    "username",
    "key_file",
    "remote_command",
    "session_id",
    "screen",
    "fps",
    "quality",
    "persistent",
    "idle_timeout",
    "shared_folder",
    "known_hosts",
    "clipboard_enabled",
    "clipboard_max_bytes",
    "reconnect_enabled",
    "reconnect_attempts",
    "reconnect_delay",
    "proxy_jump",
}


def default_profiles_path() -> Path:
    override = os.environ.get("REMOTE_SSH_DESKTOP_PROFILES")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "remote-ssh-desktop" / "profiles.json"


def validate_profile_name(name: str) -> str:
    clean = " ".join(name.strip().split())
    if not clean:
        raise ValueError("profile name is required")
    if len(clean) > 80:
        raise ValueError("profile name must be at most 80 characters")
    return clean


def sanitize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in profile.items():
        if key in SENSITIVE_FIELDS or key not in PROFILE_FIELDS:
            continue
        if value is None:
            continue
        if key in {"port", "fps", "quality", "idle_timeout", "clipboard_max_bytes", "reconnect_attempts"}:
            clean[key] = int(value)
        elif key == "reconnect_delay":
            clean[key] = float(value)
        elif key in {"persistent", "clipboard_enabled", "reconnect_enabled"}:
            clean[key] = bool(value)
        elif key == "screen":
            if isinstance(value, str):
                parts = value.lower().replace(" ", "").split("x", 1)
                if len(parts) != 2:
                    raise ValueError("screen must look like 1920x1080")
                clean[key] = [int(parts[0]), int(parts[1])]
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                clean[key] = [int(value[0]), int(value[1])]
            else:
                raise ValueError("screen must be a two-item list or 1920x1080")
        else:
            clean[key] = str(value)
    return clean


def load_profiles(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    target = Path(path).expanduser() if path else default_profiles_path()
    if not target.exists():
        return {}
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("profiles file must contain a JSON object")
    if "profiles" in raw:
        raw_profiles = raw.get("profiles")
    else:
        raw_profiles = raw
    if not isinstance(raw_profiles, dict):
        raise ValueError("profiles must be a JSON object")
    profiles: dict[str, dict[str, Any]] = {}
    for name, profile in raw_profiles.items():
        if not isinstance(profile, dict):
            continue
        profiles[validate_profile_name(str(name))] = sanitize_profile(profile)
    return profiles


def save_profiles(profiles: dict[str, dict[str, Any]], path: str | Path | None = None) -> Path:
    target = Path(path).expanduser() if path else default_profiles_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": PROFILE_SCHEMA_VERSION,
        "profiles": {validate_profile_name(name): sanitize_profile(profile) for name, profile in sorted(profiles.items())},
    }
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def export_profiles(profiles: dict[str, dict[str, Any]], path: str | Path) -> Path:
    return save_profiles(profiles, path)


def import_profiles(source: str | Path, destination: str | Path | None = None) -> dict[str, dict[str, Any]]:
    imported = load_profiles(source)
    existing = load_profiles(destination)
    existing.update(imported)
    save_profiles(existing, destination)
    return existing


def import_ssh_config(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    target = Path(path).expanduser() if path else Path.home() / ".ssh" / "config"
    if not target.exists():
        return {}
    profiles: dict[str, dict[str, Any]] = {}
    current_hosts: list[str] = []
    current: dict[str, str] = {}

    def flush() -> None:
        nonlocal current_hosts, current
        if not current_hosts:
            current = {}
            return
        for alias in current_hosts:
            if any(ch in alias for ch in "*?"):
                continue
            profile = {
                "host": current.get("hostname", alias),
                "port": int(current.get("port", "22")),
                "username": current.get("user", ""),
                "key_file": current.get("identityfile", ""),
                "proxy_jump": current.get("proxyjump", ""),
            }
            profiles[validate_profile_name(alias)] = sanitize_profile(profile)
        current_hosts = []
        current = {}

    for raw_line in target.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if not parts:
            continue
        key = parts[0].lower()
        value = parts[1].strip() if len(parts) > 1 else ""
        if key == "host":
            flush()
            current_hosts = value.split()
        elif current_hosts and key in {"hostname", "user", "port", "identityfile", "proxyjump"}:
            current[key] = value
    flush()
    return profiles
