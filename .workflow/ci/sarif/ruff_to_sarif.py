"""ruff JSON Lines -> SARIF 2.1.0.

Invocation in CI is pinned via ``ruff check --output-format=json-lines``
per ADR-042 §4.3 line 514.  Each line is a JSON object of the shape::

    {
      "code": "F401",
      "message": "'os' imported but unused",
      "filename": "src/scieasy/foo.py",
      "location": {"row": 12, "column": 1},
      "end_location": {"row": 12, "column": 9},
      "fix": null,
      "url": "https://docs.astral.sh/ruff/rules/unused-import",
      "noqa_row": null
    }

We map ``code -> ruleId``, ``message -> message.text``, ``filename ->
artifactLocation.uri``, and ``location.row/column -> region``.  All
records emerge at SARIF ``level=warning`` — ruff doesn't expose severity
in its JSON output beyond the rule code, and the ratchet wrapper does the
real gating.
"""

from __future__ import annotations

import json
from typing import Any

from ._common import collect_rules, make_log, make_result, make_run

_TOOL_NAME = "ruff"


def convert_lines(lines: list[str], *, tool_version: str | None = None) -> dict[str, Any]:
    """Convert ruff JSON-Lines output to a SARIF log.

    ``lines`` is the raw stdout of ``ruff check --output-format=json-lines``
    split on newlines (blanks ignored).
    """
    results: list[dict[str, Any]] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        record = json.loads(raw)
        results.append(_record_to_result(record))
    rules = collect_rules(results)
    run = make_run(
        tool_name=_TOOL_NAME,
        tool_version=tool_version,
        rules=rules,
        results=results,
    )
    return make_log([run])


def convert_text(text: str, *, tool_version: str | None = None) -> dict[str, Any]:
    """Convenience wrapper accepting the raw stdout blob."""
    return convert_lines(text.splitlines(), tool_version=tool_version)


def _record_to_result(record: dict[str, Any]) -> dict[str, Any]:
    rule_id = str(record.get("code") or "ruff")
    message = str(record.get("message") or "")
    file_path = str(record.get("filename") or "")
    loc = record.get("location") or {}
    line = loc.get("row") if isinstance(loc, dict) else None
    column = loc.get("column") if isinstance(loc, dict) else None
    return make_result(
        rule_id=rule_id,
        level="warning",
        message=message,
        file_path=file_path,
        line=int(line) if line is not None else None,
        column=int(column) if column is not None else None,
    )
