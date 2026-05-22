"""Path constants and classifiers for ADR-042 gate records.

Holds the path-matching primitives and policy classifiers (test vs.
implementation vs. governance vs. sentrux-applicable). Kept separate from
the pydantic models and validation logic so that other governance modules
(and tests) can import these helpers without dragging the full CLI surface.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable
from pathlib import Path

from scistudio.qa.governance.paths import is_gate_record_path

VALID_OVERRIDE_LABELS: frozenset[str] = frozenset(
    {
        "human-authored",
        "admin-approved:ai-override",
        "admin-approved:core-change",
        "admin-approved:merge",
    }
)

IMPLEMENTATION_TASK_KINDS: frozenset[str] = frozenset({"feature", "bugfix", "hotfix", "refactor", "maintenance"})

IMPLEMENTATION_PATTERNS: tuple[str, ...] = (
    "src/**",
    "packages/**",
    "frontend/**",
    "web/**",
    ".workflow/**",
    ".github/workflows/**",
    ".pre-commit-config.yaml",
    "scripts/hooks/**",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
)

NON_IMPLEMENTATION_PATTERNS: tuple[str, ...] = (
    "docs/**",
    "tests/**",
    "**/tests/**",
    "**/test_*.py",
    "**/*_test.py",
    ".workflow/records/**",
)

CLOSING_KEYWORD_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
    r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#(?P<number>\d+)\b",
    re.IGNORECASE,
)

TRAILER_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z-]*):\s*(?P<value>.+?)\s*$", re.MULTILINE)
SLUG_RE = re.compile(r"[^a-z0-9]+")

_VITEST_NAME_SUFFIXES: tuple[str, ...] = (
    ".test.ts",
    ".test.tsx",
    ".test.js",
    ".test.jsx",
    ".spec.ts",
    ".spec.tsx",
    ".spec.js",
    ".spec.jsx",
)
"""Co-located vitest filename suffixes. Vitest discovers ``Foo.test.tsx``
next to ``Foo.tsx`` rather than under a dedicated ``tests/`` tree, so the
gate-record classifier must recognise these alongside the pytest
conventions; otherwise a vitest-only PR is treated as touching an
implementation file with no test change (#1389)."""


# Paths under ``.workflow/records/**`` are gate-record evidence files that
# every AI-authored PR creates by design. They live under ``.workflow/`` but
# are not the governance policy itself, so treating them as governance touches
# would force every ordinary AI PR to flip ``governance_touch=true`` (#1340).
# Governance code (``src/scistudio/qa/governance/**``), governance config
# (``.workflow/active``, ``.workflow/hooks/**``), CI pipelines, and ADR-042
# itself remain governance touches.
_GOVERNANCE_PATTERNS: tuple[str, ...] = (
    ".workflow/**",
    ".github/workflows/**",
    ".pre-commit-config.yaml",
    "docs/adr/ADR-042.md",
    "docs/adr/ADR-042-addendum*.md",
    "src/scistudio/qa/governance/**",
)
_GOVERNANCE_NON_TOUCH_PATTERNS: tuple[str, ...] = (".workflow/records/**",)


def _normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _match_path(path: str, pattern: str) -> bool:
    normalized_path = _normalize_path(path)
    normalized_pattern = _normalize_path(pattern)
    if normalized_pattern.endswith("/**"):
        return normalized_path == normalized_pattern[:-3] or normalized_path.startswith(normalized_pattern[:-2])
    if normalized_pattern.endswith("/"):
        return normalized_path.startswith(normalized_pattern)
    return fnmatch.fnmatchcase(normalized_path, normalized_pattern) or normalized_path == normalized_pattern


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(_match_path(path, pattern) for pattern in patterns)


def _is_test_path(path: str) -> bool:
    normalized = _normalize_path(path)
    name = Path(normalized).name
    return (
        normalized.startswith("tests/")
        or "/tests/" in normalized
        # Codex P2 from PR #1396: also match top-level `__tests__/` (rare but
        # valid — e.g. a repo with a root-level `__tests__/` directory). Without
        # the prefix check, `__tests__/foo.tsx` was still classified as a
        # non-test path because `/__tests__/` substring requires a leading slash.
        or normalized.startswith("__tests__/")
        or "/__tests__/" in normalized
        or name.startswith("test_")
        or name.endswith("_test.py")
        or any(name.endswith(suffix) for suffix in _VITEST_NAME_SUFFIXES)
    )


def _is_implementation_path(path: str) -> bool:
    normalized = _normalize_path(path)
    if _matches_any(normalized, NON_IMPLEMENTATION_PATTERNS):
        return False
    return _matches_any(normalized, IMPLEMENTATION_PATTERNS)


def _sentrux_applies(path: str) -> bool:
    normalized = _normalize_path(path)
    # Gate-record evidence files live under .workflow/ but are per-PR audit
    # trail rows that every AI PR creates; they are not architectural
    # surface and must not force Sentrux evidence on records-only changes
    # (#1362, same pattern as core_change_guard / sentrux_gate / docs_landing).
    if is_gate_record_path(normalized):
        return False
    if normalized.startswith("docs/") and not normalized.startswith(("docs/adr/", "docs/specs/")):
        return False
    return _matches_any(
        normalized,
        (
            "src/**",
            "packages/**",
            ".workflow/**",
            ".github/workflows/**",
            ".pre-commit-config.yaml",
            "scripts/hooks/**",
            ".sentrux/**",
            "docs/adr/**",
            "docs/specs/**",
        ),
    )


def _is_governance_path(path: str) -> bool:
    normalized = _normalize_path(path)
    if _matches_any(normalized, _GOVERNANCE_NON_TOUCH_PATTERNS):
        return False
    return _matches_any(normalized, _GOVERNANCE_PATTERNS)
