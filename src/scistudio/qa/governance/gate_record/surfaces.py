"""Single file-surface classifier for the ADR-042 Addendum 6 gate ledger.

This module is the ONE authority for path/surface questions the evaluator and
every guard calculator ask: is a path a test, implementation, governance,
protected-core, frontend, packaging, workflow/CI, docs, governed-doc, or
sentrux-applicable surface? It resolves the historical ``_sentrux_applies``
(excluded ``tests/**``) vs ``sentrux_gate.sentrux_applies_to_changes``
(included ``tests/**``) divergence into a single ``sentrux_applies`` predicate
(spec §4.1). The CI-inclusive definition is canonical; local and CI agree.

It also absorbs ``paths.is_gate_record_path`` so guards no longer reimplement
the per-PR-records exclusion (#1316/#1340/#1362).
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable
from pathlib import Path

# ---------------------------------------------------------------------------
# Regex + slug primitives (ported from gate_record/paths.py).
# ---------------------------------------------------------------------------

CLOSING_KEYWORD_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
    r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#(?P<number>\d+)\b",
    re.IGNORECASE,
)
TRAILER_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z-]*):\s*(?P<value>.+?)\s*$", re.MULTILINE)
SLUG_RE = re.compile(r"[^a-z0-9]+")

# Implementation task kinds (added ``guided`` per Addendum 6 §4.2). ``guided``
# is an implementation mode that may touch any production surface.
IMPLEMENTATION_TASK_KINDS: frozenset[str] = frozenset(
    {"feature", "bugfix", "hotfix", "refactor", "maintenance", "guided"}
)

# ---------------------------------------------------------------------------
# Surface glob sets.
# ---------------------------------------------------------------------------

GATE_RECORD_PATTERNS: tuple[str, ...] = (".workflow/records/**",)

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

# Protected core/runtime/engine paths (Addendum 6 §7.8). Touching any of these
# escalates the strictness tier to Tier 1 and requires admin-approved
# authorization for AI-authored work.
PROTECTED_CORE_PATTERNS: tuple[str, ...] = (
    "src/scistudio/core/**",
    "src/scistudio/engine/**",
    "src/scistudio/blocks/**",
    "src/scistudio/workflow/**",
    "src/scistudio/utils/**",
)

# Governance surfaces (Addendum 6 §7.8). Editing these is a governance touch
# that requires ``governance_touch`` + owner review. Expanded from the legacy
# gate_record._GOVERNANCE_PATTERNS to include the full §7.8 list, including
# ``docs/ai-developer/**``.
GOVERNANCE_PATTERNS: tuple[str, ...] = (
    "AGENTS.md",
    ".agents/**",
    ".claude/**",
    ".codex/**",
    ".gemini/**",
    ".github/workflows/**",
    ".workflow/**",
    ".pre-commit-config.yaml",
    "pyproject.toml",
    "pyrightconfig.json",
    ".codespellrc",
    ".yamllint",
    ".markdownlint.yaml",
    "MAINTAINERS",
    "docs/adr/ADR-042.md",
    "docs/adr/ADR-042-addendum*.md",
    "docs/ai-developer/**",
    "scripts/audit/**",
    "src/scistudio/qa/**",
)
# Per-PR gate-record evidence is not itself governance policy (#1340).
GOVERNANCE_NON_TOUCH_PATTERNS: tuple[str, ...] = (".workflow/records/**",)

# Governed-doc surfaces: AI-developer workflow docs treated as governance docs
# (Addendum 6 §7.8).
GOVERNED_DOCS_PATTERNS: tuple[str, ...] = ("docs/ai-developer/**",)

# Architecture/spec/ADR doc surfaces (full-audit + workflow-gate docs checks).
ARCHITECTURE_DOC_PATTERNS: tuple[str, ...] = (
    "docs/adr/**",
    "docs/specs/**",
    "docs/architecture/**",
)

FRONTEND_PATTERNS: tuple[str, ...] = ("frontend/**",)

PACKAGING_PATTERNS: tuple[str, ...] = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "MANIFEST.in",
    "frontend/dist/**",
    "src/scistudio/**/static/**",
)

WORKFLOW_CI_PATTERNS: tuple[str, ...] = (
    ".github/workflows/**",
    ".pre-commit-config.yaml",
    "scripts/hooks/**",
    ".workflow/**",
)

# Sentrux applicability — the CI-inclusive canonical definition (includes
# ``tests/**``). Single source of truth resolving the §4.1 asymmetry.
SENTRUX_APPLICABLE_PATTERNS: tuple[str, ...] = (
    "src/**",
    "tests/**",
    "packages/**",
    "frontend/**",
    "scripts/hooks/**",
    ".github/workflows/**",
    ".workflow/**",
    ".sentrux/**",
    ".pre-commit-config.yaml",
    "docs/adr/**",
    "docs/specs/**",
    "docs/architecture/**",
)

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


def normalize_path(path: str) -> str:
    """Normalize to POSIX-relative form, stripping leading ``./``."""

    normalized = str(path).replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def match_path(path: str, pattern: str) -> bool:
    """Match ``path`` against a glob ``pattern`` with ``/**`` recursion."""

    normalized_path = normalize_path(path)
    normalized_pattern = normalize_path(pattern)
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3]
        return normalized_path == prefix or normalized_path.startswith(prefix + "/")
    if normalized_pattern.endswith("/"):
        return normalized_path.startswith(normalized_pattern)
    return fnmatch.fnmatchcase(normalized_path, normalized_pattern) or normalized_path == normalized_pattern


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    """Return True when ``path`` matches any glob in ``patterns``."""

    return any(match_path(path, pattern) for pattern in patterns)


def is_gate_record_path(path: str) -> bool:
    """Return True if ``path`` is a per-PR gate-record evidence file."""

    return matches_any(path, GATE_RECORD_PATTERNS)


def is_test_path(path: str) -> bool:
    """Return True for pytest or co-located vitest test paths."""

    normalized = normalize_path(path)
    name = Path(normalized).name
    return (
        normalized.startswith("tests/")
        or "/tests/" in normalized
        or normalized.startswith("__tests__/")
        or "/__tests__/" in normalized
        or name.startswith("test_")
        or name.endswith("_test.py")
        or any(name.endswith(suffix) for suffix in _VITEST_NAME_SUFFIXES)
    )


def is_implementation_path(path: str) -> bool:
    """Return True for non-test, non-docs implementation/config surfaces."""

    normalized = normalize_path(path)
    if matches_any(normalized, NON_IMPLEMENTATION_PATTERNS):
        return False
    return matches_any(normalized, IMPLEMENTATION_PATTERNS)


def is_protected_core_path(path: str) -> bool:
    """Return True for protected core/runtime/engine paths (§7.8)."""

    normalized = normalize_path(path)
    if is_gate_record_path(normalized):
        return False
    return matches_any(normalized, PROTECTED_CORE_PATTERNS)


def is_governance_path(path: str) -> bool:
    """Return True for governance surfaces (§7.8). Gate records excluded."""

    normalized = normalize_path(path)
    if matches_any(normalized, GOVERNANCE_NON_TOUCH_PATTERNS):
        return False
    return matches_any(normalized, GOVERNANCE_PATTERNS)


def is_governed_doc_path(path: str) -> bool:
    """Return True for AI-developer workflow docs (governance docs, §7.8)."""

    return matches_any(path, GOVERNED_DOCS_PATTERNS)


def is_architecture_doc_path(path: str) -> bool:
    """Return True for ADR/spec/architecture docs."""

    return matches_any(path, ARCHITECTURE_DOC_PATTERNS)


def is_docs_path(path: str) -> bool:
    """Return True for any ``docs/**`` surface."""

    return normalize_path(path).startswith("docs/")


def is_frontend_path(path: str) -> bool:
    """Return True for frontend surfaces."""

    return matches_any(path, FRONTEND_PATTERNS)


def is_packaging_path(path: str) -> bool:
    """Return True for packaging/build/release surfaces."""

    return matches_any(path, PACKAGING_PATTERNS)


def is_workflow_ci_path(path: str) -> bool:
    """Return True for GitHub workflow / hook / pre-commit surfaces."""

    normalized = normalize_path(path)
    if is_gate_record_path(normalized):
        return False
    return matches_any(normalized, WORKFLOW_CI_PATTERNS)


def sentrux_applies(path: str) -> bool:
    """Return True when Sentrux evidence applies to ``path`` (§4.1).

    CI-inclusive canonical predicate: includes ``tests/**``. Gate-record
    evidence and ordinary non-ADR/non-spec docs are excluded.
    """

    normalized = normalize_path(path)
    if is_gate_record_path(normalized):
        return False
    if normalized.startswith("docs/") and not matches_any(normalized, ARCHITECTURE_DOC_PATTERNS):
        return False
    return matches_any(normalized, SENTRUX_APPLICABLE_PATTERNS)


def sentrux_applies_to_changes(changed_files: Iterable[str]) -> bool:
    """Return True when any changed file is sentrux-applicable."""

    return any(sentrux_applies(path) for path in changed_files)
