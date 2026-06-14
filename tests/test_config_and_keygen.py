from __future__ import annotations

import stat

import pytest

from remote_ssh_desktop.common.config import parse_screen
from remote_ssh_desktop.crypto.keygen import authorized_keys_helper, save_keypair
from remote_ssh_desktop.version import __version__


def test_parse_screen_rejects_invalid_values():
    assert parse_screen("1280x720") == (1280, 720)
    with pytest.raises(ValueError):
        parse_screen("319x240")
    with pytest.raises(ValueError):
        parse_screen("not-a-screen")


def test_keygen_writes_secure_ed25519_pair(tmp_path):
    private_path, public_path = save_keypair(tmp_path, "id_rsd", "ed25519")

    assert private_path.exists()
    assert public_path.exists()
    assert stat.S_IMODE(private_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(public_path.stat().st_mode) == 0o644
    assert public_path.read_text(encoding="utf-8").startswith("ssh-ed25519 ")
    assert "authorized_keys" in authorized_keys_helper(public_path)


def test_package_version_is_semver():
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
