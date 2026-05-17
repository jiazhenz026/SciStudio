# I2 — Phase 2 supplementary: GitHub-issue-driven classifications
Date: 2026-05-17
Auditor: I2 (independent of I1)
Issues scanned: 65 open + 0 closed-relevant (no closed issues with "actually not closed / reopening" pattern found)
Issue-driven entries: 14 new + 8 refinements

---

## Summary
- New entries (NOT in K1/K2/K3): 14
  - c-impl: 8
  - d-document: 4
  - b-code-wins: 1
  - b-docs-wins: 1
- Refinements to existing K-report rows: 8

Authority applied: ARCHITECTURE.md PRIMARY; ADR SUPPLEMENTARY. Each issue's referenced spec section is the doc-side authority for that entry.

---

## New entries (NOT in K1/K2/K3)

### `block-abc.IOBlock.supported_extensions` — ADR-028 §D8 ClassVar not implemented
- **Class**: c-impl
- **Source**: [CODE: absent] — `src/scieasy/blocks/io/io_block.py` has no `supported_extensions: ClassVar[dict[str, str]]` declaration on `IOBlock` base class
- **Doc-source**: ADR-028 §D8 (`docs/adr/ADR.md:5704-5721`)
- **Issue**: #1073 — "Implement ADR-028 §D8: `supported_extensions` ClassVar + `_detect_format` helper on IOBlock"
- **Issue body excerpt**: "§D8 specifies: Each concrete IOBlock subclass declares `supported_extensions: ClassVar[dict[str, str]]` mapping lowercase extension (including the leading dot) to a short internal format name. ... The framework provides a helper `IOBlock._detect_format(path)` implementing this lookup so subclasses do not reimplement it. Current state: `src/scieasy/blocks/io/io_block.py` declares no `supported_extensions` ClassVar on the base class. No `_detect_format(path)` helper exists."
- **Sub-label**: c-impl
- **Rationale**: ADR-028 §D8 is a binding decision (P1, audit-followup label). Interface is documented in the ADR but 0% implemented. Docs say it must exist; code does not have it. Classic c-class.
- **Signature**:
```python
class IOBlock(Block):
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

### `block-registry.BlockRegistry.find_loader` / `find_saver` / `find_io_blocks_for_type` — new query interface
- **Class**: c-impl
- **Source**: [CODE: absent] — verified by issue body: "Currently BlockRegistry has no such methods (verified via grep for `extension` in `src/scieasy/blocks/registry.py`: zero matches)"
- **Doc-source**: ADR-028 §D8 (implicit: the extension query system is a consequence of the §D8 decision); issue #1077 defines the interface.
- **Issue**: #1077 — "BlockRegistry: `find_loader(type, ext)` / `find_saver(type, ext)` query methods"
- **Issue body excerpt**: "Add to `BlockRegistry`: `def find_loader(self, dtype: type[DataObject] | None, extension: str) -> type[IOBlock] | None` ... `def find_saver(self, dtype: type[DataObject], extension: str) -> type[IOBlock] | None` ... `def find_io_blocks_for_type(self, dtype: type[DataObject], direction: str) -> list[type[IOBlock]]`"
- **Sub-label**: c-impl
- **Rationale**: Interface fully specified in issue, blocked on #1073 (base ClassVar). Neither K1/K2/K3 had any entry for these three methods — they were not visible without reading the issue tracker. Pure issue-driven new entry.
- **Signature**:
```python
def find_loader(self, dtype: type[DataObject] | None, extension: str) -> type[IOBlock] | None: ...
def find_saver(self, dtype: type[DataObject], extension: str) -> type[IOBlock] | None: ...
def find_io_blocks_for_type(self, dtype: type[DataObject], direction: str) -> list[type[IOBlock]]: ...
```

---

### `core.materialisation.materialise_to_file` / `reconstruct_from_file` — new module
- **Class**: c-impl
- **Source**: [CODE: absent] — module `src/scieasy/core/materialisation.py` does not exist yet
- **Doc-source**: Issue #1078 defines the spec; depends on #1077 (BlockRegistry queries)
- **Issue**: #1078 — "Engine: `core/materialisation.py` helpers (`materialise_to_file` / `reconstruct_from_file`)"
- **Issue body excerpt**: "Create `src/scieasy/core/materialisation.py` with: `def materialise_to_file(obj: DataObject, dest_dir: Path, extension: str | None = None) -> Path` ... `def reconstruct_from_file(path: Path, target_type: type[DataObject], extension: str | None = None) -> DataObject`"
- **Sub-label**: c-impl
- **Rationale**: Entirely new module specified in issue to fix dead code paths in AppBlock bridge. Not in any K-report because no code exists and no ARCH section covers the materialisation helper module.
- **Signature**:
```python
def materialise_to_file(
    obj: DataObject,
    dest_dir: Path,
    extension: str | None = None,
) -> Path: ...

