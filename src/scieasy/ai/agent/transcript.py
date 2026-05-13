"""Append-only transcript writer for stream-json snapshots.

Each chat session writes a write-through mirror of every canonical
:class:`scieasy.ai.agent.provider.AgentEvent` to a JSONL file under
``{project_dir}/.scieasy/sessions/<chat_id>/transcript.jsonl`` (spec
§3 D7.1). The mirror makes the project directory portable / shareable
without depending on the upstream CLI's home-directory transcript.

Implementation notes (spec §5 T-ECA-106):

* The file is opened in append mode (``"a"``) so concurrent readers
  (frontend tail, ``jq``) see consistent lines.
* Each :meth:`write_event` call writes exactly one JSON object plus a
  trailing ``\\n`` and flushes the buffer.
* Write failures (full disk, read-only mount, missing dir we couldn't
  create) log a WARNING and are swallowed — the chat must keep working
  even when the transcript persistence layer fails. The first failure
  is logged loudly; subsequent failures from the same writer drop to
  DEBUG to avoid log spam.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
from pathlib import Path
from typing import IO, Any

from scieasy.ai.agent.provider import AgentEvent

logger = logging.getLogger(__name__)


def _serialise_event(event: AgentEvent) -> dict[str, Any]:
    """Return a JSON-serialisable dict for ``event``.

    Falls back to ``{kind, raw}`` if the event cannot be ``asdict``-ed
    (no known case in the current taxonomy, but defensive).
    """
    if dataclasses.is_dataclass(event):
        try:
            return dataclasses.asdict(event)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass
    return {"kind": event.kind, "raw": event.raw}


class TranscriptWriter:
    """Append-only JSONL writer for one chat session's event stream.

    Invariants
    ----------
    * One file per (project, chat_id); the file is opened in append
      mode so concurrent readers see consistent lines.
    * Each :meth:`write_event` call writes exactly one valid JSON
      object and a trailing newline.
    * Write failures log WARNING and are swallowed; they do not
      propagate. The streaming chat surface keeps working even when
      the transcript disk is full or read-only.
    """

    def __init__(self, path: Path) -> None:
        """Construct a writer bound to ``path``.

        Parameters
        ----------
        path
            Absolute path to the ``transcript.jsonl`` file. Parent
            directories are created lazily on first write.
        """
        self.path: Path = path
        self._fh: IO[str] | None = None
        self._failed: bool = False
        self._closed: bool = False

    def _ensure_open(self) -> None:
        """Lazily create the parent directory and open the append-mode handle."""
        if self._fh is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    async def write_event(self, event: AgentEvent) -> None:
        """Append one event to the transcript and flush.

        Failures are swallowed; they never propagate.
        """
        if self._closed:
            return
        try:
            self._ensure_open()
            assert self._fh is not None
            line = json.dumps(_serialise_event(event), ensure_ascii=False)
            self._fh.write(line + "\n")
            self._fh.flush()
        except OSError as exc:
            if not self._failed:
                logger.warning(
                    "TranscriptWriter.write_event: write failed for %s: %s — disabling further attempts",
                    self.path,
                    exc,
                )
                self._failed = True
                # Mark effectively closed so we don't retry on every event.
                self._closed = True
                if self._fh is not None:
                    with contextlib.suppress(OSError):
                        self._fh.close()
                    self._fh = None
            else:  # pragma: no cover - first failure closes the writer
                logger.debug("TranscriptWriter: repeat write failure for %s: %s", self.path, exc)

    def close(self) -> None:
        """Flush + close the underlying file handle.

        Idempotent. Safe to call even if the writer never opened
        because of a permission error.
        """
        if self._closed:
            self._closed = True
            return
        self._closed = True
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            except OSError as exc:  # pragma: no cover
                logger.warning("TranscriptWriter.close: %s", exc)
            self._fh = None
