---
title: "Track B — Fix #1335 (core.types ↔ backend_router) Dispatch Prompt"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Track B — Fix #1335 dispatch prompt

Source template:
`docs/ai-developer/templates/agent-dispatch-prompt-template.md`

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Fix the `core.types ↔ core.storage.backend_router` 10-module SCC tracked in #1335 by extracting `core/storage/_defaults.py` while preserving the public `backend_router.get_router` symbol path.
- Task kind: refactor
- Persona: implementer
- Issue: #1335
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1335
- Umbrella PR: #<pending — manager will fill in after PR creation> `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/no-cycles-1335-1337
- Agent branch: fix/1335-router-defaults
- Agent worktree: .claude/worktrees/fix-1335
- Gate record: .workflow/records/1335-router-defaults.json
- Checklist: docs/planning/no-cycles-1335-1337-checklist.md (you own Track B rows in §8)

## Required Rules

Read and follow:

- The GitHub issue `#1335` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/implementer.md
- docs/ai-developer/specific_rules/bug-fix.md (this is a refactor that fixes a structural issue — closest task-rule fit)

## Scope

You own only:

- src/scistudio/core/storage/_defaults.py (NEW)
- src/scistudio/core/storage/backend_router.py
- src/scistudio/core/storage/__init__.py (touch ONLY if a re-export needs to be added; otherwise leave as-is)
- tests/core/test_backend_router.py (regression test addition)
- .workflow/records/1335-router-defaults.json (your gate record)

You must not touch:

