"""Doc-length cap enforcement (ADR-044 §4.1 / §4.3).

Files under ``docs/{contributing,user,prod-agent,doc-guide}/`` are
capped at "2 letter pages", measured deterministically via two
source-file metrics (per audit fix P2.1):

* non-empty source lines (frontmatter excluded) ≤ 120 (error >120,
  warning >100);
* word count (frontmatter + fenced code blocks excluded) ≤ 600 (error).

Auto-generated files (``generation: auto``) are exempt because their
length is determined by the generator, not the author. ADR / spec /
architecture documents are also exempt (the cap is for procedural docs
only).

The ``length_exception_reason`` frontmatter escape hatch from §4.5 is
honoured: when set, the error is downgraded to INFO (with a note about
the 30-day auto-expiry). The expiry semantics themselves live in a
later 1F consistency-lint TC; this lint just respects the marker.

References
----------
ADR-044 §4.1 — statement.
ADR-044 §4.3 — algorithm (authoritative source).
ADR-044 §4.5 — exemption mechanism.
ADR-044 §11.5 — entry-point signature contract.

Deferred work
-------------
* 30-day auto-expiry of length exceptions — TODO(#1154-ext-expiry).

# TODO(#1154-ext): wire 30-day auto-expiry on length_exception_reason
#   Out of scope per ADR-044 §4.5 (expiry mechanism); the lint here
#   only honours the marker.
#   Followup: open as 1F consistency-lint follow-up.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from scieasy.qa.schemas.report import Finding, Severity

__all__ = [
    "ERROR_LINE_CAP",
    "ERROR_WORD_CAP",
    "WARNING_LINE_CAP",
    "check",
    "count_metrics",
]

#: Source-line cap for errors (ADR-044 §4.3).
ERROR_LINE_CAP = 120

#: Source-line cap that triggers a warning before the hard error.
WARNING_LINE_CAP = 100

#: Word-count cap (frontmatter + fenced code stripped).
ERROR_WORD_CAP = 600

#: Path prefixes inside ``docs/`` that the cap applies to.
_COVERED_PREFIXES = ("contributing/", "user/", "prod-agent/", "doc-guide/")


def check(repo_root: Path | None = None) -> list[Finding]:
    """Verify covered docs satisfy the §4.3 source-line + word caps.

    Skipped scenarios:

    * Files outside ``docs/{contributing,user,prod-agent,doc-guide}/``.
    * Frontmatter ``generation: auto`` (cap doesn't apply to AG output).
    * Missing repo / docs directories (empty result).
    """
    repo_root = repo_root or Path.cwd()
    docs_dir = repo_root / "docs"
    findings: list[Finding] = []
    if not docs_dir.is_dir():
        return findings

    for path in sorted(docs_dir.rglob("*.md")):
        rel_path = path.relative_to(repo_root).as_posix()
        if not _covered(rel_path):
            continue
        frontmatter, text = _split_frontmatter(path)
        if frontmatter is None:
            continue
        if frontmatter.get("generation") == "auto":
            continue

        line_count, word_count = count_metrics(text)
        exception_reason = frontmatter.get("length_exception_reason")

        if line_count > ERROR_LINE_CAP:
            severity = Severity.INFO if exception_reason else Severity.ERROR
            findings.append(
                Finding(
                    rule_id="doc-length-lint.line-cap-exceeded",
                    severity=severity,
                    file=rel_path,
                    message=_line_message(line_count, exception_reason),
                )
            )
        elif line_count > WARNING_LINE_CAP:
            findings.append(
                Finding(
                    rule_id="doc-length-lint.approaching-line-cap",
                    severity=Severity.WARNING,
                    file=rel_path,
                    message=(
                        f"document has {line_count} non-empty source lines; "
                        f"approaching the {ERROR_LINE_CAP}-line hard cap "
                        "per ADR-044 §4.3 — consider splitting before the next edit."
                    ),
                )
            )

        if word_count > ERROR_WORD_CAP:
            severity = Severity.INFO if exception_reason else Severity.ERROR
            findings.append(
                Finding(
                    rule_id="doc-length-lint.word-cap-exceeded",
                    severity=severity,
                    file=rel_path,
                    message=_word_message(word_count, exception_reason),
                )
            )

    return findings


def count_metrics(body_text: str) -> tuple[int, int]:
    """Count non-empty source lines + words (frontmatter assumed stripped).

    Source lines count every non-empty line of the body. Word count
    strips fenced code blocks (````` … `````) before splitting on whitespace.
    """
    line_count = sum(1 for line in body_text.splitlines() if line.strip())
    text_for_words = _strip_fenced_code(body_text)
    word_count = len(text_for_words.split())
    return line_count, word_count


# --------------------------------------------------------------------------- #
# Internal helpers                                                            #
# --------------------------------------------------------------------------- #


def _covered(rel_path: str) -> bool:
    """Return True iff the path falls inside one of the four covered categories."""
    if not rel_path.startswith("docs/"):
        return False
    tail = rel_path.removeprefix("docs/")
    return any(tail.startswith(prefix) for prefix in _COVERED_PREFIXES)


def _split_frontmatter(path: Path) -> tuple[dict[str, Any] | None, str]:
    """Return ``(frontmatter_dict, body_text)``; ``frontmatter_dict`` ``None`` if absent."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, ""
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None, parts[2]
    if not isinstance(data, dict):
        return None, parts[2]
    return data, parts[2]


_FENCED_CODE_RE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)


def _strip_fenced_code(text: str) -> str:
    """Remove fenced ````` … ````` blocks for word counting."""
    return _FENCED_CODE_RE.sub("", text)


def _line_message(line_count: int, exception_reason: str | None) -> str:
    if exception_reason:
        return (
            f"document has {line_count} non-empty source lines (cap "
            f"{ERROR_LINE_CAP}); ``length_exception_reason`` honoured: "
            f"{exception_reason!r}. The exception auto-expires 30 days after "
            "its issue date — see ADR-044 §4.5."
        )
    return (
        f"document has {line_count} non-empty source lines, exceeding the "
        f"{ERROR_LINE_CAP}-line hard cap per ADR-044 §4.3. Split into "
        "per-procedure files, or add ``length_exception_reason`` + "
        "``length_exception_issue`` to the frontmatter."
    )


def _word_message(word_count: int, exception_reason: str | None) -> str:
    if exception_reason:
        return (
            f"document has {word_count} words (cap {ERROR_WORD_CAP}); "
            f"``length_exception_reason`` honoured: {exception_reason!r}."
        )
    return (
        f"document has {word_count} words, exceeding the {ERROR_WORD_CAP}-word "
        "hard cap per ADR-044 §4.3. Split into per-procedure files, or add "
        "``length_exception_reason`` + ``length_exception_issue`` to the "
        "frontmatter."
    )
