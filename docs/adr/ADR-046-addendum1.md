---
adr: 46
addendum: 1
title: "Path D Class-Binding Extends To Thin Subprocess-Wrapper Classes"
status: Accepted
date_created: 2026-05-22
date_accepted: 2026-05-22
date_superseded: null

supersedes: []
superseded_by: null
related: [46, 47, 28]
closes_issues: [1472]
tracking_issue: 1465

is_code_implementation: false
governs:
  modules:
    - scistudio.core.versioning.git_engine
  contracts:
    - scistudio.core.versioning.git_engine.GitEngine
    - scistudio.core.versioning.git_engine.HeadState
  entry_points: []
  files:
    - docs/adr/ADR-046-addendum1.md
    - src/scistudio/core/versioning/git_engine.py
    - src/scistudio/core/versioning/_commit_ops.py
    - src/scistudio/core/versioning/_history_ops.py
    - src/scistudio/core/versioning/_branch_ops.py
    - src/scistudio/core/versioning/_status_ops.py
    - src/scistudio/core/versioning/_merge_ops.py
  excludes:
    - tests/**
    - docs/audit/**

tests:
  - tests/core/test_git_engine.py
  - tests/core/versioning/test_git_engine_package_layout.py
agent_editable: false
assisted_by:
  - "claude:opus-4-7"
phase: planning
tags:
  - god-file-refactor
  - path-d
  - class-binding
  - umbrella-1427
owner: "@jiazhenz026"
co_authors: []
language_source: en
translations: []
---

# ADR-046 Addendum 1: Path D Class-Binding Extends To Thin Subprocess-Wrapper Classes

## 1. Decision Summary

ADR-046 documents Path D for `DAGScheduler`, which had ~30 module-level helpers
ready to be extracted alongside class-binding for the remaining bound methods.
ADR-047 documents the same Path D pattern for `BlockRegistry`. This Addendum 1
confirms the **Path D class-binding scheme** (extract bound-method bodies into
private module-level functions; the class binds them via class-body assignment)
applies equally well to thin subprocess-wrapper classes like `GitEngine` —
files that are "all class, no module helpers" — without needing a separate
full ADR per instance.

### 1.1 Problems Addressed

| Problem | Current pain | Response |
|---|---|---|
| `git_engine.py` is 849 LOC of single `GitEngine` class (no module-level helpers to extract) | The helper-extraction half of Path D (Phase 2 PR #1460) has nothing to apply | Apply ADR-046's class-binding half: extract method bodies into `_*_ops.py` private siblings; class binds them in the class body |
| Writing a full ADR per thin-wrapper class is overhead | ADR-046 already documents the binding pattern + §C9 constraints; restating those for each future thin wrapper is bureaucratic | This addendum says "same pattern, same constraints, applies to thin subprocess-wrapper classes too" |
| §C9-style compliance still required | Siblings must have zero classes; only private module-level functions | Inherited verbatim from ADR-046 §3 + ADR-028 Addendum 1 §C9 |

## 2. Pattern (inherited from ADR-046 §4)

```python
# In _commit_ops.py (no classes; only private module-level functions
# taking the engine instance as the first positional argument)
def _commit(engine: "GitEngine", message: str, *, files=None, ...) -> str: ...

# In git_engine.py
from scistudio.core.versioning import (
    _branch_ops,
    _commit_ops,
    _history_ops,
    _merge_ops,
    _status_ops,
)

class GitEngine:
    def __init__(self, ...): ...

    # bindings — method bodies live in private siblings
    commit = _commit_ops._commit
    log = _history_ops._log
    branches = _branch_ops._branches
    merge = _merge_ops._merge
    status = _status_ops._status
    # … etc
```

Each sibling module:

- Contains only `_underscore` private functions taking the `GitEngine`
  instance as the first positional argument (named `engine`).
- Reads `engine.project_path`, `engine._run(...)`, `engine._git.run(...)`,
  `engine._rev_parse_head(...)` — the same `self.*` attribute reads the
  original methods had, just spelled as `engine.*`.
- Contains zero `class` definitions (§C9-style compliance — guarded by
  `tests/core/versioning/test_git_engine_package_layout.py`).
- Stays under 750 LOC (advisory god-file threshold).

## 3. Decomposition Layout

| File | Methods (bound from sibling) |
|---|---|
| `git_engine.py` | `HeadState` dataclass + `MergeResult` literal + `GitEngine` class body. Retains `__init__`, the `_git` property, and the in-class helpers `_run`, `_author_env`, `_rev_parse_head` (used by every sibling). Plus the ~14 binding lines + repo-lifecycle methods `init_repository` and `is_repository` (which read `_DEFAULT_AUTHOR_*` constants at class-definition time and remain inline for clarity). `HeadState` / `MergeResult` are DEFINED here (not aliased) so the ADR-039 governed contracts `scistudio.core.versioning.git_engine.{HeadState,MergeResult}` resolve to real symbol facts and pass `audit.closure`. |
| `_commit_ops.py` | `_commit` |
| `_history_ops.py` | `_log`, `_diff`, `_restore`, `_files_unchanged_vs_commit` |
| `_branch_ops.py` | `_branches`, `_current_branch`, `_branch_create`, `_branch_switch`, `_branch_delete`, `_commits_reachable_only_from`, `_tag` |
| `_status_ops.py` | `_status`, `_head_state` (lazy-imports `HeadState` from `git_engine` inside `_head_state` body to avoid an at-import cycle) |
| `_merge_ops.py` | `_merge`, `_cherry_pick`, `_merge_stage_file`, `_merge_complete`, `_merge_abort` |

All siblings <750 LOC. Main `git_engine.py` <300 LOC.

## 4. Scope

In scope:

- The class-binding split per Section 2 + 3.
- `tests/core/test_git_engine.py` import-surface verification (must pass UNEDITED).
- A new `tests/core/versioning/test_git_engine_package_layout.py` AST guard
  (zero class defs in `_*_ops.py` siblings).
- `scripts/check_god_files.py` waiver removal for
  `src/scistudio/core/versioning/git_engine.py`.

Out of scope:

- Any behavior change in any `GitEngine` method.
- New methods, removed methods, renamed methods.
- Changes to the `_run` / `_git` / `_rev_parse_head` private helpers
  (these stay as methods on `GitEngine`).
- `HeadState` schema changes.
- Any other file under `src/scistudio/core/versioning/`.

## 5. Verification

The implementer PR is acceptance-bound on:

- `ruff check` + `ruff format --check` — pass.
- `pytest tests/core/ tests/integration/ tests/api/test_git*.py --timeout=60 -x` — pass
  with `tests/core/test_git_engine.py` UNEDITED.
- `grep -nE "^class " src/scistudio/core/versioning/_*_ops.py
  src/scistudio/core/versioning/git_engine.py` returns exactly
  `git_engine.py:HeadState` and `git_engine.py:GitEngine`; zero class
  defs in `_*_ops.py` siblings. The AST guard at
  `tests/core/versioning/test_git_engine_package_layout.py` enforces
  the zero-class invariant on `_*_ops.py` siblings only.
- `python -m scistudio.qa.audit.full_audit` — status=pass.
- Sentrux MCP — `quality_signal` Δ within ±0.5% of baseline.
- `python scripts/check_god_files.py --enforce` — `core/versioning/git_engine.py`
  removed from waivers; 0 NEW violations.

## 6. Consequences

Positive:

- `git_engine.py` shrinks from 849 → <300 LOC (class body with bindings only,
  plus `HeadState` and the in-class helpers `_run`, `_author_env`,
  `_rev_parse_head`).
- Each `_*_ops.py` sibling is one cohesive concern (commit / history /
  branch / status / merge), individually reviewable.
- The pattern is now reusable for any future thin-wrapper class; no new ADR
  needed per instance — point at this addendum.

Negative / accepted:

- The `GitEngine` public API surface is now defined by ~14 binding lines in
  `git_engine.py` rather than 849 inline lines. Same trade-off as ADR-046's
  scheduler and Phase 1's `ApiRuntime` (PR #1445). Pattern audited and
  accepted by the umbrella.

## 7. References

- ADR-046 (parent — Path D for scheduler; this addendum extends the pattern
  to thin wrappers).
- ADR-047 (Path D for `BlockRegistry`, same family).
- ADR-028 Addendum 1 §C9 ("private functions, not helper classes").
- Phase 1 PR #1445 (`ApiRuntime` class-binding precedent).
- Phase 2 PR #1460 (Path D helper extraction for `io/savers` + `io/loaders`).
- Umbrella #1427 / Phase 3 cascade ticket #1465.
