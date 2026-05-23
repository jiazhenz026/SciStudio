---
title: "Umbrella #1465 Phase 3 Bucket D — Independent Audit (With Context)"
date: 2026-05-22
auditor: audit_reviewer (with-context)
umbrella_issue: 1465
umbrella_pr: 1475
sub_prs:
  - 1473
  - 1476
  - 1477
checklist: docs/planning/phase3-bucket-d-checklist.md
audit_branch: audit/issue-1465/phase3-review
worktree: .claude/worktrees/audit-phase3
overall_recommendation: pass
language_source: en
---

# Umbrella #1465 Phase 3 Bucket D — Independent Audit (With Context)

## 1. Scope

Independent post-implementation review of the three Phase 3 Bucket D
sub-PRs against their authoritative specs (ADR-046, ADR-047, ADR-046
Addendum 1):

- **PR #1473 (D1, issue #1470)** — `engine/scheduler.py` 1744 LOC → 7-module sub-package per ADR-046.
- **PR #1476 (D2, issue #1471)** — `blocks/registry.py` 1708 LOC → 4-module sub-package per ADR-047 + legacy IO finder deletion.
- **PR #1477 (D3', issue #1472)** — `core/versioning/git_engine.py` 849 → 256 LOC class-binding split per ADR-046 Addendum 1 (which lands in this same PR).

All three PRs target `umbrella/phase3-bucket-d`. The umbrella PR #1475
remains `[DO NOT MERGE]` per umbrella protocol.

Owner authorized this audit on 2026-05-22.

## 2. Method

The audit branch (`audit/issue-1465/phase3-review`) was created off
`origin/umbrella/phase3-bucket-d` (commit `c6f85429`). To verify the
integrated Phase 3 merge outcome, all three sub-PRs were temporarily
merged locally into the audit worktree, exercised, then reverted before
writing this report. The audit branch contains only this report.

Checks performed:

- Read each sub-PR's diff (`gh pr diff <N>`), description, gate record (`.workflow/records/<issue>-*.json`), and CI rollup (`gh pr checks`).
- Inspected each sub-PR's `src/scistudio/.../*` files via `git show origin/refactor/...:<path>`.
- Class-grep guard: `^class [A-Za-z_]` against every sibling module.
- LOC count: per-file `wc -l` against every new module.
- Public-import sweep: `PYTHONPATH=src python -c "from scistudio.<path> import <every public name>"` for every name listed in each ADR's `governs.contracts`.
- Legacy-IO-finder absence: `hasattr(BlockRegistry, name)` for the 6 removed methods.
- Integrated full audit: `python -m scistudio.qa.audit.full_audit --repo-root . --format json` on the locally-merged Phase 3 state.
- Integrated pytest: `pytest tests/engine/ tests/blocks/ tests/core/versioning/ tests/contracts/ --timeout=60 --no-cov` on the locally-merged Phase 3 state (with env-missing plugin tests excluded — see §6).
- Sentrux MCP: `scan` + `check_rules` + `health` on the locally-merged Phase 3 state.
- Per-PR `gh pr checks <N>` — all 15+ required jobs SUCCESS on each PR.
- Cross-PR coordination: actual `git merge` exercise of all 3 PRs together to surface `scripts/check_god_files.py` conflict.

## 3. Findings — Per PR

### 3.1 PR #1473 (D1 — scheduler) — recommendation: **pass**

