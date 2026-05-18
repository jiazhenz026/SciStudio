"""Shared SARIF 2.1.0 envelope + partialFingerprints helper.

Per ADR-042 §4.3 lines 504-507::

    SARIF unification — convert ruff/mypy/bandit/pyright JSON ->
    SARIF (community converters exist; zizmor emits SARIF natively).
    Upload to GitHub Code Scanning.  partialFingerprints gives free
    per-finding stable IDs + auto-close on PR diff.  This is the
    standard GitHub-native mechanism for "PR closes findings X, Y,
    Z, N remain."

We compute ``partialFingerprints.primaryLocationLineHash`` deterministically
from ``(rule_id, file_path, normalized_message, line)``.  GitHub Code
Scanning matches findings across runs on this fingerprint, so two runs of
the same tool on identical code MUST produce identical fingerprints — the
hash inputs are normalized accordingly (whitespace collapsed, line
numbers included only when stable).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_message(text: str) -> str:
    """Collapse whitespace runs to a single space; strip ends.

    Used to keep fingerprints stable across cosmetic message changes
    (some tools wrap long messages differently on different terminals).
    """
    return _WHITESPACE_RUN.sub(" ", text or "").strip()


def compute_partial_fingerprint(
    *,
    rule_id: str,
    file_path: str,
    normalized_message: str,
    line: int | None,
) -> str:
    """Compute a deterministic ``primaryLocationLineHash``.

    The output is a 32-character hex string (SHA-256 truncated to 128 bits)
    suitable for the ``partialFingerprints.primaryLocationLineHash`` SARIF
    field.

    Inputs are joined with ``\\x1f`` (ASCII unit separator) — a byte that
    cannot legitimately appear in any of the inputs, so collisions across
    different inputs are impossible by construction.

    Per GitHub Code Scanning docs, this fingerprint is what the matching
    algorithm uses to recognise "same finding, moved by N lines" across
    runs — so the inputs deliberately exclude *absolute* line numbers
    when ``line is None`` (some converters lack reliable line info; we
    still emit a fingerprint, just less precise).
    """
    parts = [
        rule_id or "",
        file_path or "",
        normalized_message or "",
        str(line) if line is not None else "",
    ]
    joined = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()[:32]


def make_result(
    *,
    rule_id: str,
    level: str,
    message: str,
    file_path: str,
    line: int | None,
    column: int | None = None,
) -> dict[str, Any]:
    """Build a single SARIF ``result`` object with partialFingerprints set.

    ``level`` must be one of ``"none"``, ``"note"``, ``"warning"``, or
    ``"error"`` per SARIF 2.1.0.  Callers should map tool-specific
    severities to this set.
    """
    normalized = normalize_message(message)
    fp = compute_partial_fingerprint(
        rule_id=rule_id,
        file_path=file_path,
        normalized_message=normalized,
        line=line,
    )
    physical_location: dict[str, Any] = {
        "artifactLocation": {"uri": file_path},
    }
    if line is not None:
        region: dict[str, Any] = {"startLine": line}
        if column is not None:
            region["startColumn"] = column
        physical_location["region"] = region
    return {
        "ruleId": rule_id,
        "level": level,
        "message": {"text": normalized},
        "locations": [{"physicalLocation": physical_location}],
        "partialFingerprints": {"primaryLocationLineHash": fp},
    }


def make_run(
    *,
    tool_name: str,
    tool_version: str | None,
    rules: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a single SARIF ``run`` object (one tool invocation)."""
    driver: dict[str, Any] = {"name": tool_name, "rules": rules}
    if tool_version is not None:
        driver["version"] = tool_version
    return {
        "tool": {"driver": driver},
        "results": results,
    }


def make_log(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the top-level SARIF log envelope (one or more runs)."""
    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": runs,
    }


def collect_rules(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive a SARIF ``rules`` array from a list of results.

    SARIF requires the rule metadata to live under ``tool.driver.rules``;
    repeating it inside each result would inflate the file.  This helper
    walks the results and produces a deduplicated ``rules`` array suitable
    for direct insertion.
    """
    seen: dict[str, dict[str, Any]] = {}
    for r in results:
        rid = r.get("ruleId")
        if not rid or rid in seen:
            continue
        seen[rid] = {"id": rid, "name": rid}
    return list(seen.values())
