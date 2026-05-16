#!/usr/bin/env python
"""hook_enforce_concrete_port_types.py — PostToolUse (ADR-040 §3.6).

After a write touched ``<project>/blocks/*.py``, AST-parse the file and
scan for generic-typed ports (``PortSpec(type="DataObject")`` or the
bare ``type=DataObject`` Name reference). Stderr-warn the agent so the
next turn corrects the type.

Always exits 0 (PostToolUse cannot block).

# TODO(#1016): BlockRegistry runtime rejection of DataObject-typed ports
#   is the hard enforcement — out of scope per ADR-040 §3.10 (cross-cutting
#   policy decision affecting human-authored blocks too; deferred to a
#   future ADR if pursued).
#   Followup: https://github.com/zjzcpj/SciEasy/issues/1016.

# TODO(#1013): live TypeRegistry lookup (call mcp__scieasy__list_types
#   out-of-band and validate every PortSpec(type=<X>) against the snapshot).
#   The current implementation flags only the bare DataObject case;
#   typo'd / unregistered type names are deferred until the hook can
#   subprocess into the MCP layer safely.
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


def _scan_for_generic_ports(source: str) -> list[tuple[int, str]]:
    """Return list of (lineno, port_name_hint) tuples flagged as generic."""
    findings: list[tuple[int, str]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return findings

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Identify PortSpec(...) calls (by attribute name; covers both
        # ``PortSpec(...)`` and ``blocks.PortSpec(...)``).
        func = node.func
        if isinstance(func, ast.Name):
            if func.id != "PortSpec":
                continue
        elif isinstance(func, ast.Attribute):
            if func.attr != "PortSpec":
                continue
        else:
            continue

        # Extract the type= kwarg.
        type_value: ast.expr | None = None
        name_hint = ""
        for kw in node.keywords:
            if kw.arg == "type":
                type_value = kw.value
            elif kw.arg == "name" and isinstance(kw.value, ast.Constant):
                name_hint = str(kw.value.value)

        if type_value is None:
            continue

        is_generic = False
        if (isinstance(type_value, ast.Constant) and type_value.value == "DataObject") or (
            isinstance(type_value, ast.Name) and type_value.id == "DataObject"
        ):
            is_generic = True

        if is_generic:
            findings.append((node.lineno, name_hint or "<unknown>"))

    return findings


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
    for lineno, port_name in findings:
        print(
            f"Block at {target}:{lineno} declares port '{port_name}' with "
            "generic DataObject. This degrades preview & edge-time "
            "type-check. Call mcp__scieasy__list_types and pick a concrete "
            "type; DataObject is reserved for SubWorkflowBlock and generic "
            "AppBlock-class blocks.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