| Item | Verdict | Evidence |
|---|---|---|
| Scope discipline | pass | Diff touches only `src/scistudio/engine/scheduler.py` (deleted), the new `scheduler/` sub-package (7 files), ADR frontmatter (4 files: ADR-018/023/044/046), `scripts/check_god_files.py` (waiver removed), one new test, and the gate record. No out-of-scope files. |
| ADR-046 §3 layout | pass | All 6 siblings present with method assignments exactly matching ADR-046 §3 (full 33-method mapping verified). `_helpers.py` was added by the implementer for the 3 module-level helpers (`_extract_error_summary`, `_collect_object_ids`, `_object_ids_for_value`) plus `_MAX_ERROR_SUMMARY_LEN`. The ADR placed those helpers in `__init__.py`; relocating them to `_helpers.py` and re-exporting via `from ._helpers import *` is a minor scope-interpretation choice — semantically equivalent and preserves the public import path. Not a violation. |
| §C9 compliance | pass | Class-grep on `_dispatch.py`, `_events.py`, `_lineage.py`, `_state.py`, `_rerun.py`, `_helpers.py` returns **zero** class definitions. The layout test (`tests/engine/test_scheduler_package_layout.py`) AST-asserts the same invariant. |
| State machine "only-move" (ADR-046 §5) | pass | `_state.py` `_check_readiness`, `_check_completion`, `_propagate_skip` are byte-identical to the original `scheduler.py` lines 1335-1350 + propagate-skip body (modulo `self` → `self: DAGScheduler` annotation). Verified by direct diff. |
| #1449 contract test | pass | `pytest tests/engine/test_scheduler_state_machine_contract.py --timeout=60 -x` → **24 passed, 6 xfailed UNEDITED** (the 6 xfails are the same #1376 entries that exist on `main`). |
| `_dispatch` name collision fix | pass | `__init__.py` aliases `from . import _dispatch as _dispatch_mod` to avoid collision between the module name and the method name. Idiomatic; same approach used in Phase 1 PR #1445 (`_runtime_mod`). |
| Module LOC | pass | `__init__.py`=519, `_dispatch.py`=569, `_events.py`=274, `_lineage.py`=367, `_state.py`=73, `_rerun.py`=169, `_helpers.py`=68. All <750. |
| Public import surface | pass | `from scistudio.engine.scheduler import DAGScheduler, RunHandle, logger, _MAX_ERROR_SUMMARY_LEN, _collect_object_ids, _extract_error_summary, _object_ids_for_value` succeeds; identities preserved. |
| Gate record | pass | 6/6 stages `done`, full_audit `pass`, sentrux `pass` q_signal=4233, admin-approved:core-change applied, PR body has `Closes #1470`. |
| CI status | pass | All 15+ required jobs SUCCESS: Verify Workflow Compliance, Full Audit, Type Check, Test (Python 3.11 + 3.13), Architecture Tests, Import Contracts, Frontend, Wheel Release Smoke, CodeQL (3 langs), Lint & Format, Semantic duplication ratchet. |

### 3.2 PR #1476 (D2 — registry + legacy IO finder delete) — recommendation: **pass**

| Item | Verdict | Evidence |
|---|---|---|
| Scope discipline | pass | Diff touches only `src/scistudio/blocks/registry.py` (deleted), the new `registry/` sub-package (4 files), `validation.py`, `materialisation.py`, 10 ADR frontmatter + 1 spec frontmatter, `scripts/check_god_files.py`, the deleted `test_registry_find.py`, the new layout test, and 3 deleted tests in `test_block_registry_capabilities.py`. No out-of-scope files. |
| ADR-047 §3 layout | pass | All 4 siblings present with method assignment exactly per ADR-047 §3. |
| §C9 compliance | pass | Grep matches in `_scan.py` line 5 and `_capability.py` line 5 are docstring text ("`class` lives in `__init__.py`."), not actual class definitions. Strict regex confirms zero `class <Identifier>` defs. Layout test enforces. |
| Legacy IO finder deletion (ADR-047 §4) | pass | `find_loader` / `find_saver` / `find_io_blocks_for_type` and all 5 internal helpers (`_find_io_block`, `_class_accepts_dtype`, `_best_specificity`, `_matching_capabilities_for_legacy_io`, `_resolve_legacy_capability_class`) confirmed absent via `hasattr(BlockRegistry, name)` for all 6. |
| Caller migration: `validation.py` | pass | Fallback branch removed; the `capability_method = getattr(registry, method_name, None)` + `if not callable(capability_method): return []` pattern is preserved as a defensive guard (test mocks may still lack the method). The behavior is equivalent — the legacy fallback that used to be reached after the `not callable` early-return is gone. |
| Caller migration: `materialisation.py:_format_supported_savers` | pass | Rewritten on `list_format_capabilities(direction="save", data_type=type(obj))` with `grouped` dict + `order` list preserving registration-order. Output string shape (`<ClassName>=[<exts>]`) preserved. |
| 3 deleted tests in `test_block_registry_capabilities.py` | pass | The 3 deleted tests (`test_legacy_find_loader_keeps_first_registered_migration_fallback`, `test_legacy_find_loader_without_dtype_keeps_registration_order`, `test_legacy_find_loader_falls_back_when_winning_capability_class_cannot_resolve`) all exercise behaviors that ADR-043 explicitly rejects (registration-order fallback, dtype=None ordering, private `_resolve_class` monkeypatch fallback). Their deletion is justified — the capability methods raise `AmbiguousCapabilityError` / `MissingCapabilityError` instead, which is the contract ADR-043 codified. The remaining 48 tests in `test_block_registry_capabilities.py` cover the positive capability behavior. The agent's drift-log §9 row 2 rationale is sound and the manager pre-accepted it. |
| `test_registry_find.py` deletion | pass | Entire file (344 LOC, 13 tests) deleted; every test invoked `reg.find_loader` / `reg.find_saver` / `reg.find_io_blocks_for_type` (the deleted API). The capability equivalent coverage already exists in `test_block_registry_capabilities.py`. |
| Module LOC | pass | `__init__.py`=426, `_scan.py`=372, `_capability.py`=595, `_spec.py`=367. All <750. |
| Public import surface | pass | `from scistudio.blocks.registry import BlockRegistry, BlockSpec, BlockRegistrationError, CapabilityRegistrationError, CapabilityLookupError, MissingCapabilityError, AmbiguousCapabilityError` succeeds. |
| Gate record | pass | 6/6 stages `done`, full_audit `pass`, sentrux `pass` q_signal=4333, admin-approved:core-change applied, PR body has `Closes #1471`. |
| CI status | pass | All 15+ required jobs SUCCESS. |

