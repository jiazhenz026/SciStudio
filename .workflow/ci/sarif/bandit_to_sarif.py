"""bandit JSON -> SARIF 2.1.0 (with partialFingerprints adapter).

Bandit ships a native SARIF formatter (``bandit -f sarif``) but its
fingerprint algorithm differs from the one we want for the ratchet.  This
converter takes bandit's JSON output (``bandit -f json``) and emits SARIF
with our :func:`._common.compute_partial_fingerprint` -based fingerprints
so the same rule + file + message produces the same fingerprint across
runs.

bandit JSON shape::

    {
      "errors": [...],
      "metrics": {...},
      "results": [
        {
          "code": "...",
          "filename": "src/scieasy/foo.py",
          "issue_confidence": "HIGH",
          "issue_severity": "MEDIUM",
          "issue_text": "...",
          "line_number": 42,
          "line_range": [42],
          "test_id": "B101",
          "test_name": "assert_used",
          "col_offset": 4
        },
        ...
      ]
    }
"""

from __future__ import annotations

import json
from typing import Any

from ._common import collect_rules, make_log, make_result, make_run

_TOOL_NAME = "bandit"

_SEVERITY_MAP = {
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "note",
}


def convert_json(payload: str | dict[str, Any], *, tool_version: str | None = None) -> dict[str, Any]:
    """Convert bandit JSON to SARIF."""
    data: dict[str, Any] = payload if isinstance(payload, dict) else json.loads(payload)
    results: list[dict[str, Any]] = []
    for record in data.get("results") or []:
        results.append(_record_to_result(record))
    rules = collect_rules(results)
    run = make_run(
        tool_name=_TOOL_NAME,
        tool_version=tool_version,
        rules=rules,
        results=results,
    )
    return make_log([run])


def _record_to_result(record: dict[str, Any]) -> dict[str, Any]:
    severity = str(record.get("issue_severity") or "").upper()
    level = _SEVERITY_MAP.get(severity, "warning")
    rule_id = str(record.get("test_id") or "bandit")
    file_path = str(record.get("filename") or "")
    line_raw = record.get("line_number")
    column_raw = record.get("col_offset")
    line = int(line_raw) if line_raw is not None else None
    column = int(column_raw) + 1 if column_raw is not None else None
    return make_result(
        rule_id=rule_id,
        level=level,
        message=str(record.get("issue_text") or ""),
        file_path=file_path,
        line=line,
        column=column,
    )
