"""Committed gate-record validation for ADR-042 Addendum 1.

This package replaces the original single-file
``src/scistudio/qa/governance/gate_record.py`` (umbrella #1427, sub-issue
#1433). The decomposition follows the natural ADR-042 seam:

- ``paths``       — path classifiers + regex/constant primitives
- ``models``      — pydantic schema for ``GateRecord`` and its evidence
- ``io``          — disk read/write, git diff, slug + record-path resolution
- ``stages``      — per-subcommand mutators (start, plan, amend, docs, check,
                    sentrux, finalize)
- ``validation``  — ``validate_gate_record`` + ``check_*`` entry points used
                    by hooks and CI
- ``cli``         — argparse glue + ``main()`` dispatched from ``__main__``

The public import surface (``from scistudio.qa.governance.gate_record
import ...``) is preserved byte-identical, including the leading-underscore
helpers that ``tests/qa/test_gate_record.py`` reaches into. The private
imports below are intentional re-exports for back-compatibility; the
``noqa: F401`` markers suppress the unused-import lint without dragging
underscored names into ``__all__``.
"""

from __future__ import annotations

# Public CLI surface.
# Private re-exports for back-compat (tests import these by underscored name).
from scistudio.qa.governance.gate_record.cli import (
    _render_text,  # noqa: F401
    main,
)
from scistudio.qa.governance.gate_record.io import (
    _discover_gate_record,  # noqa: F401
    _git_lines,  # noqa: F401
    _load_record,  # noqa: F401
    _mark_stage,  # noqa: F401
    _parse_issue_numbers,  # noqa: F401
    _parse_key_values,  # noqa: F401
    _record_path,  # noqa: F401
    _record_task_kind,  # noqa: F401
    _slugify,  # noqa: F401
    _upsert_check,  # noqa: F401
    _write_record,  # noqa: F401
)

# Models / enums / canonical constants.
from scistudio.qa.governance.gate_record.models import (
    CANONICAL_STAGE_ORDER,
    POST_PR_STAGES,
    AdminLabelEvidence,
    CheckEvidence,
    CommitEvidence,
    FullAuditEvidence,
    GateRecord,
    GateStage,
    IssueRef,
    PullRequestEvidence,
    Scope,
    ScopeAmendment,
    SentruxEvidence,
    StageEvidence,
)

# Path primitives (regexes + constants).
from scistudio.qa.governance.gate_record.paths import (
    _GOVERNANCE_NON_TOUCH_PATTERNS,  # noqa: F401
    _GOVERNANCE_PATTERNS,  # noqa: F401
    _VITEST_NAME_SUFFIXES,  # noqa: F401
    CLOSING_KEYWORD_RE,
    IMPLEMENTATION_PATTERNS,
    IMPLEMENTATION_TASK_KINDS,
    NON_IMPLEMENTATION_PATTERNS,
    SLUG_RE,
    TRAILER_RE,
    VALID_OVERRIDE_LABELS,
    _is_governance_path,  # noqa: F401
    _is_implementation_path,  # noqa: F401
    _is_test_path,  # noqa: F401
    _match_path,  # noqa: F401
    _matches_any,  # noqa: F401
    _normalize_path,  # noqa: F401
    _sentrux_applies,  # noqa: F401
)

# Stage mutators (one per CLI subcommand).
from scistudio.qa.governance.gate_record.stages import (
    _CHANGELOG_PATHS,  # noqa: F401
    amend_record,
    check_record,
    docs_record,
    finalize_record,
    plan_record,
    sentrux_record,
    start_record,
)

# Validators consumed by hooks and CI.
from scistudio.qa.governance.gate_record.validation import (
    _closed_issue_numbers,  # noqa: F401
    _effective_exclude,  # noqa: F401
    _effective_include,  # noqa: F401
    _env_bypass_labels,  # noqa: F401
    _finding,  # noqa: F401
    _invalid_override_labels,  # noqa: F401
    _local_bypass_report,  # noqa: F401
    _report,  # noqa: F401
    _split_labels,  # noqa: F401
    _trailers,  # noqa: F401
    check_commit_msg,
    check_pr,
    check_pr_ready,
    check_pre_commit,
    check_pre_push,
    validate_gate_record,
)

__all__ = [
    "CANONICAL_STAGE_ORDER",
    "CLOSING_KEYWORD_RE",
    "IMPLEMENTATION_PATTERNS",
    "IMPLEMENTATION_TASK_KINDS",
    "NON_IMPLEMENTATION_PATTERNS",
    "POST_PR_STAGES",
    "SLUG_RE",
    "TRAILER_RE",
    "VALID_OVERRIDE_LABELS",
    "AdminLabelEvidence",
    "CheckEvidence",
    "CommitEvidence",
    "FullAuditEvidence",
    "GateRecord",
    "GateStage",
    "IssueRef",
    "PullRequestEvidence",
    "Scope",
    "ScopeAmendment",
    "SentruxEvidence",
    "StageEvidence",
    "amend_record",
    "check_commit_msg",
    "check_pr",
    "check_pr_ready",
    "check_pre_commit",
    "check_pre_push",
    "check_record",
    "docs_record",
    "finalize_record",
    "main",
    "plan_record",
    "sentrux_record",
    "start_record",
    "validate_gate_record",
]
