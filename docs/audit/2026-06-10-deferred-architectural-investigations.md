# Deferred Architectural Investigations — 2026-06-10

Persona: `audit_reviewer`. Task kind: `docs` (investigation only).
Scope: READ-ONLY investigation of six deferred architectural / governance
items. No source code was changed. Each section gives current behavior, root
cause, blast radius, options + trade-offs, a recommended direction, whether an
ADR is required, and a proposed follow-up issue for the owner to file.

Issues investigated (not closed): #1517, #1519, #1530, #1549, #887, #1336.
Verification base: branch `claude/p1p2-core-inv`, merge tip `d99f4e4`.

> Note on re-verification: several of these issues were filed against an older
> merge-base. Where the landed code has changed the picture (notably #1336 and,
> partially, #1530), this report states the **current** state explicitly rather
> than re-asserting the issue body.

---

## 1. #1517 (DSN-1, P1) — Process-global EventBus has no run identity

### Current behavior (verified)

`ApiRuntime` constructs exactly one process-wide `EventBus`
(`src/scistudio/api/runtime/__init__.py:222`) and shares it — together with one
`ResourceManager`, one `ProcessRegistry`, and one `LocalRunner` — across every
workflow run (`src/scistudio/api/runtime/_runs.py:290-300`).

Each `start_workflow` call builds a fresh `DAGScheduler`, and the scheduler
constructor subscribes **six** handlers to the shared bus
(`src/scistudio/engine/scheduler/__init__.py:168-173`): `BLOCK_DONE`,
`BLOCK_ERROR`, `CANCEL_BLOCK_REQUEST`, `CANCEL_WORKFLOW_REQUEST`,
`PROCESS_EXITED`, `INTERACTIVE_COMPLETE`. There is **no scheduler `dispose()` /
unsubscribe** anywhere — grep for `dispose|unsubscribe|_subscribed` under
`engine/scheduler/` returns nothing. `_finalize_lineage_run`
(`_runs.py:145-175`) disposes the `LineageRecorder` but never the scheduler.

`EngineEvent` carries no `run_id` (`src/scistudio/engine/events.py:57-64`); only
some payloads carry `data["workflow_id"]`.

Three concrete corruption paths, all confirmed against current code:

1. **Cancel cross-contamination.** `_on_cancel_workflow`
   (`engine/scheduler/_events.py:198-211`) ignores `event.data["workflow_id"]`
   entirely and cancels *every* block in `RUNNING`/`PAUSED` state in *its own*
   `_block_states`. Because every live scheduler is subscribed to
   `CANCEL_WORKFLOW_REQUEST`, an emit on the bus fans out to *all* schedulers.
   The MCP tool `cancel_run`
   (`src/scistudio/ai/agent/mcp/tools_workflow/write.py:261`) emits
   `CANCEL_WORKFLOW_REQUEST` on the bus → cancels all concurrent runs.
   *Partial mitigation already present:* the WS handler (`api/ws.py:172-176`)
   and the REST route (`api/routes/workflows.py:492`) call
   `scheduler.cancel_workflow()` directly on the targeted run, so those two
   paths are scoped. The bus-emit path (MCP) is not.
2. **Stale-subscriber checkpoint/lineage writes.** A finished run's scheduler
   stays subscribed. Its `_on_block_done` (`_events.py:55-63`) calls
   `_dispatch_newly_ready` + `_check_completion` + `save_checkpoint` against the
   *old* run's `_block_states` whenever *any* later run emits `BLOCK_DONE`,
   overwriting the checkpoint slot with stale state. This is the identical bug
   class already fixed for `LineageRecorder` (`core/lineage/recorder.py:160-182`
   `dispose()`, "Codex P1 on PR #926") — the fix was never generalized to the
   scheduler.
3. **ProcessRegistry key collision.** `ProcessRegistry` keys handles by bare
   `block_id` (`engine/runners/process_handle.py:113-123`). Two concurrent
   workflows that share a node id collide; `register` overwrites, and
   `get_handle` / `terminate` can act on the wrong run's process.

### Root cause

Runtime identity (the run) is not a first-class concept in the event/dispatch
layer. The EventBus is a process singleton with no addressing, subscriptions
have no lifecycle tied to a run, and the registry namespace is `block_id` not
`(run_id, block_id)`. The single-run assumption is baked into ADR-018's
subscription matrix.

### Blast radius

Any time two runs overlap: GUI multi-tab, "Run from here" while a full run is
live, AI-agent-triggered runs concurrent with a GUI run, rerun-while-running.
Symptoms: wrong run cancelled, corrupted checkpoints (bad "Run from here"),
duplicated/wrong-run lineage rows, killed-wrong-process. #1544 (snapshot emit)
and #1525 (short-term double-run guard) reduced exposure but did not remove the
shared-identity defect.

### Options

- **A — Per-run EventBus.** `start_workflow` creates a run-scoped bus;
  process-wide concerns (WS fan-out, event logger) bridge via a parent/child or
  an explicit forwarder. Cleanest isolation; largest surface (every subscriber
  that today assumes the singleton, e.g. `api/ws.py`, `install_event_logger`,
  `_bind_event_logging`, must be re-pointed or bridged).
- **B — Mandatory `run_id` on every event + subscribe-time filtering.** Add
  `run_id` to `EngineEvent`; scheduler/recorder/registry filter on their own
  `run_id`; registry keyed `(run_id, block_id)`; symmetric subscribe/dispose in
  the scheduler lifecycle (mirror the recorder). Smaller blast radius than A,
  keeps one bus, but every emit site and handler must thread `run_id` and every
  handler must early-return on mismatch (easy to miss one).
- **C — Minimal hardening only.** Add scheduler `dispose()` (called from
  `_finalize_lineage_run`), make `_on_cancel_workflow` honor
  `data["workflow_id"]`, key the registry `(run_id, block_id)`. Lowest effort;
  does not fix the architectural shared-bus identity gap, so future handlers can
  reintroduce the class.

### Recommended direction

**B (mandatory `run_id` + symmetric dispose + `(run_id, block_id)` registry).**
It directly closes all three confirmed paths, reuses the already-blessed
recorder dispose pattern, and avoids the larger bridging work of A. Land C's
three fixes as the first increment inside the same effort so the acute
corruption stops early. Add a regression test that runs two overlapping
workflows sharing a node id and asserts isolated cancel + checkpoint + registry
behavior.

### ADR required? **Yes.**

This changes the `EngineEvent` contract (a field on the runtime backbone, ADR-018),
the scheduler lifecycle, and the `ProcessRegistry` key contract (ADR-019). Per
AGENTS.md §3.4 (contracts/runtime behavior) and the issue body itself, an ADR
addendum to ADR-018/019 is warranted; bundle with the report §7 group-2 items
(BUG-4/BUG-6/DSN-8) as the issue suggests.

### Proposed follow-up issue

- **Title:** `[P1] engine: introduce run identity — run_id on EngineEvent, scheduler dispose, (run_id, block_id) ProcessRegistry`
- **Scope:** ADR-018/019 addendum defining run-scoped events; add `run_id` to
  `EngineEvent` and thread it through all emit sites; scheduler symmetric
  subscribe/`dispose()` wired from `_finalize_lineage_run`; `_on_cancel_workflow`
  honors `workflow_id`; registry rekey; concurrent-run isolation tests. Land the
  three acute fixes (dispose, cancel-scoping, registry key) first.

---

## 2. #1519 (DSN-3, P1) — Gate machinery is only effective against cooperative agents

This is a governance **threat model**, not a code bug. The reality stated in the
issue holds today: real enforcement = `ci.yml` + branch protection + human
review. The ADR-042 gate/receipt layer is advisory against an adversarial agent.

### Re-verified gaps (post-Addendum-6, against current `workflow-gate.yml`)

1. **CI runs PR-controlled guard code (CONFIRMED, still open).**
   `.github/workflows/workflow-gate.yml:14` uses `actions/checkout@v6` with no
   `ref:` override → on `pull_request` it checks out the **PR merge ref** (PR
   head merged into base). Line 25 then `uv pip install --system -e ".[dev]"`
   from that checkout, and line 130 runs
   `python -m scistudio.qa.governance.gate_record check --mode ci` from the
   PR's own tree. A PR that edits `src/scistudio/qa/governance/` (the evaluator,
   tier selection, guard calculators) is validated by its *own modified* code.
   The single-evaluator consolidation in Addendum 6 did not change which ref the
   evaluator is loaded from. (Side note: CI itself uses `pip install -e .`, which
   AGENTS.md §3.1 forbids for agents — acceptable for the CI runner, but worth
   noting the asymmetry.)
