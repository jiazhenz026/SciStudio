# AX — Phase 4 cross-architecture audit
Date: 2026-05-17
Auditor: AX (CLAUDE CODE side, ARCHITECTURE.md primary authority)
Branch: track/adr-040
Draft input: `docs/planning/spec-ssot-draft-v1.md` (all 13 modules, Phase 3 manager-merged consolidation)

---

## Summary

| Severity | Count |
|---|---|
| P1 (must fix before draft v2): contradictions with ARCHITECTURE.md | 9 |
| P1 (ARCH-mandated entries missing from draft v1) | 4 |
| P2 (ADR-mandated entries missing from draft v1) | 5 |
| P3 (ADR↔draft contradictions, ARCH silent, draft recommended) | 4 |
| LOG-ONLY ADR↔ADR conflicts | 3 |

---

## P1 findings — ARCHITECTURE.md contradictions

### `block-abc` — `allowed_input_types` default value

- **ARCH §5.2 (Variadic ports ClassVar table) says**:
  > `allowed_input_types: ClassVar[list[type]] = [DataObject]   # no constraint`
- **Draft v1 Module 1 says**:
  > `Block` class itself: **b-code-wins** (allowed_input_types default `[]` not `[DataObject]`, plus many ClassVars ARCH omits)
- **Issue**: Draft declares code wins over ARCH and that ARCH should be updated. This is the correct framing for the SSOT, but ARCH §5.2 currently asserts `[DataObject]` as the canonical default. If code genuinely has `[]`, ARCH §5.2 is in direct contradiction with the running implementation. The ARCH text must be reconciled before Phase 6.
- **Recommended fix for Phase 5**: Add an explicit note in Module 1 entry that this is a ARCH §5.2 update requirement (P1 fix: update ARCH §5.2 default to `[]`). Do not silently claim code wins without flagging the ARCH text for update.

### `block-abc` — `postprocess` signature inconsistency

- **ARCH §5.1 says**:
  ```python
  def postprocess(self, outputs: dict[str, DataObject]) -> dict[str, DataObject]:
  ```
- **Draft v1 Module 1 says**:
  > `Block.postprocess`: **b-code-wins** (same pattern as validate — annotation `dict[str, Any]` vs ARCH `dict[str, Collection]`)
- **Issue**: The draft says the annotation is `dict[str, Collection]` in ARCH vs `dict[str, Any]` in code. But ARCH §5.1 literally shows `dict[str, DataObject]` for `postprocess`, not `dict[str, Collection]`. The draft has an incorrect characterization of what ARCH says for `postprocess`. The validate/postprocess lines appear to have been conflated. ARCH §5.1 validates `dict[str, Collection]` but postprocesses `dict[str, DataObject]` — these are different.
- **Recommended fix for Phase 5**: Correct the Module 1 key decision line for `postprocess`. ARCH §5.1 says `dict[str, DataObject]` (not Collection). Code says `dict[str, Any]`. Decision is still b-code-wins but the ARCH citation must be accurate: "ARCH §5.1 says `dict[str, DataObject]`; code uses `dict[str, Any]`."

### `data-types` — Core entry-points table registers domain subtypes in `core` package

- **ARCH §4.1 says**:
  > The diagram above is the complete core type surface. There are no `Image`, `MSImage`, `Spectrum`, `PeakTable`, `AnnData`, or `SpatialData` classes in core.
- **ARCH §5.4 says**:
  > Core ships only the seven base types listed in §4.1 … **No domain subtypes live in core.**
- **PROJECT_TREE.md "Key entry_points" section says** (verbatim):
  ```toml
  [project.entry-points."scieasy.types"]
  # Built-in domain types (base types are always available, no entry_point needed)
  image = "scieasy.core.types.array:Image"
  spectrum = "scieasy.core.types.series:Spectrum"
  peak_table = "scieasy.core.types.dataframe:PeakTable"
  ```
