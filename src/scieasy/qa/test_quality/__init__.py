"""Phase 1F — test-quality enforcement tooling (ADR-043 §4).

This package implements the AST anti-pattern linter (``ast_lint``), the
commit-order test-first verifier (``test_first_check``), and the mutation-
runner shim (``mutation_runner``, Sub-PR 2). Schemas backing these tools
live in :mod:`scieasy.qa.schemas.test_quality` (Phase 1A) and findings
flow through :mod:`scieasy.qa.schemas.report`.

Public entry points (locked by ADR-043 §4.7 stub signatures):

* :func:`scieasy.qa.test_quality.ast_lint.check_test_file` — TC-1F.1.
* :func:`scieasy.qa.test_quality.test_first_check.verify_ordering` — TC-1F.2.
* :func:`scieasy.qa.test_quality.mutation_runner.run_targeted` — TC-1F.3 (Sub-PR 2).

The ``test-author`` skill at ``.claude/skills/test-author/SKILL.md``
(ADR-043 §4.4, Sub-PR 2) is the agent-facing counterpart to these tools.
"""

from __future__ import annotations

from scieasy.qa.test_quality.ast_lint import check_test_file
from scieasy.qa.test_quality.mutation_runner import run_targeted
from scieasy.qa.test_quality.test_first_check import verify_ordering

__all__ = [
    "check_test_file",
    "run_targeted",
    "verify_ordering",
]
