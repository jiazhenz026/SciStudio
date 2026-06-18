"""Single GitHub-native label vocabulary for ADR-042 Addendum 6 (§7.5/§7.8).

This module is the one source of the admin/bypass label vocabulary. The legacy
``admin-approved:ai-override`` label is migrated to ``admin-approved:bypass``
here and nowhere else owns the vocabulary.
"""

from __future__ import annotations

from typing import Final

# Bypass the AI gate workflow (CI verifies provenance). Replaces the legacy
# ``admin-approved:ai-override`` (Addendum 6 §4.2 label migration).
BYPASS_LABEL: Final[str] = "admin-approved:bypass"
# Protected core path authorization only (§7.8).
CORE_CHANGE_LABEL: Final[str] = "admin-approved:core-change"
# AI-assisted merge authorization only (§7.8).
MERGE_LABEL: Final[str] = "admin-approved:merge"
# Human AI-harness bypass (PR-level CI signal, not a CLI field) (§7.5).
HUMAN_AUTHORED_LABEL: Final[str] = "human-authored"

# Labels the ``--admin-label`` CLI flag accepts (§7.5 table).
ADMIN_LABELS: frozenset[str] = frozenset({BYPASS_LABEL, CORE_CHANGE_LABEL, MERGE_LABEL})

# Full valid label vocabulary including the CI-only ``human-authored`` signal.
VALID_LABELS: frozenset[str] = ADMIN_LABELS | {HUMAN_AUTHORED_LABEL}

# Labels that broadly bypass AI gate handling when CI verifies provenance.
BROAD_OVERRIDE_LABELS: frozenset[str] = frozenset({BYPASS_LABEL, HUMAN_AUTHORED_LABEL})

# GitHub permission levels that count as admin/maintainer for provenance.
ADMIN_PERMISSIONS: frozenset[str] = frozenset({"admin", "maintain", "write"})


def is_valid_admin_label(label: str) -> bool:
    """Return True if ``label`` is an accepted ``--admin-label`` value."""

    return label in ADMIN_LABELS


def invalid_admin_labels(labels: frozenset[str] | set[str] | list[str]) -> list[str]:
    """Return labels that are not part of the valid vocabulary."""

    return sorted(label for label in set(labels) if label not in VALID_LABELS)
