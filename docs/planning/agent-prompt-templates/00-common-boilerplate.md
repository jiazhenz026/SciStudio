# [DISPATCH-COMMON-V1] Mandatory boilerplate for cascade sub-agents

> Every dispatch prompt for a multi-agent cascade MUST start with the
> role-specific marker (e.g. `[DISPATCH-TEMPLATE-V1: skeleton]`) and
> include the rules below verbatim. The dispatch hook
> (`scripts/hooks/check-agent-template.sh`) checks for these markers
> on every `Agent` tool call.
>
> **Cascade context is injected per dispatch** — the dispatcher names the
> active cascade (e.g. "ADR-038 + ADR-039"), the plan file path, the
> checklist path, the tracking branch(es), and the hard out-of-scope file
> list. Defaults below apply to the current ADR-038/039 cascade unless
> overridden per dispatch.

## Identity & boundaries

- You are working on the SciEasy repository on a tracking branch for the active cascade — your dispatch will name the cascade and tracking branch.
- The plan file is `~/.claude/plans/whimsical-soaring-pascal.md` (read-only context for the ADR-038/039 cascade; the dispatcher will override this path for other cascades).
- The single source of truth for what's done is `docs/planning/adr-038-039-checklist.md` (or the cascade-specific checklist the dispatcher names). You **MUST** edit only the rows you own. You **MUST** append a `→ <PR-or-commit-link>` artifact to every box you tick. Drift is logged and reverted.
- The dispatch tells you (a) which sub-issue (`#N`) you own, (b) which feature branch to create off the tracking branch, and (c) the exact list of files in your scope.

## Hard scope rules — DO NOT MODIFY (defaults for ADR-038/039 cascade)

These directories / files are out of scope for ALL ADR-038/039 work, no exceptions. Touching one without explicit authorization in the dispatch = protocol violation. Stop, post on umbrella issue, exit.

- `src/scieasy/core/types/` (entire core data-type system; ADR-027 D2 freezes the seven core types)
- `src/scieasy/core/storage/` (storage backends — Zarr / Arrow / filesystem / composite frozen)
- `src/scieasy/core/proxy.py` (ViewProxy contract)
- `src/scieasy/blocks/base/` (Block ABC, BlockSpec, PortSpec, state machine — except `blocks/registry.py` where ADR-038 §3.3 explicitly authorizes the `block_version` force-injection)
- `src/scieasy/engine/runners/process_handle.py` + `process_monitor.py` + `platform.py` (ADR-019 process lifecycle)
- `src/scieasy/engine/events.py` (EventBus contract — you may **subscribe**, may NOT add new event types EXCEPT `git.head_changed` per ADR-039 §3.8 + `blocks.reloaded` which already exists)
- `src/scieasy/api/routes/ai_pty.py` — the EXISTING `WS /api/ai/pty/{tab_id}` route is frozen (ADR-034 freeze)
- `src/scieasy/blocks/ai/` — frozen except for the AI Block `run_id` → `block_execution_id` rename in D38-2.4a
- `src/scieasy/blocks/io/` + `blocks/process/` + `blocks/code/` + `blocks/app/` + `blocks/subworkflow/` — block subclasses untouched by ADR-038/039
- ANY ADR / spec / changelog except where your dispatch explicitly authorizes (changelog entry for your own PR is the one exception)
- ANY file owned by another agent in the same phase (avoid cross-agent collisions)

The dispatcher may add cascade-specific or phase-specific entries to this list. **The dispatch prompt's per-agent owned-files whitelist is the authoritative scope** — the lists above are the safety net.

If you genuinely believe your task requires touching one of these, STOP, post a comment on your umbrella issue describing why, and exit. The dispatcher escalates.

## Hygiene rules — mandatory

1. **Worktree isolation**: you are running in a worktree (`isolation: "worktree"`). Never operate on the user's main checkout.
2. **No `pip install -e .` from this worktree** — it pollutes the user's global `scieasy` import. Document any dep change in the PR body so the user runs the install in main.
3. **`pytest --timeout=60`** on every pytest invocation. Stuck pytest processes survive your exit and waste minutes.
4. **No `npm run dev` background processes** — they survive worktree teardown and serve stale UI from the next agent's perspective. Use `npm run build`, `vitest run`, or `npm test -- --run`. If you genuinely need a live dev server (rare), kill it explicitly before exit.
5. **Branch from the tracking branch** (NOT main):
   ```
   git fetch origin
   git checkout -b <your-branch> origin/track/adr-XXX/...
   ```
6. **Push order**: feature branch → wait for first CI run → only then `gh pr create`. Reviewers must see real status.
7. **PR target = tracking branch** (NOT main):
   ```
   gh pr create --base track/adr-XXX/... --head <your-branch> --title "..." --body "..."
   ```
8. **PR body MUST contain `Closes #N`** where N is your sub-issue number. After PR opens, verify the issue is linked. After merge, verify the issue actually closed.
9. **GitHub CI MUST be green** before you report done. After PR opens, run `gh pr checks <N> --watch` and DO NOT exit until all checks pass. If CI fails: diagnose, push fix commit, repeat. A red PR is not done. (Per CLAUDE.md §6.4.)
10. **Reconcile Codex auto-review**: after the first CI run, Codex posts review comments on the PR. Read each one and reply explicitly with one of `accepted (fixed in <commit>)`, `deferred (reason: ...)`, `rejected (reason: ...)`. Silence on a Codex P1 = drift.
11. **Update the cascade checklist** (the dispatcher names the file; default `docs/planning/adr-038-039-checklist.md`) — tick the rows you complete, append `→ <PR/commit/test-link>`. Edit only your rows.
12. **Run the same checks CI runs** locally before push:
    - `ruff format --check .`
    - `ruff check .`
    - `pytest -q --timeout=60` (or scoped to your changed dirs)
    - `mypy src/scieasy/ --ignore-missing-imports` (where applicable)
    - `cd frontend && npm run build && vitest run` (frontend touch)

## Definition of Done (every agent)

- All checklist rows you own are ticked with artifact links.
- PR opens, all CI checks green.
- Codex review comments all reconciled (accepted / deferred / rejected on the record).
- For UI-touching dispatches (ADR-035 frontend agent, ADR-036 frontend agents, every audit on UI work): live Chrome smoke test via Chrome MCP demonstrating the change works in a real browser. Unit tests do NOT replace this.
- PR body has `Closes #N`.
- Audit / Fix agents additionally post their report as a comment on the umbrella issue.

## When to STOP and escalate (don't push through)

- A scope rule above would force you to modify a forbidden file.
- An existing test is failing in a way unrelated to your change AND you can't quickly identify the cause.
- CI fails with an environment / dependency error you can't reproduce locally.
- Codex auto-review reports a P1 that requires changes outside your scope.
- The dispatch's task description contradicts the ADR.

In every case: post a one-paragraph comment on your umbrella issue explaining the blocker, set the relevant checklist row to `[!]` with reason, exit cleanly. Do NOT push half-finished work or thrash.
