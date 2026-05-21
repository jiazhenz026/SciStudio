"""Shared path-matching helpers for governance checks.

Files under ``.workflow/records/**`` are per-PR gate-record evidence files
that every AI-authored PR creates by design. They live under ``.workflow/``
but they are not governance policy: they are audit trail rows.

Governance checks that operate on changed-file lists must exclude these
paths before testing membership in any protected/applicable/implementation
glob set. Without a single source of truth, each governance module
reimplements the same exclusion inconsistently — see #1316 (fixed
``mod_guard``), #1340 (fixed ``gate_record._is_governance_path``), and
#1362 (fixed ``core_change_guard``, ``sentrux_gate``, ``docs_landing``, and
``gate_record._sentrux_applies``) — every pass adds the exception in one or
two places and misses the rest.

Future governance checks that consult any ``.workflow/**`` glob MUST call
:func:`is_gate_record_path` to filter records out before the glob match.
"""

from __future__ import annotations

import fnmatch

GATE_RECORD_PATTERNS: tuple[str, ...] = (".workflow/records/**",)
"""Glob patterns identifying per-PR gate-record evidence files."""


def is_gate_record_path(path: str) -> bool:
    """Return True if ``path`` is a per-PR gate-record evidence file.

    Paths are normalised to POSIX separators before comparison so callers
    can pass either Windows or POSIX paths.
    """

    normalised = str(path).replace("\\", "/")
    return any(fnmatch.fnmatchcase(normalised, pattern) for pattern in GATE_RECORD_PATTERNS)
