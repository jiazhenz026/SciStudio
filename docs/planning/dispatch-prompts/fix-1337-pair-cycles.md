---
title: "Track A — Fix #1337 (pair D + pair E) Dispatch Prompt"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Track A — Fix #1337 dispatch prompt

Source template:
`docs/ai-developer/templates/agent-dispatch-prompt-template.md`

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Fix the two pairwise circular imports tracked in #1337 by extracting `_common.py` modules in `core/versioning/` and `engine/runners/`.
- Task kind: refactor
- Persona: implementer
- Issue: #1337
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1337
- Umbrella PR: #<pending — manager will fill in after PR creation> `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/no-cycles-1335-1337
- Agent branch: fix/1337-pair-cycles
- Agent worktree: .claude/worktrees/fix-1337
- Gate record: .workflow/records/1337-pair-cycles.json
- Checklist: docs/planning/no-cycles-1335-1337-checklist.md (you own Track A rows in §7)

## Required Rules

Read and follow:

- The GitHub issue `#1337` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/implementer.md
- docs/ai-developer/specific_rules/bug-fix.md (this is a refactor that fixes a structural issue — closest task-rule fit)

## Scope

You own only:

- src/scistudio/core/versioning/_common.py (NEW)
- src/scistudio/core/versioning/git_binary.py
- src/scistudio/core/versioning/git_engine.py
- src/scistudio/core/versioning/__init__.py
- src/scistudio/engine/runners/_common.py (NEW)
- src/scistudio/engine/runners/platform.py
- src/scistudio/engine/runners/process_handle.py
- src/scistudio/engine/runners/__init__.py
- tests/core/test_git_engine.py (regression test addition)
- tests/engine/test_process_handle.py (regression test addition)
- .workflow/records/1337-pair-cycles.json (your gate record)

You must not touch:

- .sentrux/rules.toml — manager handles the `max_cycles` ratchet in the umbrella merge commit.
- pyproject.toml — the `no_cycles` import-linter contract is deferred to #1341 (blocked-by #1336).
- Anything in `src/scistudio/core/types/**`, `src/scistudio/core/storage/**` — Track B owns those.
- Anything in `src/scistudio/blocks/**`, `src/scistudio/ai/**`, `frontend/**` — out of scope.
- The other 17 lazy-import bandaids elsewhere in the codebase — separate cleanup, not this PR.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. Track B (`A-1335`) is running in parallel on the same umbrella branch in `.claude/worktrees/fix-1335`. The two tracks touch disjoint directories; if you find an unexpected overlap, stop and report.
- MUST work only on branch `fix/1337-pair-cycles`.
- MUST work only in worktree `.claude/worktrees/fix-1337`.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=src python -m …` for the gate_record CLI.
- Do not revert or overwrite Track B's work.
- Do not broaden scope.
- MUST target your PR to `track/no-cycles-1335-1337` (the umbrella branch), NOT to `main`.
- MUST NOT merge any PR.
- Edit only your Track A rows in the checklist.
- Record every completed row with a PR, commit, test, report, or gate evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items (already tracked, you do not add new ones):

- #1341 — `no_cycles` import-linter contract (blocked-by #1336). Do NOT add the contract in this PR.
- #1336 — `blocks.registry ↔ ai.agent.*` SCC. Out of scope for this umbrella.

## Work To Do

### Pair D — `core/versioning`

The cycle today is purely lazy:
- `src/scistudio/core/versioning/git_binary.py:156` lazy-imports `GitError` from `git_engine` inside `GitBinary.run()`.
- `src/scistudio/core/versioning/git_engine.py:91` lazy-imports `GitBinary` from `git_binary` inside the `GitEngine._git` property.

Fix:

1. Create `src/scistudio/core/versioning/_common.py` containing only the `GitError` exception class. One-line module docstring should cite the governing ADR (verify which ADR governs `core/versioning/`; ADR-039 is suspected per the audit Plan agent's findings — confirm and cite the correct one).
2. In `git_engine.py`: replace `class GitError(...)` with `from scistudio.core.versioning._common import GitError`. Keep `GitError` as a module attribute so `scistudio.core.versioning.git_engine.GitError` continues to resolve for all current importers.
3. In `git_engine.py`: convert the lazy `from .git_binary import GitBinary` at line ~91 (inside `_git` property) to a module-top `from scistudio.core.versioning.git_binary import GitBinary` — now safe because `git_binary` no longer imports anything from `git_engine`.
4. In `git_binary.py`: replace the lazy `from .git_engine import GitError` at line ~156 with a module-top `from scistudio.core.versioning._common import GitError`. Remove the lazy import.
5. Verify `src/scistudio/core/versioning/__init__.py:43` `GitError` re-export still resolves through `git_engine` (which now re-exports from `_common`); no change needed if `git_engine.GitError` is preserved as a module attribute.

### Pair E — `engine/runners`

The cycle today is module-top:
- `src/scistudio/engine/runners/platform.py:19` `TYPE_CHECKING` import of `ProcessExitInfo` (counts as an AST edge for sentrux) + 6 lazy imports at lines 88, 147, 197, 268, 315, 355.
- `src/scistudio/engine/runners/process_handle.py:18` top-level `from .platform import PlatformOps, get_platform_ops` (the load-time cycle edge).

Fix:

1. Create `src/scistudio/engine/runners/_common.py` containing only the `ProcessExitInfo` dataclass. One-line module docstring cites the governing ADR (verify; ADR-019 is suspected — confirm).
2. In `process_handle.py`: replace the `ProcessExitInfo` definition with `from scistudio.engine.runners._common import ProcessExitInfo`. Keep `ProcessExitInfo` as a module attribute so `engine/runners/__init__.py:9`'s re-export continues to work.
3. In `process_handle.py:18`: KEEP `from .platform import PlatformOps, get_platform_ops` as-is. The cycle was platform→process_handle; reversing that direction would be the wrong fix.
4. In `platform.py`: DELETE the `TYPE_CHECKING` block at line ~19 (and the `TYPE_CHECKING` import if unused elsewhere) AND the six lazy imports at lines ~88, 147, 197, 268, 315, 355. Replace with a single module-top `from scistudio.engine.runners._common import ProcessExitInfo`.
5. Verify `src/scistudio/engine/runners/__init__.py:9` `ProcessExitInfo` re-export still resolves.

### Regression tests

Add two new tests proving the cycle is gone:

- `tests/core/test_git_engine.py::test_no_circular_import` — spawn a fresh `python -c` subprocess that imports `scistudio.core.versioning.git_binary` and `scistudio.core.versioning.git_engine` in both orders; expect no `ImportError`.
- `tests/engine/test_process_handle.py::test_no_circular_import` — same idea for `scistudio.engine.runners.platform` and `scistudio.engine.runners.process_handle`.

Both tests should be defensive (fast) and run in CI by default.

### Gate record (your own)

Create at `.workflow/records/1337-pair-cycles.json`:

```bash
PYTHONPATH=src python -m scistudio.qa.governance.gate_record start \
  --issue 1337 \
  --issue-url https://github.com/zjzcpj/SciStudio/issues/1337 \
  --slug pair-cycles \
  --task-kind refactor \
  --branch fix/1337-pair-cycles \
  --owner-directive "Break engine.runners and core.versioning pairwise cycles via _common.py extractions" \
  --include "src/scistudio/core/versioning/_common.py" \
  --include "src/scistudio/core/versioning/git_binary.py" \
  --include "src/scistudio/core/versioning/git_engine.py" \
  --include "src/scistudio/core/versioning/__init__.py" \
  --include "src/scistudio/engine/runners/_common.py" \
  --include "src/scistudio/engine/runners/platform.py" \
  --include "src/scistudio/engine/runners/process_handle.py" \
  --include "src/scistudio/engine/runners/__init__.py" \
  --include "tests/core/test_git_engine.py" \
  --include "tests/engine/test_process_handle.py" \
  --include ".workflow/records/1337-pair-cycles.json" \
  --record-path .workflow/records/1337-pair-cycles.json
