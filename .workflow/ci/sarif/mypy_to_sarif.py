"""mypy text output -> SARIF 2.1.0.

mypy does not have an official JSON output mode (as of 1.x); the standard
CI invocation per ADR-042 §4.3 line 510-511 is::

    mypy --soft-error-limit=-1 ...

The default text format is one error per line::

    src/scieasy/foo.py:12: error: Incompatible types ...  [assignment]
    src/scieasy/foo.py:18: note: Revealed type is ...
    Found 1 error in 1 file (checked 1 source file)

We parse this line-by-line.  ``error`` rows map to SARIF ``level=error``,
``warning`` rows to ``level=warning``, and ``note`` rows are dropped (they
are advisory companions to a preceding error and don't represent a
distinct finding).  Summary lines (``Found N error...``) are ignored.

The rule_id is taken from the trailing ``[bracketed]`` tag when present
(``[assignment]``, ``[arg-type]``, etc.), falling back to ``"mypy"`` when
absent.
"""

from __future__ import annotations

import re
from typing import Any

from ._common import collect_rules, make_log, make_result, make_run

_TOOL_NAME = "mypy"

# Example: src/scieasy/foo.py:12:5: error: ...  [assignment]
# Example: src/scieasy/foo.py:12: error: ...
_LINE_RE = re.compile(
    r"^(?P<path>[^:\n]+):(?P<line>\d+)(?::(?P<col>\d+))?:\s+"
    r"(?P<severity>error|warning|note):\s+(?P<message>.+?)"
    r"(?:\s+\[(?P<rule>[\w-]+)\])?$",
)


def convert_text(text: str, *, tool_version: str | None = None) -> dict[str, Any]:
    """Convert mypy stdout to SARIF."""
    results: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        result = _parse_line(raw_line)
        if result is not None:
            results.append(result)
    rules = collect_rules(results)
    run = make_run(
        tool_name=_TOOL_NAME,
        tool_version=tool_version,
        rules=rules,
        results=results,
    )
    return make_log([run])


def _parse_line(line: str) -> dict[str, Any] | None:
    m = _LINE_RE.match(line.rstrip())
    if not m:
        return None
    severity = m.group("severity")
    if severity == "note":
        return None
    level = "error" if severity == "error" else "warning"
    rule_id = m.group("rule") or "mypy"
    col_raw = m.group("col")
    return make_result(
        rule_id=rule_id,
        level=level,
        message=m.group("message"),
        file_path=m.group("path"),
        line=int(m.group("line")),
        column=int(col_raw) if col_raw else None,
    )
