from __future__ import annotations

import json

from remote_ssh_desktop.common.profiles import (
    export_profiles,
    import_profiles,
    import_ssh_config,
    load_profiles,
    save_profiles,
    sanitize_profile,
)


def test_profiles_roundtrip_sanitizes_sensitive_fields(tmp_path):
    path = tmp_path / "profiles.json"
    profiles = {
        "prod": {
            "host": "example.com",
            "port": "2222",
            "username": "alice",
            "password": "secret",
            "key_passphrase": "hidden",
            "screen": "1280x720",
            "persistent": "yes",
            "quality_preset": "Mobile",
            "proxy_jump": "bastion",
            "unknown": "ignored",
        }
    }

    save_profiles(profiles, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    saved = raw["profiles"]["prod"]

    assert saved["port"] == 2222
    assert saved["screen"] == [1280, 720]
    assert saved["proxy_jump"] == "bastion"
    assert saved["quality_preset"] == "Mobile"
    assert "password" not in saved
    assert "key_passphrase" not in saved
    assert "unknown" not in saved
    assert load_profiles(path)["prod"] == saved


def test_import_export_profiles_merges(tmp_path):
    destination = tmp_path / "profiles.json"
    source = tmp_path / "import.json"
    save_profiles({"old": {"host": "old.example"}}, destination)
    export_profiles({"new": {"host": "new.example", "port": 2200}}, source)

    merged = import_profiles(source, destination)

    assert set(merged) == {"old", "new"}
    assert load_profiles(destination)["new"]["port"] == 2200


def test_import_ssh_config_reads_hosts_and_proxyjump(tmp_path):
    ssh_config = tmp_path / "config"
    ssh_config.write_text(
        """
Host bastion
  HostName bastion.example.com
  User jump
  Port 2201
  IdentityFile ~/.ssh/id_jump

Host prod *.wildcard
  HostName 10.0.0.5
  User alice
  Port 2222
  IdentityFile ~/.ssh/id_prod
  ProxyJump bastion
""".strip(),
        encoding="utf-8",
    )

    profiles = import_ssh_config(ssh_config)

    assert profiles["bastion"]["host"] == "bastion.example.com"
    assert profiles["bastion"]["username"] == "jump"
    assert profiles["prod"]["host"] == "10.0.0.5"
    assert profiles["prod"]["port"] == 2222
    assert profiles["prod"]["key_file"] == "~/.ssh/id_prod"
    assert profiles["prod"]["proxy_jump"] == "bastion"
    assert "*.wildcard" not in profiles


def test_sanitize_profile_rejects_bad_screen():
    try:
        sanitize_profile({"screen": "bad"})
    except ValueError as exc:
        assert "screen" in str(exc)
    else:
        raise AssertionError("bad screen should fail")
