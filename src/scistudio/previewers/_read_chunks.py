"""Byte-oriented text windows and validated collection cursors."""

from __future__ import annotations

import base64
import codecs
import json
from pathlib import Path


def text_window(path: Path, *, offset: int, length: int) -> tuple[str, int | None, int]:
    """Read at most length bytes, carrying a split UTF-8 suffix to the next read."""
    if offset < 0 or length <= 0:
        raise ValueError("Text offset must be nonnegative and length must be positive")
    total = path.stat().st_size
    if offset > total:
        raise ValueError("Text offset exceeds file size")
    with path.open("rb") as stream:
        stream.seek(offset)
        raw = stream.read(length)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    content = decoder.decode(raw, final=offset + len(raw) >= total)
    pending, _ = decoder.getstate()
    consumed = len(raw) - len(pending)
    if raw and not consumed:
        raise ValueError("Text length must fit the next UTF-8 character (up to 4 bytes)")
    end = offset + consumed
    return content, end if end < total else None, total


def collection_offset(cursor: str | None, count: int) -> int:
    if cursor is None:
        return 0
    try:
        if len(cursor) > 128:
            raise ValueError("cursor too long")
        raw = json.loads(base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True))
        if (
            not isinstance(raw, list)
            or len(raw) != 3
            or raw[0] != 1
            or type(raw[1]) is not int
            or type(raw[2]) is not int
            or raw[1] != count
            or not 0 <= raw[2] <= count
        ):
            raise ValueError("invalid cursor payload")
        return int(raw[2])
    except (ValueError, TypeError, UnicodeError) as error:
        raise ValueError("Invalid or stale collection cursor") from error


def next_collection_cursor(offset: int, count: int) -> str | None:
    if offset >= count:
        return None
    return base64.urlsafe_b64encode(json.dumps([1, count, offset], separators=(",", ":")).encode()).decode()
