"""Preview-side plot execution (ADR-048 SPEC 2 FR-023..FR-031).

``run_plot_job`` resolves the bound target's latest output to input data refs,
runs the user's render script inside a confined working directory using the
CodeBlock subprocess primitive (``run_codeblock_process`` — IMPORT ONLY, never
mutating ``scistudio.blocks``), enforces timeout / output-size / file-count caps,
sanitizes errors, and writes display-only artifacts plus ``current.json`` to the
preview cache (FR-026, FR-028).

Hard invariant (FR-025, verified by tests): a plot run NEVER registers a workflow
node, edits workflow YAML, creates a downstream collection, or claims lineage.
This module only reads the in-memory scheduler outputs and writes under
``.scistudio/previews/``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scistudio.ai.agent.mcp._context import _resolve_project_root, get_context
from scistudio.ai.agent.mcp.tools_plot._harness import PYTHON_HARNESS, R_HARNESS
from scistudio.ai.agent.mcp.tools_plot.models import (
    ABSOLUTE_MAX_FILES,
    ABSOLUTE_MAX_INPUT_BYTES,
    ABSOLUTE_MAX_OUTPUT_BYTES,
    ABSOLUTE_MAX_TIMEOUT_SECONDS,
    LOG_TRUNCATE_BYTES,
    PlotArtifact,
    PlotManifest,
    PlotPreviewTarget,
    PlotRunResult,
    PlotStatus,
)
from scistudio.ai.agent.mcp.tools_plot.validation import LoadedPlot, load_plot

logger = logging.getLogger(__name__)

_PYTHON_HARNESS_NAME = "_plot_harness.py"
_R_HARNESS_NAME = "_plot_harness.R"
_INPUTS_NAME = "_plot_inputs.json"
_PREVIEW_ROOT = ".scistudio/previews"
_CORE_OPEN_TYPES = ("Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData")
_CORE_OPEN_TYPE_SET = frozenset(_CORE_OPEN_TYPES)


# ---------------------------------------------------------------------------
# Preview cache layout (FR-026).
# ---------------------------------------------------------------------------


def preview_cache_dir(root: Path, workflow_id: str, node_id: str, output_port: str, plot_id: str) -> Path:
    """Return ``.scistudio/previews/<workflow_id>/<node_id>/<output_port>/<plot_id>/`` (FR-026)."""
    return (
        root / _PREVIEW_ROOT / _safe_seg(workflow_id) / _safe_seg(node_id) / _safe_seg(output_port) / _safe_seg(plot_id)
    ).resolve()


def cache_key_for(workflow_id: str, node_id: str, output_port: str, plot_id: str) -> str:
    """Stable cache key the UI can poll for refresh (FR-030)."""
    raw = f"{workflow_id}|{node_id}|{output_port}|{plot_id}".encode()
    return "plot_" + hashlib.sha256(raw).hexdigest()[:16]


def _safe_seg(value: str) -> str:
    """Sanitize a single path segment so a manifest value cannot traverse."""
    value = (value or "_").replace("\\", "_").replace("/", "_")
    value = value.replace("..", "_")
    return value or "_"


# ---------------------------------------------------------------------------
# Input resolution (FR-023) — latest recorded output for the bound target.
# ---------------------------------------------------------------------------


@dataclass
class _ResolvedInput:
    run_id: str | None
    refs: list[dict[str, Any]]
    collection_ids: list[str]


@dataclass
class _PreviewRegistration:
    data_ref: str | None = None
    recorded_type: str = "PlotArtifact"
    type_chain: list[str] | None = None
    preview_target: PlotPreviewTarget | None = None


def _resolve_input(ctx: Any, manifest: PlotManifest, run_id: str | None) -> _ResolvedInput:
    """Resolve the bound target output to a list of storage-ref dicts.

    Reads ``ctx.workflow_runs[*].scheduler._block_outputs`` exactly like
    ``tools_inspection.get_block_output`` — read-only, no scheduler mutation.
    """
    node_id = manifest.target.node_id
    port = manifest.target.output_port
    runs = getattr(ctx, "workflow_runs", None)
    if not isinstance(runs, dict) or not runs:
        return _ResolvedInput(run_id=None, refs=[], collection_ids=[])

    chosen_run = run_id
    value: Any = None
    if run_id is not None:
        run = runs.get(run_id)
        scheduler = getattr(run, "scheduler", None) if run is not None else None
        outputs = getattr(scheduler, "_block_outputs", {}) if scheduler is not None else {}
        payload = outputs.get(node_id)
        if isinstance(payload, dict) and port in payload:
            value = payload[port]
    else:
        for rid, run in runs.items():
            scheduler = getattr(run, "scheduler", None)
            outputs = getattr(scheduler, "_block_outputs", {}) if scheduler is not None else {}
            payload = outputs.get(node_id)
            if isinstance(payload, dict) and port in payload:
                chosen_run = rid
                value = payload[port]
    refs, collection_ids = _flatten_to_refs(value)
    return _ResolvedInput(run_id=chosen_run, refs=refs, collection_ids=collection_ids)


def _flatten_to_refs(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Flatten a block output value into a list of {backend,path,format,metadata} dicts."""
    refs: list[dict[str, Any]] = []
    collection_ids: list[str] = []

    def _one(item: Any, *, item_type: str | None = None) -> None:
        if isinstance(item, dict) and "path" in item:
            refs.append(
                {
                    "backend": item.get("backend", "filesystem"),
                    "path": str(item.get("path")),
                    "format": item.get("format"),
                    "item_type": item.get("item_type") or item.get("type") or item_type,
                    "metadata": item.get("metadata"),
                }
            )
            meta = item.get("metadata")
            if isinstance(meta, dict):
                fmw = meta.get("framework")
                if isinstance(fmw, dict) and fmw.get("object_id"):
                    collection_ids.append(str(fmw["object_id"]))

    if isinstance(value, dict):
        # Canonical Collection wire-form produced by the worker/scheduler/
        # checkpoint layers is {"_collection": True, "items": [...],
        # "item_type": "..."} (see engine/runners/worker.py::serialise_outputs
        # and engine/checkpoint.py). Read the items from "items"; keep
        # "_collection_items" as a defensive alias; otherwise treat the dict as
        # a single ref. FR-016: the plot script must receive the actual
        # selected block-output collection, not an empty one.
        if value.get("_collection") and isinstance(value.get("items"), list):
            item_type = str(value.get("item_type")) if value.get("item_type") else None
            for it in value["items"]:
                _one(it, item_type=item_type)
        elif isinstance(value.get("_collection_items"), list):
            for it in value["_collection_items"]:
                _one(it)
        else:
            _one(value)
    elif isinstance(value, (list, tuple)):
        for it in value:
            _one(it)
    return refs, collection_ids