- **Issue**: PROJECT_TREE.md (part of the primary authority documents) explicitly registers `Image`, `Spectrum`, and `PeakTable` as entry-points pointing to `scieasy.core.types.*`. This directly contradicts the ARCH §4.1/§5.4 claim that these types are NOT in core. This is a first-order architectural contradiction within the primary authority documents themselves. **Draft v1 Module 3 (data-types) does not flag this contradiction at all** — it classifies the 7 core types as all 'a' (well-aligned) without noting this inconsistency.
- **Recommended fix for Phase 5**: Draft v1 Module 3 must add a P1 note: "PROJECT_TREE.md §entry_points registers `Image`/`Spectrum`/`PeakTable` from `scieasy.core.types.*`, contradicting ARCH §4.1/§5.4 which prohibit domain subtypes in core. Either (a) the PROJECT_TREE entry-point table is wrong and should reference plugin packages, or (b) ARCH §4.1/§5.4 is wrong and these three types do live in core. This requires manager decision before Phase 6."

### `execution-engine` — `ResourceManager.memory_high_watermark` default

- **ARCH §6.4 says**:
  ```python
  def __init__(
      self,
      memory_high_watermark: float = 0.80,    # pause dispatch above 80% system RAM
      memory_critical: float = 0.95,
  ):
  ```
- **Draft v1 Module 7 says**:
  > `ResourceManager`: **b-code-wins** (C4 + xcheck flag: `memory_high_watermark` class docstring says 0.80, code default is 0.90 — code wins, doc update needed)
- **Issue**: ARCH §6.4 has the authoritative architecture showing `0.80`. Draft claims code has `0.90` and declares b-code-wins. This means ARCH §6.4 contains a specific numeric claim (`0.80`) that conflicts with the actual running code (`0.90`). The draft correctly identifies this as a b-code-wins situation, but the ARCH document itself needs the numeric update. Draft v1 must explicitly state "ARCH §6.4 must be updated: change `0.80` to `0.90`" as a concrete edit target.
- **Recommended fix for Phase 5**: Add explicit ARCH edit target to Module 7 entry: update ARCH §6.4 `memory_high_watermark: float = 0.80` to `0.90`.

### `rest-api` — Zustand slices count mismatch (ARCH §9.10 vs PROJECT_TREE.md)

- **ARCH §9.10 says** (7 slices):
  `projectSlice`, `workflowSlice`, `executionSlice`, `uiSlice`, `previewSlice`, `paletteSlice`, `chatSlice`
- **PROJECT_TREE.md `store/` section says** (9 slices: the 7 above plus):
  `lineageSlice` (ADR-038), `gitSlice` (ADR-039)
- **Draft v1 Module 10 says**:
  > Frontend Zustand slices (10 actual vs ARCH §9.10's 7): **b-code-wins** (`chatSlice` doesn't exist; code adds `gitSlice`, `lineageSlice`, `tabSlice`, `terminalTabsSlice`. Doc update.)
- **Issue**: The draft says "`chatSlice` doesn't exist" — but ARCH §9.10 explicitly lists `chatSlice` and PROJECT_TREE.md explicitly lists `chatSlice.ts`. The draft's claim that `chatSlice` doesn't exist contradicts both ARCH §9.10 and PROJECT_TREE.md. This is a factual error in draft v1.
- **Recommended fix for Phase 5**: Correct Module 10 Zustand slice entry. `chatSlice` exists per both ARCH §9.10 and PROJECT_TREE.md. The slices missing from ARCH §9.10 are: `lineageSlice` (added by ADR-038 §3.8) and `gitSlice` (added by ADR-039). `tabSlice` and `terminalTabsSlice` are code-only additions not in any authority document. Draft should revise this to: "ARCH §9.10 lists 7; PROJECT_TREE.md lists 9 (adds `lineageSlice`, `gitSlice`); code may have additional slices (`tabSlice`, `terminalTabsSlice`). ARCH §9.10 needs update for `lineageSlice` + `gitSlice`."

### `mcp-tools` — ARCH §7.2 category (a) tool count is wrong (finish_ai_block missing)

- **ARCH §7.2 says**:
  > **(a) Workflow design + execution** | `list_blocks`, `get_block_schema`, `list_types`, `get_workflow`, `validate_workflow`, `get_run_status`, `write_workflow`, `run_workflow`, `cancel_run` | 6 R / 3 W