- Any file under `src/scistudio/core/types/**` — the fix removes the router→types direction; the existing lazy `get_router()` calls in `core/types/base.py:484` and `core/types/composite.py:81` stay unchanged. If you find a reason to touch them, STOP and report.
- `tests/blocks/test_auto_flush_composite.py` — its monkeypatch on `scistudio.core.storage.backend_router.get_router` MUST continue to work unchanged. You verify this by re-running the test, not by editing it.
- `.sentrux/rules.toml` — manager handles the `max_cycles` ratchet in the umbrella merge commit.
- `pyproject.toml` — the `no_cycles` import-linter contract is deferred to #1341 (blocked-by #1336).
- Anything in `src/scistudio/core/versioning/**`, `src/scistudio/engine/runners/**` — Track A owns those.
- Anything in `src/scistudio/blocks/**`, `src/scistudio/ai/**`, `frontend/**` — out of scope.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. Track A (`A-1337`) is running in parallel on the same umbrella branch in `.claude/worktrees/fix-1337`. The two tracks touch disjoint directories; if you find an unexpected overlap, stop and report.
- MUST work only on branch `fix/1335-router-defaults`.
- MUST work only in worktree `.claude/worktrees/fix-1335`.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=src python -m …` for the gate_record CLI.
- Do not revert or overwrite Track A's work.
- Do not broaden scope.
- MUST target your PR to `track/no-cycles-1335-1337` (the umbrella branch), NOT to `main`.
- MUST NOT merge any PR.
- Edit only your Track B rows in the checklist.
- Record every completed row with a PR, commit, test, report, or gate evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Required TODO this PR adds (see step 3 below):

- `TODO(#1342)` at the lazy-import site in `backend_router.get_router()`. Issue #1342 is already open ("Eliminate lazy import in core.storage.backend_router.get_router (transitional after #1335)") with `tech-debt, audit-followup, architecture, P3` labels. The TODO comment text is specified in step 3.

Other deferred items (already tracked, you do not add new ones):

- #1341 — `no_cycles` import-linter contract (blocked-by #1336). Do NOT add the contract in this PR.
- #1336 — `blocks.registry ↔ ai.agent.*` SCC. Out of scope for this umbrella.

## Work To Do

The cycle today is already lazy on both sides:
- `src/scistudio/core/storage/backend_router.py:59-64` lazy-imports 6 concrete types inside `_build_default_router()`.
- `src/scistudio/core/types/base.py:484-487` (in `DataObject.save()`) and `src/scistudio/core/types/composite.py:81-89` (in `CompositeData.get_in_memory_data()`) lazy-import `get_router` from `backend_router`.

Sentrux still counts these as cycle edges because they exist in the AST graph regardless of position. The fix removes the `backend_router → core.types.*` edges entirely.

### Step 1 — Create `_defaults.py`

Create `src/scistudio/core/storage/_defaults.py` containing a single function `build_default() -> BackendRouter`. Move the body of `_build_default_router()` (currently lines 53-78 of `backend_router.py`) into `build_default()`. The new file imports:

- `from scistudio.core.storage.backend_router import BackendRouter` (one-way edge, no cycle)
- The 6 concrete types: `Array`, `Artifact`, `CompositeData`, `DataFrame`, `Series`, `Text` (from their respective `core.types.*` modules)
- The 4 backend classes (verify by reading the current `_build_default_router` body): `ArrowBackend`, `ZarrBackend`, `FilesystemBackend`, `CompositeStore` — from `scistudio.core.storage` or whichever exports them today.

One-line module docstring should cite the governing ADR (verify which ADR governs `core/storage/`; ADR-031 is suspected per the audit Plan agent's findings — confirm and cite the correct one).

### Step 2 — Rewrite `backend_router.py`

Delete `_build_default_router()` and the 6 lazy type imports inside it. Keep:

- The `BackendRouter` class definition.
- The `_BACKEND_EXTENSIONS` mapping.
- The `get_router()` function — but rewritten as the lazy-singleton below.
- Any other unrelated helpers (do not change them).

The new `get_router()` MUST be defined locally in `backend_router.py` (NOT re-exported from `_defaults`). Re-exporting would recreate the cycle: `base.py → backend_router → _defaults → core.types.base`. The constraint is that `backend_router.py` MUST have ZERO `core.types.*` or `core.storage._defaults` imports at module top level. The only `_defaults` import lives inside the function body.

```python
_router_singleton: BackendRouter | None = None


def get_router() -> BackendRouter:
    global _router_singleton
    if _router_singleton is None:
        # TODO(#1342): lazy import preserves the public symbol path
        # `scistudio.core.storage.backend_router.get_router` and the test
        # monkeypatch target at tests/blocks/test_auto_flush_composite.py:49,72.
        # Out of scope per #1335 surgical-extraction plan.
        # Followup: https://github.com/zjzcpj/SciStudio/issues/1342
        from scistudio.core.storage._defaults import build_default

        _router_singleton = build_default()
    return _router_singleton
```

Use the exact TODO format from AGENTS.md §3.6 (the project's tracked-TODO format). The comment is REQUIRED — without it, this PR introduces undocumented lazy-import debt.

### Step 3 — `core/storage/__init__.py`

Verify it imports `get_router` from `backend_router`. No change should be needed because `get_router` still lives there. If anything broke, STOP and report rather than touching `__init__.py` to paper over an unexpected breakage.

### Step 4 — Regression tests

Add to `tests/core/test_backend_router.py`:

- `test_no_circular_import` — spawn a fresh `python -c` subprocess that imports `scistudio.core.storage.backend_router` and `scistudio.core.types.base` in both orders; expect no `ImportError`.
- `test_singleton_identity` — call `get_router()` twice and assert `is` identity (the lazy singleton must be cached after first call).
- `test_backend_router_has_no_types_top_level_import` (optional but recommended) — read `backend_router.py` source and assert no module-top `from scistudio.core.types` or `import scistudio.core.types` exists (regex grep). This locks in the cycle-free state.

DO NOT edit `tests/blocks/test_auto_flush_composite.py`. Run it after your changes to verify the monkeypatch at lines 49 and 72 still works as-is.

### Step 5 — Gate record (your own)

Create at `.workflow/records/1335-router-defaults.json`:

```bash
PYTHONPATH=src python -m scistudio.qa.governance.gate_record start \
  --issue 1335 \
  --issue-url https://github.com/zjzcpj/SciStudio/issues/1335 \
  --slug router-defaults \
  --task-kind refactor \
  --branch fix/1335-router-defaults \
  --owner-directive "Break core.types <-> core.storage.backend_router 10-module SCC via _defaults.py extraction. Preserve public symbol path. Track lazy-import debt at #1342." \
  --include "src/scistudio/core/storage/_defaults.py" \
  --include "src/scistudio/core/storage/backend_router.py" \
  --include "src/scistudio/core/storage/__init__.py" \
  --include "tests/core/test_backend_router.py" \
  --include ".workflow/records/1335-router-defaults.json" \
  --record-path .workflow/records/1335-router-defaults.json
```

(No `--governance-touch` — you do not touch governance files. If sentrux flags pyproject or .sentrux changes, you have drifted.)

Run `plan` next with all `--planned-file`s above and `--changed-test-path tests/core/test_backend_router.py` and required checks `ruff,format,pytest,sentrux,full_audit`.

## Required Tests And Checks

- `PYTHONPATH=src ruff check src/scistudio/core/storage tests/core` — must pass clean.
- `PYTHONPATH=src ruff format --check src/scistudio/core/storage tests/core` — must pass clean.
- `PYTHONPATH=src pytest tests/core/test_backend_router.py tests/blocks/test_auto_flush_composite.py --timeout=60` — both green; the auto_flush_composite test must pass with no edits to it.
- `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-track-b.json` — record evidence; classify any new findings.
- Sentrux MCP (`mcp__plugin_sentrux_sentrux__rescan` then `dsm`) — expected `clusters` count drops from 5 to 4 if Track A has not landed yet, or to 2 if Track A has landed.
- Record each completed check via `python -m scistudio.qa.governance.gate_record check`.
- Record sentrux via `python -m scistudio.qa.governance.gate_record sentrux ...`.

## Output Required

Before reporting done, provide:

- All changed file paths.
- Tests/checks run and results (PASS/FAIL counts, sentrux cluster delta).
- Confirmation that `tests/blocks/test_auto_flush_composite.py` still passes UNCHANGED (line counts of the file unchanged).
- Checklist rows updated (link to commit that edited the checklist).
- PR number — open with title `refactor(#1335): extract storage/_defaults.py to break core.types <-> backend_router cycle` targeting `track/no-cycles-1335-1337`.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file (especially anything in `core/types/**` — that would change the scope materially; see #1342 for the broader cleanup).
- The `tests/blocks/test_auto_flush_composite.py` monkeypatch breaks (means re-export logic is wrong).
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- CI or local checks fail for unclear reasons.
- Track A's work blocks yours (it should not — disjoint directories).
- You cannot add/update required tests.
- Sentrux MCP fails to scan or reports unexpected cluster counts.
- ADR-031 reference in `_defaults.py` docstring turns out to be wrong (verify which ADR governs `core/storage/`).
- You discover that `get_router` MUST move to `_defaults` after all (e.g., because the lazy-import constraint makes the test impossible). In that case, STOP — this is a scope expansion that requires manager amendment to add `core/types/base.py`, `core/types/composite.py`, `blocks/base/block.py`, and `tests/blocks/test_auto_flush_composite.py` to your write set. Do NOT do it unilaterally.
```
