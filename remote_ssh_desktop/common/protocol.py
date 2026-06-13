from __future__ import annotations

import asyncio
import json
import struct
from dataclasses import dataclass
from typing import Any

MAGIC = b"RDS1"
HEADER = struct.Struct(">4sBBI")

FRAME_CONTROL = 1
FRAME_VIDEO = 2
FRAME_INPUT = 3
FRAME_CLIPBOARD = 4
FRAME_FILE = 5
FRAME_STATS = 6

FLAG_JSON = 1
FLAG_RAW = 2


@dataclass(slots=True)
class Frame:
    kind: int
    flags: int
    payload: bytes


def encode_message(message: Any) -> bytes:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def decode_message(payload: bytes) -> Any:
    return json.loads(payload.decode("utf-8"))


def pack_frame(kind: int, payload: bytes | str | dict[str, Any] | list[Any], flags: int = 0) -> bytes:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    elif isinstance(payload, (dict, list)):
        payload = encode_message(payload)
        flags |= FLAG_JSON
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes, string, list, or dict")
    body = bytes(payload)
    return HEADER.pack(MAGIC, kind, flags, len(body)) + body


async def read_exactly(reader: asyncio.StreamReader, size: int) -> bytes:
    data = await reader.readexactly(size)
    if len(data) != size:
        raise EOFError
    return data


async def read_frame(reader: asyncio.StreamReader) -> Frame:
    header = await read_exactly(reader, HEADER.size)
    magic, kind, flags, length = HEADER.unpack(header)
    if magic != MAGIC:
        raise ValueError("bad frame magic")
    payload = await read_exactly(reader, length) if length else b""
    return Frame(kind=kind, flags=flags, payload=payload)


def unpack_frame(raw: bytes) -> Frame:
    if len(raw) < HEADER.size:
        raise ValueError("frame too short")
    magic, kind, flags, length = HEADER.unpack(raw[: HEADER.size])
    if magic != MAGIC:
        raise ValueError("bad frame magic")
    payload = raw[HEADER.size : HEADER.size + length]
    if len(payload) != length:
        raise ValueError("truncated frame")
    return Frame(kind=kind, flags=flags, payload=payload)
