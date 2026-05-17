# I1 — Phase 2 supplementary: GitHub-issue-driven classifications
Date: 2026-05-17
Auditor: I1 (independent of I2)
Issues scanned: 98 open + 0 closed-and-relevant (no squash-merge-reopen pattern found matching issues)
Issue-driven entries: 14 new + 12 refinements to existing K-report entries

## Summary
- New entries (not in K1/K2/K3): 14
  - c-class: 3 (c-impl: 3, c-drop: 0, c-defer: 0)
  - d-class: 8 (d-document: 6, d-private: 0, d-remove: 2)
  - b-class: 3 (b-code-wins: 1, b-docs-wins: 2)
- Refinements to existing K-report entries: 12
  - Confirmations (K's class matches issue): 7
  - Reclassifications (issue evidence changes the class): 5

---

## Scanning methodology

Filtered the full open issue list (98 issues) for:
1. Issues with ADR-section references in title or body (e.g. "ADR-028 §D8", "ADR-035 §3.5", "ADR-040 §3.10")
2. Issues describing an interface that "should", "must", "is not implemented", or "is a stub"
3. Issues referencing an interface name + declaring it absent from code (c-class signal)
4. Issues with labels `enhancement`, `documentation`, `audit-followup`, `P1`, `P2` where body described contract drift
5. Checked for "squash-merge-reopen" closed issues — none found matching that pattern in the relevant interface space

---

## New entries (interfaces NOT in K1/K2/K3 reports)

### `block-registry.IOBlock.supported_extensions` + `IOBlock._detect_format` — ADR-028 §D8 base ClassVar + helper: 0% implemented on IOBlock base class

- **Class**: c-impl
- **Source**: `[CODE: not implemented]` — `src/scieasy/blocks/io/io_block.py` declares no `supported_extensions` ClassVar; no `_detect_format` helper exists; concrete loaders use module-level frozensets and inline `if suffix == ".x":` chains
- **Doc-source**: `ADR-028 §D8` (`docs/adr/ADR.md:5704-5721`)
- **Issue**: #1073 — "Implement ADR-028 §D8: `supported_extensions` ClassVar + `_detect_format` helper on IOBlock" — https://github.com/zjzcpj/SciEasy/issues/1073
- **Issue body excerpt**: "Audit on 2026-05-16 confirmed that ADR-028 §D8 (`docs/adr/ADR.md:5704-5721`) is **0% implemented** in code despite being a binding decision. §D8 specifies: Each concrete IOBlock subclass declares `supported_extensions: ClassVar[dict[str, str]]` ... The framework provides a helper `IOBlock._detect_format(path)` implementing this lookup so subclasses do not reimplement it."
- **Recommended sub-label**: c-impl (the ADR is the binding spec; the issue is the implementation tracker)
- **Rationale**: ADR-028 §D8 is the primary authority (ADR-supplementary layer); the interface is promised in the spec and entirely absent from code. This is a classic c-class entry. The issue (#1073) serves as the implementation tracker.
- **Signature (as promised in spec)**:
  ```python
  # On IOBlock base class
  supported_extensions: ClassVar[dict[str, str]] = {}

  def _detect_format(self, path: Path) -> str | None:
      compound = "".join(path.suffixes).lower()
      if compound in self.supported_extensions:
          return self.supported_extensions[compound]
      single = path.suffix.lower()
      if single in self.supported_extensions:
          return self.supported_extensions[single]
      return None
  ```

---

### `block-registry.IOBlock.supported_extensions` (LoadData / SaveData declarations) — §D8 per-block declarations absent on core IO blocks

- **Class**: c-impl
- **Source**: `[CODE: not implemented]` — `src/scieasy/blocks/io/loaders/load_data.py` and `src/scieasy/blocks/io/savers/save_data.py` have no `supported_extensions` ClassVar declarations; extension knowledge is inlined in if/elif chains
- **Doc-source**: `ADR-028 §D8` (`docs/adr/ADR.md:5704-5721`, also see concrete example at ADR.md:5490 showing `LoadArray.supported_extensions = {".zarr": "zarr", ...}`)
- **Issue**: #1074 — "ADR-028 §D8: declare `supported_extensions` on LoadData / SaveData" — https://github.com/zjzcpj/SciEasy/issues/1074
- **Issue body excerpt**: "Per ADR-028 §D8 (`docs/adr/ADR.md:5704-5721`), every concrete IOBlock subclass MUST declare `supported_extensions`... Currently extension knowledge is inlined in `if suffix == \".x\":` chains and embedded in ValueError messages."
- **Recommended sub-label**: c-impl (blocked by #1073)
- **Rationale**: Downstream of #1073. The per-block declarations are a distinct interface surface — each block's `supported_extensions` ClassVar is part of the public contract that BlockRegistry.find_loader/find_saver (#1077) will query.

---

### `block-registry.IOBlock.supported_extensions` (LoadImage / SaveImage declarations) — §D8 declarations absent on imaging plugin IO blocks

- **Class**: c-impl
- **Source**: `[CODE: not implemented]` — `packages/scieasy-blocks-imaging/.../io/load_image.py:27-29` uses module-level constants `_TIFF_EXTS`, `_ZARR_EXTS`, `_SUPPORTED_EXTS` instead of ClassVar; `save_image.py:31-35` uses `_EXT_TO_FORMAT`
- **Doc-source**: `ADR-028 §D8` (`docs/adr/ADR.md:5704-5721`)
- **Issue**: #1075 — "ADR-028 §D8: declare `supported_extensions` on LoadImage / SaveImage" — https://github.com/zjzcpj/SciEasy/issues/1075; #1076 covers remaining plugin IO blocks (LoadMzMLFiles, LoadPeakTable, SaveTable, LoadMIDTable, LoadSampleMetadata) — https://github.com/zjzcpj/SciEasy/issues/1076
- **Issue body excerpt** (#1075): "Currently the imaging plugin uses module-level constants instead of the ClassVar: `packages/scieasy-blocks-imaging/.../io/load_image.py:27-29`: `_TIFF_EXTS`, `_ZARR_EXTS`, `_SUPPORTED_EXTS`... `packages/scieasy-blocks-imaging/.../io/save_image.py:31-35`: `_EXT_TO_FORMAT`"
- **Recommended sub-label**: c-impl (blocked by #1073)
- **Rationale**: Same §D8 mandate applied to plugin blocks. Note: #1076 (remaining LCMS plugin blocks) is also a c-impl entry under this same surface; treating as one combined entry for the "plugin IOBlock declarations" surface.

---

### `block-registry.BlockRegistry.find_loader` / `find_saver` / `find_io_blocks_for_type` — BlockRegistry query methods for format routing

- **Class**: c-impl
- **Source**: `[CODE: not implemented]` — confirmed "zero matches for `extension` in `src/scieasy/blocks/registry.py`" per issue body
- **Doc-source**: `ADR-028 §D8` (implicit — the BlockRegistry must be queryable once blocks declare `supported_extensions`; see also ARCH §5.4 which documents BlockRegistry as the routing authority)
- **Issue**: #1077 — "BlockRegistry: `find_loader(type, ext)` / `find_saver(type, ext)` query methods" — https://github.com/zjzcpj/SciEasy/issues/1077
- **Issue body excerpt**: "Currently BlockRegistry has no such methods (verified via grep for `extension` in `src/scieasy/blocks/registry.py`: zero matches). Downstream callers (engine helpers, AppBlock binner) need this query."
- **Recommended sub-label**: c-impl (blocked by #1073 + #1074/#1075)
- **Rationale**: This is an interface promised by the ADR-028 §D8 design (the ClassVar only makes sense if the registry can query it) and the issue explicitly proposes the interface signatures. Not in any K report. The three method signatures below are from the issue.
- **Signature (as promised in issue)**:
  ```python
  def find_loader(self, dtype: type[DataObject] | None, extension: str) -> type[IOBlock] | None: ...
  def find_saver(self, dtype: type[DataObject], extension: str) -> type[IOBlock] | None: ...
  def find_io_blocks_for_type(self, dtype: type[DataObject], direction: str) -> list[type[IOBlock]]: ...
  ```

---

### `core.materialisation.materialise_to_file` / `reconstruct_from_file` — new module for typed DataObject file exchange

- **Class**: c-impl
- **Source**: `[CODE: not implemented]` — `src/scieasy/core/materialisation.py` does not exist; the functionality is currently done ad-hoc (bridge.py:31-74 uses json.dumps dead fallback; app_block.py:240-258 silently downgrades to Artifact)
- **Doc-source**: ARCH §2.4 (data flows as references, not large in-memory payloads) + ADR-028 §D8 design requiring typed round-trip through BlockRegistry
- **Issue**: #1078 — "Engine: `core/materialisation.py` helpers (`materialise_to_file` / `reconstruct_from_file`)" — https://github.com/zjzcpj/SciEasy/issues/1078
- **Issue body excerpt**: "AppBlock `prepare()` and `_bin_outputs_by_extension` need a uniform way to (a) write a DataObject to a file in a chosen format and (b) construct a typed DataObject from a path. Today both are ad-hoc — `prepare()` uses `json.dumps(value, default=str)` as a dead fallback (`bridge.py:31-74`); `_bin_outputs_by_extension` silently downgrades typed ports to `Artifact` (`app_block.py:240-258`)."
- **Recommended sub-label**: c-impl (blocked by #1077)
- **Rationale**: New module proposed in issue; blocked by BlockRegistry query methods. Not present in any K report. The two function signatures are from the issue body.
- **Signature (as promised in issue)**:
  ```python
  def materialise_to_file(obj: DataObject, dest_dir: Path, extension: str | None = None) -> Path: ...
  def reconstruct_from_file(path: Path, target_type: type[DataObject], extension: str | None = None) -> DataObject: ...
  ```

---

### `block-abc.AppBlock.bridge.prepare` — JSON-dump dead fallback: b-docs-wins (bridge contract violated)

- **Class**: b-docs-wins
- **Source**: `src/scieasy/blocks/app/bridge.py:31-74` — uses `json.dumps(value, default=str)` for DataObject inputs; produces useless string representations for array-backed types
- **Doc-source**: ARCH §5.3 (AppBlock exchange protocol: typed DataObjects staged as real files) + ADR-028 §D8 intent
- **Issue**: #1080 — "AppBlock `bridge.py::prepare()`: replace JSON-dump dead fallback with type-dispatched materialisation" — https://github.com/zjzcpj/SciEasy/issues/1080
- **Issue body excerpt**: "For numpy-array-backed objects (Image, Mask, Array, etc.) this produces a `str(ndarray)` truncated repr in a `.json` file — completely useless to any real external tool. The path is dead code today because every concrete AppBlock subclass (FijiBlock, NapariBlock) overrides `Block.run()` and uses its own `_prepare_X_exchange()` helper. But CodeBlock v2 (ADR-041) will rely on the generic bridge path; it needs to work."
- **Recommended sub-label**: b-docs-wins (code must be brought to match the documented exchange protocol)
- **Rationale**: This is code drift from the documented AppBlock exchange contract. Not identical to K-report entries on ExternalAppBridge/FileExchangeBridge (those are classified d for being undocumented; this entry is about a specific code bug vs documented behavior). Not in any K report as a classified interface gap.

---

### `block-abc.AppBlock._bin_outputs_by_extension` — typed reconstruction absent: b-docs-wins

- **Class**: b-docs-wins
- **Source**: `src/scieasy/blocks/app/app_block.py:240-258` — silently downgrades any non-Artifact declared port type to Artifact with a logger.warning
- **Doc-source**: ARCH §5.3 (AppBlock output collection: type-dispatched) + ADR-028 §D8 (typed reconstruction via supported_extensions)
- **Issue**: #1079 — "AppBlock `_bin_outputs_by_extension`: replace Artifact downgrade with typed reconstruction" — https://github.com/zjzcpj/SciEasy/issues/1079
- **Issue body excerpt**: "This breaks the FijiBlock → SaveImage edge: user declares `accepted_types=[Image]` on the FijiBlock output port, gets an Artifact at runtime, downstream SaveImage rejects the type."
- **Recommended sub-label**: b-docs-wins (code must be brought to match documented typed transport contract)
- **Rationale**: Distinct from K-report entries on FileExchangeBridge/ExternalAppBridge (those are d-class for missing method docs; this is a specific algorithm that violates the typed-transport contract). Not in K reports.

---

### `execution-engine.axis_iter.iterate_over_axes` — lazy O(one-slice) contract: b-docs-wins

- **Class**: b-docs-wins
- **Source**: `src/scieasy/utils/axis_iter.py:151-154` — calls `source.to_memory()` on the full input Array; actual memory profile O(full source), not O(one slice)
- **Doc-source**: `ARCHITECTURE.md:457` — "Memory: O(one slice + one output slice) regardless of the number of extra-axis combinations"; also `ADR-027 D4` (`docs/adr/ADR.md:4208`)
- **Issue**: #888 — "iterate_over_axes materializes full source — violates O(one slice) contract for Zarr-backed Arrays" — https://github.com/zjzcpj/SciEasy/issues/888
- **Issue body excerpt**: "`src/scieasy/utils/axis_iter.py:151-154`: `source_data = source.to_memory()` / `source_arr = np.asarray(source_data)` ... Then `:174-216` iterates via `product(...)` over `source_arr` — but the iteration is over an **already-materialized numpy array**. Actual memory profile: `O(full source + one output slice)`, not `O(one slice + one output slice)`."
- **Recommended sub-label**: b-docs-wins (the ARCHITECTURE.md and ADR-027 D4 are source of truth; code must implement the lazy path)
- **Rationale**: Issue explicitly states "documentation is source of truth." The code-level comment at axis_iter.py:151-152 even acknowledges the deferral ("lazy Zarr partial-reads are deferred") but the module docstring and ARCH were never updated. The docs describe the intended Level 1 design; code is incomplete. Not in any K report (axis_iter is not in the module list as an explicit interface).

---

### `execution-engine.ResourceManager.acquire` (L1 GPU/CPU slot accounting) — not wired: b-code-wins (with known doc-first option)

- **Class**: b-code-wins
- **Source**: `src/scieasy/engine/scheduler.py:197` — calls `can_dispatch(ResourceRequest(), ...)` with empty default; never reads `block.resource_request`; `ResourceManager.acquire()` has zero production callers
- **Doc-source**: `ARCHITECTURE.md:1516` — shows `can_dispatch(block.resource_request)` as canonical pattern; `ADR.md:327` — "Blocks declare resource needs via `ResourceRequest`"
- **Issue**: #887 — "Engine resource accounting (L1 GPU/CPU slots) is not wired into dispatch" — https://github.com/zjzcpj/SciEasy/issues/887
- **Issue body excerpt**: "Three layers of resource management per ADR-022/027: L1 — Declarative slot accounting (GPU/CPU): **not wired**... `src/scieasy/engine/scheduler.py:197` calls `can_dispatch(ResourceRequest(), ...)` with a default empty request. It never reads `block.resource_request`... **Doc-reality divergence**: `ARCHITECTURE.md:1516` shows `can_dispatch(block.resource_request)` as the canonical pattern — not implemented. `ADR.md:327` claims 'Blocks declare resource needs via `ResourceRequest`' — no block does."
- **Recommended sub-label**: b-code-wins (issue proposes Option A: update docs to describe what actually runs; the code behavior is the current reality, with L1 accounting genuinely deferred)
- **Rationale**: The issue explicitly recommends "Option A — Document reality, mark L1 as future work." Code is the current truth for L1 behavior (not wired); ARCH/ADR describe the intended future. The K reports classify `ResourceManager` as `a` (both present) and `ResourceRequest` as `b` (memory_high_watermark default mismatch). This issue adds a distinct interface-level gap: the `acquire()` API and L1 dispatch wiring. Not in K reports as a separate entry.

---

### `block-abc.SubWorkflowBlock._scheduler_factory` injection + `_run_with_scheduler` — deferred real scheduler integration

- **Class**: c-defer
- **Source**: `src/scieasy/blocks/subworkflow/subworkflow_block.py:45,139,154` — `_scheduler_factory = None` never injected; `_run_with_scheduler` falls back to `_sequential_execute`
- **Doc-source**: `ARCHITECTURE.md §?` (described as intended behavior); ADR-017/018/022 guarantees (subprocess isolation, concurrency, event-bus integration, cancellation)
- **Issue**: #890 — "SubWorkflowBlock falls back to sequential in-process execution — scheduler integration unfinished" — https://github.com/zjzcpj/SciEasy/issues/890
- **Issue body excerpt**: "SubWorkflowBlock is implemented as a functional stub: it runs child blocks via a sequential in-process for-loop (`_sequential_execute`) rather than a child `DAGScheduler` with subprocess isolation, concurrency, event-bus integration, and cancellation propagation... The implementation comments explicitly mark the stub as deferred."
- **Recommended sub-label**: c-defer (to ADR-017/022 Phase 5.2b; issue #890 IS the tracking artifact)
- **Rationale**: K1 and K2 both classify `SubWorkflowBlock` as `b` (disagreement on workflow_ref ClassVar vs config). This entry is DISTINCT — it covers the scheduler injection contract (`_scheduler_factory` ClassVar hook + `_run_with_scheduler` real implementation) which the K reports do not address as a separate interface. The issue says "not a doc drift — the implementation comments mark it as deferred." Sub-label c-defer is correct per the issue's own framing.

---

### `execution-engine.DAGScheduler._run_interactive` (6-step interactive protocol) — not in ARCH

- **Class**: d-document
- **Source**: `src/scieasy/engine/scheduler.py` — `_run_interactive` method implementing #591/#594 interactive block protocol
- **Doc-source**: ARCH §6.1 mentions INTERACTIVE mode briefly but does not document `_run_interactive` as a named method or enumerate its 6-step protocol
- **Issue**: (no dedicated issue found; derived from K1 #91 / K3 #92 classification cross-referenced with C4 report)
- **Recommended sub-label**: d-document
- **Rationale**: K1 row 91 and K3 row 92 both classify this as `d`. No issue directly tracks this documentation gap, but it is confirmed code-side. Including here to confirm the K classification stands and flag for manager attention.

---

### `ws-sse-protocol.useSSE` / `useWebSocket` reconnection logic — frontend hooks contract undocumented

- **Class**: d-document
- **Source**: `frontend/src/hooks/useSSE.ts` (26 lines), `frontend/src/hooks/useWebSocket.ts` (29 lines) — no reconnection logic
- **Doc-source**: ARCH §8.2 references SSE log-stream and WebSocket block state push; neither mentions reconnection contract or heartbeat semantics
- **Issue**: #177 — "fix(frontend): add reconnection logic to useSSE and useWebSocket hooks" — https://github.com/zjzcpj/SciEasy/issues/177
- **Issue body excerpt**: "Neither hook implements reconnection logic — if the connection drops (network interruption, server restart, laptop sleep/wake), the client silently stops receiving updates... `useSSE.ts` (26 lines) / `useWebSocket.ts` (29 lines)"
- **Recommended sub-label**: d-document (the reconnection/heartbeat contract should be specified in ARCH §8.2 alongside the WS/SSE surface; implementation is a separate concern)
- **Rationale**: Not in any K report. This is a frontend interface gap (the reconnection behavior is undocumented; code is also missing the feature). The primary classification is d-document because ARCH §8.2 does not specify reconnection semantics; the code absence is a follow-up c-impl once docs are updated. Treating as d-document here since the SSOT cascade is about documenting interfaces first.

---

### `frontend.BottomPanel.LineageView` / `JobsPanel` — UI components promised but stubbed

- **Class**: c-defer
- **Source**: `frontend/src/components/BottomPanel.tsx:355` — falls through to `PlaceholderTab` for `activeTab === "lineage"`; Jobs tab same
- **Doc-source**: ARCH §9 (Frontend layer) — implies Lineage and Jobs tabs exist as functional components; these are listed as tabs in the UI contract
- **Issue**: #835 — "Bottom-panel tabs: implement Lineage + Jobs (stubs today); decide Logs vs Problems overlap" — https://github.com/zjzcpj/SciEasy/issues/835
- **Issue body excerpt**: "`BottomPanel.tsx:355` falls through to `PlaceholderTab` for `activeTab === 'lineage'`. No component renders the lineage view. Backend has data: ADR-032 added a project-scoped SQLite `metadata.db`... MCP exposes it: `mcp__scieasy__get_lineage(ref)` already returns `{nodes, edges}`"
- **Recommended sub-label**: c-defer (Lineage tab implementation is deferred pending design; Jobs tab same; issue #835 is the tracker)
- **Rationale**: Not in any K report as a distinct frontend interface entry. The Lineage tab rendering interface (`LineageView.tsx`, `GET /api/lineage/{object_id}`) and Jobs panel component are promised by the UI layer contract but entirely absent. The issue provides a concrete design path (React Flow + MetadataStore.ancestors()).

---

### `utils.logging.configure_logging` — NotImplementedError stub violates observability contract

- **Class**: c-impl
- **Source**: `src/scieasy/utils/logging.py::configure_logging` — raises `NotImplementedError` stub; no central log config
- **Doc-source**: ARCH §6.1 (EventBus observability) + ARCH §7.4 (system prompt / logging infrastructure)
- **Issue**: #827 — "feat(observability): central event/log helper subscribing to all engine events" — https://github.com/zjzcpj/SciEasy/issues/827
- **Issue body excerpt**: "`src/scieasy/utils/logging.py::configure_logging` NotImplementedError stub — no central log config... Only 7 of 14 event types observed... `Unobserved event types: block_ready, block_paused, cancel_block_request, cancel_workflow_request, process_spawned, process_exited, checkpoint_saved, interactive_prompt, interactive_complete, workflow.changed`"
- **Recommended sub-label**: c-impl (the stub exists; the interface is defined but needs implementation)
- **Rationale**: Not in any K report. The `configure_logging` stub and the proposed `install_event_logger` function are an interface surface promised by the architecture. The issue also covers 7 unobserved event types.
- **Signature (as promised in issue)**:
  ```python
  def install_event_logger(
      event_bus: EventBus,
      *,
      sink: Literal['stdlib', 'file', 'both'] = 'stdlib',
      file_path: Path | None = None,
      level: int = logging.INFO,
  ) -> None: ...
  ```

---

### `docs.block-sdk` — `_data` pattern elimination: d-remove

- **Class**: d-remove
- **Source**: 32 sites across 14 files in `examples/` and `docs/block-development/` still use deprecated `result._data = arr` monkey-patch pattern (ADR-031 Addendum 2 eliminated it)
- **Doc-source**: ADR-031 Addendum 2 (data= constructor parameter is the canonical replacement)
- **Issue**: #661 — "docs(#652): align Block SDK docs with ADR-031 Addendum 2 — data= constructor, eliminate _data examples" — https://github.com/zjzcpj/SciEasy/issues/661
- **Issue body excerpt**: "All ProcessBlock examples and documentation still use the monkey-patch `_data` pattern: `result._data = arr  # type: ignore[attr-defined]  ← deprecated`. After Addendum 2 (#660), the correct pattern is: `result = Image(axes=..., shape=..., dtype=..., data=arr)`"
- **Recommended sub-label**: d-remove (32 documented instances of the deprecated pattern must be removed from SDK docs + examples)
- **Rationale**: Not in any K report as a specific entry. K reports cover `DataObject._transient_data` and `DataObject._data` at the code level (classified d); this entry covers the SDK documentation / example surface where the deprecated pattern is still instructed. Distinct from the code-level bridge properties.

---

### `docs.architecture.PROJECT_TREE.md proxy.py` — stale ViewProxy annotation: d-remove

- **Class**: d-remove
- **Source**: `docs/architecture/PROJECT_TREE.md:83-84` — annotates `proxy.py` as "ViewProxy: lazy-loading accessor (slice, iter_chunks, to_memory, shape). Injected into block.run() inputs."
- **Doc-source**: `ARCHITECTURE.md Appendix B` — "ViewProxy *(Eliminated in ADR-031.)*"
- **Issue**: #908 — "Docs: PROJECT_TREE.md proxy.py annotation describes ViewProxy as live; ADR-031 marks it eliminated" — https://github.com/zjzcpj/SciEasy/issues/908
- **Issue body excerpt**: "But `docs/architecture/ARCHITECTURE.md` Appendix B (line 3256) glosses ViewProxy as superseded: 'ViewProxy *(Eliminated in ADR-031.)* Formerly a lazy-loading accessor…'. ADR-031 explicitly eliminated ViewProxy and moved lazy-loading to direct methods on `DataObject` and subclasses."
- **Recommended sub-label**: d-remove (the stale annotation in PROJECT_TREE.md must be corrected or removed)
- **Rationale**: Not in K reports as a specific PROJECT_TREE.md annotation entry. K reports classify `DataObject` as `b` and ViewProxy references as d-class code-side gaps, but this specific docs-side stale annotation in PROJECT_TREE.md was not flagged by K agents.

---

## Refinements to existing K-report entries

| Interface | K-class (K1/K2/K3 majority) | Issue # | Issue says | I1 final class | Why |
|---|---|---|---|---|---|
| `block-abc.IOBlock` (base class) | K1=a, K2=b, K3=a | #1073 | `supported_extensions` ClassVar and `_detect_format` helper mandated by ADR-028 §D8 are 0% implemented; K2's b classification (IOBlock.load signature drift) is confirmed correct; the ClassVar gap adds a second b-dimension | **b** (confirm K2) | Issue #1073 proves K2 was right: IOBlock is b-class because code lacks the mandated `supported_extensions` ClassVar (docs/spec promise it) AND the `output_dir` param signature mismatch K1/K2 already flagged. K3's `a` was too generous. |
| `block-abc.SubWorkflowBlock` | K1=b, K2=b, K3=a | #890 | Scheduler injection stub is intentionally deferred — NOT a doc drift; the implementation comment explicitly says "deferred (Phase 5.2b)"; issue confirms "not a doc drift" | **b + c-defer note** | K3's `a` was wrong — K1/K2's `b` confirmed by issue. Additionally, the `_scheduler_factory` interface specifically is c-defer (issue #890 tracks it). K1/K2 are confirmed; K3 reclassified. |
| `execution-engine.ResourceManager.acquire` (wiring) | K1=a (ResourceManager row 101), K2=a (row not explicit on acquire), K3=a (row 96) | #887 | `acquire()` has zero production callers; L1 dispatch path is dead code; ARCH §1516 shows it wired but it isn't | **b** | All K agents classified ResourceManager as `a` based on the class and method existence. Issue #887 reveals the wiring is absent — `acquire()` exists in code and docs but is never called. This makes ResourceManager `b` (both present but docs describe wired behavior, code has dead method). K classification needs upgrade to b. |
| `execution-engine.CheckpointManager` / `WorkflowCheckpoint` | K1=d (row 110), K2 no entry, K3=b (row 97/98) | No new issue — existing #890 indirectly | K3 already classified as b (WorkflowCheckpoint.pending_block/config_snapshot always written as None; list_checkpoints missing; CHECKPOINT_SAVED never emitted) | **b** (confirm K3 over K1) | K1 said d (no ARCH entry); K3 found both present but disagreeing. K3's b is more accurate given C4 confirms the class exists and ARCH/docs describe behavior that code doesn't implement (CHECKPOINT_SAVED never emitted, list_checkpoints absent). Confirming K3's b. |
| `block-abc.AIBlock.completion` — OR vs AND semantics | K1=b, K2=b, K3=b | #882 | ADR-035 §3.5 currently specifies OR/first-wins; implementation matches OR; issue proposes amending ADR to conditional-AND with `auto_complete` config — i.e., a SPEC amendment, not a code fix | **b + c-impl note** | K agents correctly classified AIBlock as b (pre-ADR-035 docs vs current PTY implementation). Issue #882 proposes a further amendment to ADR-035 §3.5 that would add the `auto_complete: bool` config field. This is a c-impl for the NEW interface (completion AND semantics + `auto_complete` field) pending the ADR addendum. The K classification of b remains correct for the current state. |
| `rest-api.validate_connection` (effective ports) | K1=a (row 142), K2 no explicit entry, K3 no explicit entry | #889 | `POST /api/blocks/validate_connection` does not accept `source_node_config` / `target_node_config`; handler uses static port schema, not effective ports per ADR-028/029 | **b** | K1 classified blocks routes (BLK-001 through BLK-004) as `a`. Issue #889 reveals a specific API contract gap: the validate_connection endpoint payload schema is wrong per ADR-028/029. The route exists (K1's `a` is partially right) but the payload contract disagrees with what ADR-028 Addendum 1 §C5 and ADR-029 D12 mandate. Upgrading to b for this endpoint. |
| `block-registry.scieasy.blocks` entry-points (count) | K1=a (row 84), K2 no conflict, K3=b (row 70) | No explicit issue — per K3 analysis | K3 found 14 in pyproject.toml vs 8 in PROJECT_TREE.md; K1 said ARCH §12.1 shows all 14 so it's a | **K3 b confirmed** | Cross-validation: K3's b is correct (PROJECT_TREE.md is the stale source; ARCH §12.1 is correct at 14). The gap is in PROJECT_TREE.md. K1's a is based on the more-authoritative ARCH §12.1, but the discrepancy still makes this b (two doc sources disagree). K3's classification preserved. |
| `block-abc.LazyList` (ViewProxy dependency) | K1=a (row 76), K2=b (row 64), K3=a (row 13/63) | #707 (CodeBlock._unpack_inputs calls `.view()`) | `.view()` was eliminated in ADR-031 Phase 2 (PR #626); CodeBlock still calls `value[0].view().to_memory()` — confirming ViewProxy not fully removed from code | **b** (confirm K2) | Issue #707 proves K2's b is correct: code still has `.view()` call paths despite ADR-031 elimination. K1/K3's `a` was too generous. This is a docs-wins drift (ADR-031 says ViewProxy eliminated; code still has live `.view()` calls). |
| `block-abc.CodeBlock.run` (config field 'code' vs 'script') | K1=a (row 22), K2=b (row 7 on variadic), K3=a (row 7) | #708 | `config_schema` declares field as `code`; `run()` reads `script` — KeyError on any inline-mode CodeBlock | **b** (new dimension) | K agents classified CodeBlock on variadic_inputs/outputs mismatch (K2 said b; K1/K3 said a). Issue #708 surfaces a DIFFERENT b-class gap: the config field name mismatch (schema says `code`, runtime reads `script`). CodeBlock is b on TWO dimensions now. Confirming K2's b, adding this specific evidence. |
| `block-abc.AppBlock` (variadic inputs staged) | K1=a (row 23), K2=a (row 8), K3=a (row 8) | #709 | FijiBlock.run() only stages the hardcoded `"image"` port; user-added variadic input ports (ADR-029) are silently dropped; NapariBlock has same gap | **b** | All K agents classified AppBlock as `a` (exchange dir protocol, variadic ports structure all present). Issue #709 reveals code does not honor variadic_inputs at runtime: user-added ports are ignored in FijiBlock/NapariBlock staging. The ADR-029 D12 contract says variadic inputs must be staged; code violates this. Upgrading AppBlock to b for this staging gap. |
| `agent-provisioning.ADR-041 BlockRegistry rejection` | K1 no entry, K2 no entry, K3 no entry | #1016 | Explicitly out-of-scope deferral per ADR-040 §3.10; TODO tags required in code | **c-defer** (new entry) | Not in K reports. #1016 is a confirmed c-defer: BlockRegistry hard-rejection of `DataObject`-typed ports is a promised interface (ADR-040 §3.10 advisory layers exist but hard rejection deferred to ADR-041). |
| `agent-provisioning.ADR-041 Layer 7 ACL` | K1 no entry, K2 no entry, K3 no entry | #1015 | Explicitly out-of-scope deferral per ADR-040 §3.10; filesystem ACL on `<project>/blocks/` is the bulletproof escalation | **c-defer** (new entry) | Not in K reports. #1015 is a confirmed c-defer: the Layer 7 ACL interface is promised by ADR-040 §3.10 but deferred to ADR-041. |

---

## Issues investigated that DID NOT produce entries

- #1090 — umbrella issue for this SSOT cascade itself; no interface classification
- #1089 / #1088 / #1087 / #1085 / #1069 / #1068 / #1062 / #1060 — ADR-040 Phase 3 audit issues; meta-audit, not interface gaps
- #1057 / #1056 / #1045 / #1039 / #1038 / #1036 / #1035 / #1031 / #1025 / #1024 — ADR-040 Phase 2/3 implementation issues; covered by C7/K1-K3 module
- #1033 / #1023 — skeleton audit issues; no new interface gaps
- #903 — SKILL.md optimization umbrella; qualitative content, not a named interface surface
- #902 — CI flake in test_ai_block_skeleton.py; race condition bug, not an interface contract
- #891 — Wheel build without SPA verification; build process, not an interface contract
- #881 — AI Block auto-submit bug; UX bug, not interface contract drift
- #882 — ADR-035 §3.5 OR→AND semantics: RETAINED above as a K-refinement (confirms K agents' b classification and adds c-impl for the new `auto_complete` field)
- #841 — Codex/Python 3.12 Windows hang; platform-specific runtime bug
- #835 — Bottom-panel tabs: RETAINED above as a new c-defer entry (LineageView/JobsPanel)
- #827 — observability helper: RETAINED above as new c-impl entry
- #822 — LoadData type-picker wizard: RETAINED? Reconsidered — this is a pure frontend feature, not an interface contract drift vs ARCH; ARCH does not promise a wizard. Rejecting as an interface entry. Filed under "not produced" — this is a greenfield feature proposal.
- #819 — scieasy-blocks-metadata spec: pure spec doc creation for a NEW external package; no code drift. Not an interface entry.
- #709 — FijiBlock variadic inputs: RETAINED above as K-refinement on AppBlock
- #708 — CodeBlock config field: RETAINED above as K-refinement on CodeBlock
- #707 — CodeBlock .view() call: RETAINED above as K-refinement on LazyList/CodeBlock
- #692 — Type check CI failure; zarr/mypy incompatibility; not interface contract
- #679 — AppBlock output_dir to external app: per-block implementation task; issue explicitly says "no generic injection mechanism on AppBlock base, no new helper modules, no ADR." Not an interface gap.
- #661 — Block SDK docs `_data` pattern: RETAINED above as new d-remove entry
- #617 — PowerShell injection fix; security/sanitization implementation; not interface contract
- #560 — AppBlock worker state transition RUNNING→PAUSED bug; implementation bug in existing interface; not a new interface entry
- #490 — macOS compat tracking; platform-specific; no interface classification
- #177 — useSSE/useWebSocket reconnection: RETAINED above as new d-document entry
- #908 — PROJECT_TREE.md proxy.py annotation: RETAINED above as new d-remove entry

---

## ADR-section hot-spot index

| ADR § | # issues citing | Module | Hot-spot? |
|---|---|---|---|
| ADR-028 §D8 | 5 (#1073, #1074, #1075, #1076, #1077) | block-registry, block-abc (IOBlock) | **YES** — the highest-density unimplemented-promise cluster in the issue tracker |
| ADR-031 | 4 (#707, #661, #908, #1079/#1080 indirectly) | block-abc, data-types, docs.block-sdk | **YES** — ViewProxy elimination still incomplete in multiple surfaces |
| ADR-028/029 (effective ports) | 2 (#889, #709) | rest-api, block-abc (AppBlock) | Yes — two separate contract gaps from the same ADRs |
| ADR-035 §3.5 | 1 (#882) | block-abc (AIBlock completion) | Moderate — the OR→AND amendment is pending |
| ADR-041 (placeholder) | 2 (#1015, #1016) | agent-provisioning, block-registry | Yes — two explicit out-of-scope deferrals from ADR-040 cascade |
| ADR-022/027 (L1 resource) | 1 (#887) | execution-engine | Moderate — long-running known gap |
| ADR-017/018/022 (SubWorkflow) | 1 (#890) | block-abc | Moderate — scheduler injection known stub |

---

## Notes and judgment calls

**ADR-028 §D8 cluster (#1073–#1077):** This is the strongest finding — 5 tightly-chained issues all pointing to a single ADR decision that is 0% implemented. The K agents did not flag this as c-class because they only looked at `IOBlock` as an existing class (classified a or b based on the `load()` signature drift). They missed that the entire `supported_extensions` + `_detect_format` + `find_loader/find_saver` interface layer promised by §D8 is absent from code. Issue #1073's body is explicit: "ADR-028 §D8 is 0% implemented in code despite being a binding decision."

**K3 vs K1/K2 disagreements confirmed by issues:** K3 classified `SubWorkflowBlock` as `a` and `LazyList` as `a`; issues #890 and #707 confirm K1/K2's `b` classifications on both. K2 tended to classify more aggressively as `b` and was more often correct per the issue evidence.

**b-docs-wins vs b-code-wins for resource accounting (#887):** This is the one entry where I chose b-code-wins. The issue explicitly recommends "Option A — Document reality" meaning the docs should be updated to match code's current behavior (L1 not wired). This is a b-code-wins because code IS the current reality; docs promise a future state. Counter-argument: ARCH §1516 is the primary authority. However, the issue author (project owner) explicitly recommends updating docs, making b-code-wins the right sub-label here.

**Issue #560 and #177 border-line:** Both describe implementation gaps in existing interfaces. #560 (AppBlock state transition) is a bug in a specific algorithm, not an interface contract definition gap — left in "not produced." #177 (reconnection logic) is an undocumented behavior contract — kept as d-document because ARCH §8.2 should specify the reconnection semantics.

**ADR-041 placeholder issues (#1015, #1016):** These are explicitly "c-defer" per CLAUDE.md §7.6 pattern — out-of-scope items that need TODO tags in code with tracking links. They are new entries not in K reports.
