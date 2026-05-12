"""Append-only transcript writer for stream-json snapshots.

Each chat session writes a write-through mirror of every canonical
:class:`scieasy.ai.agent.provider.AgentEvent` to a JSONL file under
``{project_dir}/.scieasy/sessions/<chat_id>/transcript.jsonl`` (spec
§3 D7.1). The mirror makes the project directory portable / shareable
without depending on the upstream CLI's home-directory transcript.

Phase 1 ships the stub; T-ECA-106 implements append-mode opening,
per-event flush, and the best-effort write-failure WARNING path.
"""

from __future__ import annotations

from pathlib import Path

from scieasy.ai.agent.provider import AgentEvent


class TranscriptWriter:
    """Append-only JSONL writer for one chat session's event stream.

    Invariants (enforced by the T-ECA-106 implementation):

    * One file per (project, chat_id); the file is opened in append
      mode so concurrent readers (jq, frontend tail) see consistent
      lines.
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

    async def write_event(self, event: AgentEvent) -> None:
        """Append one event to the transcript and flush.

        Parameters
        ----------
        event
            Canonical event to mirror.

        Raises
        ------
        NotImplementedError
            Always, in Phase 1. Implementation lands in T-ECA-106.
        """
        raise NotImplementedError("TranscriptWriter.write_event is implemented in T-ECA-106")

    def close(self) -> None:
        """Flush + close the underlying file handle.

        Raises
        ------
        NotImplementedError
            Always, in Phase 1. Implementation lands in T-ECA-106.
        """
        raise NotImplementedError("TranscriptWriter.close is implemented in T-ECA-106")
