---
title: "No-Context Repository Audit — Consolidated Index"
issue: 1589
branch: audit/2026-06-11-codebase-no-context
author: manager (consolidation + verification) over 3 no-context audit_reviewer agents
date: 2026-06-11
status: committed
overall_recommendation: pass-with-fixes
---

# No-Context Repository Audit — Consolidated Index (2026-06-11)

## 1. What this is

A full-repository **prevention** audit run by **three no-context audit agents**,
each dispatched with zero current-task context — they could read only ADRs,
specs, repository docs, code, and tests, never issues, gate records, PR
descriptions, commit messages, or any manager summary. Each agent independently
compared the repository's declared contracts against the actual implementation
at `main` HEAD `cd370810`, along one lens:

| Lens | Report |
|---|---|
| Documentation / contract drift | [doc-contract-drift](2026-06-11-doc-contract-drift-no-context.md) |
| Layer & module routing / boundary integrity | [layer-module-routing](2026-06-11-layer-module-routing-no-context.md) |
| Serious code bugs / correctness defects | [code-bugs](2026-06-11-code-bugs-no-context.md) |

The manager (this consolidation) independently re-verified every P1 and the core
claim of the top P2s against the cited code before they entered these reports.

> Scope note: this is the *prevention* track. The owner's primary target — review
> of the ADR-048 implementation PRs #1577/#1580/#1581 — is a separate
> with-context PR-review report:
> [adr048-pr-review](2026-06-11-adr048-pr-review.md).

## 2. Overall recommendation: pass-with-fixes

The live contract-drift suite (`doc_drift`, `signature_drift`, `closure`,
`fact_drift`, `frontmatter_lint`) **passes** against HEAD, the layer DAG is
mostly respected, and the execution surface is materially healthier than the
prior 2026-06-10 audit. No finding breaks a documented single-workflow runtime
guarantee. But CI's green is **partly illusory** in two ways that warrant
priority fixes (a packaging/enforcement blind spot, and unenforced concurrency
scoping).

## 3. Severity rollup (16 findings)

| Severity | Count | IDs |
|---|---|---|
| **P1** | 3 | ROUTE-01, ROUTE-02, ROUTE-06 (all one root cause) |
| **P2** | 7 | DRIFT-01, ROUTE-03, ROUTE-04, ROUTE-05, BUG-RM-01, BUG-WSCANCEL-02, BUG-LINEAGE-03 |
| **P3** | 6 | DRIFT-02, DRIFT-03, DRIFT-04, ROUTE-07, BUG-PTYLEAK-04, BUG-PIDLEAK-05 |

## 4. The headline: one missing file causes all three P1s

`src/scistudio/ai/agent/__init__.py` does not exist (21 `.py` files; sibling
`ai/agent/mcp/` has one). Because of it:

- **ROUTE-01** — `grimp`/import-linter drop the whole Layer-4 agent subtree from
  the graph, so the `Blocks→ai` and `Engine→ai` forbidden contracts pass
  **vacuously** ("3 kept, 0 broken").
- **ROUTE-02** — a real inversion hides behind that blind spot:
  `blocks/ai/ai_block.py:442` imports private helpers from `ai.agent.terminal`.
- **ROUTE-06** — regular `find_packages` excludes the subtree from the built
  wheel; `wheel-release-smoke` only imports `api.app`, so a shipped
  `pip install scistudio` would be missing its entire agent runtime with CI green.

One fix (add the `__init__.py`, then honestly fix the unmasked ROUTE-02) clears
all three. **Tracked as issue #1591.**

## 5. Manager verification (independently confirmed at HEAD `cd370810`)

- `ai/agent/__init__.py` **absent**; 21 `.py` files; sibling `mcp/__init__.py`
  present. (ROUTE-01/06)
- `ai_block.py:442` imports `_ensure_mcp_config, _write_system_prompt_tempfile`
  from `scistudio.ai.agent.terminal`. (ROUTE-02)
- `code_block.py:469,488` use `importlib.import_module(
  "scistudio.engine.materialisation")`. (ROUTE-03)
- `write.py:161` imports `mark_self_write` from the api route module
  (`workflow_watcher.py:915`). (ROUTE-05)
- `ResourceManager.acquire()` has **no callers** in `src/`. (BUG-RM-01)
- `_on_cancel_workflow` (`_events.py`) and `recorder._on_terminal`
  (`recorder.py:188`) contain **no `workflow_id` filter**. (BUG-WSCANCEL-02,
  BUG-LINEAGE-03)
- `src/scistudio/api/runtime.py` absent (now a package); `flatten_subworkflows`
  absent from `src/`; `src/scistudio/previewers` absent. (DRIFT-03/04)

## 6. Proposed follow-up plan

**Opened:**

- **#1591** — `bug(packaging/imports)`: add `ai/agent/__init__.py`; fix the
  unmasked blocks→ai inversion; add grimp-coverage + wheel-content CI assertions.
  (ROUTE-01/02/06, P1.)

**Proposed (pending owner triage — not yet filed to avoid issue spam from a
prevention pass):**

1. `bug(engine/concurrency)`: scope cancel + lineage events by `workflow_id`
   (or per-run event bus). Covers BUG-WSCANCEL-02 + BUG-LINEAGE-03 (P2) — the
   still-live concurrent-different-workflow half of the documented DSN-1 root
   cause.
2. `bug(engine/resources)`: wire `ResourceManager.acquire()/release()` and the
   block's real `ResourceRequest` into `_dispatch` so ADR-022 GPU/CPU gating
   actually throttles; add a non-mock counter test. BUG-RM-01 (P2).
3. `refactor(imports)`: remove the blocks→engine importlib-string edge
   (ROUTE-03), break/pin the engine↔workflow cycle (ROUTE-04), relocate the
   self-write debounce primitive (ROUTE-05), and correct the stale import-linter
   comment (ROUTE-07).
4. `bug(engine/leaks)`: reap orphaned engine-initiated PTY tabs (BUG-PTYLEAK-04);
   deregister `ProcessHandle` on completion and key the registry by
   `(run_id, block_id)` (BUG-PIDLEAK-05).
5. `docs(audit/specs)`: regenerate or de-track the stale
   `docs/audit/latest/facts-summary.json` (DRIFT-01); advance three shipped specs
   from `Planned` to `Implemented` (DRIFT-02); fix the ADR-044 phantom governed
   path (DRIFT-03); add a `governs.entry_points` existence check to `doc_drift`
   (DRIFT-04).

## 7. Method and integrity notes

- The three audit agents were strictly read-only and context-isolated; they
  returned structured findings, and the manager persisted them as these committed
  files (no audit report exists only in chat). This orchestration choice is
  recorded in `docs/planning/codebase-no-context-audit-checklist.md §1.1`.
- Every finding cites concrete `file:line` evidence and a verification method;
  confidence is the agent's stated value, corrected where manager re-verification
  applied.
- This audit changes **no implementation, source, or test file**. It is evidence
  only; remediation happens in the follow-ups above.
