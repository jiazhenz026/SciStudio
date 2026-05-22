---
title: "Audit: Umbrella #1427 Phase 1 (backend god-file refactor) — 4 sub-PRs"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 12
  - 28
  - 34
  - 35
  - 38
  - 39
  - 42
  - 44
  - 45
language_source: en
date: 2026-05-22
audit_mode: with-context
auditor: audit_reviewer (implementer-heavy persona, Opus 4.7 1M)
audit_branch: audit/issue-1427/phase1-review
audit_worktree: .claude/worktrees/audit-1427-phase1
sentrux_quality_signal: 4441
sentrux_baseline: 4442
---

# Audit — Umbrella #1427 Phase 1: backend god-file refactor (with-context)

## TL;DR

All four Phase 1 sub-PRs (#1441 A2 / #1442 B1 / #1444 A3 / #1445 A1)
are merge-ready for the umbrella branch. Independently verified scope
discipline, public import-surface preservation, test coverage, CI
sufficiency, gate-record integrity, and cross-PR coordination. Zero P1
findings; zero P2 findings; 4 P3 findings (process/metadata
observations, none block merge).

**Per-PR recommendation: all four `pass`.**

**Overall recommendation: Phase 1 of umbrella #1427 is ready to merge
into `umbrella/backend-god-file-refactor`.** The umbrella PR #1429
itself remains `[DO NOT MERGE]` per dispatch protocol until the owner
gives explicit go-ahead for the final umbrella → `main` merge.

## Findings

### P1 (blocking)

None.

### P2 (should fix before completion)

None.

### P3 (improvement / follow-up)

1. **Dispatch-prompt scope-list omission for ADR/spec frontmatter
   updates.** Three sub-PRs (#1445 A1, #1444 A3, #1442 B1) edited
   files under `docs/adr/**` and `docs/specs/**` (frontmatter
   `governs.files` / `governs.contracts` path updates plus one short
   prose paragraph each in ADR-035 §6 and `embedded-coding-agent-spec.md`).
   Their dispatch prompts (A1, A3, B1) did not list `docs/adr/**` or
   `docs/specs/**` in the **"You own only"** section.

   The edits themselves are technically required (after a file →
   sub-package rename, griffe-resolved contract claims would become
   phantom and trigger `doc_drift` / `closure` audit failures), and
   each agent recorded its rationale in the PR body. So the work was
   correct — but the dispatch prompts were under-specified.

   - **Why P3, not P2:** the edits are minimal, surgical, and were
     necessary to keep the full-audit children green; full_audit on
     the audit branch shows `status=pass`. Agents made the right call.
   - **Follow-up:** future Bucket A/B/C/D dispatch prompts (e.g.
     Phase 2/3 of #1427-followup) should explicitly authorize
     "ADR/spec `governs.files` frontmatter updates limited to path
     rewrites necessitated by this refactor". Tracking in
     `docs/planning/backend-god-file-refactor-checklist.md` §9
     drift-log row would also be appropriate.
   - **Evidence:**
     - `docs/planning/backend-god-file-refactor-prompts/A1-api-runtime.md`
       §Scope lists only `src/scistudio/api/runtime{.py,/**}`,
       `tests/api/**`, `scripts/check_god_files.py`.
     - PR #1445 actually touched `docs/adr/ADR-012.md`,
       `ADR-038.md`, `ADR-039.md`, `ADR-044.md`, `ADR-045.md`
       (frontmatter `governs.files` rewrites — single line each).
     - Same pattern for #1444 (ADR-034/ADR-035 + spec) and #1442
       (ADR-042-addendum1/addendum3 + spec).

2. **Stale `changed_test_paths` in PR #1444 (A3) gate record.**
   `.workflow/records/1432-api-ai-pty.json` has
   `changed_test_paths: []` even though the PR adds 21 test files
   under `tests/api/routes/ai_pty/` (41 new tests).

   The values appear to have been captured from `planned_files` (which
   listed `tests/api/routes/test_ai_pty_*.py` filenames) but never
   refreshed when the agent settled on the alternate layout
   `tests/api/routes/ai_pty/test_*.py`. `gate_record ci` still
   passes (the validator accepts an empty list when ADR-042's
   implementation-cat test rule is otherwise satisfied), but the
   record is misleading evidence.

   - **Why P3, not P2:** CI passes; tests exist and run; the
     misleading field is internal gate-record metadata, not user-facing
     contract. Other three records (#1430, #1431, #1433) have correct
     `changed_test_paths`.
   - **Follow-up:** add a post-implementation reconciliation step to
     the implementer persona ("re-run `gate_record amend` with the
     final test paths before pr-ready") or have `gate_record check`
     auto-discover `tests/**` files in the diff.

3. **Gate-record metadata drift on #1442 (B1).** Two minor
   inconsistencies in `.workflow/records/1433-gate-record-refactor.json`:
   - `admin_labels=[]` even though PR #1442 has the
     `admin-approved:core-change` label applied
     (`labels`/`gh pr view 1442 --json labels` confirms). The
     `governance_touch=true` field is correctly set, and the live
     PR-label check at CI time validates the label, so this is
     metadata-only drift.
   - ADR + spec docs paths recorded under
     `docs_landing.docs.paths` rather than the canonical
     `docs_landing.adr.paths` / `docs_landing.spec.paths`. The other
     three records use the canonical keys; the validator accepts
     either (`gate_record ci` returns `pass`). Inconsistent only.

   - **Why P3, not P2:** `gate_record ci --pr-label
     admin-approved:core-change` returns `pass`; the validator
     reads PR labels live from `gh`/`--pr-label`, not from the gate
     record's `admin_labels` list.
   - **Follow-up:** decide whether `admin_labels` should be the
     authoritative source or a mirror of live PR labels (ADR-042
     Addendum 1 §6 needs a clarifying sentence).

4. **`pty_endpoint` is not re-exported at the `ai_pty` package top
   level** (PR #1444). `pty_endpoint` lives in
   `scistudio.api.routes.ai_pty.websocket.pty_endpoint` only. In the
   original god file it was a top-level `async def` on
   `scistudio.api.routes.ai_pty`.

   Independent grep of `tests/`, `src/`, and `frontend/` shows zero
   external callers actually import `pty_endpoint` from the package
   top — the FastAPI router registers it via the `@router.websocket`
   decorator inside `websocket.py`, which is imported eagerly in
   `__init__.py` at L181 (`from scistudio.api.routes.ai_pty import
   internal_routes, websocket`). The route still resolves correctly
   in the FastAPI app, and all 31 pre-existing
   `tests/api/test_ai_pty*.py` tests pass on the refactored branch.

   - **Why P3, not P1/P2:** zero observable behavior or import-surface
     impact in the current repo. The dispatch prompt's "preserve the
     FastAPI router public surface" requirement is met (the `router`
     and all monkeypatch seams ARE re-exported). The function is just
     not a top-level name on `ai_pty` — but no caller relied on it
     being one.
   - **Follow-up:** for absolute belt-and-suspenders, add
     `pty_endpoint = websocket.pty_endpoint` to `ai_pty/__init__.py`.
     Or, optional: pin "router-only access" as an explicit contract
     line in ADR-034.

## Verification Evidence

### CI Status (latest commit per PR)

| PR | Branch HEAD | Verify Workflow Compliance | Other checks |
|---|---|---|---|
| #1441 (A2 mcp-tools) | `9c3f1105` | **pass** (1m6s, run 26308004633) | none configured |
| #1442 (B1 gate_record) | `b4fbbc00` | **pass** (1m13s, run 26307244594) | none configured |
| #1444 (A3 ai_pty) | `9e4b07bc` | **pass** (1m4s, run 26308006000) | none configured |
| #1445 (A1 api/runtime) | `7d32fc4b` | **pass** (1m7s, run 26308006804) | none configured |

### Gate-record CI validation (audit-side replay)

Re-ran `python -m scistudio.qa.governance.gate_record ci --gate-record
<path> --base origin/umbrella/backend-god-file-refactor --head HEAD
--pr-body "<live PR body>"` per branch:

- #1445 (`1430-api-runtime.json`): `gate_record: pass`
- #1441 (`1431-mcp-tools-pair.json`): `gate_record: pass`
- #1444 (`1432-api-ai-pty.json`): `gate_record: pass`
- #1442 (`1433-gate-record-refactor.json`) with `--pr-label
  admin-approved:core-change`: `gate_record: pass`

### Public import-surface preservation (independent verification)

Pre-refactor public + module-private name lists were extracted from
`origin/main` for each file via regex on `^(class|def|async def|[A-Z_]+
[:=]|_[a-z_]+ [:=])`. Each refactored branch was checked out into a
temp worktree (`PYTHONPATH=src python -c "from scistudio.<path>
import <name1>, <name2>, ..."` for the public list, plus `hasattr`
sweep for the private list).

- **A1 (api/runtime)** — 6 public names + 14 module-private names: all
  importable from `scistudio.api.runtime`. `ApiRuntime.<method>` has
  24 public attrs. `MISSING: (none)`.
- **A2 (tools_workflow)** — 23 public names + 9 module-private names:
  all importable. `MISSING: (none)`. `_atomic_write_text` reachable via
  lazy package lookup pattern from `finish_ai_block.py` (preserving
  existing monkeypatch tests).
- **A2 (tools_inspection)** — 17 public names + 7 module-private
  names: all importable. `MISSING: (none)`.
- **A3 (ai_pty)** — 8 public names + 19 module-private names: 7 of 8
  public names importable; `pty_endpoint` is the exception (see P3
  finding #4). All 19 module-private names importable. FastAPI
  `router` re-exported; routes `/api/ai/pty/{tab_id}`,
  `/api/ai/pty/internal/request-tab`, `/api/ai/pty/internal/notify`
  all resolve via the registered submodule decorators.
- **B1 (gate_record)** — 35 public names + 29 module-private names:
  all importable from `scistudio.qa.governance.gate_record`. CLI
  `python -m scistudio.qa.governance.gate_record --help` returns exit
  0 with the same subcommand list (`start, plan, amend, docs, check,
  sentrux, finalize, pre-commit, commit-msg, ci, pre-push, pr-ready`).

### Test coverage (independent re-run)

Ran `PYTHONPATH=src python -m pytest <new-test-files> --timeout=60
--no-cov -q` per branch:

- #1445: `tests/api/test_runtime_import_surface.py` — **4 passed**.
- #1441: `tests/ai/agent/mcp/test_tools_workflow_surface.py` +
  `test_tools_inspection_surface.py` — **24 passed**.
- #1444: `tests/api/routes/ai_pty/test_*.py` — **41 passed**.
  Plus existing `tests/api/test_ai_pty.py`,
  `test_ai_pty_audit_fixes.py`, `test_ai_pty_engine_spawn.py` —
  **31 passed** unchanged on the refactored branch.
- #1442: `tests/qa/governance/test_gate_record_package.py` — **18
  passed** (incl. `test_self_hosting_end_to_end` driving every
  CLI subcommand against a temp record).

Total new tests added across Phase 1: **87** (4 + 24 + 41 + 18). All
match the dispatch agents' final-report claims.

### `scripts/check_god_files.py` waiver progression

Per-branch `python scripts/check_god_files.py --enforce`:

- All four branches: `OK: all files at or above threshold are tracked
  waivers` (zero NEW violations).

Per-branch removed waivers (independently re-parsed):

| Branch | Removed | Remaining count |
|---|---|---|
| `refactor/issue-1430/api-runtime` | `api/runtime.py` | 9 |
| `refactor/issue-1431/mcp-tools-pair` | `tools_workflow.py`, `tools_inspection.py` | 8 |
| `refactor/issue-1432/api-ai-pty` | `api/routes/ai_pty.py` | 9 |
| `refactor/issue-1433/gate-record` | `qa/governance/gate_record.py` | 9 |

Post-merge expected waiver list: `engine/scheduler.py`,
`blocks/registry.py`, `blocks/io/savers/save_data.py`,
`blocks/io/loaders/load_data.py`, `core/versioning/git_engine.py` (5
files — all Bucket C / Bucket D — matches the audit-prompt-stated
expectation).

### Sub-module LOC budget (all <750 threshold)

| PR | Largest sub-module | LOC | Threshold compliance |
|---|---|---|---|
| #1445 A1 | `_projects.py` | 476 | well under 750 |
| #1441 A2 (tools_workflow) | `read.py` | 302 | well under 750 |
| #1441 A2 (tools_inspection) | `read.py` | 398 | well under 750 |
| #1444 A3 | `websocket.py` | 258 | well under 750 |
| #1442 B1 | `validation.py` | 449 | well under 750 |

### Full audit

`python -m scistudio.qa.audit.full_audit --repo-root . --format json
--output docs/audit/full-audit-latest.json` on audit branch
(`source_sha 574890e5…`):

```
status: pass
findings count: 0
child_reports: 8 children — all pass
implemented_children: ['generate_facts', 'frontmatter_lint',
  'fact_drift', 'doc_drift', 'closure', 'signature_drift',
  'architecture_drift', 'vulture']
deferred_children: ['semantic_dup']
```

`doc_drift` and `closure` passing is the key evidence that the
ADR/spec frontmatter updates by the agents successfully resolved the
file → sub-package path migration.

### Sentrux

MCP `scan` + `check_rules` + `health` on audit branch HEAD
(`518f3053`):

| Metric | Value | Delta vs manager baseline |
|---|---|---|
| `quality_signal` | 4441 | -1 (baseline 4442) |
| Architectural-rule violations | 0 (3/15 free-tier rules checked) | unchanged |
| `cross_module_edges` | 1939 | within noise |
| `bottleneck` | acyclicity (pre-existing — not introduced by Phase 1) | unchanged |

Quality signal delta is within noise margin; no regression
introduced.

### Ruff

`ruff check` clean on every changed source file across all four PRs
(per-branch verification):

- #1445: `src/scistudio/api/runtime/`,
  `tests/api/test_runtime_import_surface.py`,
  `scripts/check_god_files.py` — all checks passed.
- #1441: `src/scistudio/ai/agent/mcp/tools_workflow/`,
  `tools_inspection/`, `tests/ai/agent/mcp/`,
  `scripts/check_god_files.py` — all checks passed.
- #1444: `src/scistudio/api/routes/ai_pty/`,
  `tests/api/routes/ai_pty/`, `scripts/check_god_files.py` — all
  checks passed.
- #1442: `src/scistudio/qa/governance/gate_record/`,
  `tests/qa/governance/test_gate_record_package.py`,
  `scripts/check_god_files.py` — all checks passed.

### Cross-PR coordination

Union of files touched across the 4 sub-PRs was enumerated via
`git diff --name-only origin/umbrella/backend-god-file-refactor...
origin/<branch>`. Only one file is shared across all four PRs:

- `scripts/check_god_files.py` — each PR removes only its own
  waiver line(s). No conflicting edits; merge-time conflicts are
  expected and trivial to resolve (frozenset union of removals).

Zero source-code overlaps between the PRs. Each PR's sub-package
sits in a distinct directory:

- A1 → `src/scistudio/api/runtime/`
- A2 → `src/scistudio/ai/agent/mcp/tools_workflow/` and
  `tools_inspection/`
- A3 → `src/scistudio/api/routes/ai_pty/`
- B1 → `src/scistudio/qa/governance/gate_record/`

### Codex auto-review status

Per `gh pr view <N> --json reviews,reviewDecision` for all 4 PRs:
**no reviews fired within the 5-minute cap from CI-green**. This
matches the audit prompt's expected observation (per memory
`feedback_codex_review_timeout`). Recording as audit observation,
not a finding.

### Checklist drift

`docs/planning/backend-god-file-refactor-checklist.md` Section 6
Dispatch Matrix shows all four agent rows marked `[x]` with PR
links and CI-green annotations matching the live PR state. Section
7.3 Implementation rows are also `[x]`. Section 7.4 Audit row
remains `[ ]` (this audit is the work in flight).

No checklist drift detected. Section 9 Drift Log already records
two manager-side observations (worktree nesting + skipped
`gate_record ci`) that were resolved by the manager before this
audit ran.

## Per-PR recommendations

### PR #1445 (A1: api/runtime)

**Pass.** Splits 1839 LOC into 8 sub-modules (largest 476 LOC). 6
public names + 14 private names fully preserved via re-export from
`__init__.py`. `ApiRuntime` defined directly in `__init__.py` so
griffe emits canonical facts. 4 new import-surface tests pin the
contract. ADR-012/038/039/044/045 frontmatter updates are surgical
(one line each) and required for `closure`/`doc_drift` audits to
resolve. Gate record well-formed (6 stages done, issue URL,
PR body_closes_issues=[1430], 5 ADR paths recorded under
canonical `docs_landing.adr.paths`).

### PR #1441 (A2: tools_workflow + tools_inspection)

**Pass.** Splits 884 + 809 LOC into 13 sub-modules across two
sub-packages (largest 398 LOC). 40 public names + 16 private names
preserved. Lazy-lookup contract documented inline in
`finish_ai_block.py` L121-128 for the `_atomic_write_text` seam
that monkeypatch tests reach. 24 new tests. Gate record
well-formed; correctly records `docs_landing.adr.not_applicable
= true` (no ADR governs the MCP tool files at the file level).

### PR #1444 (A3: api/routes/ai_pty)

**Pass.** Splits 757 LOC into 6 sub-modules (largest 258 LOC). 7 of
8 public names directly importable from package top (see P3 #4 re
`pty_endpoint`); all 19 module-private names importable. FastAPI
router and three route paths unchanged. 31 existing tests pass +
41 new sub-package tests. ADR-034/035 + embedded-coding-agent-spec
frontmatter updates are minimal and required. Gate record
well-formed except stale `changed_test_paths` (P3 #2).

### PR #1442 (B1: qa/governance/gate_record)

**Pass.** Splits 1402 LOC into 7 sub-modules (largest 449 LOC) plus
`__main__.py` (15 LOC). 35 public names + 29 private names fully
preserved. CLI `--help` exit 0 with identical subcommand list.
Self-hosting confirmed (`test_self_hosting_end_to_end` drives
`start → plan → docs → check → sentrux → finalize` on the
refactored CLI). 18 new tests + 102 existing pass.
`admin-approved:core-change` label correctly applied to PR. ADR-042
Addendum 1/3 + spec `governs.contracts` updated to canonical
sub-module paths (e.g. `gate_record.models.GateRecord`,
`gate_record.validation.validate_gate_record`). Gate record has
two minor metadata drifts (P3 #3) that do not affect CI.

## Overall recommendation

**Phase 1 of umbrella #1427 is ready to merge sub-PRs → umbrella
branch.** All four sub-PRs `pass`. The umbrella PR #1429 should
stay `[DO NOT MERGE]` until the owner authorizes the final
umbrella → `main` merge per the protected-branch protocol.

Suggested manager next steps (advisory, not in audit scope):

1. Merge PRs in any order into `umbrella/backend-god-file-refactor`
   (no source-code conflicts; trivial `check_god_files.py` waiver
   union conflicts only).
2. After all 4 are merged, manually close issues #1430-#1433 if
   GitHub auto-close did not fire (sub-PR `Closes #N` only triggers
   on default-branch merge; see memory
   `feedback_umbrella_subpr_manual_close`).
3. Update umbrella PR #1429 body to include `Closes #1427` once the
   owner removes the `[DO NOT MERGE]` prefix and authorizes the
   umbrella → `main` merge.
4. Optional: address P3 finding #4 with a one-line
   `pty_endpoint = websocket.pty_endpoint` re-export in
   `ai_pty/__init__.py` for symmetry with the original surface.

## Stop conditions hit

None. Audit completed without needing implementation-code changes,
without scope conflict, and without unavailable evidence.

## Methodology notes

- Audit branch was rebased onto `origin/umbrella/backend-god-file-refactor`
  before starting (audit-prompt commit `518f3053` pulled).
- For each sub-PR branch, used `git worktree add -f --detach
  /tmp/audit-pr<N> origin/<branch>` for non-destructive checkout,
  then ran the verification commands inside the temp worktree.
  Worktrees removed at end via `git worktree remove --force`.
- Public/private-name extraction used `git show origin/main:<path>` |
  regex on top-level `def/class/CONSTANT/_name` patterns rather than
  trusting the agents' own lists.
- All four `gate_record ci` re-runs used the live PR body fetched
  via `gh pr view <N> --json body --jq .body`, mirroring CI's
  Verify Workflow Compliance step.
