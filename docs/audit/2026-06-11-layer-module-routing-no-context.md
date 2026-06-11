---
title: "No-Context Audit — Layer & Module Routing / Boundary Integrity"
issue: 1589
branch: audit/2026-06-11-codebase-no-context
author: audit_reviewer agent (AUD-2, no-context) + manager verification
date: 2026-06-11
status: committed
lens: layer & module routing / boundary integrity
overall_recommendation: pass-with-fixes
---

# No-Context Audit — Layer & Module Routing / Boundary Integrity (2026-06-11)

## 1. Scope and method

One lens of a three-lens **no-context** repository audit (issue #1589). The agent
read only ADRs/specs/docs/code/tests (no issues, gate records, PRs, or manager
summaries) and built the static import graph of `src/scistudio/**` (AST +
`grimp`), ran `lint-imports` live, read the declared import-linter contracts in
`pyproject.toml` and the CI `import-lint` job, and checked the layer model in
`docs/architecture/ARCHITECTURE.md §3.1-3.2` against reality at HEAD `cd370810`.

The manager independently re-verified every P1 against the cited code (see
**Manager verification**).

> Headline: the declared import contracts report "3 kept, 0 broken", but that
> green is **partly illusory**. A single missing file —
> `src/scistudio/ai/agent/__init__.py` — drops the entire 21-file Layer-4 agent
> subtree out of the analysis graph, vacuously satisfying the Blocks→ai and
> Engine→ai contracts **and** excluding the agent runtime from the built wheel.
> One fix (add that `__init__.py`) resolves ROUTE-01, ROUTE-06, and unmasks
> ROUTE-02.

## 2. Findings (severity-ordered)

### ROUTE-01 — Missing `ai/agent/__init__.py` blinds import-linter to the whole Layer-4 agent subtree (P1)

- **Category:** routing · **Confidence:** high · *(agent id: DRIFT-01)*
- **Locations:** `src/scistudio/ai/agent/` (no `__init__.py`; 21 `.py` files),
  `pyproject.toml:262-284` (Blocks contract), `pyproject.toml:286-290` (Engine
  contract), `.github/workflows/ci.yml:147-166` (import-lint job),
  `src/scistudio/blocks/ai/ai_block.py:442`
- **Evidence:** `ai/agent/` has 21 `.py` files but **no** `__init__.py` (its
  child `ai/agent/mcp/` does have one). `grimp.build_graph('scistudio')` reports
  `scistudio.ai.agent` **not present** in the graph; `get_import_details(
  importer='scistudio.blocks.ai.ai_block', imported='scistudio.ai.agent.terminal')`
  returns `[]`, and `find_shortest_chain(...)` raises *"Module
  scistudio.ai.agent.terminal is not present in the graph."* Yet `import
  scistudio.ai.agent.terminal` succeeds (PEP 420 namespace under PYTHONPATH=src).
  `lint-imports` reports "Blocks must not depend on … ai — KEPT" and "3 kept, 0
  broken".
- **Impact:** The Blocks→ai and Engine→ai forbidden contracts are **vacuously
  satisfied** — any boundary violation into `ai.agent.*` passes CI silently
  (ROUTE-02 already does). The architecture's "higher layers depend on lower
  layers" guarantee is unenforced for the entire production agent runtime.
- **Recommendation:** Add `src/scistudio/ai/agent/__init__.py`; re-run
  `lint-imports` (the Blocks→ai contract should then go BROKEN, surfacing
  ROUTE-02 honestly). Add a CI assertion that `grimp`'s graph includes
  `scistudio.ai.agent.*` so a future missing `__init__` cannot re-blind the
  linter.

### ROUTE-02 — Layer inversion: blocks (L2) imports private functions from ai (L4) (P1)

- **Category:** routing · **Confidence:** high · *(agent id: DRIFT-02)*
- **Locations:** `src/scistudio/blocks/ai/ai_block.py:442`,
  `pyproject.toml:263-266`, `docs/architecture/ARCHITECTURE.md:198-221`
- **Evidence:** `ai_block.py:442` (inside `_build_spawn_argv`):
  `from scistudio.ai.agent.terminal import _ensure_mcp_config,
  _write_system_prompt_tempfile` — two underscore-prefixed **private** helpers.
  The Blocks contract forbids `scistudio.ai` with the only carve-out being
  `blocks.ai.ai_block → engine.pty_control`; there is no blocks→ai exception.
  ARCHITECTURE.md places Block System at Layer 2 and AI Agents at Layer 4.
- **Impact:** A Layer-2 block binds to Layer-4 agent **private internals**;
  renaming those helpers silently breaks AIBlock spawning, and block contracts
  are coupled to agent-launch implementation details. It escapes detection only
  because of ROUTE-01.
- **Recommendation:** Invert the dependency — expose MCP-config / system-prompt
  construction as a stable contract the engine (L3) passes down, or move the
  shared launch-argv builder to a lower layer both can depend on. If owner
  approves an engine-mediated callback, add an explicit cited `ignore_imports`
  entry rather than relying on the invisible graph.

### ROUTE-06 — Missing `ai/agent/__init__.py` excludes the agent runtime from the built wheel (P1)

- **Category:** bug (packaging) · **Confidence:** high · *(agent id: DRIFT-06)*
- **Locations:** `pyproject.toml:121-122`
  (`[tool.setuptools.packages.find] where=['src']`),
  `src/scistudio/ai/agent/` (no `__init__.py`), `.github/workflows/ci.yml:275-296`
  (wheel smoke imports only `api.app`)
- **Evidence:** pyproject uses regular `find_packages`, which requires
  `__init__.py` and prunes non-package dirs. Replicating its pruning over `src/`
  yields only `scistudio.ai` under `ai` — `scistudio.ai.agent` and
  `scistudio.ai.agent.mcp` are **excluded** (mcp is pruned because its parent is
  not a package). Yet `api/routes/ai.py:24`, `api/app.py`, `cli/mcp_bridge.py`,
  and `blocks/ai/ai_block.py` import `scistudio.ai.agent.*` at runtime. The
  `wheel-release-smoke` job only imports `api.app.create_app` + `GET /`, so it
  never touches the agent subtree.
- **Impact:** A real `pip install scistudio` wheel ships **without**
  `scistudio/ai/agent/**` — the entire production Layer-4 agent runtime (PTY
  spawn, FastMCP server, MCP workflow/inspection tools). Importing
  `api.routes.ai` or launching an AIBlock from an installed wheel raises
  `ModuleNotFoundError`. Local dev (`PYTHONPATH=src` + PEP 420) and editable
  installs mask this, so CI is green while the shipped artifact is broken.
- **Recommendation:** Add `ai/agent/__init__.py` (same fix as ROUTE-01).
  Strengthen `wheel-release-smoke` to assert `scistudio.ai.agent.*` is present in
  the wheel (inspect namelist or import in the installed-wheel venv).

### ROUTE-03 — blocks (L2) depends on engine (L3) via an importlib string that evades the static linter (P2)

- **Category:** routing · **Confidence:** high · *(agent id: DRIFT-03)*
- **Locations:** `src/scistudio/blocks/code/code_block.py:469,488`,
  `src/scistudio/blocks/code/exchange.py:8`,
  `src/scistudio/engine/materialisation.py:10`, `pyproject.toml:263-266`
- **Evidence:** `code_block.py:469/488` (in `_materialise_adapter` /
  `_reconstruct_adapter`): `importlib.import_module(
  "scistudio.engine.materialisation")`. The static linter cannot see string
  imports, so this blocks→engine edge is undetected. `engine/materialisation.py:10`
  is a re-export shim
  (`from scistudio.blocks.io.materialisation import materialise_to_file,
  reconstruct_from_file`) — the call round-trips blocks→engine→blocks.
  `exchange.py:8` even claims this is done "without CodeBlock importing
  engine-level materialisation helpers" — but it does, dynamically.
- **Impact:** The "Blocks must not depend on engine" contract is bypassed by
  construction; the boundary is unenforceable and the docstring is false. If
  `engine/materialisation.py` is removed/renamed, code execution breaks at
  runtime with no lint-time signal.
- **Recommendation:** Import `scistudio.blocks.io.materialisation` directly (where
  the implementation lives) instead of the engine re-export shim, removing the
  inverted edge; or replace the importlib string with a normal import + cited
  `ignore_imports` entry. Correct the `exchange.py:8` docstring.

### ROUTE-04 — Latent engine↔workflow package cycle, governed by no contract (P2)

- **Category:** routing · **Confidence:** high · *(agent id: DRIFT-04)*
- **Locations:** `src/scistudio/engine/dag.py:13`,
  `src/scistudio/engine/scheduler/__init__.py:53`,
  `src/scistudio/workflow/validator.py:13`, `pyproject.toml:245-290`
- **Evidence:** `engine/dag.py:13` (module-level, not TYPE_CHECKING):
  `from scistudio.workflow.definition import EdgeDef, WorkflowDefinition`;
  `workflow/validator.py:13` (module-level):
  `from scistudio.engine.dag import CycleError, build_dag, topological_sort`. AST
  confirms all are runtime, non-lazy. The three import-linter contracts constrain
  core/blocks/engine against a fixed forbidden set; none forbids
  workflow↔engine, so the cycle is unflagged.
- **Impact:** engine (L3) and workflow form a bidirectional package dependency.
  It does not deadlock today only because engine imports the leaf
  `workflow.definition` while validator imports `engine.dag`; any new
  module-level engine import inside `workflow.definition` (or vice versa) turns
  it into a hard circular-import `ImportError`, and it muddies the layer DAG.
- **Recommendation:** Move the shared graph primitives (DAG / `build_dag` /
  `topological_sort`, or the `WorkflowDefinition` types) into one lower layer both
  depend on one-directionally, **or** add an import-linter `layers`/`independence`
  contract pinning the engine↔workflow direction. Place `workflow` in the §3.1
  layer stack (currently unnumbered).

### ROUTE-05 — Layer inversion: ai (L4) imports an api (L5) route handler internal (P2)

- **Category:** routing · **Confidence:** high · *(agent id: DRIFT-05)*
- **Locations:** `src/scistudio/ai/agent/mcp/tools_workflow/write.py:161`,
  `src/scistudio/api/routes/workflow_watcher.py:915`,
  `docs/architecture/ARCHITECTURE.md:198-212,279-283`
- **Evidence:** `write.py:161` (lazy, in `_emit_agent_workflow_changed`, wrapped
  in try/except): `from scistudio.api.routes.workflow_watcher import
  mark_self_write`; `mark_self_write` is a module-level function at
  `workflow_watcher.py:915`. ARCHITECTURE.md §3.2 says AI agents use the API/MCP
  *as clients*, not by importing API route internals.
- **Impact:** A Layer-4 agent tool reaches up into a Layer-5 route module to
  suppress the file-watcher self-write echo, inverting the documented direction
  and coupling agent tooling to route internals. Invisible to import-linter (no
  api/ai contract; and ROUTE-01 drops the ai subtree). The try/except masks
  breakage, so a rename degrades self-write suppression silently.
- **Recommendation:** Move the self-write debounce primitive into a lower shared
  layer that both api and ai depend on downward; after adding `ai/agent/
  __init__.py`, add an api/ai import contract to lock the direction.

### ROUTE-07 — Stale import-linter contract comment describes a carve-out that no longer matches the code (P3)

- **Category:** doc_drift · **Confidence:** high · *(agent id: DRIFT-07)*
- **Locations:** `pyproject.toml:274-284`,
  `src/scistudio/blocks/app/app_block.py:253`,
  `src/scistudio/blocks/code/code_block.py:469`
- **Evidence:** The pyproject comment says "AppBlock's `_bin_outputs_by_extension`
  dispatches to `engine.materialisation.reconstruct_from_file` … Both ignore
  entries below are lazy function-body imports …". But the `ignore_imports` list
  has only ONE entry (`blocks.ai.ai_block → engine.pty_control`); there is no
  AppBlock entry. The actual AppBlock import (`app_block.py:253`) is
  `from scistudio.blocks.io.materialisation import reconstruct_from_file` —
  blocks→blocks, needing no carve-out. The only block touching
  `engine.materialisation` is `code_block.py` via importlib string (ROUTE-03),
  which the comment does not mention.
- **Impact:** The contract's justifying comment is incorrect — it cites a
  carve-out for an import that no longer crosses into engine and omits the one
  place that actually does. A maintainer trusting the comment mis-models the
  blocks/engine boundary.
- **Recommendation:** Update the comment to reflect reality (AppBlock uses
  `blocks.io.materialisation`, no crossing; `engine.materialisation` is reached
  only by `code_block.py` via importlib); keep only genuinely needed ignore
  entries with accurate citations.

## 3. Manager verification

Independently confirmed against HEAD `cd370810`:

- **ROUTE-01:** `src/scistudio/ai/agent/__init__.py` is absent; `ai/agent/` has
  21 `.py` files; sibling `ai/agent/mcp/__init__.py` exists. **Confirmed.**
- **ROUTE-02:** `ai_block.py:442` imports `_ensure_mcp_config,
  _write_system_prompt_tempfile` from `scistudio.ai.agent.terminal`. **Confirmed.**
- **ROUTE-06:** root cause (missing `__init__.py` under regular `find_packages`)
  **confirmed**; wheel-exclusion behavior follows from setuptools semantics.
- **ROUTE-03:** `code_block.py:469,488` use
  `importlib.import_module("scistudio.engine.materialisation")`. **Confirmed.**
- **ROUTE-05:** `write.py:161` imports `mark_self_write`; defined at
  `workflow_watcher.py:915`. **Confirmed.**

## 4. Recommendation

**pass-with-fixes.** The single highest-leverage fix — add
`src/scistudio/ai/agent/__init__.py` — resolves the import-linter blind spot
(ROUTE-01), the wheel exclusion (ROUTE-06), and unmasks the real blocks→ai
inversion (ROUTE-02) so it can be fixed honestly. The remaining routing items
(ROUTE-03/04/05/07) should be tracked as focused follow-ups. The two P1 packaging
/ enforcement gaps warrant priority because CI is green while a shipped wheel
would be missing its agent layer. See the consolidated index for the follow-up
issue plan.
