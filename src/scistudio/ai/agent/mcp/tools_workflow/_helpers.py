"""Shared helpers for the ``tools_workflow`` sub-package.

ADR-040 §3.1 FastMCP migration. Extracted from the original single-file
``tools_workflow.py`` (#1431, umbrella #1427) so each sub-module stays
below the 750 LOC god-file threshold. No behavior change.

Public surface preserved at ``scistudio.ai.agent.mcp.tools_workflow``
via the package ``__init__`` re-exports.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import tempfile
from pathlib import Path
from typing import Any

from scistudio.ai.agent.mcp._context import get_context

_LOCK_TIMEOUT_SECONDS: float = 10.0
"""ADR-033 OQ7: file lock timeout for atomic-write tools."""


def _spec_to_dict(spec: Any) -> dict[str, Any]:
    """Serialise a :class:`BlockSpec` (dataclass) to a JSON-safe dict.

    ``input_ports`` and ``output_ports`` carry :class:`Port` instances
    that are not natively JSON-serialisable; we project them to a
    minimal {name, type, required} envelope.
    """
    if dataclasses.is_dataclass(spec) and not isinstance(spec, type):
        raw = dataclasses.asdict(spec)
    else:  # pragma: no cover - non-dataclass spec
        raw = dict(spec.__dict__)
    raw["input_ports"] = [_port_to_dict(p) for p in (spec.input_ports or [])]
    raw["output_ports"] = [_port_to_dict(p) for p in (spec.output_ports or [])]
    return raw


def _port_to_dict(port: Any) -> dict[str, Any]:
    """Project a :class:`Port` to a JSON-safe dict."""
    if isinstance(port, dict):
        return port
    type_obj = getattr(port, "type", None)
    type_name = getattr(type_obj, "__name__", str(type_obj)) if type_obj is not None else ""
    return {
        "name": getattr(port, "name", ""),
        "type": type_name,
        "required": bool(getattr(port, "required", False)),
    }


def _render_port_type(port: Any) -> str:
    """Render a port's accepted type(s) for a catalog signature.

    SciStudio ports declare their type via ``accepted_types`` (a list of type
    classes); an empty list means "accept/emit any data object" and renders as
    ``Any``. Multiple accepted types render as ``A|B``; collection ports get a
    ``[]`` suffix.
    """
    if isinstance(port, dict):
        accepted = port.get("accepted_types") or []
        is_collection = bool(port.get("is_collection"))
    else:
        accepted = getattr(port, "accepted_types", None) or []
        is_collection = bool(getattr(port, "is_collection", False))
    names = [getattr(t, "__name__", str(t)) for t in accepted]
    rendered = "|".join(names) if names else "Any"
    return f"{rendered}[]" if is_collection else rendered


def _spec_signature(spec: Any) -> str:
    """Render a one-line I/O signature for a block's catalog entry.

    Example: ``image:Image, mask?:Array → result:Image``. Port types come from
    each port's ``accepted_types`` (``Any`` when none is declared); optional
    ports carry a ``?`` suffix; collection ports a ``[]`` suffix; an empty side
    renders as ``()``. Variadic sides append a ``*:<Type|Type>`` element (after
    any fixed seed ports) to signal that more ports of those types may be
    added — ``*:Any`` when no allowed types are declared.

    This is the only I/O detail ``list_blocks`` carries — enough for the
    agent to judge wiring compatibility during selection without fetching
    the full per-block schema. Call ``get_block_schema`` for exact port
    names/types and the config_schema.
    """

    def _port_name(port: Any) -> str:
        if isinstance(port, dict):
            return port.get("name") or "?"
        return getattr(port, "name", "") or "?"

    def _port_required(port: Any) -> bool:
        if isinstance(port, dict):
            return bool(port.get("required", True))
        return bool(getattr(port, "required", True))

    def _fmt_side(ports: Any, variadic: bool, allowed: Any) -> str:
        rendered = []
        for port in ports or []:
            optional = "" if _port_required(port) else "?"
            rendered.append(f"{_port_name(port)}{optional}:{_render_port_type(port)}")
        if variadic:
            allowed_types = [str(a) for a in (allowed or [])]
            rendered.append("*:" + ("|".join(allowed_types) if allowed_types else "Any"))
        return ", ".join(rendered) if rendered else "()"

    inputs = _fmt_side(
        spec.input_ports,
        bool(getattr(spec, "variadic_inputs", False)),
        getattr(spec, "allowed_input_types", None),
    )
    outputs = _fmt_side(
        spec.output_ports,
        bool(getattr(spec, "variadic_outputs", False)),
        getattr(spec, "allowed_output_types", None),
    )
    return f"{inputs} → {outputs}"


def _atomic_write_text(path: Path, text: str) -> int:
    """Write *text* to *path* via tempfile + rename. Returns bytes written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return len(text.encode("utf-8"))


def _diff_summary(old: str, new: str) -> str:
    """Compact diff summary used in INFO log + return envelope."""
    old_lines = old.splitlines() if old else []
    new_lines = new.splitlines()
    added = max(0, len(new_lines) - len(old_lines))
    removed = max(0, len(old_lines) - len(new_lines))
    return f"+{added}/-{removed} lines, {len(new.encode('utf-8'))} bytes"


def _looks_like_inline_yaml(s: str) -> bool:
    """Heuristic: starts with ``name:`` or contains ``nodes:`` ⇒ inline."""
    stripped = s.lstrip()
    if stripped.startswith(("name:", "workflow:", "id:", "version:")):
        return True
    return "nodes:" in s and "\n" in s


def _get_workflow_runtime() -> Any:
    """Locate a runtime that knows how to start workflows."""
    ctx = get_context()
    if not hasattr(ctx, "start_workflow"):
        raise RuntimeError(
            "Active MCPContext does not expose start_workflow(); run_workflow requires a full ApiRuntime."
        )
    return ctx


def _resolve_ai_block_run_dir() -> Path | None:
    """Locate the active AI Block run dir from MCP context or env var.

    Resolution order (first hit wins):

      1. ``MCPContext.ai_block_run_dir`` attribute, when present.
      2. ``SCISTUDIO_AI_BLOCK_RUN_DIR`` environment variable.

    Returns ``None`` when neither is configured.
    """
    try:
        ctx = get_context()
    except Exception:
        ctx = None
    if ctx is not None:
        run_dir = getattr(ctx, "ai_block_run_dir", None)
        if run_dir is not None:
            return Path(run_dir)
    raw = os.environ.get("SCISTUDIO_AI_BLOCK_RUN_DIR")
    if raw:
        candidate = Path(raw)
        if candidate.is_dir():
            return candidate
    return None


__all__ = [
    "_LOCK_TIMEOUT_SECONDS",
    "_atomic_write_text",
    "_diff_summary",
    "_get_workflow_runtime",
    "_looks_like_inline_yaml",
    "_port_to_dict",
    "_render_port_type",
    "_resolve_ai_block_run_dir",
    "_spec_signature",
    "_spec_to_dict",
]