### 3.3 PR #1477 (D3' — git_engine + ADR-046 Addendum 1) — recommendation: **pass**

| Item | Verdict | Evidence |
|---|---|---|
| Scope discipline | pass | Diff touches only `git_engine.py` (modified, 678 lines deleted + 85 added), the new 5 `_*_ops.py` siblings, `ADR-046-addendum1.md` (new), the new layout test + `__init__.py`, `scripts/check_god_files.py`, the gate record, and 2 evidence artifacts (`docs/audit/1472-full-audit.json`, `docs/audit/1472-sentrux.json`). No out-of-scope files. |
| Addendum 1 spec ↔ implementation alignment | pass | Addendum §3 specifies: `HeadState` + `MergeResult` defined in `git_engine.py` (not aliased) so ADR-039 governed contracts resolve to real symbol facts; `_status_ops._head_state` lazy-imports `HeadState` to break the at-import cycle. Both verified in the actual code. |
| §C9 compliance | pass | Class-grep on `_commit_ops.py`, `_history_ops.py`, `_branch_ops.py`, `_status_ops.py`, `_merge_ops.py` returns **zero** class definitions. Layout test AST-asserts the same and adds a sanity check (`_SIBLING_FILES >= 3`). |
| Method extraction | pass | 23 methods extracted across 5 siblings exactly matching Addendum §3 table. The 3 in-class helpers (`_run`, `_author_env`, `_rev_parse_head`), the `_git` property, and the lifecycle methods (`init_repository`, `is_repository`) correctly remain inline as the addendum specifies (they read class-level `_DEFAULT_AUTHOR_*` constants at class-definition time). |
| griffe alias-fact concern (resolved per drift log §9 row 4) | pass | The earlier abandoned D3 attempt moved `HeadState` to `_engine_types.py` and re-exported via `from ._engine_types import HeadState`, which broke `audit.closure` because griffe excludes aliases from facts. D3' moved `HeadState` + `MergeResult` back to `git_engine.py` as concrete definitions. The integrated full audit (§5 below) confirms `audit.closure` passes. |
| Module LOC | pass | `git_engine.py`=256, `_commit_ops.py`=98, `_history_ops.py`=207, `_branch_ops.py`=186, `_status_ops.py`=118, `_merge_ops.py`=198. All <750; the original 849-LOC waivered file is fully decomposed. |
| Public import surface | pass | `from scistudio.core.versioning.git_engine import GitEngine, HeadState, MergeResult, GitError` succeeds. |
| Gate record | pass | 6/6 stages `done`, full_audit `pass`, sentrux `pass` q_signal=4232, admin-approved:core-change applied, PR body has `Closes #1472`. |
| CI status | pass | All 15+ required jobs SUCCESS. |
| Addendum frontmatter lint (per drift log §9 row 4) | pass | The earlier duplicated `ADR-046 Addendum 1:` H1 prefix is fixed. Frontmatter lints clean. |

## 4. Findings — Cross-PR Coordination

### 4.1 Cross-PR coordination on `scripts/check_god_files.py`

**Severity: P3** (acceptable; expected umbrella-merge handling required).

All three PRs touch `scripts/check_god_files.py` to remove their own
waiver line. The auditor exercised the actual merge sequence
`umbrella → D1 → D2 → D3'` and observed:

- D1 merges cleanly (no conflict).
- D2 produces a content conflict in `scripts/check_god_files.py` — D1's
  edit position and D2's edit position interleave (D1 keeps the
  `"src/scistudio/blocks/registry.py"` line below its new comment; D2
  keeps the `"src/scistudio/engine/scheduler.py"` line below its new
  comment).
