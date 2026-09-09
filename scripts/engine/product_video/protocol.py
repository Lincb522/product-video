"""Volcengine v3 binary frames; no request or response payload logging."""
from dataclasses import dataclass
import gzip
import json
import struct

from .common import VideoError

CONNECTION_EVENTS = {1, 2, 50, 51, 52}


def blob(value):
    return struct.pack(">I", len(value)) + value


def encode(event, payload=None, session_id=""):
    data = bytes([0x11, 0x14, 0x10, 0]) + struct.pack(">i", event)
    if event not in CONNECTION_EVENTS:
        data += blob(session_id.encode())
    return data + blob(json.dumps(payload or {}, ensure_ascii=False).encode())


@dataclass
class Message:
    kind: int
    event: int
    session_id: str
    payload: bytes
    error_code: int = 0


def decode(data):
    if not isinstance(data, bytes) or len(data) < 4:
        raise VideoError("TTS 返回了无效二进制帧。")
    version, header_size = data[0] >> 4, (data[0] & 15) * 4
    kind, flags, compression = data[1] >> 4, data[1] & 15, data[2] & 15
    if version != 1 or header_size < 4 or header_size > len(data) or compression not in (0, 1):
        raise VideoError("TTS 二进制帧版本或压缩方式不受支持。")
    pos = header_size

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(data):
            raise VideoError("TTS 返回的帧被截断。")
        value = data[pos:pos + n]
        pos += n
        return value

    def uint():
        return struct.unpack(">I", take(4))[0]

    def read_blob():
        return take(uint())

    error = uint() if kind == 15 else 0
    if kind != 15 and flags & 3 in (1, 3):
        take(4)
    event = uint() if flags & 4 else 0
    session = ""
    try:
        if flags & 4:
            if event not in CONNECTION_EVENTS:
                session = read_blob().decode()
            elif event in (50, 51, 52):
                read_blob()  # Connection ID is not needed outside the transport.
        payload = read_blob()
        if pos != len(data):
            raise VideoError("TTS 二进制帧存在未解析数据。")
        if compression:
            payload = gzip.decompress(payload)
    except (UnicodeError, OSError, EOFError):
        raise VideoError("TTS 帧内容无法解码。") from None
    return Message(kind, event, session, payload, error)
