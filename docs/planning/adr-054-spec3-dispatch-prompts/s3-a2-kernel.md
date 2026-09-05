---
title: "ADR-054 Spec 3 Dispatch Prompt: S3-A2 The Kernel Handle"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S3-A2 — The Kernel Handle

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 3, the Explore Session runtime, in full.
- Task kind: feature
- Persona: implementer
- Issue: #2240
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2240
- Umbrella PR: #2241 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-spec3-explore-session
- Agent branch: feat/2240-kernel-handle
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s3-a2-kernel
- Gate record: .workflow/records/2240-feat-2240-kernel-handle.json (yours; create it with `gate_record init`)
- Checklist: docs/planning/adr-054-spec3-explore-session-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2240` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- **docs/specs/adr-054-explore-session.md — this is your specification. Read all of it; T-002 of §4.3, and FR-007, FR-013, FR-014, FR-015, FR-016 are yours.**
- docs/adr/ADR-054.md for the surrounding design.

## Scope

You own only:

- `src/scistudio/explore/kernel.py`
- `tests/explore/test_kernel_session.py`
- `.workflow/records/2240-feat-2240-kernel-handle.json`

You must not touch:

- `pyproject.toml` — agent S3-A1 adds `ipykernel` and `jupyter_client`. They
  may not be installed in your environment yet; see the note below.
- `src/scistudio/explore/kernel_bridge.py` — agent S3-B1 owns it.
- `src/scistudio/explore/session.py` and `queue.py` — agent S3-B2 owns them.
- Every other file under `src/scistudio/explore/`, every frontend path,
  `docs/specs/**`, and `docs/architecture/**`.

If you need an out-of-scope path, stop and report back.
Do not edit it.

## Coordination

- You are not alone in this codebase. Several agents are implementing other
  modules of the same spec in separate worktrees right now. The write sets are
  disjoint by design; keep to yours.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`. Every python invocation needs `PYTHONPATH=./src`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- **Do not open a pull request.** Commit your work and push your branch. The
  manager integrates every branch into
  `track/adr-054-spec3-explore-session` and runs the pre-PR gate once for the
  whole candidate. Opening a PR per agent would multiply CI load for no signal.
- MUST NOT merge anything.
- Edit only your checklist rows (your row in §6, and your line in §7.3).

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- The bridge that runs inside the kernel, the queue that feeds it, the session
  that owns it, and the kernel list the session exposes are other agents' tasks
  and are **not** deferred work — do not write a TODO for them. Your handle is
  the object they hold: it launches, executes, interrupts, restarts, stops, and
  reports death, and it knows nothing about notebooks, cells, or marks.

## Work To Do

Implement T-002 of the spec's §4.3 sequence.

1. A `KernelHandle` over `jupyter_client`'s `KernelManager` and its client,
   launching ipykernel from SciStudio's bundled interpreter (FR-007). The
   service is the kernel's only client; `jupyter_server` is not used and must
   not be imported.
2. Execute a request and return its result and its output messages.
3. Interrupt that actually reaches a hung cell (FR-013). ADR-054 §5.2 names
   this as a known blocker: on Windows `jupyter_client` needs an interrupt mode
   that works there. Prove it with a test that runs an infinite loop and
   interrupts it — a mocked kernel would pass a test a real interrupt fails.
4. Restart, stop, and death detection: a process killed from outside is
   reported dead rather than hanging a caller (FR-014, FR-015).
5. Read the kernel process's memory for the list the session exposes (FR-016).
6. Provide a way to execute a request with its output suppressed, which the
   bridge needs so a bridge call never appears as a cell.
7. Apply the repository's stability markers to every public symbol you add.

**If `ipykernel` or `jupyter_client` is not importable in your environment**,
do not install it into the shared environment and do not use `pip install -e .`.
Write the module against the documented `jupyter_client` API, mark the
process-spawning tests with the repository's serial marker plus a skip guarded
on the import being available, and report the situation. Do not substitute a
mock for the interrupt test — a skipped honest test beats a passing dishonest
one.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/explore/test_kernel_session.py -q`
- Lifecycle against a real ipykernel process where the dependency is available:
  launch, a cell runs, a hung cell is interrupted, restart clears the
  namespace, stop terminates the process, and a process killed from outside is
  reported dead.
- Every process-spawning test carries the repository's serial marker and kills
  what it started, including on failure. Read how existing subprocess tests in
  this repository do that.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-054-spec3-explore-session --head HEAD`
- Your branch is stacked on `track/adr-054-spec3-explore-session`, not on
  `main`. Record it with `--base-ref origin/track/adr-054-spec3-explore-session`
  at `gate_record init`, and pass
  `--base origin/track/adr-054-spec3-explore-session` to every `check`.
  Without it the gate measures your branch against `origin/main`, reads spec 2's
  commits as yours, and reports false out-of-scope findings.
- Docs: `--docs-na "spec:the governing spec docs/specs/adr-054-explore-session.md landed in PR 2228 and this change implements one of its tasks without adding a separately documented surface"`, unless your task section above says otherwise.
- `git add -A` before every commit.
- Commit trailers are required on every commit:
  `Gate-Record:`, `Task-Kind: feature`, `Issue: #2240`, `Assisted-by: Claude:claude-opus-5`.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results, including the exact pytest summary line.
- The commit sha of your branch head.
- Checklist rows updated.
- Any blocker, scope issue, or spec ambiguity.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The task conflicts with AGENTS.md, ADR-054, the spec, or the gate record.
- Local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
- The spec is ambiguous in a way that changes a contract another agent builds
  against. Do not guess; report the ambiguity and your proposed reading.
```