- D3' merges cleanly after D2 conflict is resolved (its waiver-comment
  position is below D1+D2's region).

The conflict resolution is trivial — keep both comment blocks, drop
both waiver entries. The auditor verified the merged outcome works
(integrated `python scripts/check_god_files.py --enforce` produces no
new "in-waiver" lines for any of the 3 Phase 3 files).

**Recommendation**: when the manager performs the umbrella merge of all
3 sub-PRs into `umbrella/phase3-bucket-d`, expect this conflict on the
**second** sub-PR merge regardless of order; resolve by keeping both
comment blocks and dropping both waiver entries.

### 4.2 Pre-existing `workflow_watcher.py` god-file (per drift log §9 row 3)

**Severity: P3** (informational; not a Phase 3 finding).

Running `python scripts/check_god_files.py --enforce` on the merged
Phase 3 state surfaces **one** NEW violation:

```
[NEW] src/scistudio/api/routes/workflow_watcher.py (907 LOC)
```

This file was previously hidden behind the umbrella's waivered files
(it was the next-largest unwaivered file after the 3 Bucket D waivers
were carrying the gap). It is **not** a regression caused by Phase 3
— it has been 907 LOC throughout the umbrella; Phase 3 simply makes it
visible by removing the larger waivers above it.

The script is not invoked from any CI workflow (`Grep` confirms no
`.github/workflows/*` references `check_god_files`). It is an advisory
script only — green CI on all 3 PRs is correct.

D1's drift-log §9 row 3 captures this as a Phase 4 candidate. No
in-scope action required.

### 4.3 Cross-PR full audit on integrated state

The auditor merged all 3 PRs locally (resolving the §4.1 conflict) and
ran `python -m scistudio.qa.audit.full_audit --repo-root . --format
json --output docs/audit/full-audit-latest.json`:

```
status: pass
findings: 0
child_reports: 8 (generate_facts, frontmatter_lint, fact_drift,
                  doc_drift, closure, signature_drift,
                  architecture_drift, vulture; semantic_dup deferred)
```

**No closure / doc_drift / signature_drift findings** on the
integrated state. The D3' drift-log §9 row 4 fix (move `HeadState`
back to `git_engine.py`, lazy-import in `_status_ops._head_state`) is
confirmed correct end-to-end.

### 4.4 Cross-PR sentrux on integrated state

`mcp__plugin_sentrux_sentrux__scan` + `check_rules` + `health`:

```
files: 1311
import_edges: 2931
quality_signal: 4178
rules_checked: 3 / 15 (free tier)
violations: 0
bottleneck: acyclicity
```

q_signal=4178 on the integrated state is slightly below each
individual sub-PR record (D1=4233, D2=4333, D3'=4232) because the
combined diff exercises a broader set of import edges and cycles. The
delta vs `main` baseline (q_signal ≈ 4185 pre-Phase 3 per recent
records) is within ±0.5%. All 3 free-tier architectural rules pass.

### 4.5 Cross-PR pytest on integrated state

`pytest tests/engine/ tests/blocks/ tests/core/versioning/
tests/contracts/ --timeout=60 --no-cov`:

```
1413 passed, 8 skipped, 22 xfailed
```

All xfails are pre-existing #1454 / #1376 markers (lifecycle event
block_type, schema payload envelope unification, IO roundtrip drift,
scheduler cancel_block semantics). No new failures.

**Caveat**: 3 test files had to be excluded from the audit-environment
run because they import `scistudio_blocks_imaging`, an external
monorepo plugin not installed locally:

- `tests/blocks/test_registry.py` (10 failures, all `ModuleNotFoundError: No module named 'scistudio_blocks_imaging'`)
- `tests/blocks/test_imaging_plugin_fixes.py` (7 failures, same root cause)
- `tests/blocks/app/test_appblock_fiji_integration.py` (Fiji-CLI-binary timeout; environment-only)

These all **pass** on CI per `gh pr checks <N>` (CI has the imaging
plugin installed). Audit-environment limitation only.

## 5. Findings — ADR Cross-Reference

### 5.1 ADR-046 (D1)

- §3 layout: ✓ implemented as written; `_helpers.py` is a permissible
  extension (3 module-level helpers + the `_MAX_ERROR_SUMMARY_LEN`
  constant, re-imported into `__init__.py` for the public import
  path).
- §4 Path D binding: ✓ identical pattern to PR #1445 / PR #1460.
- §5 state machine "only-move": ✓ byte-identical move.
- §6 scope (in-scope items): all delivered; out-of-scope items
  preserved (no behavior change in any of the 33 methods).
