#!/usr/bin/env python
"""hook_enforce_concrete_port_types.py — PostToolUse (ADR-040 §3.6).

After a write touched ``<project>/blocks/*.py``, AST-parse the file and
scan ``InputPort(...)`` / ``OutputPort(...)`` constructor calls for
generic-``DataObject`` port types. Stderr-warn the agent so the next
turn corrects the type.

The live API on ``scieasy.blocks.base.ports`` is::

    @dataclass(kw_only=True)
    class Port:
        name: str
        accepted_types: list[type]
        ...

    class InputPort(Port): ...
    class OutputPort(Port): ...

A port is "generic" if ``accepted_types=[]`` (matches everything) or any
element of ``accepted_types`` is the bare ``DataObject`` name (the
top-of-tree root that defeats edge-time type checking).

The previous incarnation of this hook scanned for ``PortSpec(type=...)``
— a legacy shape that no longer exists in the live API. The mismatch
was identified in A1 + A3 Phase 3 audits (ADR-040) as F1.

Always exits 0 (PostToolUse cannot block).

# TODO(#1016): BlockRegistry runtime rejection of DataObject-typed ports
#   is the hard enforcement — out of scope per ADR-040 §3.10 (cross-cutting
#   policy decision affecting human-authored blocks too; deferred to a
#   future ADR if pursued).
#   Followup: https://github.com/zjzcpj/SciEasy/issues/1016.

# TODO(#1013): live TypeRegistry lookup (call mcp__scieasy__list_types
#   out-of-band and validate every accepted_types element against the
#   snapshot). The current implementation flags only the bare DataObject
#   case; typo'd / unregistered type names are deferred until the hook
#   can subprocess into the MCP layer safely.
#   Followup: https://github.com/zjzcpj/SciEasy/issues/1013.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path

_BLOCK_FILE_RE = re.compile(r"(?:^|/)blocks/[^/]+\.py$", re.IGNORECASE)

# Names recognised as port-constructor calls.  Extending this set is
# safe — extra entries simply broaden the hook's coverage.
_PORT_CTOR_NAMES = frozenset({"InputPort", "OutputPort", "Port"})


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _target_file(payload: dict) -> Path | None:
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response") or {}

    candidate: str = ""
    if tool_name == "mcp__scieasy__scaffold_block" and isinstance(tool_response, dict):
        candidate = str(tool_response.get("file_path") or tool_response.get("path") or "")
    if not candidate and isinstance(tool_input, dict):
        candidate = str(tool_input.get("file_path") or "")

    if not candidate:
        return None
    candidate_norm = candidate.replace("\\", "/")
    if not _BLOCK_FILE_RE.search(candidate_norm):
        return None

    path = Path(candidate)
    if not path.is_absolute():
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        if project_dir:
            path = Path(project_dir) / candidate
    if not path.is_file():
        return None
    return path


def _is_port_ctor(func: ast.expr) -> bool:
    """Match ``InputPort(...)`` / ``blocks.InputPort(...)`` / ``OutputPort(...)``."""
    if isinstance(func, ast.Name):
        return func.id in _PORT_CTOR_NAMES
    if isinstance(func, ast.Attribute):
        return func.attr in _PORT_CTOR_NAMES
    return False


def _accepted_type_elements(value: ast.expr) -> list[ast.expr]:
    """Return the element nodes of ``accepted_types=[...]`` (or empty list)."""
    if isinstance(value, (ast.List, ast.Tuple)):
        return list(value.elts)
    return []


def _type_element_name(node: ast.expr) -> str | None:
    """Best-effort extract a type name from an ``accepted_types=[...]`` element.

    Handles bare ``DataObject`` (``ast.Name``), attribute references
    ``core.DataObject`` (``ast.Attribute``), and string forms
    ``"DataObject"`` (``ast.Constant``).
    Returns ``None`` for shapes we can't resolve statically.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _scan_for_generic_ports(source: str) -> list[tuple[int, str, str]]:
    """Return list of ``(lineno, port_name_hint, reason)`` tuples.

    ``reason`` is one of:

    - ``"empty"`` — ``accepted_types=[]`` (matches anything).
    - ``"DataObject"`` — ``accepted_types`` contains the bare DataObject root.
    - ``"missing"`` — port constructor is called without an ``accepted_types``
      kwarg, which dataclass-validates at runtime but is worth flagging.
    """
    findings: list[tuple[int, str, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return findings

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_port_ctor(node.func):
            continue

        accepted_value: ast.expr | None = None
        name_hint = ""
        for kw in node.keywords:
            if kw.arg == "accepted_types":
                accepted_value = kw.value
            elif kw.arg == "name" and isinstance(kw.value, ast.Constant):
                name_hint = str(kw.value.value)

        if accepted_value is None:
            findings.append((node.lineno, name_hint or "<unknown>", "missing"))
            continue

        elements = _accepted_type_elements(accepted_value)
        if not elements:
            findings.append((node.lineno, name_hint or "<unknown>", "empty"))
            continue

        for element in elements:
            type_name = _type_element_name(element)
            if type_name == "DataObject":
                findings.append((node.lineno, name_hint or "<unknown>", "DataObject"))
                break

    return findings


def _format_message(target: Path, lineno: int, port_name: str, reason: str) -> str:
    common = (
        "DataObject is the type-tree root and reserved for genuinely "
        "generic blocks (SubWorkflowBlock, load_data/save_data IOBlocks, "
        "certain AppBlock patterns). Concrete types unlock preview "
        "rendering, edge-time type checking, lineage navigation, and "
        "AI-suggestion features."
    )
    if reason == "DataObject":
        return (
            f"Block at {target}:{lineno} declares port {port_name!r} with "
            "accepted_types=[DataObject]. Pick a concrete subclass via "
            "mcp__scieasy__list_types() (e.g. Image, DataFrame, Mask). "
            f"{common}"
        )
    if reason == "empty":
        return (
            f"Block at {target}:{lineno} declares port {port_name!r} with "
            "accepted_types=[] (matches anything — equivalent to DataObject). "
            f"{common}"
        )
    # reason == "missing"
    return (
        f"Block at {target}:{lineno} declares port {port_name!r} without "
        "an accepted_types kwarg. The Port dataclass requires it; this "
        "will likely raise at class definition / reload_blocks time. Add "
        "accepted_types=[<ConcreteType>]; pick from mcp__scieasy__list_types()."
    )


def main() -> int:
    payload = _read_payload()
    target = _target_file(payload)
    if target is None:
        return 0
    try:
        source = target.read_text(encoding="utf-8")
    except OSError:
        return 0
    findings = _scan_for_generic_ports(source)
    for lineno, port_name, reason in findings:
        print(_format_message(target, lineno, port_name, reason), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