- **Draft v1 Module 12 says**:
  > `finish_ai_block` (26th tool): **b-docs-wins** (xcheck: ARCH §7.2 category (a) table claims 6R/3W = 9 tools, code has 6R/4W = 10. ARCH update needed to list `finish_ai_block`.)
- **Issue**: ARCH §7.2 omits `finish_ai_block` from the category (a) tool list. The tool count is listed as "~25 tools" in ARCH §7.1 intro but the category breakdown in §7.2 only accounts for 9+5+7+4 = 25 tools. Adding `finish_ai_block` makes it 26. ARCH §7.2 category (a) table must be updated.
- **Recommended fix for Phase 5**: Draft Module 12 correctly identifies this as b-docs-wins. Phase 5 must generate a concrete ARCH edit: add `finish_ai_block` to ARCH §7.2 category (a) table, change "6 R / 3 W" to "6 R / 4 W", update the intro's "~25 tools" to "26 tools".

### `agent-provisioning` — ARCH §10.2 workspace structure shows `git_author.json` under `.scieasy/`

- **ARCH §10 says** (project workspace structure):
  ```
  .scieasy/
      └── git_author.json       # First-commit author cache (ADR-039 OQ-1)
  ```
- **Draft v1 Module 9 says**:
  > **`git_author.json`**: **c-drop** (M2 + C5 confirm: this file does NOT exist in code; identity is hardcoded as `_DEFAULT_AUTHOR_NAME = "SciEasy User"` / `_DEFAULT_AUTHOR_EMAIL = "noreply@scieasy.local"`. Spec should NOT promise the JSON file. Fix is doc-side — remove the promise from ARCH §4.6.)
- **Issue**: ARCH §10 (workspace structure) lists `git_author.json` under `.scieasy/`. The draft correctly identifies this file does not exist in code, but references ARCH §4.6 as the only fix target. ARCH §10 also needs to be updated — the workspace structure diagram in §10 must remove this file. Draft v1 Module 9 only mentions "remove the promise from ARCH §4.6" but misses the §10 workspace diagram.
- **Recommended fix for Phase 5**: Update Module 9 fix target to include both ARCH §4.6 (prose) AND ARCH §10 (workspace structure diagram) — both contain the stale `git_author.json` reference.

### `versioning-git` — ARCH §4.6 omits `watcher.py / GitChangeWatcher` removal note

- **PROJECT_TREE.md says** (in `core/versioning/`):
  ```
  ├── watcher.py          # Detect external git changes (HEAD / refs mtime;
  │                       #   feeds workflow_watcher's git.head_changed event)
  ```
- **Draft v1 Module 9 says**:
  > **`watcher.py` / `GitChangeWatcher`** (in versioning-git): **d-remove** (collapsed into `api/routes/workflow_watcher.py`; PROJECT_TREE.md outdated)
- **Issue**: PROJECT_TREE.md is a primary authority document (part of ARCH suite). If `watcher.py` was collapsed into `api/routes/workflow_watcher.py`, the PROJECT_TREE.md listing for `core/versioning/watcher.py` is outdated — but so is the fact that it's still listed there. The draft declares PROJECT_TREE.md outdated but doesn't flag that the PRIMARY AUTHORITY documents (PROJECT_TREE.md) need updating. This is a P1 because contradicting authoritative documents without flagging them is invisible drift.
- **Recommended fix for Phase 5**: Add an explicit "PRIMARY AUTH UPDATE NEEDED" note in Module 9 for `watcher.py`: "PROJECT_TREE.md `core/versioning/watcher.py` entry must be removed. ARCH §4.6 prose says watcher feeds `git.head_changed` event — update to say this is handled by `api/routes/workflow_watcher.py`."

### `collection-transport` — `core.materialisation` module assigned to wrong module bucket

- **ARCH §4.3 says** (storage backends + proxy patterns):
  > No intermediary accessor class — data access methods live directly on `DataObject` and its subclasses.
- **Draft v1 Module 5 says**:
  > **#1078 `core.materialisation` module** (NEW): c-impl. `materialise_to_file` / `reconstruct_from_file` proposed to fix AppBlock bridge dead JSON-dump fallback. 0% impl. This is a NEW module the cascade hasn't categorized — manager assigns to collection-transport (closest fit for transport-related materialisation).
