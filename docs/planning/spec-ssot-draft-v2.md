# SciEasy Interface SSOT — Draft v2 (Phase 5 manager-fix)

> **Phase 5 deliverable**: draft v1 + Phase 4 audit findings applied + manager dispositions.
>
> **🛑 PAUSED FOR CROSS-CASCADE RECONCILIATION (user direction)**.
> Codex side is running parallel Phase 0-5. Manager waits for Codex's draft v2 before Phase 6 SSOT-writing.
>
> **Source**: `docs/planning/spec-ssot-draft-v1.md` (Phase 3 manager merge) + 8 Phase 4 audit reports (`docs/audit/2026-05-17-spec-ssot-p4-*.md`).
> **Baseline SHA**: `a4b8b5f`. **Umbrella**: #1090. **Umbrella PR**: #1091 [Claude Code].
>
> **Format**: this document is a DELTA over draft v1. Phase 6 SSOT writer applies these deltas to produce `docs/specs/INTERFACE_SPEC.md` (after cross-cascade reconciliation).

---

## Phase 4 findings summary (8 audit reports)

| Auditor | Scope | P1 | P2 | P3 | Notes |
|---|---|---|---|---|---|
| A1 | block-abc + port-system | 6 | 7 | 5 | ports_from_config_dicts dedup direction wrong; AppBlock label conflicts; missing #TBD placeholders |
| A2 | data-types + storage-backends | 3 | 4 | 5 | StorageReference + CompositeStore label direction errors |
| A3 | collection-transport + block-registry | 0 (PASS) | 2 | 0 | LazyList upgrade per I1 #707; core.materialisation file naming |
| A4 | execution-engine | 5 | 5 | 0 | events.py stale matrix; ResourceManager.acquire() sub-label flip; save/load_checkpoint MISSING from inventory; RunHandle label conflict |
| A5 | lineage-db + versioning-git | 1 | 2 | 0 | RunContext family d-private→d-document (in __all__); 8 CREATE INDEX absent from ARCH |
| A6 | rest-api + ws-sse-protocol | 9 | 2 | corrections | validate_connection (#889); LineageRunDetail field-name mismatch; 3 NEW issues need opening; WS inbound message names WRONG; route count 42→61 |
| A7 | mcp-tools + agent-provisioning | 2 | 2 | 0 | SKILL.md L103 ghost `list_block_runs`; claude_agents_md.md Codex hook staleness ×5 |
| AX | cross-architecture | 9+4 missing | 5 | 4 | **HUGE: PROJECT_TREE.md still registers Image/Spectrum/PeakTable from scieasy.core.types.* — contradicts ARCH §4.1/§5.4 "no domain subtypes in core"** |
| **TOTAL** | | **39+ P1** | **~29 P2** | **~14 P3** | |

---

## P1 dispositions (manager fix → draft v2)

### Module 1 — block-abc

**A1-P1-01 `ports_from_config_dicts` dedup direction**: ACCEPT.
- Draft v1 said "last-wins"; code is **first-wins** (`continue` on duplicate).
- Fix: update draft v2 Module 2 (port-system) entry; sub-label remains d-document.

**A1-P1-02 `AppBlock.bridge.prepare` (#1080)**: ACCEPT.
- Draft v1 said b-docs-wins; I2 + A1 say **c-impl** (materialisation path doesn't exist).
- Cross-ref AX-P1 module assignment: `core.materialisation` zone (ARCH §4.7) issue → see AX disposition below.
- Fix: change to c-impl; link to #1080 + #1078.

**A1-P1-03 `AppBlock._bin_outputs_by_extension` (#1079)**: ACCEPT.
- Same pattern as -02; change to c-impl.

**A1-P1-04 Port-system d-count wrong**: ACCEPT.
- Draft v1 said d=4; M1 enumerates ≥5 (added `Port.is_collection`, `validate_port_constraint`, `port_accepts_type`, `port_accepts_signature`, `validate_connection`, `ports_from_config_dicts`, `ConstraintFn`).
- Fix: recompute module 2 breakdown → d=7, a=4, b=2. Total = 13 entries (matches M1).

**A1-P1-05 `AIBlock.auto_complete` config field (#882) missing**: ACCEPT.
- Fold I2 entry into Module 1; d-document.

**A1-P1-06 Module 2 missing #TBD-* placeholders**: ACCEPT.
- Add: `#TBD-port-is-collection-document`, `#TBD-validate-port-constraint-document`, `#TBD-port-helpers-document`, `#TBD-ports-from-config-dicts-document`, `#TBD-constraintfn-document`, `#TBD-inputport-constraint-annotation`, `#TBD-port-constraint-callable-semantics-arch-update`.

### Module 2 — port-system
(covered above under Module 1 fixes)

### Module 3 — data-types

**A2-P1 StorageReference label direction**: ACCEPT A2's correction.
- Draft v1 says b-docs-wins (fix code: add `frozen=True`); A2 + M2 say **b-code-wins** (fix docs: remove "immutable" claim, because adding `frozen=True` would break the `DataObject.storage_ref` setter).
- Fix: flip to b-code-wins. Issue placeholder `#TBD-storage-reference-immutability-doc-fix`.

**A2-P1 CompositeStore label conflict**: ACCEPT.
- Draft v1 entry shows label `a` but the key-decisions prose describes two `b` findings. Fix: change label to **b-docs-wins** (document the chunk_size and non-atomic behavior gaps).

**A2-P1 FrameworkMeta `derived_from` type fix incomplete**: ACCEPT.
- Code has `derived_from: str | None`; D1 has `UUID | None`. Manager risk: Phase 6 writer fixes only one field.
- Fix: explicit b-code-wins entry for FrameworkMeta noting BOTH `object_id: str` and `derived_from: str | None`.

### Module 4 — storage-backends
(covered above; CompositeStore + StorageReference)

### Module 5 — collection-transport

**A3-P2 LazyList upgrade per I1 #707**: ACCEPT (escalate to P1 since it changes label).
- Draft v1 a; should be **b-docs-wins** (`_load_item` calls `.view().to_memory()`, ViewProxy was eliminated in ADR-031).
- Fix: re-classify LazyList.

**AX-P1 `core.materialisation` zone assignment**: ACCEPT.
- Draft v1 assigned to collection-transport; ARCH §4.7 zones it to `blocks/app|io/`.
- Fix: re-assign to **block-abc** module (under AppBlock/IOBlock subscope) OR create a new sub-module note in collection-transport saying "this module hosts the proposed `core.materialisation` per #1078, but final placement TBD per ARCH §4.7 — may end up under blocks/io/".
- Manager decision: keep under collection-transport for v2; flag for Phase 6 final placement.

### Module 6 — block-registry
(A3 found no P1 — clean module)

### Module 7 — execution-engine

**A4-P1-1 events.py:L67-79 subscription matrix stale**: ACCEPT (separate code-fix issue).
- Add issue placeholder `#TBD-events-subscription-matrix-code-fix`. SSOT entry for EventBus subscription matrix is correct (uses C4's verified call sites).

**A4-P1-2 `#887 ResourceManager.acquire()` sub-label flip**: ACCEPT.
- Draft v1 followed I1's b-code-wins; A4 says **b-docs-wins** is correct (ARCH §6.4 PRIMARY says acquire() should be wired into _dispatch; code must catch up). Plus memory_high_watermark 0.80 vs 0.90 = separate b-code-wins.
- Fix: split into 2 entries — `ResourceManager.acquire()` b-docs-wins + `ResourceManager.memory_high_watermark` b-code-wins.

**A4-P1-3 `save_checkpoint` + `load_checkpoint` MISSING**: ACCEPT.
- Both module-level functions at `checkpoint.py:L244-L284`, public. C4 inventory missed them. True execution-engine count is **49** not 47.
- Fix: add both as d-document entries.

**A4-P1-4 `deserialize_intermediate_refs` label conflict**: ACCEPT.
- M2 d-private vs draft v1 d-document. Draft v1 correct (normative constraint about execute-from path).
- Fix: confirm draft v1 d-document; document the "must NOT be called in execute-from path" constraint.

**A4-P1-5 `RunHandle` label conflict**: ACCEPT.
- Draft v1 d-private, M2 b-code-wins, A4 recommends **d-document**.
- Fix: change to d-document with note "future-evolution placeholder, currently never returned by any BlockRunner".

### Module 8 — lineage-db

**A5-P1 `RunContext` family d-private→d-document**: ACCEPT.
- M2 had d-private; A5 confirms `lineage/__init__.__all__` exports all 4 symbols (`RunContext`, `get_run_context`, `set_run_context`, `reset_run_context`) → must be **d-document**.
- Fix: change all 4 to d-document.

**A5-P2 `render_methods_markdown` not in __all__**: ACCEPT.
- Downgrade to d-document with import-path note (only via `scieasy.core.lineage.methods_export`).

**A5-P2 8 CREATE INDEX statements absent from ARCH §4.4**: ACCEPT.
- Add to LineageStore behavior note in SSOT.

### Module 9 — versioning-git

**A5 confirmations**: PASS. `git_author.json` c-drop, `watcher.py` c-drop verified. 22 GitEngine methods enumerated. `write_default_gitignore` is in __all__ → confirmed a.

### Module 10 — rest-api

**A6-P1-01 `validate_connection` (#889)**: ACCEPT. b-code-wins confirmed.

**A6-P1-02 `LineageRunDetail` field name mismatch**: ACCEPT — NEW issue needed.
- Backend returns `{"run": ..., "block_executions": [...]}`; TS expects `{run, blocks, environment_snapshot, workflow_yaml_snapshot}`.
- 3 mismatches: field rename + 2 missing backend fields.
- Phase 9 action: open issue `#TBD-lineage-rundetail-fe-be-drift`.
- Fix: add b-code-wins entry in module 10.

**A6-P1-03 `LineageRerunResponse.new_run_id` missing**: ACCEPT — NEW issue.
- Phase 9 action: open issue `#TBD-lineage-rerun-response-new-run-id`.
- Fix: add b-code-wins entry.

**A6-P1-04 `TypeHierarchyEntry.ui_ring_color`**: ACCEPT. b-code-wins confirmed.

**A6-P1-05 `DynamicPortsConfig.input_port_mapping`**: ACCEPT. b-docs-wins confirmed.

**A6-P1-06 `configure_logging` stub (#827)**: ACCEPT. c-impl confirmed.

**A6-P1-07 `CancelBlockRequest`/`CancelWorkflowRequest` dead code**: ACCEPT — NEW issue.
- Phase 9 action: open issue `#TBD-cancel-request-schemas-remove`.
- Fix: d-remove entries.

**A6-P1-08 WS inbound message names WRONG**: ACCEPT — critical correction.
- Draft v1 says: `user_message`, `permission_decision`
- Code has: `block_user_marked_done`, `block_user_cancel`
- Fix: correct Module 11 inbound message list. Phase 6 SSOT must use code-truth names.

**A6-P1-09 `block_pty_opened`/`block_pty_closed`/`blocks.reloaded` EventBus bypass**: ACCEPT (dual routing paths).
- Confirmed d-document; SSOT should document the bypass explicitly.

**A6 corrections**:
- Route count 42→**61** (includes aliases, IPC routes, ADR-036 file/template routes). Update.
- `GET /api/blocks/template` (ADR-036 §3.12) live but missing — add as BLK-T1 (a).
- 2 IPC routes (`POST /api/ai/pty/internal/request-tab` and `/notify`) missing — add as d-document.

### Module 11 — ws-sse-protocol
(WS message name correction covered above; also `block_user_cancel` writes `mark_done.json` per A6-P2-02)

### Module 12 — mcp-tools

**A7-P1 SKILL.md L103 ghost `list_block_runs`**: ACCEPT.
- c-drop in draft v1 is correct labeling; fix is code-side: replace string in `src/scieasy/_skills/scieasy/SKILL.md:L103` with `get_block_logs`.
- Phase 9 action: open code-fix issue `#TBD-skill-md-ghost-tool-fix`.

**A7-P2 `_context.py` docstring "25 MCP tools"**: ACCEPT (P2 → fold).
- One-line fix; tracker `#TBD-mcp-context-docstring-fix`.

### Module 13 — agent-provisioning

**A7-P1 `claude_agents_md.md` template Codex hook deferral staleness** (5 occurrences): ACCEPT.
- Code-fix issue `#TBD-claude-agents-md-codex-hook-text-fix`.
- Template currently lies to agents about hook coverage.

### Cross-cutting (AX findings)

**AX-P1-1 `allowed_input_types` default contradiction**: ACCEPT (already b-code-wins; reinforces fix direction).

**AX-P1-2 `postprocess` signature conflation**: ACCEPT.
- Draft v1 conflated `validate` and `postprocess` annotations.
- ARCH §5.1 shows postprocess uses `dict[str, DataObject]` (not Collection).
- Fix: clarify Module 1 entries.

**AX-P1-3 PROJECT_TREE.md registers Image/Spectrum/PeakTable from `scieasy.core.types.*`** ⚠️ **BIGGEST UNCAUGHT FINDING**: ACCEPT — NEW issue.
- ARCH §4.1 + §5.4 say "no domain subtypes in core" (ADR-027 D2 explicit).
- PROJECT_TREE.md still registers them — contradicts.
- Fix:
  1. Add new cross-cutting entry to draft v2: `PROJECT_TREE.md entry-points table` (b-docs-wins — code reflects ADR-027 D2; PROJECT_TREE.md needs update)
  2. Phase 9 action: open issue `#TBD-project-tree-entry-points-fix`.
  3. Manager note in Phase 6 SSOT: PROJECT_TREE.md is supplementary doc, ARCH is primary — this conflict goes into ADR↔doc reconciliation log (not blocking SSOT, but ARCH wins).

**AX-P1-4 `memory_high_watermark` value**: ACCEPT (covered under Module 7 A4 fixes).

**AX-P1-5 `chatSlice` claim**: PARTIAL ACCEPT — investigate.
- Draft v1 said `chatSlice` doesn't exist (based on C6 inventory).
- AX says ARCH §9.10 AND PROJECT_TREE.md confirm it exists.
- ACTION: Phase 6 manager re-verify by grep `frontend/src/store/` for chatSlice. If found, draft v1 was wrong (a not b-code-wins).

**AX-P1-6 `finish_ai_block` missing from ARCH §7.2**: ACCEPT.
- Already captured (b-docs-wins in Module 12); reinforce explicit ARCH edit directive.

**AX-P1-7 `git_author.json` fix target incomplete**: ACCEPT.
- ARCH §10 workspace diagram ALSO has stale ref. Add to c-drop fix scope.

**AX-P1-8 `watcher.py` PROJECT_TREE.md not updated**: ACCEPT.
- Add fix target.

**AX-P1-9 `core.materialisation` zone**: covered above.

**AX P1 missing entries**:
- ACCEPT: `Collection.storage_refs()` / `DataObject.storage_ref` bilateral naming — add as d-document.
- ACCEPT: `CheckpointManager` 4 EventBus subscriptions — add as d-document.
- ACCEPT: `ProcessBlock.setup()`/`teardown()` lifecycle hooks — add explicit module 1 entries.
- ACCEPT: `SubWorkflowBlock` ARCH §5.3 `WorkflowLoader` update flag — already in module 1 b-code-wins; reinforce.

---

## P1 REJECTIONS (with reason)

(none — manager accepted all P1 findings; some downgraded to deferred but logged.)

---

## P2 dispositions (selective application)

**Applied to draft v2**:
- A2-P2 `with_meta_changes` d-private→d-document (exported in __all__)
- A2-P2 `TypeRegistry._validate_meta_class` add as d-document
- A2-P2 StorageBackend 6-method note (use C2 not D1 as source)
- A4-P2 `Block.resource_request` ClassVar sub-entry for #887
- A4-P2 `asyncio.ensure_future()` deprecation note on ProcessMonitor
- A4-P2 `register_async_process`/`build_worker_payload` d-private→d-document (no underscore)
- A4-P2 `set_in_process_handler`/`get_in_process_handler` explicit listing
- A6-P2-01 chatSlice phantom note (pending AX investigation)
- A7-P2 _context.py docstring fix (#TBD-mcp-context-docstring-fix)
- A7-P2 templates/codex_config.toml never-loaded explicit note

**Deferred to Phase 7+**:
- A1's 7 P2 (annotation nits — covered when Phase 6 lifts verbatim signatures)
- A3's 2 P2 (LazyList already escalated to P1; core.materialisation file naming → Phase 6 placement decision)
- A5's 2 P2 (covered above)
- AX's 5 P2 (covered above)

## P3 dispositions

**Bundled as Phase 6 cleanup tasks** — none individually applied to draft v2.

---

## Aggregate count update (draft v2)

| Phase | Total | a | b | c | d |
|---|---|---|---|---|---|
| Draft v1 | ~180 | ~80 | ~28 | ~12 | ~60 |
| **Draft v2 (post-Phase 4 fixes)** | **~195** | **~82** | **~33** | **~16** | **~64** |

Delta:
- +5 b (label flips: StorageReference, CompositeStore, ResourceManager.acquire, LazyList, postprocess clarification)
- +4 c (newly recognized: 3 new FE-BE issues + PROJECT_TREE.md)
- +4 d (missing entries: save/load_checkpoint, 2 IPC routes, validate_port_constraint family, RunContext upgrades)

---

## NEW issues to open in Phase 9 (added in Phase 5)

Beyond the draft v1 #TBD-* list, Phase 4 surfaced these:

1. `#TBD-storage-reference-immutability-doc-fix` (A2-P1)
2. `#TBD-compositestore-iter-write-behavior-doc` (A2-P1)
3. `#TBD-events-subscription-matrix-code-fix` (A4-P1)
4. `#TBD-process-monitor-poll-interval-configurable` (C4 flag)
5. `#TBD-lineage-rundetail-fe-be-drift` (A6-P1-02)
6. `#TBD-lineage-rerun-response-new-run-id` (A6-P1-03)
7. `#TBD-cancel-request-schemas-remove` (A6-P1-07)
8. `#TBD-ws-inbound-message-names-correction` (A6-P1-08 — code-fix? or just docs/spec?)
9. `#TBD-skill-md-ghost-tool-fix` (A7-P1)
10. `#TBD-mcp-context-docstring-fix` (A7-P2)
11. `#TBD-claude-agents-md-codex-hook-text-fix` (A7-P1)
12. `#TBD-project-tree-entry-points-fix` (AX-P1-3) ⚠️ HIGH PRIORITY
13. `#TBD-arch-workspace-diagram-git-author-fix` (AX-P1-7)
14. `#TBD-project-tree-watcher-py-removal` (AX-P1-8)

---

## Cross-cascade reconciliation checklist (when Codex draft v2 arrives)

Manager pre-defined questions to ask of Codex's draft v2:

1. **Module count match?** Codex should also have N=13. If different, why.
2. **Aggregate label breakdown match?** ~45% a, ~17% b, ~8% c, ~33% d. Significant divergence = methodology drift.
3. **Same biggest finding?** Does Codex's draft also surface ADR-028 §D8 cluster (#1073-#1078)?
4. **Same PROJECT_TREE.md ⚠️ finding?** Did Codex's AX-equivalent catch the Image/Spectrum/PeakTable contradiction?
5. **WS inbound message names**: did Codex make the same draft v1 error (user_message/permission_decision) and catch it in Phase 4?
6. **finish_ai_block c-class**: do both sides agree?
7. **versioning-git entirely d-class**: do both sides agree?
8. **List of NEW issues each side wants to open**: any divergence in which gaps got noticed?
9. **Sub-label distributions** (b-code-wins vs b-docs-wins balance): is one side more aggressive about code-as-truth?
10. **`core.materialisation` placement**: where does Codex's draft put it?

Reconciliation outcome categories:
- **Convergent**: both sides agree → high confidence → goes to Phase 6 SSOT as-is
- **One-side-stronger evidence**: e.g., Codex catches something my side missed → manager adopts Codex's call
- **Divergent without clear winner**: escalate to user for human decision

---

## Phase 5 STOP — manager waiting on Codex draft v2

This document is draft v2. Phase 6 (SSOT-writing) is BLOCKED until Codex's parallel draft v2 arrives + cross-cascade reconciliation completes.

When Codex draft v2 arrives, manager:
1. Reads it end-to-end
2. Applies the 10-point reconciliation checklist above
3. Produces a CONVERGED draft (call it draft v3) capturing both sides' decisions
4. Then proceeds to Phase 6 — write `docs/specs/INTERFACE_SPEC.md` from the converged draft v3

---

## Source reports (Phase 4 audit batch)

- `docs/audit/2026-05-17-spec-ssot-p4-A1.md` — block-abc + port-system
- `docs/audit/2026-05-17-spec-ssot-p4-A2.md` — data-types + storage-backends
- `docs/audit/2026-05-17-spec-ssot-p4-A3.md` — collection-transport + block-registry
- `docs/audit/2026-05-17-spec-ssot-p4-A4.md` — execution-engine
- `docs/audit/2026-05-17-spec-ssot-p4-A5.md` — lineage-db + versioning-git
- `docs/audit/2026-05-17-spec-ssot-p4-A6.md` — rest-api + ws-sse-protocol
- `docs/audit/2026-05-17-spec-ssot-p4-A7.md` — mcp-tools + agent-provisioning
- `docs/audit/2026-05-17-spec-ssot-p4-AX.md` — cross-architecture

All findings + dispositions consolidated above.
