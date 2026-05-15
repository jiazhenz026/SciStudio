"""RunDir — per-block-execution coordination directory for AI Block (ADR-035 §3.2, §3.4).

The directory at ``{project}/.scieasy/ai-block-runs/{block_execution_id}/``
holds the manifest.json, transcript copy, and completion-signal scratch
files for one AI Block execution.

**Naming note (ADR-038 §5.2)**: this identifier is **per block execution**
— each invocation of one AI Block within a workflow gets a fresh one — so
the ADR-038 cascade renamed the internal variable from ``run_id`` to
``block_execution_id`` to disambiguate it from the workflow-level ``run_id``
defined in the unified lineage store (ADR-038 §3.1, ``runs`` table).
External surfaces that already shipped under the legacy spelling are
preserved verbatim:

* The manifest JSON key ``block.run_id`` (ADR-035 §3.4 schema) — agent
  prompts in the wild reference this name.
* ``PtyTabSpec.block_run_id`` (engine surface, ADR-034 freeze).
* ``notify_block_pty_event(block_run_id, ...)`` (engine surface).

Only the internal Python identifiers and the on-disk path component have
been renamed.

**This is NOT a sandbox.** The agent runs with the project directory as cwd
and full filesystem access (ADR-035 §3.2, §3.7). The run dir exists only to
hold lineage / coordination artifacts. The agent is free to read and write
anywhere else the user has access.
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
#     "primary":   "Call mcp__scieasy__finish_ai_block(...)",
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


class RunDir:
    """Per-block-execution coordination directory for an AI Block.

    Owns the lifecycle of
    ``{project}/.scieasy/ai-block-runs/{block_execution_id}/``: creates it,
    writes the manifest, exposes paths for completion-signal files, copies
    the transcript on close. Does NOT enforce any access control on what
    the agent can do outside this dir — see module-level docstring.

    References:
        ADR-035 §3.2 (lineage/coordination role),
        ADR-035 §3.4 (manifest schema),
        ADR-035 §3.5 (completion signal file locations),
        ADR-038 §5.2 (rename rationale).
    """

    def __init__(self, project_dir: Path, block_execution_id: str) -> None:
        """Initialize the run-dir handle.

        Does NOT create the directory yet — :meth:`create` is explicit so
        the caller can choose to deal with collisions.

        Parameters
        ----------
        project_dir:
            Project root. The coordination directory lives under
            ``project_dir / ".scieasy" / "ai-block-runs"``.
        block_execution_id:
            Per-AI-Block execution identifier (one per invocation). Renamed
            from ``run_id`` per ADR-038 §5.2 to avoid collision with the
            workflow-level ``runs.run_id`` introduced by the unified
            lineage store.

        Raises:
            ValueError: if ``block_execution_id`` contains a path
                separator (would escape the run-dir scope).
        """
        if (
            not block_execution_id
            or os.sep in block_execution_id
            or "/" in block_execution_id
            or ".." in block_execution_id.split(os.sep)
        ):
            raise ValueError(f"block_execution_id contains path separator(s): {block_execution_id!r}")
        self.project_dir = Path(project_dir)
        self.block_execution_id = block_execution_id
        self.path = self.project_dir / ".scieasy" / "ai-block-runs" / block_execution_id

    def create(self) -> None:
        """Create the run dir and ``signals/`` subdir on disk.

        Raises:
            FileExistsError: if ``self.path`` already exists. The
                ``block_execution_id`` is supposed to encode timestamp +
                nonce, so a collision signals a bug — caller decides
                whether to retry or escalate.
            PermissionError: if the project dir is not writable.
        """
        # parents=True so .scieasy and ai-block-runs are created if missing,
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
        deadline_iso: str,
        output_paths: dict[str, str] | None = None,
    ) -> Path:
        """Write ``manifest.json`` per the schema in ADR-035 §3.4.

        Returns the absolute path to the written manifest (suitable for
        injection into the agent's initial prompt).

        Args:
            block_name: Name of the AIBlock instance.
            block_type: Class name of the AIBlock subclass.
            user_prompt: The natural-language prompt to drive the agent.
            inputs: ``{port_name: [DataObject, ...]}`` — already iterated
                from the input Collections by the caller. Each DataObject's
                ``storage_ref.path`` (if set) or ``file_path`` (Artifact)
                is recorded **verbatim** — no symlinking, no rewriting.
            outputs: List of declared output ports (effective ports).
            deadline_iso: ISO-8601 UTC deadline string.
            output_paths: Optional ``{port_name: expected_path}`` overrides
                from ``config["output_ports"]`` port-editor entries. When
                missing, defaults to ``./{block_name}_outputs/{port}.{ext}``.

        Atomically written (tempfile + ``os.replace``) so a crash mid-write
        leaves either the old file or the new file, never a partial.

        References:
            ADR-035 §3.4 (schema), §3.3 (default expected_path),
            ADR-038 §5.2 (manifest ``block.run_id`` key kept under its
            legacy spelling — agent-facing contract),
            src/scieasy/blocks/app/bridge.py (atomic-write idiom).
        """
        from scieasy.core.types.artifact import Artifact

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
                "primary": "Call mcp__scieasy__finish_ai_block(outputs={...}) when all outputs are written.",
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
        """Path the MCP tool writes to on ``finish_ai_block`` (ADR-035 §3.5 path a)."""
        return self.path / "signals" / "finish_ai_block.json"

    def mark_done_signal_path(self) -> Path:
        """Path the engine writes to on user "Mark done" (ADR-035 §3.5 path c)."""
        return self.path / "signals" / "mark_done.json"

    def copy_transcript(self, source: Path) -> Path:
        """Copy the PTY tab's transcript log into the run dir.

        Best-effort: if ``source`` does not exist, logs a warning and
        returns the destination path unchanged (no copy). Disk-full and
        other ``OSError`` propagate.

        References:
            ADR-035 §6.1 (lineage / archived alongside the manifest).
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