- **Issue**: Assigning `core.materialisation` to "collection-transport" is architecturally incorrect per ARCH. The materialisation/file-exchange pattern belongs to the AppBlock boundary (§4.7 format handling: canonical zone vs boundary, specifically §4.7.3 AppBlock invocation). ARCH §4.7 is the normative section for all boundary materialisation logic. Placing it in `core.materialisation` (a non-existent module) and assigning it to collection-transport contradicts the ARCH §4.7 zone model where format-to-file conversion belongs at the boundary, not in core transport. This risks bleeding format concerns into the canonical zone.
- **Recommended fix for Phase 5**: Re-categorize Module 5 entry for `core.materialisation`. Correct module bucket should reference ARCH §4.7 (boundary materialisation) and the new module, if needed, should live under `blocks/app/` or `blocks/io/` boundary infrastructure, NOT in `core/`.

---

## P1 findings — ARCH-mandated entries missing from draft v1

| Interface | ARCH § | Missing from draft because | Manager should add as |
|---|---|---|---|
| `Collection.storage_refs` (plural) naming vs `DataObject.storage_ref` (singular) asymmetry — ARCH §6.2 defines Collection as an opaque transport with `storage_refs()` method (plural) but DataObject has `storage_ref` (singular field) | ARCH §6.2 | Draft Module 5 notes "naming asymmetry" as d-document but does NOT flag that ARCH §6.2 defines both interfaces — the spec entry needs both sides documented together for the SSOT reader to understand the naming contract | **d-document** with explicit bilateral naming note: "`Collection.storage_refs() -> list[StorageReference]`" vs "`DataObject.storage_ref: StorageReference | None`" |
| `CheckpointManager` subscribes to 4 events (`BLOCK_DONE`, `BLOCK_ERROR`, `BLOCK_CANCELLED`, `BLOCK_SKIPPED`) per ARCH §6.3 EventBus subscription matrix | ARCH §6.3 (CheckpointManager row) | Draft Module 7 (execution-engine) covers `CheckpointManager` as b-code-wins for `list_checkpoints()` but does not enumerate the 4 EventBus subscriptions that ARCH §6.3 mandates. The subscription matrix is authoritative and these event bindings are load-bearing | **a** for the 4 subscriptions; **b-code-wins** for `list_checkpoints()` (separate entry) |
| `ProcessBlock.setup()` / `ProcessBlock.teardown()` lifecycle hooks — ARCH §5.1 explicitly specifies these with signatures, contract ("called once per run() before/after iterating"), memory semantics, and GPU use example | ARCH §5.1 (ProcessBlock lifecycle hooks section) | Draft Module 1 (block-abc) covers `process_item()` and `run()` but does not enumerate `setup()` / `teardown()` as separate spec entries despite ARCH §5.1 devoting an explicit subsection to them with full signatures and behavioral contract | **a** — two separate spec entries under block-abc: `ProcessBlock.setup(config: BlockConfig) -> Any` and `ProcessBlock.teardown(state: Any) -> None` |
| `SubWorkflowBlock` uses `WorkflowLoader.load()` per ARCH §5.3 pseudocode — draft says `_scheduler_factory` injection is the correct pattern (c-defer) | ARCH §5.3 (SubWorkflowBlock code block) | ARCH §5.3 explicitly shows `WorkflowLoader.load(self.workflow_ref)` and `DAGScheduler(child_workflow)` — these are the ARCH-specified interfaces. Draft Module 1 says the correct pattern uses `_scheduler_factory` injection (c-defer to ADR-017/022 Phase 5.2b) without noting that the ARCH currently mandates the `WorkflowLoader` pattern. Either the ARCH needs to be updated to reflect the `_scheduler_factory` approach, or the c-defer is premature | **b-code-wins** + ARCH §5.3 update flag: "ARCH §5.3 pseudocode shows `WorkflowLoader.load()` which code does not implement; draft correctly defers `_scheduler_factory` to #890 but must flag ARCH §5.3 as requiring update when #890 ships" |

---

## P2 findings — ADR-mandated entries missing from draft v1

