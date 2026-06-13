from __future__ import annotations

import asyncio
import json
import struct
from dataclasses import dataclass
from typing import Any

HEADER = struct.Struct(">BBI")
MAX_PAYLOAD_SIZE = 128 * 1024 * 1024

FRAME_CONTROL = 0x01
FRAME_VIDEO = 0x02
FRAME_INPUT = 0x03
FRAME_CLIPBOARD = 0x04
FRAME_FILE = 0x05
FRAME_STATS = 0x06

FLAG_JSON = 0x01
FLAG_KEYFRAME = 0x02
FLAG_COMPRESSED = 0x04
FLAG_RAW = 0x08

PROTOCOL_VERSION = 1
SUPPORTED_CODECS = {"jpeg"}


@dataclass(slots=True)
class Frame:
    kind: int
    flags: int
    payload: bytes

    @property
    def is_json(self) -> bool:
        return bool(self.flags & FLAG_JSON)

    def json(self) -> Any:
        return decode_message(self.payload)


def encode_message(message: Any) -> bytes:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def decode_message(payload: bytes) -> Any:
    return json.loads(payload.decode("utf-8"))


def pack_frame(kind: int, payload: bytes | str | dict[str, Any] | list[Any], flags: int = 0) -> bytes:
    if not 0 <= kind <= 0xFF:
        raise ValueError("frame kind must fit into one byte")
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    elif isinstance(payload, (dict, list)):
        payload = encode_message(payload)
        flags |= FLAG_JSON
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes, string, list, or dict")
    body = bytes(payload)
    if len(body) > MAX_PAYLOAD_SIZE:
        raise ValueError(f"payload is too large: {len(body)} bytes")
    return HEADER.pack(kind, flags, len(body)) + body


async def read_exactly(reader: asyncio.StreamReader, size: int) -> bytes:
    data = await reader.readexactly(size)
    if len(data) != size:
        raise EOFError
    return data


async def read_frame(reader: asyncio.StreamReader, max_payload_size: int = MAX_PAYLOAD_SIZE) -> Frame:
    header = await read_exactly(reader, HEADER.size)
    kind, flags, length = HEADER.unpack(header)
    if length > max_payload_size:
        raise ValueError(f"frame payload exceeds limit: {length} > {max_payload_size}")
    payload = await read_exactly(reader, length) if length else b""
    return Frame(kind=kind, flags=flags, payload=payload)


def unpack_frame(raw: bytes, max_payload_size: int = MAX_PAYLOAD_SIZE) -> Frame:
    if len(raw) < HEADER.size:
        raise ValueError("frame too short")
    kind, flags, length = HEADER.unpack(raw[: HEADER.size])
    if length > max_payload_size:
        raise ValueError(f"frame payload exceeds limit: {length} > {max_payload_size}")
    payload = raw[HEADER.size : HEADER.size + length]
    if len(payload) != length:
        raise ValueError("truncated frame")
    return Frame(kind=kind, flags=flags, payload=payload)


def control_error(code: str, message: str) -> dict[str, str]:
    return {"t": "error", "code": code, "message": message}
