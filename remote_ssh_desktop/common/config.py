from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class AppConfig:
    host: str = ""
    port: int = 22
    username: str = ""
    key_file: str = ""
    known_hosts: str = ""
    session_id: str = ""
    screen: str = "1920x1080"
    fps: int = 18
    quality: int = 80
    persistent: bool = False
    idle_timeout: int = 300
    shared_folder: str = "~/RemoteShared"
    remote_command: str = "python -m remote_ssh_desktop.server.main --proxy --session-id {session_id} --screen {screen} --fps {fps} --quality {quality} --idle-timeout {idle_timeout} {persistent_flag} --shared-folder {shared_folder}"
    clipboard_enabled: bool = True
    clipboard_max_bytes: int = 1_000_000
    reconnect: bool = True
    reconnect_attempts: int = 5
    reconnect_delay_sec: float = 2.0


def default_config_path() -> Path:
    return Path.home() / ".config" / "remote-ssh-desktop" / "config.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def load_app_config(path: Path | None = None) -> AppConfig:
    data = load_json(path or default_config_path())
    known = {field: value for field, value in data.items() if field in AppConfig.__dataclass_fields__}
    return AppConfig(**known)


def save_app_config(config: AppConfig, path: Path | None = None) -> None:
    save_json(path or default_config_path(), asdict(config))


def parse_screen(value: str) -> tuple[int, int]:
    width, height = value.lower().replace(" ", "").split("x", 1)
    w, h = int(width), int(height)
    if w < 320 or h < 240:
        raise ValueError("screen size is too small")
    return w, h