def _preview_registrar(ctx: Any) -> Any | None:
    """Return a callable plot-artifact registrar from the live MCP context.

    In the FastAPI process the MCP context is a thin adapter around
    ``ApiRuntime``. The adapter keeps the API layer out of ``ai`` imports, so
    this function duck-types the adapter method without importing from
    ``scistudio.api``.
    """
    registrar = getattr(ctx, "register_plot_artifact", None)
    return registrar if callable(registrar) else None


def _register_preview_artifact(
    ctx: Any,
    artifact_path: str,
    *,
    cache_key: str | None,
    manifest: PlotManifest,
    workflow_id: str,
) -> _PreviewRegistration:
    """Register the first produced artifact so MCP callers get a preview target."""
    registrar = _preview_registrar(ctx)
    if registrar is None:
        return _PreviewRegistration(type_chain=[])

    try:
        record = registrar(
            artifact_path,
            cache_key=cache_key,
            workflow_id=workflow_id,
            node_id=manifest.target.node_id,
            output_port=manifest.target.output_port,
            plot_id=manifest.id,
        )
    except Exception:
        logger.warning("plot artifact registration failed", exc_info=True)
        return _PreviewRegistration(type_chain=[])
    data_ref = str(getattr(record, "id", "") or "")
    if not data_ref:
        return _PreviewRegistration(type_chain=[])
    recorded_type = str(getattr(record, "type_name", "") or "PlotArtifact")
    raw_chain = getattr(record, "type_chain", None)
    type_chain = [str(name) for name in raw_chain] if raw_chain else ["DataObject", "PlotArtifact"]
    source: dict[str, str | None] = {
        "workflow_id": workflow_id,
        "node_id": manifest.target.node_id,
        "output_port": manifest.target.output_port,
    }
    preview_target = PlotPreviewTarget(
        ref=data_ref,
        recorded_type=recorded_type,
        type_chain=type_chain,
        source=source,
    )
    return _PreviewRegistration(
        data_ref=data_ref,
        recorded_type=recorded_type,
        type_chain=type_chain,
        preview_target=preview_target,
    )