2. **Gate evidence is self-reported.** Ledger `check`/record calls persist
   agent-declared statuses; the ledger is committed by the same actor whose work
   it attests. Amendments carry an arbitrary `approved_by` string. CI re-running
   `check --mode ci` recomputes *some* obligations from the diff, which narrows
   this, but any obligation marked satisfied by a self-reported event and not
   independently recomputed by CI remains forgeable.
3. **Receipts are local/forgeable / CI-invisible.** Receipt behavior now folds
   into the ledger (Addendum 6 removed the separate `gate_receipt` command), but
   any locally-produced check evidence that is not independently recomputed
   server-side from the base ref is still trust-the-agent. CI must be the
   authority for anything that matters.
4. **Local hooks honor agent-settable env vars / partial guard coverage.**
   The worktree write guard (`scripts/hooks/check-worktree-write-guard.sh`) is a
   PreToolUse hook keyed on Edit/Write tool calls; `Bash`-driven writes
   (`sed -i`, `python -c "open(...).write()"`, redirections) are not intercepted
   by the Edit/Write matcher. Bypass-label / governance-approved env vars are
   set in the same environment the agent controls. These are advisory.

### Root cause

The gate system was designed as a *cooperative* developer-experience layer
(catch honest mistakes early, produce reviewable evidence), but is described in
places as if it were an *enforcement boundary*. The trust boundary (what CI
recomputes from a ref the PR cannot influence) is not written down, so the
machinery's guarantees are overstated.