- §7 verification: ✓ all 7 checks pass per §3.1 above.
- `governs.files` frontmatter expansion: ✓ updated to include all 7
  scheduler sub-package files; 3 other ADRs (ADR-018, ADR-023,
  ADR-044) had 1-line frontmatter touches each that reflect the same
  expansion.

### 5.2 ADR-047 (D2)

- §3 layout: ✓ implemented as written.
- §4 legacy IO finder deletion + caller migration: ✓ all 6 methods
  deleted; both callers migrated correctly with output-shape preserved.
- §5 Path D binding: ✓ same pattern.
- §6 scope: all delivered.
- §7 verification: ✓ all 7 checks pass per §3.2 above.
- `governs.files` frontmatter expansion: ✓ ADR-047 expanded; 10 other
  ADRs (ADR-008/009/025/028/029/030/036/037/043) + ADR-043 spec had
  1-line frontmatter touches each.

### 5.3 ADR-046 Addendum 1 (D3')

- §2 pattern: ✓ implemented as written.
- §3 layout table: ✓ exact method assignment per the table.
- §3 griffe-alias rationale: ✓ `HeadState` + `MergeResult` defined in
  `git_engine.py`, not aliased; verified by direct file inspection.
- §4 scope: all delivered.
- §5 verification: ✓ all 7 checks pass per §3.3 above.
- The addendum's status went from `Proposed` (per its filename
  convention in ADR-046.md §1.1) to `Accepted` with `date_accepted:
  2026-05-22` — appropriate since the addendum lands as part of the
  same PR that exercises the pattern, and the ADR-046 parent is also
  `Proposed`. This matches the umbrella's "addendum lands in D3' PR"
  protocol from the checklist §1.1.

## 6. Findings — Drift Against the Checklist

The checklist (`docs/planning/phase3-bucket-d-checklist.md`) §9 Drift Log
currently has 4 entries. The auditor verified:

| Drift Entry | Verdict |
|---|---|
| 1. Retroactive umbrella scaffold (manager) | Recorded; remediation path was sound (sub-PRs retargeted as they opened). No further action needed. |
| 2. D2 deleted 3 tests instead of editing (D2) | Verdict reviewed in §3.2 above — agent's rationale is sound; ADR-043 rejects the deleted behaviors. |
| 3. `workflow_watcher.py` 907 LOC surfaced (D1) | Verdict reviewed in §4.2 above — not a Phase 3 regression; phase-4 candidate. |
| 4. Earlier abandoned D3 attempt left dirty worktree (D3') | Verdict reviewed in §3.3 above — D3' correctly fixed the 2 real bugs from the earlier attempt. |

**No unrecorded drift** was found beyond these 4 entries.

## 7. Codex Auto-Review Reconcile Note

Per memory `feedback_codex_review_timeout`, the auditor capped the
Codex auto-review wait at 5 minutes from CI-green. Result on all 3
sub-PRs (CI completed 2026-05-22 ~23:36 UTC):

| PR | Codex reviews fired | Codex comments |
|---|---|---|
| #1473 | 0 | 0 |
| #1476 | 0 | 0 |
| #1477 | 0 | 0 |

Same pattern as PR #1104 — most likely Codex token-exhaustion. No
reconcile required.

## 8. Recommendations

| PR | Recommendation |
|---|---|
| #1473 (D1) | **pass** |
| #1476 (D2) | **pass** |
| #1477 (D3') | **pass** |

**Overall recommendation for umbrella Phase 3 merge readiness:
pass.**

All three sub-PRs are merge-ready into `umbrella/phase3-bucket-d`.
The only operational note is the `scripts/check_god_files.py` conflict
the manager will encounter on the second sub-PR merge (any of D1/D2,
since either order produces the same conflict shape) — resolution is
trivial (keep both comment blocks, drop both waiver entries; see
§4.1).

Once all 3 sub-PRs are merged into the umbrella branch, the umbrella
PR (#1475) is itself merge-ready into `main` per the umbrella merge
protocol (owner removes `[DO NOT MERGE]` prefix as per-merge owner
authorization).

## 9. References

- ADR-046, ADR-047, ADR-046 Addendum 1 (canonical specs)
- Phase 1 audit precedent: `docs/audit/2026-05-22-umbrella-1427-phase1-with-context.md`
- Manager checklist: `docs/planning/phase3-bucket-d-checklist.md`
- Phase 1 pattern PRs: #1445 (ApiRuntime Path D), #1460 (savers/loaders Path D)
- Umbrella root: closed #1427 → tracking #1465 → umbrella PR #1475