```

(No `--governance-touch` — you do not touch governance files. If sentrux flags pyproject or .sentrux changes, you have drifted.)

Run `plan` next with all `--planned-file`s above and `--changed-test-path tests/core/test_git_engine.py --changed-test-path tests/engine/test_process_handle.py` and required checks `ruff,format,pytest,sentrux,full_audit`.

## Required Tests And Checks

- `PYTHONPATH=src ruff check src/scistudio/core/versioning src/scistudio/engine/runners tests/core tests/engine` — must pass clean.
- `PYTHONPATH=src ruff format --check src/scistudio/core/versioning src/scistudio/engine/runners tests/core tests/engine` — must pass clean.
- `PYTHONPATH=src pytest tests/core/test_git_engine.py tests/engine/ tests/blocks/test_tier1_dropin_subprocess.py tests/api/test_workflow_run_git.py --timeout=60` — all green.
- `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-track-a.json` — record evidence; classify any new findings.
- Sentrux MCP (`mcp__plugin_sentrux_sentrux__rescan` then `dsm`) — expected `clusters` count drops from 5 to 3 (Pair D + Pair E gone, three remain: blocks/registry triangle, mcp tools↔context, core.types↔backend_router).
- Record each completed check via `python -m scistudio.qa.governance.gate_record check`.
- Record sentrux via `python -m scistudio.qa.governance.gate_record sentrux ...`.

## Output Required

Before reporting done, provide:

- All changed file paths.
- Tests/checks run and results (PASS/FAIL counts, sentrux cluster delta).
- Checklist rows updated (link to commit that edited the checklist).
- PR number — open with title `fix(#1337): break engine.runners + core.versioning pairwise cycles` targeting `track/no-cycles-1335-1337`.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file (especially anything in `core/types/**` or `core/storage/**` — that's Track B).
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- CI or local checks fail for unclear reasons.
- Track B's work blocks yours (it should not — disjoint directories).
- You cannot add/update required tests.
- Sentrux MCP fails to scan or reports unexpected cluster counts.
- ADR-039 / ADR-019 references in `_common.py` docstrings turn out to be wrong (verify which ADR governs each).
```