### Blast radius

Governance integrity for AI-authored work. An adversarial or malfunctioning
agent can produce green gate evidence without doing the work, or weaken the
guards in the same PR that CI uses to check them. The owner's protection against
this today is human review + branch protection, which is fine *if documented as
the real boundary*.

### Options

- **A — Document the cooperative-agent threat model (cheap, honest).** Add a
  section to AGENTS.md and `docs/ai-developer/rules.md` stating explicitly: the
  gate ledger is advisory; the enforced boundary is `ci.yml` + branch
  protection + human review; receipts/ledger events are not security controls.
- **B — Move verification server-side (real hardening).** In
  `workflow-gate.yml`, check out and run the evaluator/guards **from the base
  ref** (`github.base_ref`), feeding only the PR diff as data — so a PR cannot
  alter the code that judges it. Recompute every gate-critical obligation in CI
  rather than trusting committed events.
- **C — Both.** Document the model now (A); schedule the base-ref evaluator move
  (B) as the durable fix.

### Recommended direction

**C.** Do A immediately (removes the "overstated guarantee" harm, which is the
most actionable). File B as a hardening issue: the base-ref-evaluator change is
the only one of the four gaps that converts the gate from advisory to enforced
for governance-path PRs.

### ADR required? **Yes (lightweight).**

The threat model + the "CI is the only enforcement boundary" statement is an
architectural governance decision (ADR-042 surface). An ADR-042 addendum
recording the threat model and the base-ref-evaluator decision is appropriate.

### Proposed follow-up issues

- **Title:** `[P1][governance] Document the cooperative-agent threat model; declare CI+branch-protection+review as the only enforcement boundary`
  **Scope:** AGENTS.md + rules.md section; ADR-042 addendum; explicitly mark
  ledger/receipts as advisory.
- **Title:** `[P1][governance] Run the ADR-042 gate evaluator from the base ref so a PR cannot validate itself with modified guard code`
  **Scope:** `workflow-gate.yml` checks out evaluator/guards from
  `github.base_ref`; recompute gate-critical obligations server-side; tests for
  a guard-editing PR being judged by base-ref guards.

---

## 3. #1530 (DSN-6, P2) — No schema versioning/migration for persisted formats

### Current behavior (verified — partially evolved since filing)

