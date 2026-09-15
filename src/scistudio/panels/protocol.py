"""Length-prefixed frames for the panel-process control channel."""
# Length-prefixed frames for the panel-process control channel (ADR-054 §10).
#
# The backend and a panel's ``panel.py`` subprocess exchange messages over a
# dedicated pipe that user code's ``print`` cannot reach: the bootstrap saves the
# process's original stdin/stdout as the request/response channel and redirects
# fd 0/1/2 to the per-context log before any author code runs (see
# :mod:`scistudio.panels.bootstrap`). No network port is ever opened.
#
# A frame is a 4-byte big-endian header length, that many bytes of UTF-8 JSON,
# and — only when the header carries ``"nbytes"`` — exactly ``nbytes`` raw bytes
# that follow. The raw tail carries a NumPy array's buffer so a call that returns
# an array is delivered to the page as ``application/octet-stream`` with dtype and
# shape, mirroring the binary read path of ``adr-054-panels`` FR-012.

from __future__ import annotations

import json
import struct
from typing import Any, BinaryIO

# A single header frame is bounded so a malformed or hostile length cannot make
# the reader allocate without limit; array payloads use the raw ``nbytes`` tail.
MAX_HEADER_BYTES = 1 * 1024 * 1024
_LEN = struct.Struct(">I")


class ProtocolError(Exception):
    """The peer closed the pipe or sent a frame the reader cannot parse."""


def send_frame(stream: BinaryIO, header: dict[str, Any], payload: bytes = b"") -> None:
    """Write one frame; ``payload`` is the raw tail declared by ``header['nbytes']``."""
    if payload:
        header = {**header, "nbytes": len(payload)}
    body = json.dumps(header, allow_nan=False).encode("utf-8")
    if len(body) > MAX_HEADER_BYTES:
        raise ProtocolError("panel frame header exceeds its byte budget")
    stream.write(_LEN.pack(len(body)))
    stream.write(body)
    if payload:
        stream.write(payload)
    stream.flush()


def _read_exactly(stream: BinaryIO, count: int) -> bytes:
    """Read exactly *count* bytes or raise; EOF means the peer is gone."""
    chunks: list[bytes] = []
    remaining = count
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            raise ProtocolError("panel pipe closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def recv_frame(stream: BinaryIO, *, max_payload: int) -> tuple[dict[str, Any], bytes]:
    """Read one frame; refuse a raw tail larger than *max_payload*."""
    length = _LEN.unpack(_read_exactly(stream, _LEN.size))[0]
    if length > MAX_HEADER_BYTES:
        raise ProtocolError("panel frame header exceeds its byte budget")
    header = json.loads(_read_exactly(stream, length).decode("utf-8"))
    if not isinstance(header, dict):
        raise ProtocolError("panel frame header must be a JSON object")
    nbytes = header.get("nbytes")
    if nbytes is None:
        return header, b""
    if not isinstance(nbytes, int) or nbytes < 0:
        raise ProtocolError("panel frame nbytes must be a non-negative integer")
    if nbytes > max_payload:
        raise ProtocolError("panel frame payload exceeds its byte budget")
    return header, _read_exactly(stream, nbytes)


__all__ = ["MAX_HEADER_BYTES", "ProtocolError", "recv_frame", "send_frame"]