# ---------------------------------------------------------------------------
# Execution (FR-024) - CodeBlock subprocess primitive, confined cwd.
# ---------------------------------------------------------------------------


def _clamp_limits(manifest: PlotManifest) -> tuple[float, int, int, int]:
    timeout = min(float(manifest.runtime.timeout_seconds), ABSOLUTE_MAX_TIMEOUT_SECONDS)
    max_input_bytes = min(int(manifest.limits.max_input_bytes), ABSOLUTE_MAX_INPUT_BYTES)
    max_bytes = min(int(manifest.limits.max_output_bytes), ABSOLUTE_MAX_OUTPUT_BYTES)
    max_files = min(int(manifest.limits.max_files), ABSOLUTE_MAX_FILES)
    return timeout, max_bytes, max_files, max_input_bytes


def _input_envelope(refs: list[dict[str, Any]], type_registry: Any | None = None) -> dict[str, Any]:
    """Build the context-free collection envelope consumed by the harness."""
    items = [_normalise_input_item(ref, type_registry=type_registry) for ref in refs]
    types: list[str] = []
    for item in items:
        typ = str(item.get("type") or "DataObject")
        if typ != "DataObject" and typ not in types:
            types.append(typ)
    return {"schema_version": 1, "collection": {"types": types, "items": items}}


def _normalise_input_item(ref: dict[str, Any], *, type_registry: Any | None = None) -> dict[str, Any]:
    """Fold package subclasses to supported core base types for user code."""
    metadata = ref.get("metadata") if isinstance(ref.get("metadata"), dict) else {}
    normalised_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    slots = normalised_metadata.get("slots")
    if isinstance(slots, dict):
        normalised_metadata["slots"] = {
            str(name): _normalise_input_item(slot, type_registry=type_registry)
            for name, slot in slots.items()
            if isinstance(slot, dict)
        }
    return {
        "type": _normalise_core_type(ref, type_registry=type_registry),
        "_backend": ref.get("backend"),
        "_path": ref.get("path"),
        "_format": ref.get("format"),
        "metadata": normalised_metadata,
    }


def _normalise_core_type(ref: dict[str, Any], *, type_registry: Any | None = None) -> str:
    raw_chain: Any = None
    metadata = ref.get("metadata")
    if isinstance(metadata, dict):
        raw_chain = metadata.get("type_chain")
    if not raw_chain:
        raw_chain = ref.get("type_chain")
    if not raw_chain:
        raw_chain = ref.get("item_type")
    if isinstance(raw_chain, str):
        chain = [raw_chain]
    elif isinstance(raw_chain, (list, tuple)):
        chain = [str(name) for name in raw_chain]
    else:
        chain = []
    for name in reversed(chain):
        if name in _CORE_OPEN_TYPE_SET:
            return name
        base = _registered_core_base(type_registry, name)
        if base is not None:
            return base
    if str(ref.get("format") or "").lower() in {"csv", "tsv", "parquet", "pq"}:
        return "DataFrame"
    return "DataObject"


