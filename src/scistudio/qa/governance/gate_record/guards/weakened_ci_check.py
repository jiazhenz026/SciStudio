"""weakened_ci_check calculator (ADR-042 Addendum 6 spec §4).

Produces: removal of required check tokens or addition of CI-weakening
constructs in governed CI/pre-commit/pyproject diffs.

Ported from the legacy ``weakened_ci_check`` (deleted on this branch). Two
changes per the digest/spec:

1. The ``SCISTUDIO_GATE_BYPASS_LABELS`` environment-variable bypass channel is
   removed (authorization flows through the ledger; ``mod_guard`` owns the
   governance-authorization decision).
2. The required-removal token set is derived from the CI command graph
   (``checks.CHECK_CATALOG``) rather than a hand-maintained static list, so it
   tracks the single CI snapshot the evaluator already uses for check selection.

The guard does NOT run git. The evaluator supplies the governed unified diff via
``GuardInputs.extras['governed_diff_text']`` (a unified-diff string) or
``extras['governed_diff_lines']`` (pre-parsed ``(path, sign, text)`` triples).
When no governed diff is supplied, there is nothing to scan and the guard
passes, recording the absence in its summary.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from scistudio.qa.governance.gate_record import checks, surfaces
from scistudio.qa.governance.gate_record.guards import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import source_sha
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

# Governed config surfaces whose diffs are scanned for weakening.
GOVERNED_PATTERNS: tuple[str, ...] = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".pre-commit-config.yaml",
    "pyproject.toml",
)

# Intrinsic pre-commit / shell-runner tokens not represented as CI catalog
# commands but that the repository's governed configuration must not drop.
_INTRINSIC_REMOVAL_TOKENS: tuple[tuple[str, str], ...] = (
    ("pytest-timeout", "--timeout=60"),
    ("shell-timeout", "timeout 600"),
    ("detect-private-key", "detect-private-key"),
    ("check-merge-conflict", "check-merge-conflict"),
    ("check-yaml", "check-yaml"),
    ("check-json", "check-json"),
)

ADDED_WEAKENING_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "continue-on-error",
        re.compile(r"\bcontinue-on-error\s*:\s*true\b", re.IGNORECASE),
        "added continue-on-error: true to governed CI/pre-commit configuration",
    ),
    (
        "disabled-if",
        re.compile(r"\bif\s*:\s*(?:false|\${{\s*false\s*}})\b", re.IGNORECASE),
        "added an always-false conditional to governed CI/pre-commit configuration",
    ),
    (
        "no-verify",
        # NOTE: the legacy port used ``\b(?:--no-verify|SKIP=)\b``, but a leading
        # ``\b`` never matches before ``--`` (both sides non-word), so the common
        # ``--no-verify`` form slipped through. Anchored without the broken
        # leading boundary so the realistic bypass form is detected.
        re.compile(r"(?:--no-verify|\bSKIP=)"),
        "added a local hook bypass mechanism to governed configuration",
    ),
    (
        "ignore-failures",
        re.compile(r"\b(?:\|\|\s*true|exit\s+0)\b"),
        "added a failure-suppression command to governed configuration",
    ),
)


def _required_removal_tokens() -> list[tuple[str, str]]:
    """Derive the required-token set from the CI graph + intrinsic tokens.

    Each CI catalog command contributes its command head (e.g. ``ruff check``,
    ``mypy``, ``lint-imports``) as a token that must not be removed from
    governed configuration. This replaces the legacy hand-maintained list.
    """

    tokens: dict[str, str] = {}
    for name, spec in checks.CHECK_CATALOG.items():
        if not spec.command:
            continue
        # Use the first two argv parts as a stable, human-meaningful token
        # (e.g. "ruff check", "ruff format", "mypy", "lint-imports").
        head = " ".join(spec.command[:2]) if len(spec.command) >= 2 else spec.command[0]
        tokens.setdefault(name, head)
    for suffix, token in _INTRINSIC_REMOVAL_TOKENS:
        tokens.setdefault(suffix, token)
    return sorted(tokens.items())


def _is_governed(path: str) -> bool:
    return surfaces.matches_any(path, GOVERNED_PATTERNS)


def _parse_unified_diff(diff_text: str) -> list[tuple[str, str, str]]:
    """Parse a unified diff into ``(path, sign, text)`` triples for governed files."""

    lines: list[tuple[str, str, str]] = []
    current_path: str | None = None
    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            parts = raw_line.split()
            current_path = parts[3][2:] if len(parts) >= 4 and parts[3].startswith("b/") else None
            continue
        if current_path is None or not _is_governed(current_path):
            continue
        if raw_line.startswith(("+++", "---")):
            continue
        if raw_line.startswith("+"):
            lines.append((current_path, "+", raw_line[1:].strip()))
        elif raw_line.startswith("-"):
            lines.append((current_path, "-", raw_line[1:].strip()))
    return lines


def _governed_diff_lines(extras: Mapping[str, Any]) -> tuple[list[tuple[str, str, str]], bool]:
    """Extract governed diff lines from the evaluator-supplied extras.

    Returns ``(lines, supplied)`` where ``supplied`` is True when the evaluator
    attached governed diff data (so a genuine empty diff is distinguishable from
    a missing supply).
    """

    raw_lines = extras.get("governed_diff_lines")
    if isinstance(raw_lines, Sequence) and not isinstance(raw_lines, str):
        parsed: list[tuple[str, str, str]] = []
        for item in raw_lines:
            if isinstance(item, Sequence) and not isinstance(item, str) and len(item) == 3:
                path, sign, text = (str(part) for part in item)
                if _is_governed(path):
                    parsed.append((path, sign, text))
        return parsed, True
    diff_text = extras.get("governed_diff_text")
    if isinstance(diff_text, str):
        return _parse_unified_diff(diff_text), True
    return [], False


def check(inputs: GuardInputs) -> AuditReport:
    """Fail when governed diffs remove required checks or add weakening."""

    lines, supplied = _governed_diff_lines(inputs.extras)
    required_tokens = _required_removal_tokens()
    findings: list[Finding] = []

    for path, sign, text in lines:
        lowered = text.lower()
        if sign == "-":
            for rule_suffix, token in required_tokens:
                if token.lower() in lowered:
                    findings.append(
                        Finding(
                            rule_id=f"weakened-ci.removed-{rule_suffix}",
                            severity=Severity.ERROR,
                            file=path,
                            message=f"removed required CI/pre-commit check token: {token}",
                            git_evidence=f"-{text}",
                        )
                    )
        elif sign == "+":
            for rule_suffix, pattern, message in ADDED_WEAKENING_PATTERNS:
                if pattern.search(text):
                    findings.append(
                        Finding(
                            rule_id=f"weakened-ci.added-{rule_suffix}",
                            severity=Severity.ERROR,
                            file=path,
                            message=message,
                            git_evidence=f"+{text}",
                        )
                    )

    return AuditReport(
        tool="weakened_ci_check",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=source_sha(inputs.repo_root),
        findings=findings,
        summary={
            "diff_lines_checked": len(lines),
            "governed_diff_supplied": supplied,
            "governed_patterns": list(GOVERNED_PATTERNS),
            "mode": inputs.mode,
        },
    )
