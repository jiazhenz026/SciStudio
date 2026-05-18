"""pyright JSON -> SARIF 2.1.0.

pyright's ``--outputjson`` flag emits::

    {
      "version": "1.1.x",
      "time": "...",
      "generalDiagnostics": [
        {
          "file": "src/scieasy/foo.py",
          "severity": "error" | "warning" | "information",
          "message": "...",
          "rule": "reportGeneralTypeIssues",
          "range": {
            "start": {"line": 11, "character": 4},
            "end":   {"line": 11, "character": 20}
          }
        },
        ...
      ],
      "summary": {...}
    }

pyright line/character numbers are **0-indexed**; SARIF uses **1-indexed**
positions.  We add 1 to both before emitting.
"""

from __future__ import annotations

import json
from typing import Any

from ._common import collect_rules, make_log, make_result, make_run

_TOOL_NAME = "pyright"

_SEVERITY_MAP = {
    "error": "error",
    "warning": "warning",
    "information": "note",
    "hint": "note",
}


def convert_json(payload: str | dict[str, Any], *, tool_version: str | None = None) -> dict[str, Any]:
    """Convert pyright ``--outputjson`` blob to SARIF."""
    data: dict[str, Any] = payload if isinstance(payload, dict) else json.loads(payload)
    diagnostics = data.get("generalDiagnostics") or []
    results: list[dict[str, Any]] = []
    inferred_version = data.get("version") if tool_version is None else tool_version
    for record in diagnostics:
        results.append(_record_to_result(record))
    rules = collect_rules(results)
    run = make_run(
        tool_name=_TOOL_NAME,
        tool_version=inferred_version,
        rules=rules,
        results=results,
    )
    return make_log([run])


def _record_to_result(record: dict[str, Any]) -> dict[str, Any]:
    severity = str(record.get("severity") or "").lower()
    level = _SEVERITY_MAP.get(severity, "warning")
    rule_id = str(record.get("rule") or "pyright")
    file_path = str(record.get("file") or "")
    rng = record.get("range") or {}
    start = rng.get("start") if isinstance(rng, dict) else None
    line: int | None = None
    column: int | None = None
    if isinstance(start, dict):
        if "line" in start:
            line = int(start["line"]) + 1  # 0-indexed -> 1-indexed
        if "character" in start:
            column = int(start["character"]) + 1
    return make_result(
        rule_id=rule_id,
        level=level,
        message=str(record.get("message") or ""),
        file_path=file_path,
        line=line,
        column=column,
    )