def _registered_core_base(type_registry: Any | None, type_name: str) -> str | None:
    if type_registry is None or type_name in _CORE_OPEN_TYPE_SET:
        return type_name if type_name in _CORE_OPEN_TYPE_SET else None
    try:
        types = type_registry.all_types()
    except Exception:
        return None
    if not isinstance(types, dict):
        return None
    current = type_name
    seen: set[str] = set()
    while current and current not in seen:
        if current in _CORE_OPEN_TYPE_SET:
            return current
        seen.add(current)
        spec = types.get(current)
        if spec is None:
            return None
        if isinstance(spec, dict):
            current = str(spec.get("base_type") or "")
        else:
            current = str(getattr(spec, "base_type", "") or "")
    return None


def _interpreter_for(loaded: LoadedPlot) -> list[str] | None:
    """Resolve interpreter argv prefix for the harness, or None if unavailable."""
    language = loaded.manifest.script.language
    if language == "python":
        import sys

        return [sys.executable, _PYTHON_HARNESS_NAME]
    if language == "r":
        rscript = shutil.which("Rscript")
        if rscript is None:
            return None
        return [rscript, _R_HARNESS_NAME]
    return None  # pragma: no cover


def _truncate(text: str | None) -> str:
    if not text:
        return ""
    data = text.encode("utf-8", errors="replace")
    if len(data) <= LOG_TRUNCATE_BYTES:
        return text
    return "...[truncated]...\n" + data[-LOG_TRUNCATE_BYTES:].decode("utf-8", errors="replace")


def _sanitize_error(message: str, root: Path) -> str:
    """Strip absolute project paths from an error message (FR-029)."""
    if not message:
        return ""
    try:
        root_str = str(root.resolve())
        message = message.replace(root_str, "<project>")
        message = message.replace(root_str.replace("\\", "/"), "<project>")
    except Exception:  # pragma: no cover
        pass
    return _truncate(message)


def _clear_current_artifacts(cache_dir: Path) -> None:
    """Remove stale display artifacts while preserving ``current.json`` state."""
    if not cache_dir.exists():
        return
    for old in cache_dir.glob("current.*"):
        if old.name != "current.json":
            old.unlink()