| Interface | ADR § | Recommended add |
|---|---|---|
| `BlockRunner.run()` return type: ADR-018 §6.8 specifies `BlockRunner.run()` returns `RunHandle` (containing `ProcessHandle` + `asyncio.Future`), but draft Module 7 marks `RunHandle` as **d-private** ("future-evolution placeholder"). ADR-018 and ARCH §6.8 both explicitly specify this return type as the protocol contract. | ADR-018 (BlockRunner protocol, §6.8) | Change `RunHandle` from d-private to **d-document**: it IS part of the public BlockRunner protocol per ADR-018, just not yet returned by LocalRunner. Note the current/target state gap explicitly. |
| `ProcessBlock.min_input_ports` / `max_input_ports` / `min_output_ports` / `max_output_ports` — ADR-029 Addendum 1 §D1 adds four ClassVar port count limit fields to `Block`. Draft Module 1 covers variadic ports (ADR-029) but does not enumerate these four limit ClassVars as separate spec entries. | ADR-029 Addendum 1 §D1 | Add 4 spec entries under block-abc: `Block.min_input_ports: ClassVar[int | None] = None`, etc. Sub-label: **a** (all four are at the Block ABC level per ADR-029-Add1 §D1). |
| `BlockSpec` gains `min_input_ports`, `max_input_ports`, `min_output_ports`, `max_output_ports` fields per ADR-029 Addendum 1 §D2 — draft Module 6 (block-registry) covers `BlockSpec.source` as b-code-wins but does not add the four new optional fields | ADR-029 Addendum 1 §D2 | Add to Module 6 `BlockSpec` spec entry: four optional `int | None` fields. Sub-label: **a**. |
| `scieasy.runners` entry-point group is listed in PROJECT_TREE.md as a third entry-point group alongside `scieasy.blocks` and `scieasy.types`. Draft Module 6 mentions it as a d-document cross-reference to CodeRunner Protocol (block-abc) but does not give it its own spec entry. ARCH §12.1 says "two surviving entry-point groups" — but the PROJECT_TREE.md `pyproject.toml` section shows three (including `scieasy.runners`). | ARCH §12.1 + PROJECT_TREE.md entry-points section | Add Module 6 spec entry for `scieasy.runners` entry-point group. ARCH §12.1 has an internal inconsistency (says "two surviving" but PROJECT_TREE.md shows three). Sub-label: **b-docs-wins** — ARCH §12.1 must be corrected to acknowledge `scieasy.runners`. The group exists; only its mention in §12.1 is missing. |
| `EnvironmentSnapshot` has 5 fields per ADR-038 §3.4 and ARCH §6.7. But the `conda_env: str | None = None` optional field is listed in ARCH §6.7 but NOT mentioned in draft Module 8 (lineage-db). Draft Module 8 says "EnvironmentSnapshot: **a** (5 fields per ADR-038 §3.4)". | ARCH §6.7 | Verify draft Module 8 `EnvironmentSnapshot` entry explicitly enumerates all 5 fields including `conda_env`. If the current "**a**" classification assumes 5 fields, it is only correct if `conda_env` is included. Add a d-document note that `conda_env` is populated only when running inside a Conda environment. |

---

## P3 findings — ADR↔draft contradictions (ARCH silent)