def reconstruct_from_file(
    path: Path,
    target_type: type[DataObject],
    extension: str | None = None,
) -> DataObject: ...
```

---

### `block-abc.IOBlock.supported_extensions` on `LoadData` / `SaveData` — per-block declarations missing
- **Class**: c-impl
- **Source**: [CODE: inline ad-hoc] — `load_data.py:395` uses `ValueError` message string to enumerate extensions; no `supported_extensions` ClassVar
- **Doc-source**: ADR-028 §D8 (same authority as #1073)
- **Issue**: #1074 — "ADR-028 §D8: declare `supported_extensions` on LoadData / SaveData"
- **Issue body excerpt**: "Per ADR-028 §D8, every concrete IOBlock subclass MUST declare `supported_extensions: ClassVar[dict[str, str]]`. Currently extension knowledge is inlined in `if suffix == '.x':` chains and embedded in ValueError messages."
- **Sub-label**: c-impl
- **Rationale**: Downstream concrete block declarations; same §D8 authority. Not in K reports (K agents saw the base class gap but not these per-block follow-ons because they are in packages/ which is out of K scope).

---

### `block-abc.IOBlock.supported_extensions` on `LoadImage` / `SaveImage` — imaging plugin
- **Class**: c-impl
- **Source**: [CODE: module-level constants only] — `load_image.py:27-29` uses `_TIFF_EXTS`, `_ZARR_EXTS`, `_SUPPORTED_EXTS` frozensets; no ClassVar on class
- **Doc-source**: ADR-028 §D8
- **Issue**: #1075 — "ADR-028 §D8: declare `supported_extensions` on LoadImage / SaveImage"
- **Issue body excerpt**: "Currently the imaging plugin uses module-level constants instead of the ClassVar: `packages/scieasy-blocks-imaging/.../io/load_image.py:27-29`: `_TIFF_EXTS`, `_ZARR_EXTS`, `_SUPPORTED_EXTS`"
- **Sub-label**: c-impl
- **Rationale**: Same §D8 authority pattern; applies to plugin packages. Out of K-agent scope (K agents did not read plugin packages).

---

### `block-abc.IOBlock.supported_extensions` on remaining plugin IO blocks
- **Class**: c-impl
- **Source**: [CODE: inline chains] — LCMS plugin `load_mzml_files.py:160` has private `_detect_format`; `load_peak_table.py` has inline `if suffix` chains
- **Doc-source**: ADR-028 §D8
- **Issue**: #1076 — "ADR-028 §D8: declare `supported_extensions` on remaining plugin IO blocks"
- **Issue body excerpt**: "Inventory + populate ClassVar on: `packages/scieasy-blocks-lcms/.../io/load_mzml_files.py` (LoadMzMLFiles) — has private `_detect_format` at line 160 which should be replaced with base-class helper from #1073."
- **Sub-label**: c-impl
- **Rationale**: Same authority chain. LCMS plugin is out of K-agent direct scope.

---

### `block-abc.AppBlock.FileExchangeBridge.prepare` — type-dispatched materialisation not implemented
- **Class**: c-impl
- **Source**: [CODE: dead path] — `src/scieasy/blocks/app/bridge.py:31-74` uses `json.dumps(value, default=str)` fallback for all DataObject types
- **Doc-source**: Issue #1080; ADR-041 (referenced in body)
- **Issue**: #1080 — "AppBlock `bridge.py::prepare()`: replace JSON-dump dead fallback with type-dispatched materialisation"
- **Issue body excerpt**: "FileExchangeBridge.prepare() materialises any DataObject input via `to_memory()` then writes via `json.dumps(value, default=str)`. For numpy-array-backed objects (Image, Mask, Array, etc.) this produces a `str(ndarray)` truncated repr in a `.json` file — completely useless to any real external tool."
- **Sub-label**: c-impl
- **Rationale**: The AppBlock's exchange contract per ARCH §5.3 requires typed file materialisation; the existing dead-fallback implementation violates this contract. Issue is about fixing the dead code path to match the intended interface. Not in K reports — K agents noted `FileExchangeBridge` as d-class (code exists, docs don't enumerate method contracts) but did not surface the dead-fallback bug from the issue tracker.

---

### `block-abc.AppBlock._bin_outputs_by_extension` — typed reconstruction not implemented
- **Class**: c-impl
- **Source**: [CODE: wrong behavior] — `src/scieasy/blocks/app/app_block.py:240-258` silently downgrades declared typed ports to `Artifact`
- **Doc-source**: Issue #1079; ARCH §5.3 AppBlock contract
- **Issue**: #1079 — "AppBlock `_bin_outputs_by_extension`: replace Artifact downgrade with typed reconstruction"
- **Issue body excerpt**: "AppBlock._bin_outputs_by_extension silently downgrades any non-Artifact declared port type to Artifact and emits a warning ... This breaks the FijiBlock → SaveImage edge: user declares `accepted_types=[Image]` on the FijiBlock output port, gets an Artifact at runtime, downstream SaveImage rejects the type."
- **Sub-label**: c-impl
- **Rationale**: The typed output reconstruction is part of the AppBlock contract (ADR-028 §D8 completion chain: #1073 → #1077 → #1078 → this fix). Blocked on #1078.

---

### `execution-engine.ResourceRequest` + `ResourceManager` — L1 GPU/CPU slot accounting not wired
- **Class**: b-code-wins
- **Source**: [CODE: struct defined, not wired] — `scheduler.py:197` passes `ResourceRequest()` (default empty); `ResourceManager.acquire()` has zero production callers; no block declares `resource_request`
- **Doc-source**: ARCH §6.4; ADR-022/027
- **Issue**: #887 — "Engine resource accounting (L1 GPU/CPU slots) is not wired into dispatch"
- **Issue body excerpt**: "1. `src/scieasy/engine/scheduler.py:197` calls `can_dispatch(ResourceRequest(), ...)` with a default empty request. It never reads `block.resource_request`. 2. `ResourceManager.acquire()` is defined but has zero callers in production code. 3. No block declares `resource_request` — `grep -r 'resource_request|requires_gpu' src/scieasy/blocks/` returns zero matches."
- **Sub-label**: b-code-wins
- **Rationale**: ARCH §6.4 documents L1 slot accounting as operational. Code has the data structures but the wiring is absent. This is a b-class entry where the interface (ResourceRequest/ResourceManager contract) is documented but the code implementation is incomplete. The resolution is code-side (wire the dispatch path) not doc-side. K1/K2 both classified `ResourceRequest` as either a (K1 row 100) or b (K2 row 100) and `ResourceManager` as a/b — this issue provides concrete confirmation of the code→doc divergence: L1 is documented as working but is a stub.

---

### `execution-engine.DAGScheduler.validate_connection` — effective-ports contract not respected in validate path
- **Class**: b-docs-wins
- **Source**: [CODE: uses static ports] — `App.tsx:737 → POST /api/blocks/validate_connection` passes block-type-level port lists, not instance-effective ports
- **Doc-source**: ADR-028 Addendum 1 §C5; ADR-029 D12 (both explicitly define effective ports as the canonical contract)
- **Issue**: #889 — "API validate_connection and edge coloring do not consume node config — ADR-028/029 effective ports drift"
- **Issue body excerpt**: "Per ADR-028 (dynamic IO ports) and ADR-029 (variadic ports), blocks like `LoadData`, `AIBlock`, `CodeBlock`, and `AppBlock` resolve their effective port set from per-instance config, not from the class's static `input_ports` / `output_ports`. The node renderer respects this (BlockNode.tsx:705 uses `get_effective_*_ports`), but two adjacent paths still use the class's static schema."
- **Sub-label**: b-docs-wins
- **Rationale**: ADR-028/029 (supplementary docs) explicitly define the effective-ports contract. Code path (`validate_connection` API + edge coloring) uses the old static schema. Documentation (ADR) is source of truth; code is behind. K-report classified `get_effective_input_ports`/`get_effective_output_ports` as a-class (K1 row 9, K2 row 30) because they exist in code — but this issue surfaces that the REST API validation route does NOT use them, creating a code-internal inconsistency. This is a new entry specifically about the REST API validation endpoint's failure to call `get_effective_*_ports`.

---

### `block-abc.AIBlock.auto_complete` config field — amendment to ADR-035 §3.5
- **Class**: d-document
- **Source**: [CODE: not yet implemented] — `src/scieasy/blocks/ai/completion.py:3,75-76,131-132` uses OR/first-wins semantics; no `auto_complete` config field
- **Doc-source**: ADR-035 §3.5 (to be amended per issue); issue #882 defines the proposed amendment
- **Issue**: #882 — "ADR-035 §3.5 amend: completion semantics OR → conditional-AND (auto_complete config)"
- **Issue body excerpt**: "Add `auto_complete: bool` to AIBlock config_schema: [true → (a) AND (b); false (default) → (a) AND (b) AND (c) — also requires explicit Mark done from user]"
- **Sub-label**: d-document
- **Rationale**: Proposed interface amendment to AIBlock's config_schema that is not yet implemented and has no doc entry. The amendment would add `auto_complete: bool` as a new AIBlock config field with specific semantics. K-reports classified AIBlock as b-class (K1 row 24, K2 row 9, K3 row 9) due to the ADR-035 rewrite — this issue adds another dimension of drift (new proposed config field). Classifying d-document because neither code nor docs currently have this field; the issue is a forward proposal awaiting decision + implementation.

---

### `execution-engine.EventBus` — 7 of 17 event types not subscribed by logging
- **Class**: d-document
- **Source**: [CODE: partial] — `src/scieasy/api/runtime.py:266` `_bind_event_logging` subscribes to 7 of 17 event types; 10 are never observed for logging
- **Doc-source**: ARCH §6.1 (EventBus contract); issue #827 surfaces the gap
- **Issue**: #827 — "feat(observability): central event/log helper subscribing to all engine events"
- **Issue body excerpt**: "Engine has a well-defined EventBus emitting 14 distinct event types, but only 7 are currently observed (`_bind_event_logging`) ... Unobserved event types: `block_ready`, `block_paused`, `cancel_block_request`, `cancel_workflow_request`, `process_spawned`, `process_exited`, `checkpoint_saved`, `interactive_prompt`, `interactive_complete`, `workflow.changed`"
- **Sub-label**: d-document
- **Rationale**: The EventBus subscription pattern is not a new interface but reveals that the documented contract (EventBus emits N event types) is not fully consumed by the runtime's logging path. This is a d-document entry: the interface (EventBus + 17 constants) exists in both code and docs (K1 row 98 b-class, K2 row 88 b-class), but the logging subscriber gap is not documented anywhere. The issue proposes a new `configure_logging` module — which is currently a `NotImplementedError` stub (`src/scieasy/utils/logging.py`) — making this a c-class sub-surface of the observability layer.

---

### `block-abc.SubWorkflowBlock._scheduler_factory` / `_cleanup_callback` ClassVars — deferred injection contract
- **Class**: d-document
- **Source**: [CODE: stub with ClassVar=None] — `subworkflow_block.py:45,50`: `_scheduler_factory: ClassVar[Any] = None`, `_cleanup_callback: ClassVar[Any] = None`; `_run_with_scheduler` delegates to `_sequential_execute` stub
- **Doc-source**: ARCH §5.3 SubWorkflowBlock section; issue #890
- **Issue**: #890 — "SubWorkflowBlock falls back to sequential in-process execution — scheduler integration unfinished"
- **Issue body excerpt**: "SubWorkflowBlock._scheduler_factory: ClassVar[Any] = None (line 45) — designed to be injected by the engine at startup so blocks can use the real scheduler without importing engine. ... _run_with_scheduler (line 139) — meant to use the injected factory; currently delegates straight back to `_sequential_execute`"
- **Sub-label**: d-document
- **Rationale**: K-reports classified SubWorkflowBlock as b-class (K1 row 25, K2 row 10) due to config-vs-ClassVar pattern differences. Issue #890 surfaces a deeper gap: the injection contract for `_scheduler_factory` and `_cleanup_callback` ClassVars (how the engine wires them at startup) is not documented anywhere. This is a d-document entry for the injection protocol specifically, not for SubWorkflowBlock itself.

---

### `data-types.Array.iterate_over_axes` — memory contract violated in code
- **Class**: d-document
- **Source**: [CODE: violates contract] — `src/scieasy/utils/axis_iter.py:151-154` calls `source.to_memory()` unconditionally despite documenting O(one slice) contract
- **Doc-source**: ARCHITECTURE.md:457 ("Memory: O(one slice + one output slice) regardless of the number of extra-axis combinations"); ADR-027 D4
- **Issue**: #888 — "iterate_over_axes materializes full source — violates O(one slice) contract for Zarr-backed Arrays"
- **Issue body excerpt**: "`ARCHITECTURE.md:457`: Memory: O(one slice + one output slice) regardless of the number of extra-axis combinations. ... Module docstring `src/scieasy/utils/axis_iter.py:16-17`: Memory: O(one input slice + one output slice). Serial by design. ... Code at lines 151-154: `source_data = source.to_memory()` — contradicts both the ARCHITECTURE.md contract and the module's own docstring."
- **Sub-label**: d-document
- **Rationale**: The `iterate_over_axes` function exists and has a documented contract in ARCHITECTURE.md, but code contradicts that contract. This is specifically about the memory-efficiency contract of `iterate_over_axes` — not covered by any K-report row (K agents covered `Array` as a-class, row K1:51, K2:35, K3:36, but not the utility function's contract compliance). This issue-driven entry flags the function as a b-class interface (ARCH says one-slice, code does full materialise) that needs to be tracked in the INTERFACE_SPEC.

---

## Refinements to K-report entries

| Interface | K-class | Issue # | Issue says | I2 final | Why |
|---|---|---|---|---|---|
| `block-abc.IOBlock` (K1 row 21 / K2 row 6 / K3 row 6) | b | #1073, #1074 | ADR-028 §D8 specifies `supported_extensions` ClassVar on IOBlock base — 0% implemented, binding P1 | **c** | Both K1 and K2 classified as b (docs vs code signature on `load()`); but §D8 is a separate doc-says-must-have that code entirely lacks. The `supported_extensions` sub-surface should be c-impl, not just b. K3 classified IOBlock as a. I2 verdict: IOBlock overall remains b (for `load(output_dir)` gap), but adds a c sub-entry for the `supported_extensions` ClassVar. |
| `block-registry.BlockSpec` (K1 row 79 / K2 row 73 / K3 row 67) | K2=b, K3=a | #1077 | `find_loader`/`find_saver`/`find_io_blocks_for_type` are new methods on BlockRegistry (not on BlockSpec) | **a** (BlockSpec unchanged; BlockRegistry gets new methods) | Issue proposes new BlockRegistry methods, not BlockSpec changes. K2's b for BlockSpec is based on field count mismatch. No refinement to BlockSpec classification; new BlockRegistry interface is a separate new entry above. |
| `execution-engine.ResourceManager` (K1 row 101 / K2 row 100 / K3 row 96) | K1=a, K2=b, K3=a | #887 | `acquire()` has zero production callers; L1 slot accounting entirely unwired | **b** | Issue confirms K2's b classification. K1 and K3 classified as a — issue evidence overrides. The interface contract (L1 accounting) is documented in ARCH §6.4 as operational, but code has a dead `acquire()`. b-class confirmed by issue. |
| `execution-engine.ResourceRequest.resource_request` on Block (K1 row 100 / K2 row 100 / K3 row 94) | K1=b (watermark default), K3=a | #887 | No block declares `resource_request`; grep returns zero matches | **b** | Issue provides concrete grep confirmation that no block has `resource_request`. K1 flagged watermark default mismatch (0.90 vs 0.80) separately. K3 classified ResourceRequest as a. Issue confirms code→doc gap is deeper: not just the watermark default but the entire L1 wiring. |
| `block-abc.AIBlock` (K1 row 24 / K2 row 9 / K3 row 9) | K1=b, K2=b, K3=b | #882 | Proposes new `auto_complete: bool` config field + semantics change for completion paths | **b + d-pending** | All three K-agents correctly classify AIBlock as b (ADR-035 rewrite). Issue #882 adds a proposed amendment (auto_complete field) that is d-class pending decision. Does not change the b classification but adds a tracked d-pending sub-surface. |
| `block-abc.SubWorkflowBlock` (K1 row 25 / K2 row 10 / K3 row 10) | K1=b, K2=b, K3=a | #890 | `_scheduler_factory` injection contract not documented; stub intentional but untracked | **b** confirmed | K3 classified as a; issue confirms K1/K2's b is correct. The injection contract for ClassVars is not documented. K3's a-verdict is based on `workflow_ref`/`input_mapping`/`output_mapping` alignment — which is correct for those fields — but the injection protocol for `_scheduler_factory` is a separate undocumented contract. Overall: b. |
| `ws-sse-protocol.EventBus event types` (K1 row 98 / K2 row 88/89 / K3 row 82) | K1=b, K2=b, K3=b | #827 | Only 7 of 17 event types subscribed in `_bind_event_logging`; `configure_logging` is a stub | **b** confirmed + new c sub-entry | All three K-agents correctly classify as b (17 vs 14 documented). Issue adds: the `configure_logging` at `src/scieasy/utils/logging.py` is a NotImplementedError stub — this is a c-class sub-surface (docs describe centralized logging; code has a stub). |
| `block-abc.AppBlock` + `FileExchangeBridge` (K1 rows 23/31 / K2 rows 8/18 / K3 rows 8/20) | K1=a/d, K2=a/d, K3=a/d | #1080, #1079 | `prepare()` has dead JSON-dump fallback; `_bin_outputs_by_extension` downgrades typed ports | **b/c** refinement | K-agents classified AppBlock as a (ARCH coverage good) and FileExchangeBridge as d (code-only Protocol). Issues #1079/#1080 surface that specific AppBlock code paths have incorrect/dead implementations that violate the ARCH §5.3 contract. FileExchangeBridge.prepare() should be upgraded from d to c-impl: ARCH implies correct materialisation behavior; code has broken behavior. |

---

## Issues investigated that DID NOT produce entries

| #NNN | reason rejected |
|---|---|
| #1090 | Umbrella tracking issue for the INTERFACE_SPEC cascade; no interface contract proposed |
| #1085 | ADR-040 integration audit tracking; no new interface contract — summarizes existing findings |
| #1069, #1068, #1062, #1060 | ADR-040 Phase 3 audit tracking issues; no new interface contracts |
| #1057, #1056, #1045, #1039, #1038, #1036, #1035 | ADR-040 Phase 2 implementation tracking; no new interfaces beyond what K-agents saw |
| #1031, #1025, #1024, #1014, #1013, #1012 | ADR-040 phase planning/skeleton tracking issues; no concrete new interface contracts |
| #969, #923 | ADR-039 chore/nits; specific code fixes but no new interface contracts |
| #908 | `proxy.py` annotation drift — K3 row 35 already covers `DataObject._data`/`_arrow_table` as b-class. This issue documents the PROJECT_TREE.md annotation as stale prose, not a new interface entry. |
| #903 | Tracking issue for system prompt optimization; interface (compose_system_prompt) already in K1 row 172 / K2 row 195 as d-class |
| #902 | CI flake (race in test); no interface contract |
| #891 | Wheel build missing SPA; deployment artifact issue, not a core interface contract |
| #881 | AI Block UI bug (auto-submit); no interface contract — existing AIBlock contract covers this |
| #841 | Codex terminal hang on Windows; platform compatibility, not an interface contract |
| #835 | Bottom-panel stubs (Lineage/Jobs); UI implementation gap, not a core module interface. Note: references `MetadataStore` vs `LineageStore` confusion — already in K1 row 128 as d-class. |
| #822 | LoadData type-picker wizard; feature design proposal, no current interface to classify |
| #819 | Spec for `scieasy-blocks-metadata` plugin; out of scope (plugin package, not core contracts) |
| #709 | FijiBlock variadic port bug; relates to AppBlock existing b-class entries (K1 row 23) but no new interface |
| #708 | CodeBlock `code` vs `script` field name mismatch — adds to existing b-class for CodeBlock (K2 row 7) but is a bug fix, not a new interface entry. The field name mismatch is already capturable as a sub-entry of CodeBlock. |
| #707 | `CodeBlock._unpack_inputs` calls `.view()` (removed in ADR-031) — adds to existing b-class for DataObject/LazyList (K2 row 64: LazyList b-class for ViewProxy still present). No new interface entry. |
| #692 | Type-check CI failure on zarr version; no interface contract |
| #679 | AppBlock output_dir communication to external app; follow-up to existing AppBlock b-class, no new interface |
| #661 | Block SDK docs _data example cleanup; documentation fix to align with ADR-031 Add2. Adds to DataObject b-class evidence (K1 row 48, K2 row 34, K3 row 35). No new interface. |
| #617 | PowerShell apostrophe escaping security fix; no interface contract |
| #560 | AppBlock RUNNING→PAUSED state transition bug; relates to existing BlockState a-class entries. Code bug, not new interface. |
| #490 | macOS compatibility tracking; no interface contract |
| #177 | Frontend WebSocket/SSE reconnection; code fix to existing ws-sse-protocol b-class entries. No new interface. |

---

## ADR-section hot-spots

| ADR § | # issues citing it | Module | Hot-spot? |
|---|---|---|---|
| ADR-028 §D8 | 5 (#1073, #1074, #1075, #1076, #1080) | block-abc / block-registry | YES — §D8 is the single most-cited ADR section; 5 open P1 issues all track the same unimplemented feature. The entire IOBlock extension-detection contract is c-class. |
| ADR-028/029 (effective ports) | 1 (#889) | port-system / execution-engine | Moderate — confirms K-reports' b-class for `get_effective_*_ports` in the REST API path |
| ADR-035 §3.5 | 1 (#882) | block-abc (AIBlock) | Low — proposed amendment; no current code/doc entry |
| ADR-022/027 (resource management) | 1 (#887) | execution-engine | Moderate — confirms L1 slot accounting is undocumented-as-broken |
| ADR-027 D4 (lazy Array slicing) | 1 (#888) | data-types | Low — code violates documented contract |
| ADR-031 (DataObject/_data/ViewProxy) | 3 (#707, #661, #908 indirect) | data-types | Already covered by K-reports; issues add evidence for b-class |

---

## Notes & judgment calls

### 1. ADR-028 §D8 cluster is the dominant new finding

Five P1 issues (#1073, #1074, #1075, #1076, #1080) all trace to ADR-028 §D8. This is exactly the pattern described in the dispatch brief (ADR promise not in code, issue exists). K-agents missed this cluster because §D8 affects only the IOBlock hierarchy and plugin packages — not the core BlockSpec/BlockRegistry interfaces they were auditing.

These entries should be treated as a single feature cluster in INTERFACE_SPEC:
- `IOBlock.supported_extensions: ClassVar[dict[str, str]]` (c-impl)
- `IOBlock._detect_format(path)` (c-impl)
- `BlockRegistry.find_loader/find_saver/find_io_blocks_for_type` (c-impl)
- `core.materialisation.materialise_to_file/reconstruct_from_file` (c-impl)

The whole cluster is blocked by #1073 and resolves in sequence: #1073 → #1074/#1075/#1076 → #1077 → #1078 → #1080/#1079.

### 2. b vs c for IOBlock.supported_extensions

I classified this as c-impl (docs say it must exist; code is 0%). The K-agents classified IOBlock overall as b (based on the `load(output_dir)` parameter difference). Both are correct but about different sub-surfaces. The `supported_extensions`/`_detect_format` gap is c; the `load(output_dir)` gap is b. These are distinct sub-entries within the same interface.

### 3. b-code-wins vs b-docs-wins for resource accounting (#887)

Classified b-code-wins: the code has the data structures (ResourceRequest, ResourceManager) but the wiring is absent. Resolution requires fixing code, not docs. ARCH §6.4 accurately describes the intended system; code just doesn't implement L1. This is code-falls-behind-docs (docs win, code needs to catch up).

### 4. Issue #882 (auto_complete) classified d-document not c-impl

The issue proposes an ADR-035 amendment — the field does not exist in docs yet either. This is a d-document (neither code nor docs have it; issue proposes it). If and when ADR-035 is amended to add `auto_complete`, it becomes c-impl. For INTERFACE_SPEC purposes it should be listed as a proposed-but-pending sub-entry of AIBlock.

### 5. K-agent divergence on SubWorkflowBlock

K1=b, K2=b, K3=a. Issue #890 confirms b. The K3 a-verdict was based on `workflow_ref`/`input_mapping`/`output_mapping` field alignment — those specific fields do align. But the injection protocol for `_scheduler_factory` (how the engine wires the real scheduler at startup) is undocumented, making the overall interface b. I2 verdict: b.

### 6. issues-that-confirm vs issues-that-add

Approximately half the investigated issues confirmed existing K-report classifications (b or d) by providing concrete grep evidence. The other half added new entries not visible without the issue tracker (ADR-028 §D8 cluster, materialisation module, validate_connection effective-ports gap). The K-agents' code-reading methodology captured the structure well; the issue tracker captures the intended-but-not-yet-implemented layer.
