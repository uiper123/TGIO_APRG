from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from remote_ssh_desktop.common.history import clear_history, latest_history, load_history, record_connection


def profile(host: str, username: str = "alice") -> dict:
    return {
        "host": host,
        "port": 2222,
        "username": username,
        "password": "secret",
        "key_passphrase": "hidden",
        "screen": "1280x720",
        "key_file": "~/.ssh/id_rsd",
    }


def test_history_records_sorts_limits_and_strips_secrets(tmp_path):
    path = tmp_path / "history.json"
    base = datetime(2026, 1, 1, tzinfo=UTC)

    record_connection("one", profile("one.example"), path, limit=2, now=base)
    record_connection("two", profile("two.example"), path, limit=2, now=base + timedelta(seconds=10))
    entries = record_connection("three", profile("three.example"), path, limit=2, now=base + timedelta(seconds=20))

    assert [entry["profile_name"] for entry in entries] == ["three", "two"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    saved_profile = raw["entries"][0]["profile"]
    assert saved_profile["screen"] == [1280, 720]
    assert "password" not in saved_profile
    assert "key_passphrase" not in saved_profile
    assert latest_history(path)["profile_name"] == "three"


def test_history_deduplicates_by_profile_and_target(tmp_path):
    path = tmp_path / "history.json"
    first = datetime(2026, 1, 1, tzinfo=UTC)
    second = first + timedelta(minutes=5)

    record_connection("prod", profile("prod.example"), path, now=first)
    record_connection("prod", profile("prod.example"), path, now=second)

    entries = load_history(path)
    assert len(entries) == 1
    assert entries[0]["connected_at"].startswith("2026-01-01T00:05:00")


def test_clear_history_leaves_empty_history_file(tmp_path):
    path = tmp_path / "history.json"
    record_connection("prod", profile("prod.example"), path)

    clear_history(path)

    assert load_history(path) == []
