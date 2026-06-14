from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from remote_ssh_desktop.common.profiles import sanitize_profile, validate_profile_name

HISTORY_SCHEMA_VERSION = 1
DEFAULT_HISTORY_LIMIT = 20


def default_history_path() -> Path:
    override = os.environ.get("REMOTE_SSH_DESKTOP_HISTORY")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "remote-ssh-desktop" / "history.json"


def _parse_time(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.fromtimestamp(0, UTC)
    return datetime.fromtimestamp(0, UTC)


def _timestamp(now: datetime | None = None) -> str:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _entry_key(entry: dict[str, Any]) -> tuple[str, str, int, str]:
    profile = entry.get("profile") if isinstance(entry.get("profile"), dict) else {}
    profile_name = str(entry.get("profile_name", ""))
    return (
        profile_name,
        str(profile.get("host", "")),
        int(profile.get("port", 22) or 22),
        str(profile.get("username", "")),
    )


def connection_label(entry: dict[str, Any]) -> str:
    profile = entry.get("profile") if isinstance(entry.get("profile"), dict) else {}
    profile_name = str(entry.get("profile_name", "")).strip()
    user = str(profile.get("username", "")).strip()
    host = str(profile.get("host", "")).strip()
    port = int(profile.get("port", 22) or 22)
    prefix = f"{profile_name} — " if profile_name else ""
    target = f"{user + '@' if user else ''}{host or 'unknown'}:{port}"
    when = str(entry.get("connected_at", ""))
    return f"{prefix}{target} · {when}"


def sanitize_history_entry(entry: dict[str, Any]) -> dict[str, Any]:
    profile = sanitize_profile(entry.get("profile", {}) if isinstance(entry.get("profile"), dict) else entry)
    raw_name = str(entry.get("profile_name", "")).strip()
    profile_name = validate_profile_name(raw_name) if raw_name else ""
    connected_at = _timestamp(_parse_time(entry.get("connected_at")))
    return {"profile_name": profile_name, "connected_at": connected_at, "profile": profile}


def load_history(path: str | Path | None = None) -> list[dict[str, Any]]:
    target = Path(path).expanduser() if path else default_history_path()
    if not target.exists():
        return []
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("history file must contain a JSON object")
    entries = raw.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("history entries must be a list")
    clean = [sanitize_history_entry(entry) for entry in entries if isinstance(entry, dict)]
    clean.sort(key=lambda entry: _parse_time(entry.get("connected_at")), reverse=True)
    return clean


def save_history(entries: list[dict[str, Any]], path: str | Path | None = None, limit: int = DEFAULT_HISTORY_LIMIT) -> Path:
    target = Path(path).expanduser() if path else default_history_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    clean = [sanitize_history_entry(entry) for entry in entries]
    clean.sort(key=lambda entry: _parse_time(entry.get("connected_at")), reverse=True)
    payload = {"version": HISTORY_SCHEMA_VERSION, "entries": clean[: max(0, limit)]}
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def record_connection(
    profile_name: str,
    profile: dict[str, Any],
    path: str | Path | None = None,
    limit: int = DEFAULT_HISTORY_LIMIT,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    entry = sanitize_history_entry({"profile_name": profile_name, "profile": profile, "connected_at": _timestamp(now)})
    existing = load_history(path)
    key = _entry_key(entry)
    merged = [entry] + [old for old in existing if _entry_key(old) != key]
    save_history(merged, path, limit=limit)
    return load_history(path)


def latest_history(path: str | Path | None = None) -> dict[str, Any] | None:
    entries = load_history(path)
    return entries[0] if entries else None


def clear_history(path: str | Path | None = None) -> Path:
    return save_history([], path)
