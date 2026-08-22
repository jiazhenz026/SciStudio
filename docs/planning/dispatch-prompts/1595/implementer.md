---
title: "Issue 1595 Host Safety Runtime Implementer Dispatch"
status: Active
owners:
  - "@jiazhenz026"
related_adrs:
  - 22
language_source: en
---

# Issue 1595 Host Safety Runtime Implementer Dispatch

[DISPATCH-TEMPLATE-V1: implementer]

## 1. Task Identity

- Repository: SciStudio
- Owner request: implement ADR-022 Addendum 1 completely with one final public
  PR owned by the manager.
- Task kind: `bugfix`
- Persona: `implementer`
- Issue: `#1595`
- Issue URL: `https://github.com/jiazhenz026/SciStudio/issues/1595`
- Manager branch: `feat/1595-host-safety-runtime`
- Agent branch: `fix/1595-host-safety-implementation`
- Agent worktree: `../SciStudio-wt-1595-impl`
- Final PR owner: manager; do not open an agent PR.
- Manager gate record:
  `.workflow/records/1595-docs-1595-adr022-addendum1-host-safety.json`
- Checklist:
  `docs/planning/1595-host-safety-implementation-checklist.md`

## 2. Required Rules

Read and follow:

- `AGENTS.md`
- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/gated-workflow.md`
- `docs/ai-developer/specific_rules/bug-fix.md`
- `docs/ai-developer/personas/implementer.md`
- `docs/adr/ADR-022-addendum1.md`
- GitHub issue `#1595`

## 3. Scope

You own implementation edits only in:

- `src/scistudio/engine/resources.py`
- `src/scistudio/engine/scheduler/**`
- `src/scistudio/engine/runners/process_handle.py`
- `src/scistudio/api/runtime/__init__.py`
- `src/scistudio/cli/main.py`
- `tests/engine/test_resources.py`
- `tests/engine/test_resource_manager_gpu_autodetect.py`
- `tests/engine/test_scheduler_concurrency.py`
- `tests/engine/test_process_handle.py`
- `tests/test_import_coverage.py`
- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/PROJECT_TREE.md`
- `docs/package-development/blocks.md`

Do not edit:

- the addendum, manager checklist, dispatch prompt, audit report, or gate ledger;
- frontend or generated static assets;
- unrelated ADRs/specs, legacy architecture documents, or package code.

If an additional path is genuinely required, stop and report the exact path and
reason. Do not edit it before manager approval.

## 4. Coordination

- Work only on the assigned branch and worktree.
- Do not use `pip install -e .`.
- Do not revert or overwrite unrelated work.
- Do not open or merge a PR; commit the finished slice for manager integration.
- Do not edit the manager checklist. Report evidence for the manager to record.
- Any deferral must use a tracked `TODO(#NNN)` with governing context. Do not
  create untracked V1/MVP/later work.

## 5. Work To Do

1. Implement every normative local-runtime requirement in ADR-022 Addendum 1.
2. Make one `ResourceManager` instance enforce a positive configurable
   runtime-global `max_concurrent_blocks`, default `255`, across all schedulers
   that share it.
3. Keep live memory admission behavior exactly as specified, including the idle
   high-watermark escape and critical hard stop.
4. Provide machine-readable wait reasons without representing CPU/GPU capacity.
5. Remove predictive CPU/GPU/GPU-autodetect/allocation bookkeeping and remove
   `ResourceRequest` plus `ProcessHandle.resource_request` plumbing.
6. Acquire a permit before RUNNING/process launch; leave denied nodes READY;
   release idempotently on success, error, cancellation, launch failure, and
   abnormal exit.
7. Update affected tests and current documentation. Delete obsolete tests only
   when their entire contract was superseded, and replace them with coverage of
   the new contract.
8. Preserve public compatibility only where the addendum permits it. Do not keep
   dead resource-request fields as undocumented extension points.

## 6. Required Tests And Checks

- Use real `ResourceManager` behavior in scheduler tests, not a mock that
  reproduces the intended result.
- Cover default `255` using 256 READY blocks without requiring 256 real worker
  subprocesses if a deterministic scheduler harness can prove the permit bound.
- Cover shared permits across two schedulers using the same runtime manager.
- Cover explicit `1` and greater-than-255 configurations.
- Cover memory thresholds, wait reasons, retry, idempotent release, and every
  terminal/launch-failure path named by the addendum.
- Run focused tests with `--timeout=60`.
- Run `ruff check`/`ruff format --check` on changed Python paths if available.
- Report exact commands and results. The manager owns final gate reconciliation.

## 7. Output Required

Before reporting done:

- commit all scoped implementation changes on the agent branch;
- provide the commit SHA and changed paths;
- list tests/checks and their outcomes;
- identify any compatibility or scope concern;
- stop rather than silently deferring a required addendum behavior.
