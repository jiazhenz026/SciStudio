"""RunDir — per-run coordination directory for an AI Block.

Each AI Block execution gets its own directory under
``{project}/.scistudio/ai-block-runs/{block_execution_id}/`` that holds the
manifest the agent reads, the completion-signal files, and a copy of the
terminal transcript.

This is **not** a sandbox. The agent runs with the project directory as its
working directory and full filesystem access; this directory only holds the
coordination and lineage files for one run. The agent is free to read and
write anywhere else the user can.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scistudio.blocks.base.ports import OutputPort

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Manifest schema reference (ADR-035 §3.4)
#
# {
#   "block": {
#     "name": "extract_metadata",
#     "type": "AIBlock",
#     "run_id": "20260513-220045-extract_metadata-abc1234"
#                # ^ kept as ``run_id`` to preserve the ADR-035 §3.4
#                # public schema; the Python identifier was renamed to
#                # ``block_execution_id`` per ADR-038 §5.2.
#   },
#   "user_prompt": "...",
#   "inputs": {
#     "<port_name>": [
#       {"path": "/abs/path/to/file.czi",
#        "type_chain": ["Artifact", "DataObject"],
#        "meta": {"mime_type": "application/octet-stream"}},
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
#     "primary":   "Call mcp__scistudio__finish_ai_block(...)",
#     "fallback":  "Or write all expected_path files; the watcher will detect them.",
#     "deadline":  "<ISO-8601 UTC>"
#   }
# }
# ---------------------------------------------------------------------------


def _type_chain(cls: type) -> list[str]:
    """Return ``[<cls>, <bases>...]`` up to (but not including) object."""
    chain: list[str] = []
    for klass in cls.__mro__:
        if klass is object:
            break
        chain.append(klass.__name__)
    return chain


# Naming note: this identifier is per block *execution* (one per invocation of
# an AI Block in a workflow), not the workflow-level run id. Some already-shipped
# external surfaces keep the older ``run_id`` spelling for back-compat: the
# manifest JSON key ``block.run_id``, ``PtyTabSpec.block_run_id``, and
# ``notify_block_pty_event(block_run_id, ...)``. Only the internal Python names
# and the on-disk path component use ``block_execution_id``.
class RunDir:
    """Per-execution coordination directory for an AI Block.

    Owns the lifecycle of one run's directory under
    ``{project}/.scistudio/ai-block-runs/{block_execution_id}/``: creates it,
    writes the manifest, exposes the paths of the completion-signal files, and
    copies the terminal transcript in. It does not restrict what the agent can
    do outside this directory — see the module docstring.

    Example:
        >>> from pathlib import Path
        >>> run_dir = RunDir(Path("/tmp/proj"), "20260513-220045-extract-abc1234")
        >>> run_dir.path.name
        '20260513-220045-extract-abc1234'
    """

    def __init__(self, project_dir: Path, block_execution_id: str) -> None:
        """Set up the run-dir handle.

        Does not create the directory — call :meth:`create` explicitly so the
        caller controls when (and how to handle a collision).

        Args:
            project_dir: Project root. The coordination directory lives under
                ``project_dir / ".scistudio" / "ai-block-runs"``.
            block_execution_id: Identifier for one AI Block execution (one per
                invocation).

        Raises:
            ValueError: ``block_execution_id`` contains a path separator, which
                would let it escape the run-dir location.
        """
        if (
            not block_execution_id
            or os.sep in block_execution_id
            or "/" in block_execution_id
            or ".." in block_execution_id.split(os.sep)
        ):
            raise ValueError(f"block_execution_id contains path separator(s): {block_execution_id!r}")
        self.project_dir = Path(project_dir)
        """Project root this run directory hangs off of."""
        self.block_execution_id = block_execution_id
        """Identifier for this single AI Block execution."""
        self.path = self.project_dir / ".scistudio" / "ai-block-runs" / block_execution_id
        """Absolute path to this run's coordination directory."""

    def create(self) -> None:
        """Create the run dir and ``signals/`` subdir on disk.

        Raises:
            FileExistsError: if ``self.path`` already exists. The
                ``block_execution_id`` is supposed to encode timestamp +
                nonce, so a collision signals a bug — caller decides
                whether to retry or escalate.
            PermissionError: if the project dir is not writable.
        """
        # parents=True so .scistudio and ai-block-runs are created if missing,
        # but exist_ok=False so the per-run leaf collision is loud.
        self.path.mkdir(parents=True, exist_ok=False)
        (self.path / "signals").mkdir(exist_ok=True)

    def write_manifest(
        self,
        block_name: str,
        block_type: str,
        user_prompt: str,
        inputs: dict[str, list[Any]],
        outputs: list[OutputPort],
        deadline_iso: str | None = None,
        output_paths: dict[str, str] | None = None,
    ) -> Path:
        """Write ``manifest.json`` describing this run's inputs and outputs.

        The manifest is what the agent reads to learn its task, where its
        inputs are on disk, and where each output is expected. Written
        atomically (temp file + ``os.replace``) so a crash mid-write leaves
        either the old file or the new one, never a partial.

        Args:
            block_name: Name of the AI Block instance.
            block_type: Class name of the AI Block.
            user_prompt: Natural-language task that drives the agent.
            inputs: ``{port_name: [DataObject, ...]}`` already collected from
                the input Collections by the caller. Each object's storage path
                (or, for an Artifact, its file path) is recorded verbatim — no
                copying, symlinking, or rewriting.
            outputs: Declared output ports for this instance.
            deadline_iso: Optional ISO-8601 UTC deadline string, or ``None``
                when the block runs without a wall-clock deadline (the default),
                which records ``"deadline": null``.
            output_paths: Optional ``{port_name: expected_path}`` overrides from
                the port-editor entries. When missing, defaults to
                ``./{block_name}_outputs/{port}.{ext}``.

        Returns:
            Absolute path to the written manifest, suitable for handing to the
            agent in its first prompt.
        """
        from scistudio.core.types.artifact import Artifact

        # Inputs section ------------------------------------------------------
        inputs_section: dict[str, list[dict[str, Any]]] = {}
        for port_name, items in inputs.items():
            inputs_section[port_name] = []
            for obj in items:
                # Materialize verbatim: prefer storage_ref, fall back to
                # Artifact.file_path. If neither is present, ask the object
                # to produce one via save() (best effort) — but we keep the
                # caller path simple by relying on the engine's auto-flush
                # already having run.
                path: str | None = None
                ref = getattr(obj, "storage_ref", None)
                if ref is not None and getattr(ref, "path", None):
                    path = str(ref.path)
                elif isinstance(obj, Artifact) and obj.file_path is not None:
                    path = str(obj.file_path)
                else:
                    # In-memory only — log and emit a placeholder; the agent
                    # will see the type info but no path. Implementation
                    # contracts upstream (ADR-031) say all inputs to EXTERNAL
                    # blocks should be materialized; this branch is a
                    # diagnostic.
                    logger.warning(
                        "AIBlock manifest: input %r item has no storage_ref or file_path; "
                        "agent will see type info only.",
                        port_name,
                    )
                meta_dict: dict[str, Any] = {}
                if isinstance(obj, Artifact) and obj.mime_type:
                    meta_dict["mime_type"] = obj.mime_type
                inputs_section[port_name].append(
                    {
                        "path": path,
                        "type_chain": _type_chain(type(obj)),
                        "meta": meta_dict,
                    }
                )

        # Outputs section -----------------------------------------------------
        outputs_section: dict[str, dict[str, Any]] = {}
        output_paths = output_paths or {}
        for port in outputs:
            expected_path = output_paths.get(port.name) or self._default_expected_path(block_name, port)
            # First accepted type is the "expected" type; default to DataObject.
            if port.accepted_types:
                cls = port.accepted_types[0]
                expected_type = cls.__name__
                type_chain = _type_chain(cls)
            else:
                expected_type = "DataObject"
                type_chain = ["DataObject"]
            outputs_section[port.name] = {
                "expected_path": expected_path,
                "expected_type": expected_type,
                "type_chain": type_chain,
                "description": port.description or "",
            }

        manifest: dict[str, Any] = {
            "block": {
                "name": block_name,
                "type": block_type,
                # ADR-038 §5.2: the JSON key is kept as ``run_id`` to
                # preserve the ADR-035 §3.4 agent-facing schema. The
                # Python identifier is ``block_execution_id``.
                "run_id": self.block_execution_id,
            },
            "user_prompt": user_prompt,
            "inputs": inputs_section,
            "outputs": outputs_section,
            "completion": {
                "primary": "Call mcp__scistudio__finish_ai_block(outputs={...}) when all outputs are written.",
                "fallback": "Or write all expected_path files; the watcher will detect them.",
                "deadline": deadline_iso,
            },
        }

        # Atomic write: tempfile in the same dir + os.replace.
        manifest_path = self.path / "manifest.json"
        # NamedTemporaryFile so we get a unique name; delete=False so we own
        # the file's lifetime through replace().
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json.tmp",
            prefix="manifest-",
            dir=str(self.path),
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(manifest, handle, indent=2)
            tmp_name = handle.name
        os.replace(tmp_name, manifest_path)
        return manifest_path

    def write_reuse_marker(
        self,
        *,
        block_name: str,
        block_type: str,
        outputs: dict[str, str],
    ) -> Path:
        """#1898: write ``reuse.json`` recording a reuse-last-output hit.

        A reuse hit re-emits the previous run's output files without spawning
        the agent, so this run dir gets a ``reuse.json`` marker instead of a
        ``manifest.json`` + ``signals/``. The presence of this marker (and the
        absence of a manifest) is the durable, per-execution audit signal that
        distinguishes a reused result from a genuine agent run — see ADR-035
        Addendum 1 §4.3. Atomic write via tempfile + ``os.replace``.
        """
        marker = {
            "reused_last_output": True,
            "block": {"name": block_name, "type": block_type},
            "outputs": outputs,
        }
        marker_path = self.path / "reuse.json"
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json.tmp",
            prefix="reuse-",
            dir=str(self.path),
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(marker, handle, indent=2)
            tmp_name = handle.name
        os.replace(tmp_name, marker_path)
        return marker_path

    @staticmethod
    def _default_expected_path(block_name: str, port: OutputPort) -> str:
        """Compute ``./{block_name}_outputs/{port.name}.{ext}`` per ADR-035 §3.3.

        Picks an extension based on the first accepted type:
            DataFrame  -> .csv
            Series     -> .csv
            Array      -> .npy
            Text       -> .txt
            Artifact   -> .bin
            other      -> .dat
        """
        ext_map = {
            "DataFrame": "csv",
            "Series": "csv",
            "Array": "npy",
            "Text": "txt",
            "Artifact": "bin",
            "CompositeData": "json",
        }
        ext = ext_map.get(port.accepted_types[0].__name__, "dat") if port.accepted_types else "dat"
        return f"./{block_name}_outputs/{port.name}.{ext}"

    def mcp_signal_path(self) -> Path:
        """Path the agent's ``finish`` tool writes to when it completes a run."""
        return self.path / "signals" / "finish_ai_block.json"

    def mark_done_signal_path(self) -> Path:
        """Path written when the user clicks "Mark done" in the tab."""
        return self.path / "signals" / "mark_done.json"

    def copy_transcript(self, source: Path) -> Path:
        """Copy the terminal transcript log into this run's directory.

        Best-effort: if *source* is missing, logs a warning and returns the
        destination path without copying. Disk-full and other ``OSError``
        propagate.

        Args:
            source: Path to the terminal transcript log to copy in.

        Returns:
            Destination path inside the run directory (``transcript.log``),
            whether or not the copy happened.
        """
        dest = self.path / "transcript.log"
        if not source.exists() or not source.is_file():
            logger.warning(
                "AIBlock transcript source missing: %s (lineage will be incomplete).",
                source,
            )
            return dest
        shutil.copy2(source, dest)
        return dest