- **lineage.db:** still **no `PRAGMA user_version`** and no migration
  framework. `_ensure_schema` (`core/lineage/store.py:241-252`) runs
  `CREATE TABLE IF NOT EXISTS` plus **two ad-hoc, hand-written column
  back-fills** added after the issue was filed: `_migrate_runs_provenance_degraded`
  (`store.py:261-270`, for #1527) and `_migrate_data_objects_content_hash`
  (`store.py:273-280`, for #1529). These detect a missing column via
  `PRAGMA table_info` and `ALTER TABLE ADD COLUMN`. So additive column changes
  are handled, but there is no version stamp, no ordered migration chain, and no
  story for non-additive changes (renames, type changes, table drops).
- **Checkpoints:** `WorkflowCheckpoint` (`engine/checkpoint.py:224-238`) is a
  versionless dataclass dumped to JSON; grep for `version|schema` in
  `checkpoint.py` returns nothing in the dataclass/serialization area.
- **Wire format:** `core/types/serialization.py` carries no
  `format_version`/`schema` field (grep returns none).
- **metadata_store:** `core/metadata_store.py:23` still states "**no historical
  data migration** is performed"; line 112 defers legacy migration to ADR-038
  §6 Phase 2.

### Root cause

Persistence formats were added incrementally without a versioning convention;
the "persisted artifacts" product promise outran the migration discipline. The
two recent ad-hoc `_migrate_*` functions show the cost is already being paid
reactively, one column at a time, with no shared mechanism.

### Blast radius

Any format change strands existing on-disk projects: a checkpoint or
wire-format change silently misparses (no version to detect mismatch); a
non-additive lineage change has no upgrade path. The ad-hoc column back-fills
will accumulate unboundedly and have no test that a fresh-schema DB and a
migrated DB converge.

### Options

- **A — Version stamps everywhere now (cheap, recommended floor).** Add
  `PRAGMA user_version` to lineage.db; add a `schema_version` int to
  `WorkflowCheckpoint` and to the wire envelope. On read, if the stored version
  is newer/older than supported, **refuse + explain** rather than misparse.
- **B — A + a minimal migration registry.** Replace the two ad-hoc `_migrate_*`
  with an ordered `(from_version → to_version)` migration list driven by
  `user_version`; define the policy ("forward-only; refuse on unknown future
  version"). Adds a small framework but stops the one-off accretion.
- **C — Full migration framework (alembic-style).** Over-engineered for a local
  single-file SQLite + JSON system; not warranted now.

### Recommended direction

**B.** A is the non-negotiable floor (do it for all three formats), and folding
the two existing ad-hoc back-fills into a `user_version`-driven chain is cheap
now and prevents the accretion the code already shows. Policy: forward-only
migrations; on an unknown *newer* version, refuse to open and tell the user to
upgrade SciStudio. Add a test asserting fresh-schema == migrated-schema.

### ADR required? **Yes (lightweight).**

Storage/format contracts and a migration policy are exactly the "schemas /
storage" surface AGENTS.md §3.4 says needs a spec/ADR. A short ADR defining the
version-stamp convention + forward-only/refuse policy across lineage.db,
checkpoints, and wire format.

### Proposed follow-up issue

- **Title:** `[P2][core] Add schema version stamps + minimal migration policy for lineage.db, checkpoints, and wire format`
- **Scope:** `PRAGMA user_version` for lineage.db; `schema_version` on
  `WorkflowCheckpoint` and the wire envelope; refuse-on-unknown-version reads;
  fold `_migrate_runs_provenance_degraded` / `_migrate_data_objects_content_hash`
  into a `user_version`-driven ordered migration chain; ADR for the policy;
  fresh-vs-migrated convergence test.

---

## 4. #1549 (DSN-10, P3) — Protected-path friction breeds untyped backdoors

### Current behavior (verified)

The protection system is provably causing the implicit coupling it exists to
prevent:

- `ApiRuntime.__init__` sets `self.event_bus.runtime = self  # type: ignore[attr-defined]`
  (`api/runtime/__init__.py:223-227`) with a comment saying a typed attribute
  "would require a core-change label." `api/ws.py` consumes it by duck-typing:
  `getattr(event_bus, "runtime", None)` at lines 162 and 194
  (`_cancel_running_workflows_for_gui_disconnect`, `_has_active_workflow_runs`).
- `api/ws.py:44-48` declares `BLOCKS_RELOADED = "blocks.reloaded"` as a bare
  string "because the events module is frozen by ADR-035/036 hard-scope rules"
  — i.e. the canonical place (`engine/events.py`) is off-limits, so the constant
  is duplicated out-of-band.
- `core/lineage/recorder.py:43-46` hardcodes `_BLOCK_DONE`/`_BLOCK_ERROR`/
  `_BLOCK_CANCELLED`/`_BLOCK_SKIPPED` string constants that must stay
  byte-identical to `engine/events.py`, to satisfy the `core` must-not-import-
  `engine` layer test (`pyproject.toml:200-202` even has a TYPE_CHECKING-only
  ignore for the single unavoidable type reference).

### Root cause

Protection granularity is **file-path friction**, not **semantic review**.
Freezing a file makes the *cheapest path* for a legitimate, type-safe extension
an *untyped, unreviewed backdoor* (a dynamic attribute set with `# type: ignore`,
a duplicated magic string). The friction inverts the intended outcome: the
runtime the protection guards accumulates exactly the implicit cross-module
coupling the protection is meant to stop.

### Blast radius

Type safety and reviewability of the runtime's most central seams (EventBus
back-reference; event-name constants). The duplicated string constants are a
latent correctness hazard: if `engine/events.py` ever changes an event name, the
`recorder.py` and `ws.py` duplicates drift silently and lineage/WS handlers stop
matching. Today it's contained because the strings happen to agree.

### Options

- **A — Lightweight ADR-amendment path for typed, reviewed extensions to frozen
  modules.** Allow a typed `runtime` attribute on `EventBus` and a single
  authoritative `BLOCKS_RELOADED` constant in `engine/events.py`, gated by a
  small reviewed amendment instead of full friction. Replace the duck-typed
  `getattr`/`# type: ignore` backdoors with the typed attributes.
- **B — Keep paths frozen, add a typed extension seam.** Define a typed protocol
  (e.g. `RuntimeRef`) the EventBus can carry without importing the runtime; move
  shared event-name constants to a `core`-importable constants module both
  layers can read (removes the duplication without `core → engine`).
- **C — Status quo.** Document the backdoors as accepted. Lowest cost; leaves
  the drift hazard and the inverted-protection smell.

### Recommended direction

**B, governed by A's amendment path.** A typed seam removes the `# type: ignore`
and the duplicated strings (the real correctness hazard) while preserving the
intent of protection; the lightweight amendment path is the governance change
that makes "protect semantics via review, not file paths via friction" real.
P3 — schedule after the P1s.

### ADR required? **Yes.**

This is a governance-model change (how protected paths are extended) plus edits
to ADR-035/036-frozen modules. An ADR amendment defining the typed-extension
review path and authorizing the specific typed additions is required;
`docs/ai-developer/**` and the frozen modules are governance surfaces.

### Proposed follow-up issue

- **Title:** `[P3][governance] Replace duck-typed runtime backdoors with typed seams; add a lightweight amendment path for frozen modules`
- **Scope:** ADR amendment for the typed-extension review path; typed `runtime`
  ref on EventBus (drop `getattr`/`# type: ignore` in `ws.py` + runtime); single
  authoritative `BLOCKS_RELOADED` + shared event-name constants removing the
  `ws.py`/`recorder.py` duplication; drift test.

---

## 5. #887 (P2/P3) — L1 GPU/CPU resource accounting not wired into dispatch

### Current behavior (verified at current paths under `engine/`)

The gap the issue describes is intact; only the package moved (`scieasy` →
`scistudio`, and the scheduler god-file split into `engine/scheduler/_*.py`):

1. `engine/scheduler/_dispatch.py:86` calls
   `self._resource_manager.can_dispatch(ResourceRequest(), active_count=...)`
   — a **default empty request**. It never reads `block.resource_request`.
2. `ResourceManager.acquire()` (`engine/resources.py:229-245`) has **zero
   production callers**: grep `\.acquire(` across `src/scistudio` returns none.
3. **No block declares `resource_request`/`requires_gpu`:** grep across
   `src/scistudio/blocks/` returns no files.
4. `_on_block_terminal` auto-release (`resources.py:258-266`) is subscribed but
   `_allocations` is never populated (only `acquire()` populates it, and that is
   never called) — a permanent no-op.

Concurrency today is gated by DAG topology + the OS memory watermark
(`can_dispatch` psutil check). The GPU branch is dead (`requires_gpu` always
False) and the CPU branch is dead (`_cpu_in_use` always 0). L2 (psutil
watermark) and L3 (ProcessMonitor → PROCESS_EXITED) work.

### Root cause

L1 slot accounting was scaffolded (ADR-022/027) but never connected: the Block
contract never gained a `resource_request`, the scheduler never threads it, and
`acquire/release` were left as test-only API. The owner's 2026-05-14 assessment
(in the issue) deliberately deferred wiring because current workloads are not
resource-bound (AI blocks run cloud LLMs; the 100 GB MS-imaging case uses
lazy/chunked storage).

### Blast radius

Low **today** (confirmed by owner in the issue). Becomes high when: a block runs
local GPU inference, multi-tenant/shared-GPU deployment, or parallel
heavyweight-CPU branches on capacity-bound machines. Secondary harm *now* is
doc-reality divergence (ARCHITECTURE.md / ADR.md claim the wiring exists).

### Options (as enumerated in the issue, re-confirmed)

- **A — Document reality, mark L1 future work.** Fix ARCHITECTURE.md/ADR.md to
  describe DAG + memory-watermark gating; keep `acquire/release/ResourceRequest`
  as forward scaffolding; add `# TODO(L1)` at `_dispatch.py:86`. ~1 day.
- **B — Implement L1 fully.** `resource_request: ClassVar[ResourceRequest]` on
  `Block`; per-block declarations; scheduler reads it + `await acquire()` before
  dispatch + ensure auto-release; integration tests. ~1 week; Block-contract
  change touching plugins.
- **C — Hybrid opt-in.** Only AIBlock(local)/ProcessBlock declare; scheduler
  uses `getattr(block, "resource_request", ResourceRequest())`. ~2 days; sets a
  messy "some blocks opt in" precedent.

### Recommended direction

**A now** (matches the owner's own proposed decision in the issue), with B
gated on a concrete trigger (first local-inference AIBlock / first GPU
contention report / first multi-tenant deployment). The most actionable harm
today is the doc lie; fix that and add the TODO marker so the deferral is
visible per AGENTS.md §3.6.

### ADR required?

**A: No** (doc-only; ROADMAP already shows L1 `[ ]`). **B/C: Yes** — a Block
contract change is exactly the kind of cross-module, hard-to-reverse change that
needs an ADR addendum to ADR-022/027.

### Proposed follow-up issues

- (#887 stays open as the tracking issue.) Optionally split:
- **Title:** `[docs] Correct ARCHITECTURE.md/ADR.md resource-management section to describe DAG + memory-watermark gating; add TODO(L1) at dispatch`
  **Scope:** Option A only.
- **Title:** `[feature][gated] Wire L1 GPU/CPU slot accounting into dispatch (Block.resource_request + acquire/release)`
  **Scope:** Option B; **blocked until a real trigger** — note the gate in the
  issue body.

---

## 6. #1336 (P0 label) — Circular import: `blocks.registry ↔ ai.agent.*`

### Current behavior (verified — **the cycle no longer exists at module level**)

This issue was filed 2026-05-21 against an older tree. The landed refactor
(umbrella #1427 / ADR-046 scheduler+registry split) has **already broken the
10-module cross-layer SCC**. Evidence:

- An AST-based SCC scan over **module-level** imports of all
  `src/scistudio/**.py` (excluding `TYPE_CHECKING` blocks and function-body
  imports) finds **one** multi-module SCC, and it is unrelated:
  `{scistudio.core.versioning, scistudio.core.versioning.git_engine}` (a
  package-`__init__` ↔ submodule re-export pair, internal to `core`). **No SCC
  contains both `blocks.*` and `ai.agent.*`.**
- `blocks/ai/ai_block.py` has **no module-level import** of `scistudio.ai.agent`
  — the only reference, `from scistudio.ai.agent.terminal import ...`, is a lazy
  function-body import at line 442.
- The new `blocks/registry/` package does **not** import concrete block classes
  at top level. `_scan.py` imports `AIBlock`/`LoadData`/`SaveData`/
  `SubWorkflowBlock` lazily *inside* `_scan_builtins` (line 106), and the
  `registry/__init__.py` defers `_scan`/`_capability`/`_spec` helpers into
  method bodies. The acceptance-criteria bullets ("`ai_block` does not import
  `ai.agent.*`", "`registry` does not import the concrete block classes at
  module top level") are **already satisfied**.
- `ai/agent/terminal.py` has **no module-level import of `blocks`**.

Additionally, the import-linter contract set has *also* moved on: there is now a
`forbidden` contract "Blocks must not depend on engine, api, or **ai** services"
(`pyproject.toml:204-208`, `forbidden_modules` includes `scistudio.ai`) with
only a narrow carve-out for `blocks.ai.ai_block -> scistudio.engine.pty_control`.
The issue's premise ("`lint-imports` is happy only because contracts don't check
`blocks → ai`") is no longer true — the contract now exists.

> Caveat: import-linter could not be executed here (the package is not installed
> in this read-only audit env: `lint-imports` reports "Could not find package
> 'scistudio'"). The AST scan above is the substitute evidence and is
> conservative (it counts a static module-level edge wherever one exists). A CI
> run of `lint-imports` should confirm the contract passes green.

### Root cause (historical) and current state

The original cycle was import-time auto-registration (`registry` imports block
classes) crossing the Layer-2/Layer-4 boundary (`blocks` ↔ `ai.agent`). The
ADR-046 refactor converted both directions to lazy/injected imports, which is
essentially "Step 1/Step 2" of the issue's own suggested fix shape (decouple
registry from concrete classes; don't import `ai.agent` from `blocks` at module
level). The decoupling was achieved via deferred imports rather than the
explicit `blocks.ai.protocols` interface the issue proposed.

### Blast radius

None acute — the architectural-inversion import cycle is gone. Residual concern:
the decoupling relies on **deferred imports** (a runtime convention) rather than
a **structural** interface (`blocks.ai.protocols`). Deferred imports are easy to
accidentally re-promote to module level, which would silently reintroduce the
SCC. The standing guard against that is the new `blocks → ai` forbidden
contract — *if* CI actually runs `lint-imports`.

### Options

- **A — Close #1336 as already-resolved; verify with a CI `lint-imports` run +
  add the AST-SCC scan as a test.** Confirm green, then unblock #1341
  (import-linter contract) and add `type = "no_cycles"` once all four SCCs are
  confirmed gone. Lowest effort; locks in the win.
- **B — Also do the structural Step-2 (`blocks.ai.protocols`).** Replace the
  lazy `ai.agent.terminal` import in `ai_block.py` with a runtime-injected
  protocol, so the boundary is enforced by *types* not by *import placement*.
  Stronger guarantee; modest effort; arguably the "right" end state.
- **C — Leave as-is, no verification.** Risk: silent regression of a deferred
  import back to module level.

### Recommended direction

**A, then B as a small follow-up.** The cycle is empirically gone; the priority
is to (1) confirm with the real `lint-imports` in CI, (2) add the AST-SCC scan
as a committed test so a future deferred-import promotion fails CI, and (3)
unblock #1341. B (the `blocks.ai.protocols` interface) makes the layer boundary
structural rather than convention-based and should follow, but it is no longer
urgent. The P0 label should be **downgraded** given the SCC is resolved.

### ADR required? **No (for A).**

A is verification + a test + closing the issue. B (introducing
`blocks.ai.protocols` as the formal layer seam) is an architecture-direction
change worth a short ADR note, but it is optional and lower priority now.

### Proposed follow-up issues

- **Title:** `[verify] Confirm blocks↔ai.agent SCC is resolved (lint-imports green + committed AST-SCC test), then unblock #1341`
  **Scope:** Run `lint-imports` in CI on the "Blocks must not depend on ... ai"
  contract; add an AST SCC scan test asserting no `blocks*+ai.agent*` SCC;
  close #1336; unblock #1341; downgrade the P0 label.
- **Title (optional, lower priority):** `[refactor] Make the blocks→ai boundary structural via blocks.ai.protocols instead of deferred imports`
  **Scope:** Issue's Step 2 — inject an agent-spawn protocol into AIBlock; remove
  the lazy `ai.agent.terminal` import.

---

## Summary table

| Issue | Current state | Recommendation | ADR? | Severity (as found) |
|-------|---------------|----------------|------|---------------------|
| #1517 | Confirmed; 3 corruption paths live | Run identity (Option B) + acute fixes | Yes | P1 |
| #1519 | Confirmed; gaps 1–4 persist post-Add.6 | Document model + base-ref evaluator | Yes (light) | P1 |
| #1530 | Partially evolved (ad-hoc back-fills, no version stamp) | Version stamps + min migration policy | Yes (light) | P2 |
| #1549 | Confirmed; backdoors live + drift hazard | Typed seam + amendment path | Yes | P3 |
| #887  | Confirmed; L1 fully dead | Document reality (A); gate B on trigger | A:No, B:Yes | P2/P3 |
| #1336 | **Resolved at module level** (cycle gone) | Verify + test + close; downgrade P0 | No (A) | P0 label → stale |

**Cross-cutting note:** #1517, #1549, and part of #1519 all trace to the same
root — the process-global `EventBus` singleton with no run identity and a frozen
contract. Sequencing the run-identity ADR (#1517) and the typed-seam amendment
(#1549) together would let the typed `EventBus.runtime` attribute and the
`run_id` field land under one coherent EventBus-contract revision.
