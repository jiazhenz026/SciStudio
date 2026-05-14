"""RunDir — per-run coordination directory for AI Block (skeleton).

ADR-035 §3.2, §3.4. The directory at ``{project}/.scieasy/ai-block-runs/{run_id}/``
holds the manifest.json, transcript copy, and completion-signal scratch files
for one AI Block run.

**This is NOT a sandbox.** The agent runs with the project directory as cwd
and full filesystem access (ADR-035 §3.2, §3.7). The run dir exists only to
hold lineage / coordination artifacts. The agent is free to read and write
anywhere else the user has access.

Skeleton invariants (per skeleton-agent.md):
    * Every method body raises ``NotImplementedError``.
    * Each one is preceded by a docstring + structured implementation plan.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scieasy.blocks.base.ports import OutputPort

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Manifest schema reference (ADR-035 §3.4)
#
# {
#   "block": {
#     "name": "extract_metadata",
#     "type": "AIBlock",
#     "run_id": "20260513-220045-extract_metadata-abc1234"
#   },
#   "user_prompt": "...",
#   "inputs": {
#     "<port_name>": [
#       {
#         "path": "/abs/path/to/file.czi",
#         "type_chain": ["Artifact", "DataObject"],
#         "meta": {"mime_type": "application/octet-stream"}
#       },
#       ...
#     ]
#   },
#   "outputs": {
#     "<port_name>": {
#       "expected_path": "./results/metadata.csv",
#       "expected_type": "DataFrame",
#       "type_chain": ["DataFrame", "DataObject"],
#       "description": "..."
#     }
#   },
#   "completion": {
#     "primary":   "Call mcp__scieasy__finish_ai_block(...)",
#     "fallback":  "Or write all expected_path files; the watcher will detect them.",
#     "deadline":  "<ISO-8601 UTC>"
#   }
# }
#
# Layout under {project}/.scieasy/ai-block-runs/{run_id}/:
#   manifest.json       — written before agent spawn (this module)
#   transcript.log      — copy of the PTY tab transcript (written on close)
#   signals/            — completion-signal scratch files
#     finish_ai_block.json    — written by the MCP tool (§3.5 path a)
#     mark_done.json          — written by the engine on user-button (§3.5 path c)
# ---------------------------------------------------------------------------


class RunDir:
    """Per-run coordination directory for an AI Block run.

    Owns the lifecycle of ``{project}/.scieasy/ai-block-runs/{run_id}/``:
    creates it, writes the manifest, exposes paths for completion-signal
    files, copies the transcript on close. Does NOT enforce any access
    control on what the agent can do outside this dir — see module-level
    docstring.

    Implementation plan (per ADR-035 §3.2, §3.4):
        * Constructor: take ``project_dir: Path`` + ``run_id: str``,
          compute ``self.path = project_dir / ".scieasy" / "ai-block-runs" / run_id``.
        * :meth:`create()`: ``mkdir(parents=True, exist_ok=False)``;
          create ``signals/`` subdir.
        * :meth:`write_manifest()`: build the dict per ADR-035 §3.4,
          write atomically (tempfile + rename in same directory).
        * :meth:`mcp_signal_path()` / :meth:`mark_done_signal_path()`:
          return absolute paths under ``signals/`` for the watcher.
        * :meth:`copy_transcript()`: copy a transcript log into the dir.

    References:
        ADR-035 §3.2 (lineage/coordination role),
        ADR-035 §3.4 (manifest schema),
        ADR-035 §3.5 (completion signal file locations).
    """

    def __init__(self, project_dir: Path, run_id: str) -> None:
        """Initialize the run-dir handle.

        Implementation plan:
            1. Store ``self.project_dir = project_dir``, ``self.run_id = run_id``.
            2. Compute ``self.path = project_dir / ".scieasy" / "ai-block-runs" / run_id``.
            3. Do NOT create the directory yet — :meth:`create` is explicit.

        Edge cases:
            * ``run_id`` contains path separators → ``ValueError``.
            * ``project_dir`` does not exist → defer; :meth:`create` will fail.

        Test plan:
            * test_init_computes_path_correctly
            * test_init_rejects_run_id_with_separators

        References: ADR-035 §3.4
        """
        raise NotImplementedError("see comment block above")

    def create(self) -> None:
        """Create the run dir and ``signals/`` subdir on disk.

        Implementation plan:
            1. ``self.path.mkdir(parents=True, exist_ok=False)`` — fail if
               run_id collides (run_id encodes timestamp + nonce so this
               should never happen; collision = bug).
            2. ``(self.path / "signals").mkdir(exist_ok=True)``.

        Edge cases:
            * Path already exists → ``FileExistsError``. Caller chooses
              whether to retry with a fresh run_id or escalate.
            * Project dir not writable → ``PermissionError``. Caller surfaces
              as ERROR with actionable message.

        Test plan:
            * test_create_makes_dir_and_signals_subdir
            * test_create_raises_on_collision

        References: ADR-035 §3.2
        """
        raise NotImplementedError("see comment block above")

    def write_manifest(
        self,
        block_name: str,
        block_type: str,
        user_prompt: str,
        inputs: dict[str, list[Any]],
        outputs: list[OutputPort],
        deadline_iso: str,
    ) -> Path:
        """Write ``manifest.json`` per the schema in ADR-035 §3.4.

        Returns the absolute path to the written manifest (suitable for
        injection into the agent's initial prompt).

        Implementation plan:
            1. Build the dict shape shown in the module-level comment block
               (and the schema in ADR-035 §3.4).
            2. For each input port, iterate the Collection items and emit
               ``{"path": <abs path>, "type_chain": [...], "meta": {...}}``.
               **Paths are recorded verbatim** (ADR-035 §3.4) — no symlinking,
               no rewriting. If the input is in-memory only (no
               ``storage_ref``), materialize first via the existing
               ``DataObject.to_storage_ref()`` path.
            3. For each output port, emit ``expected_path`` (defaulting to
               ``./{block_name}_outputs/{port}.{ext}`` per §3.3),
               ``expected_type``, ``type_chain``, ``description``.
            4. Add ``completion`` block with the deadline and the standard
               instructional strings from ADR-035 §3.4.
            5. Write atomically: ``json.dumps`` to a tempfile in the same
               directory, ``os.replace()`` to ``manifest.json``.

        Edge cases:
            * Input has no ``storage_ref`` → materialize via ``to_memory()``
              + ``write_to_storage()``. If materialization fails, raise
              the original exception (caller handles).
            * Output port has no ``expected_path`` → apply default per §3.3.
            * ``inputs[port_name]`` is empty list → emit ``"inputs": {"port_name": []}``
              (the agent should still see the port declaration).

        Test plan:
            * test_write_manifest_basic_shape (one input, one output, JSON
              matches ADR §3.4 example)
            * test_write_manifest_records_paths_verbatim (no rewriting)
            * test_write_manifest_atomic (kill mid-write — file is old or
              new, never partial)
            * test_write_manifest_inmemory_input_triggers_materialization
            * test_write_manifest_default_expected_path

        References:
            ADR-035 §3.4 (schema), §3.3 (default expected_path),
            src/scieasy/blocks/app/bridge.py:31-142 (similar atomic-write pattern)
        """
        raise NotImplementedError("see comment block above")

    def mcp_signal_path(self) -> Path:
        """Return the absolute path the MCP tool writes to on
        ``finish_ai_block``.

        Implementation plan:
            Return ``self.path / "signals" / "finish_ai_block.json"``.
            The MCP tool writes ``{"outputs": {...}}`` to this path
            atomically; the :class:`CompletionWatcher` polls for its
            existence (see ``completion.py`` and ADR-035 §3.5 path a).

        Test plan:
            * test_mcp_signal_path_under_signals_dir

        References: ADR-035 §3.5 path (a)
        """
        raise NotImplementedError("see comment block above")

    def mark_done_signal_path(self) -> Path:
        """Return the absolute path the engine writes to on user "Mark done".

        Implementation plan:
            Return ``self.path / "signals" / "mark_done.json"``.
            The engine writes ``{"timestamp": <iso>}`` when the user clicks
            the "Mark done" button in the AI Block tab header (ADR-035 §3.5
            path c). The :class:`CompletionWatcher` polls for its existence.

        Test plan:
            * test_mark_done_signal_path_under_signals_dir

        References: ADR-035 §3.5 path (c)
        """
        raise NotImplementedError("see comment block above")

    def copy_transcript(self, source: Path) -> Path:
        """Copy the PTY tab's transcript log into the run dir.

        Called by the engine on tab close (success, error, or cancel) to
        preserve the conversation for lineage / post-mortem (ADR-035 §6.1).

        Implementation plan:
            1. Validate ``source`` exists and is a regular file.
            2. ``shutil.copy2(source, self.path / "transcript.log")``.
            3. Return the destination path.

        Edge cases:
            * Source missing → log warning + return ``self.path / "transcript.log"``
              (no copy; lineage is best-effort, not load-bearing).
            * Disk full → propagate ``OSError`` to caller.

        Test plan:
            * test_copy_transcript_basic
            * test_copy_transcript_missing_source_logs_warning

        References: ADR-035 §6.1 "lineage / archived alongside the manifest"
        """
        raise NotImplementedError("see comment block above")