| Interface | Draft says | ADR-N says | Recommendation |
|---|---|---|---|
| `CompositeStore.iter_chunks` behavior | b-docs-wins: silently ignores `chunk_size`, yields `(slot_name, data)` tuples — semantically inconsistent with other backends; fix code-side OR document the exception (Module 4) | ADR-031 §D1 defines `iter_chunks(chunk_size)` on DataObject as "yield successive chunks from storage." CompositeData inherits this contract. ARCH §4.2 describes CompositeData storage as "directory of slot backends" with each slot using its type's backend. The inconsistency is that `iter_chunks` on CompositeData doesn't fit the "successive chunks" semantic naturally — slots are not chunks. | Draft recommendation stands: document the exception explicitly in spec. `CompositeStore.iter_chunks` should state: "yields `(slot_name, DataObject)` pairs; `chunk_size` is ignored. For chunk-level access, call `iter_chunks()` on individual slots." |
| `StorageReference` frozen status | b-docs-wins: docstring says "immutable" but dataclass NOT `frozen=True`. Fix is code-side: add `frozen=True` (Module 4) | ADR-031 defines StorageReference as a lightweight pointer. No explicit freeze requirement in ADR-031, but the reference-only contract assumes immutability. | Draft recommendation stands. Code-side fix preferred. Document in spec: "StorageReference is `frozen=True` (code fix pending `#TBD-storage-ref-frozen`)." |
| `DAGScheduler` constructor param count | b-code-wins: C4 flag: constructor has 9 params, ARCH §6.1 lists 5 — code has truth; ARCH update needed (Module 7) | ADR-018 (scheduler design) and ADR-018 Addendum 1 (asyncio concurrency) both add parameters (`_active_tasks`, etc.) that wouldn't be visible in the original constructor listing. | Draft recommendation stands. ARCH §6.1 constructor signature must be updated to match the 9-param version. The ARCH §6.1 code block showing the 5-param constructor is definitively wrong. |
| `WorkflowCheckpoint.pending_block` and `config_snapshot` fields | b-code-wins: C4 flag: always written as None/{} — either drop fields or implement (Module 7) | ADR-012 defines the checkpoint contract. ADR-038 §3.6a clarifies the checkpoint scope. Neither explicitly requires these fields to be populated. | Draft recommendation stands. Spec should note current behavior: "Fields `pending_block` and `config_snapshot` are present in schema but always `None`/`{}` in current implementation. Implementation tracked in `#TBD-checkpoint-pending-block`." |

---

## ADR↔ADR conflicts (log only, not blocking)

| ADR-A | ADR-B | What they disagree on | Affected interface(s) |
|---|---|---|---|
| **ADR-025 §6** says a `scieasy.adapters` entry-point group exists for format adapters | **ADR-028 §D4** supersedes this and removes `scieasy.adapters` | The PROJECT_TREE.md still reflects the post-ADR-028 state (no `scieasy.adapters`) but ADR-025 §6 text was never updated. Any reader going to ADR-025 §6 for the entry-point protocol will find stale guidance. | `block-registry` entry-point groups; `IOBlock` registration path |
| **ADR-027 D2** (and ARCH §4.1, §5.4) prohibits domain subtypes in core | **PROJECT_TREE.md "Key entry_points"** registers `Image`, `Spectrum`, `PeakTable` from `scieasy.core.types.*` | These two documents in the primary authority set contradict each other. One says no domain types in core; the other registers them from core paths. This may be a PROJECT_TREE.md stale draft entry. | `data-types` module; `TypeRegistry` scan behavior |
| **ADR-007 §4.4** originally defined a lineage schema (now superseded) | **ADR-038** supersedes ADR-007 §4.4 with a 4-table schema | ADR-038 mentions "dormant earlier lineage schema per the original ADR-007 §4.4" — but ADR-007 §4.4 text in the ADR file may still describe the old schema without the supersession note being clearly marked at the ADR-007 header level. Readers of ADR-007 may miss the supersession. | `lineage-db` module; `LineageStore` schema |

---

## Recommended fixes for Phase 5 draft v2

Ordered checklist (P1 → P2 → P3):

### P1 fixes (required before draft v2)