def run_plot_job(plot_id: str, run_id: str | None = None, timeout_seconds: float | None = None) -> PlotRunResult:
    """Execute a plot job preview-side and write display-only artifacts (FR-023..FR-031)."""
    from scistudio.blocks.code._backends_registry import (
        CodeBlockTimeoutError,
        run_codeblock_process,
    )

    ctx = get_context()
    root = _resolve_project_root(ctx)
    loaded = load_plot(plot_id=plot_id)
    manifest = loaded.manifest
    timeout, max_bytes, max_files, max_input_bytes = _clamp_limits(manifest)
    if timeout_seconds is not None:
        timeout = min(float(timeout_seconds), ABSOLUTE_MAX_TIMEOUT_SECONDS)

    workflow_id = manifest.target.workflow_id or Path(manifest.target.workflow_path).stem
    cache_dir = preview_cache_dir(root, workflow_id, manifest.target.node_id, manifest.target.output_port, plot_id)
    cache_key = cache_key_for(workflow_id, manifest.target.node_id, manifest.target.output_port, plot_id)
    _clear_current_artifacts(cache_dir)

    warnings: list[str] = []
    errors: list[str] = []

    # Resolve input collection (FR-023).
    resolved = _resolve_input(ctx, manifest, run_id)
    if not resolved.refs:
        warnings.append(
            "no recorded output for the bound target; run the workflow first. The plot ran against an empty collection."
        )

    # Interpreter availability (FR-021 runner diagnostics surface as a run status).
    interp = _interpreter_for(loaded)
    if interp is None:
        result = PlotRunResult(
            status="failed",
            returncode=None,
            cache_key=cache_key,
            errors=["R runner unavailable: 'Rscript' is not on PATH."],
            warnings=warnings,
        )
        _write_metadata(cache_dir, loaded, resolved, result, run_id, workflow_id)
        return result

    # Confined working dir (FR-024): a per-run temp dir under the cache.
    work_dir = cache_dir / "_work"
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Materialize harness + user script + inputs into the confined dir.
    if manifest.script.language == "python":
        (work_dir / _PYTHON_HARNESS_NAME).write_text(PYTHON_HARNESS, encoding="utf-8")
    else:
        (work_dir / _R_HARNESS_NAME).write_text(R_HARNESS, encoding="utf-8")
    user_script_name = Path(manifest.script.path).name
    shutil.copy2(loaded.script_path, work_dir / user_script_name)
    (work_dir / _INPUTS_NAME).write_text(
        json.dumps(_input_envelope(resolved.refs, type_registry=getattr(ctx, "type_registry", None))),
        encoding="utf-8",
    )

    allowed_csv = ",".join(manifest.outputs.allowed_formats)
    argv = [
        *interp,
        user_script_name,
        manifest.script.entrypoint,
        _INPUTS_NAME,
        ".",
        manifest.outputs.preferred_format,
        allowed_csv,
        str(max_input_bytes),
    ]

    status: PlotStatus = "failed"
    returncode: int | None = None
    stdout = ""
    stderr = ""
    artifacts: list[PlotArtifact] = []

    try:
        proc = run_codeblock_process(argv=argv, cwd=work_dir, env_delta={}, timeout_seconds=timeout)
        returncode = proc.returncode
        stdout = _truncate(proc.stdout)
        stderr = _sanitize_error(proc.stderr or "", root)
        harness = _parse_harness_stdout(proc.stdout or "")
        if harness is None:
            errors.append("plot harness produced no parseable result line.")
        elif not harness.get("ok"):
            err_msg = _sanitize_error(str(harness.get("error", "render failed")), root)
            errors.append(f"render failed: {err_msg}")
        else:
            produced = [str(name) for name in harness.get("artifacts", [])]
            artifacts, cap_warnings, cap_errors = _promote_artifacts(
                work_dir, cache_dir, produced, max_bytes, max_files, manifest
            )
            warnings.extend(cap_warnings)
            errors.extend(cap_errors)
            if artifacts and not cap_errors:
                status = "succeeded"
    except CodeBlockTimeoutError as exc:
        status = "timed_out"
        stdout = _truncate(getattr(exc, "stdout", "") or "")
        stderr = _sanitize_error(getattr(exc, "stderr", "") or "", root)
        errors.append(f"plot timed out after {timeout} seconds.")
    except Exception as exc:  # sanitized below — plot failures never crash the tool
        errors.append(_sanitize_error(f"plot execution error: {exc}", root))
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    result = PlotRunResult(
        status=status,
        returncode=returncode,
        artifact_paths=[a.path for a in artifacts],
        cache_key=cache_key,
        stdout=stdout,
        stderr=stderr,
        warnings=warnings,
        errors=errors,
    )
    if status == "succeeded" and result.artifact_paths:
        registration = _register_preview_artifact(
            ctx,
            result.artifact_paths[0],
            cache_key=cache_key,
            manifest=manifest,
            workflow_id=workflow_id,
        )
        result.data_ref = registration.data_ref
        result.recorded_type = registration.recorded_type
        result.type_chain = registration.type_chain or []
        result.preview_target = registration.preview_target
    metadata_path = _write_metadata(cache_dir, loaded, resolved, result, run_id, workflow_id, artifacts=artifacts)
    result.metadata_path = str(metadata_path)
    return result


