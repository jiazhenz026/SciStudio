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

## 6. Owner triage & issue tracking (2026-06-11)

Owner decisions on review:

- **The ADR-048 preview path is reclassified P0.** Track B/C found `PreviewHost`
  is mounted nowhere, so the ADR-048-prescribed routed preview path is
  non-functional end-to-end (not a cosmetic scope note). Filed as **#1592**.
- **Pre-alpha → no compatibility/adapter layers.** Delete the shims and migrate
  callers to the canonical contracts; where old code did not fit, change the
  callers, not add an adapter. This reverses ADR-048's FR-007/FR-008 compat-adapter
  approach and needs an ADR/amendment. Filed as **#1594 (P1)**.

Every P0–P2 finding is now tracked by a GitHub issue:

| Issue | Sev | Finding(s) |
|---|---|---|
| **#1592** | **P0** | ADR-048 routed preview path dead-wired — `PreviewHost` mounted nowhere; live UI on legacy renderer (Track B #1577 F2 + Track C #1577 F3) |
| **#1591** | P1 | Missing `ai/agent/__init__.py` → import-linter blind + wheel exclusion + hidden blocks→ai inversion (ROUTE-01/02/06) |
| **#1593** | P1 | `Collection[T]` mis-routes to a single-item previewer before core collection fallback (#1577 F1) |
| **#1594** | P1 | Architecture: pre-alpha — delete all compat/adapter layers, migrate callers (owner directive) |
| **#1595** | P2 | ADR-022 GPU/CPU dispatch gating is dead code — `ResourceManager.acquire()` never called (BUG-RM-01) |
| **#1596** | P2 | Cancel + lineage events not scoped by `workflow_id` — concurrent workflows cross-cancel/cross-attribute (BUG-WSCANCEL-02 + BUG-LINEAGE-03) |
| **#1597** | P2 | Layer-boundary inversions evade import-linter (ROUTE-03 blocks→engine importlib, ROUTE-04 engine↔workflow cycle, ROUTE-05 ai→api) |
| **#1598** | P2 | "core" previewers subsystem imports up into `api.runtime` — inverted dep, unguarded by layer test (#1577 F3) |
| **#1599** | P2 | Stale `docs/audit/latest/facts-summary.json` contradicts the live audit (DRIFT-01) |

**P3 findings remain documented in the per-lens / PR-review / diff-only reports
and are not separately ticketed** (per the "all P0–P2" tracking scope). Notable
P3s for later: ADR-044 phantom governed path (DRIFT-03), `doc_drift` not checking
`governs.entry_points` (DRIFT-04), three shipped specs still `Planned` (DRIFT-02),
PTY/PID leaks (BUG-PTYLEAK-04 / BUG-PIDLEAK-05), the R-harness `max_rows` clamp
(#1580), and the CI-passing dead doc anchor (#1581).

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