- [ ] **P1-1** Module 1 (`block-abc`): Correct `allowed_input_types` default citation. ARCH §5.2 says `[DataObject]`. If code has `[]`, add explicit ARCH §5.2 update note: "ARCH §5.2 must change `[DataObject]` to `[]`."
- [ ] **P1-2** Module 1 (`block-abc`): Fix `postprocess` signature characterization. ARCH §5.1 says `dict[str, DataObject]` (not `dict[str, Collection]`). Correct the "same pattern as validate" collapse — they are different annotations in ARCH.
- [ ] **P1-3** Module 3 (`data-types`): Add new b-finding: "PROJECT_TREE.md §entry_points registers `Image`/`Spectrum`/`PeakTable` from `scieasy.core.types.*`, contradicting ARCH §4.1/§5.4. Manager decision required: (a) correct PROJECT_TREE.md to reference plugin packages, or (b) update ARCH §4.1/§5.4 to acknowledge these three types ship in core."
- [ ] **P1-4** Module 7 (`execution-engine`): Add concrete ARCH edit target for `memory_high_watermark`: "ARCH §6.4 numeric `0.80` must be updated to `0.90`."
- [ ] **P1-5** Module 10 (`rest-api`): Fix Zustand slice claim. `chatSlice` exists in ARCH §9.10 and PROJECT_TREE.md. Correct to: "ARCH §9.10 lists 7 slices; PROJECT_TREE.md lists 9 (adds `lineageSlice` + `gitSlice`). Code may add `tabSlice` + `terminalTabsSlice`. ARCH §9.10 needs update for `lineageSlice` + `gitSlice`."
- [ ] **P1-6** Module 12 (`mcp-tools`): Add concrete ARCH edit target for `finish_ai_block`: "ARCH §7.2 category (a) table must add `finish_ai_block`, change '6 R / 3 W' to '6 R / 4 W', update intro '~25 tools' to '26 tools'."
- [ ] **P1-7** Module 9 (`versioning-git`): Expand `git_author.json` fix target from "ARCH §4.6 only" to both "ARCH §4.6 prose AND ARCH §10 workspace structure diagram."
- [ ] **P1-8** Module 9 (`versioning-git`): Add PRIMARY AUTH UPDATE NEEDED flag for `watcher.py`: "PROJECT_TREE.md `core/versioning/watcher.py` entry must be removed; update ARCH §4.6 prose about `git.head_changed` event source."
- [ ] **P1-9** Module 5 (`collection-transport`): Re-categorize `core.materialisation` proposal. ARCH §4.7 assigns boundary materialisation to `blocks/app/` or `blocks/io/` (boundary infrastructure), NOT `core/`. Correct the bucket and add ARCH §4.7 citation.

### P1 missing entries (add to draft v2)

- [ ] **P1-M1** Add `Collection.storage_refs()` / `DataObject.storage_ref` bilateral naming doc entry to Module 5 (d-document per ARCH §6.2).
- [ ] **P1-M2** Add `CheckpointManager` EventBus subscriptions (4 events) to Module 7 spec entries — **a** per ARCH §6.3 subscription matrix.
- [ ] **P1-M3** Add `ProcessBlock.setup()` and `ProcessBlock.teardown()` as distinct spec entries in Module 1 — **a** per ARCH §5.1 explicit subsection.
- [ ] **P1-M4** Add flag to Module 1 `SubWorkflowBlock` entry: "ARCH §5.3 pseudocode shows `WorkflowLoader.load()` — needs ARCH update when #890 ships."

### P2 fixes (should fix before Phase 6)

- [ ] **P2-1** Module 7: Change `RunHandle` from d-private to d-document per ADR-018/ARCH §6.8 BlockRunner protocol.
- [ ] **P2-2** Module 1: Add 4 port-limit ClassVars from ADR-029-Add1 §D1 as spec entries.
- [ ] **P2-3** Module 6: Add 4 optional port-limit fields to `BlockSpec` from ADR-029-Add1 §D2.
- [ ] **P2-4** Module 6: Add `scieasy.runners` entry-point group as own spec entry + flag ARCH §12.1 "two surviving groups" as needing correction to "three."
- [ ] **P2-5** Module 8: Verify `EnvironmentSnapshot` 5-field enumeration explicitly includes `conda_env: str | None`.

### P3 fixes (recommended)

- [ ] **P3-1** Module 4: Finalize `CompositeStore.iter_chunks` exception documentation.
- [ ] **P3-2** Module 4: Finalize `StorageReference frozen=True` code-side fix tracking.
- [ ] **P3-3** Module 7: Finalize `DAGScheduler` 9-param constructor ARCH §6.1 update.
- [ ] **P3-4** Module 7: Document `WorkflowCheckpoint.pending_block`/`config_snapshot` current behavior with tracking issue.

---

*AX audit complete. 9 P1 contradictions, 4 P1 missing entries, 5 P2, 4 P3, 3 ADR↔ADR log-only conflicts. All findings derived directly from ARCHITECTURE.md, PROJECT_TREE.md, and ADR.md — no code-side sources consulted per scope rules.*
