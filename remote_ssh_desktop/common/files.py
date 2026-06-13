from __future__ import annotations

from pathlib import PurePosixPath


def normalize_remote_rel(path: str) -> str:
    candidate = PurePosixPath("/" + (path or ".").replace("\\", "/"))
    parts: list[str] = []
    for part in candidate.parts:
        if part in ("/", "", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def join_remote_jail(root: str, relative_path: str = "") -> str:
    root_path = PurePosixPath(root.rstrip("/") or "/")
    rel = normalize_remote_rel(relative_path)
    return str(root_path / rel) if rel else str(root_path)