def _parse_harness_stdout(stdout: str) -> dict[str, Any] | None:
    """Parse the last JSON line the harness printed."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _promote_artifacts(
    work_dir: Path,
    cache_dir: Path,
    produced: list[str],
    max_bytes: int,
    max_files: int,
    manifest: PlotManifest,
) -> tuple[list[PlotArtifact], list[str], list[str]]:
    """Move produced artifacts into the cache as current.* (FR-026, FR-027, FR-029)."""
    warnings: list[str] = []
    errors: list[str] = []

    # Re-scan the work dir for ALL produced output files to enforce the
    # file-count + byte caps against what the script actually wrote, not just
    # what it declared.
    on_disk = [
        p
        for p in sorted(work_dir.iterdir())
        if p.is_file() and p.suffix.lower().lstrip(".") in {"svg", "pdf", "png", "jpeg", "jpg"}
    ]
    if len(on_disk) > max_files:
        errors.append(f"plot wrote {len(on_disk)} files; max_files cap is {max_files}.")
        return [], warnings, errors
    total = sum(p.stat().st_size for p in on_disk)
    if total > max_bytes:
        errors.append(f"plot output is {total} bytes; max_output_bytes cap is {max_bytes}.")
        return [], warnings, errors

    cache_dir.mkdir(parents=True, exist_ok=True)
    # Current-overwrite: clear previous current.* before writing new ones (FR-027).
    _clear_current_artifacts(cache_dir)

    # Order: declared artifacts first, then any extras found on disk.
    ordered: list[Path] = []
    for name in produced:
        candidate = work_dir / Path(name).name
        if candidate.is_file() and candidate not in ordered:
            ordered.append(candidate)
    for p in on_disk:
        if p not in ordered:
            ordered.append(p)
    if not ordered:
        errors.append("render returned success but wrote no recognised artifact.")
        return [], warnings, errors

    artifacts: list[PlotArtifact] = []
    for idx, src in enumerate(ordered):
        ext = src.suffix.lower().lstrip(".")
        if ext == "jpg":
            ext = "jpeg"
        # First artifact is the canonical current.<ext>; extras get an index.
        dest_name = (
            "current." + (src.suffix.lower().lstrip("."))
            if idx == 0
            else f"current_{idx}.{src.suffix.lower().lstrip('.')}"
        )
        dest = cache_dir / dest_name
        shutil.copy2(src, dest)
        artifacts.append(
            PlotArtifact(filename=dest.name, format=ext, path=str(dest), size_bytes=dest.stat().st_size)  # type: ignore[arg-type]
        )
    return artifacts, warnings, errors


def _write_metadata(
    cache_dir: Path,
    loaded: LoadedPlot,
    resolved: _ResolvedInput,
    result: PlotRunResult,
    requested_run_id: str | None,
    workflow_id: str,
    artifacts: list[PlotArtifact] | None = None,
) -> Path:
    """Write current.json with the full run record (FR-028)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest = loaded.manifest
    try:
        script_hash = hashlib.sha256(loaded.script_path.read_bytes()).hexdigest()
    except OSError:
        script_hash = ""
    record = {
        "schema_version": 1,
        "plot_id": manifest.id,
        "manifest_path": str(loaded.manifest_path),
        "script_path": str(loaded.script_path),
        "script_hash": script_hash,
        "target": {
            "workflow_path": manifest.target.workflow_path,
            "workflow_id": workflow_id,
            "node_id": manifest.target.node_id,
            "output_port": manifest.target.output_port,
        },
        "input_collection_ids": resolved.collection_ids,
        "requested_run_id": requested_run_id,
        "run_id": resolved.run_id,
        "runner": manifest.script.language,
        "created": datetime.now(UTC).isoformat(),
        "outputs": [
            {"filename": a.filename, "format": a.format, "size_bytes": a.size_bytes} for a in (artifacts or [])
        ],
        "status": result.status,
        "returncode": result.returncode,
        "error": "; ".join(result.errors) if result.errors else None,
        "cache_key": result.cache_key,
    }
    metadata_path = cache_dir / "current.json"
    metadata_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return metadata_path


__all__ = [
    "cache_key_for",
    "preview_cache_dir",
    "run_plot_job",
]
