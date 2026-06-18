# Package Validator Contract Survey Draft

Status: working scratchpad.

Purpose: collect ADR/spec/architecture-derived obligations for a package
development-time and install-time validator. This is not yet a formal spec.

## Scope

- Validate package contracts during development.
- Validate installed packages before production registration.
- Focus on extension surfaces: package metadata, entry points, DataObject types,
  blocks, IO capabilities, previewers, preview assets, and runtime registration
  consistency.

## Source Index

- ADR-017: subprocess isolation and reference-oriented worker boundary.
- ADR-020: Collection transport, homogeneous item type, no engine-level
  per-item scheduling.
- ADR-022: resource hints are CPU/GPU declarations and memory is OS-observed,
  not a package RAM estimate contract.
- ADR-025: package distribution through `scistudio.blocks` and
  `scistudio.types`; `PackageInfo` and package grouping.
- ADR-026: SDK scaffolding and `BlockTestHarness` contract validation.
- ADR-027: plugin-owned domain types, type registry, typed worker
  reconstruction, axis/Meta constraints.
- ADR-028: `IOBlock` replaces central adapters; dynamic ports and effective
  port hooks.
- ADR-029: variadic port count through node config and effective ports.
- ADR-030: config schema MRO merge and direction-aware IO path field injection.
- ADR-031: reference-only DataObject boundary; IOBlock loaders persist through
  storage refs; no cross-boundary `_data` / `_arrow_table` backdoors.
- ADR-037: desktop/plugin distribution; future `[tool.scistudio]` plugin
  manifest, API version, min/max core version, permissions/resources, PyPI
  naming/classifier, per-plugin venv.
- ADR-038: lineage records block version from package distribution and rejects
  `"unknown"` versions; recipe/environment tracking, not raw-data retention.
- ADR-041: CodeBlock v2 as AppBlock file exchange; capability-aware type +
  extension boundary validation.
- ADR-043: IO format capability registry and explicit package validity rules.
- ADR-044: SubWorkflowBlock authoring-only container; generic ports are a
  legitimate exception there, scheduler sees flattened DAG.
- ADR-047: BlockRegistry subpackage split; `find_*_capability` is canonical,
  legacy IO finder API removed.
- ADR-048: `scistudio.previewers`, `PreviewerSpec`, deterministic routing,
  same-origin manifests, bounded `PreviewDataAccess`, plot jobs.
- `docs/architecture/ARCHITECTURE.md`: stable architecture overview for
  plugin ecosystem, package installation, user-wide extension paths, and
  extension philosophy.
- `docs/block-development/**`: current author-facing package contract:
  publishing, block contract, custom types, previewers/plots, testing,
  memory safety, architecture for block developers.

## Discovered Obligations

### Package Metadata And Distribution

- Installed package should expose standard Python package metadata:
  distribution name, version, requires-python, dependencies, and entry points.
- New package names should use the documented block/plugin convention
  (`scistudio-blocks-*` or future `scistudio-plugin-*`) and classifier
  `Framework :: SciStudio` when the desktop/plugin-browser model is in scope.
- Preferred block package callable is
  `get_blocks() -> (PackageInfo, list[type[Block]])`; plain list and direct
  class shapes are compatibility, not ideal production compliance.
- `PackageInfo.name` and version must be non-empty and should agree with the
  installed distribution metadata.
- Package version must be resolvable; registry/lineage must not stamp
  `"unknown"`.
- Future `[tool.scistudio]` manifest needs validation if ADR-037 is activated:
  plugin API version, min/max SciStudio version, resource declarations,
  permission declarations, heavy dependency URL, and compatibility range.

### Entry Points

- `scistudio.blocks`: callable returns package metadata plus block classes, or
  accepted legacy forms in compatibility mode.
- `scistudio.types`: callable returns `list`/`tuple` of `DataObject`
  subclasses.
- `scistudio.previewers`: callable returns `list[PreviewerSpec]`.
- The three surfaces are independent; importing one surface should not require
  unnecessarily importing heavy or unrelated surfaces when avoidable.
- Historical `scistudio.adapters` is superseded and must not be accepted as a
  current package contract.

### Type Contracts

- Plugin domain types belong outside core and must subclass a core
  `DataObject` base type.
- Custom type `Meta` must be a Pydantic model, frozen, no `PrivateAttr`, and
  JSON-round-trippable.
- Array subclasses must respect required/allowed/canonical axes when declared.
- CompositeData subclasses must validate expected slots and slot object types.
- Types that add constructor-required fields may need
  `_reconstruct_extra_kwargs` and `_serialise_extra_metadata` round-trip hooks.
- Type names/type chains must be concrete enough to support port validation
  and preview routing.

### Block Contracts

- Every block class must be a concrete `Block` subclass with non-empty `name`,
  `input_ports: list[InputPort]`, `output_ports: list[OutputPort]`, and a
  usable `run()` path.
- `OutputPort` uses `accepted_types`; any `produced_type` guidance is invalid.
- Ports should use the most specific registered `DataObject` type available.
  Empty `accepted_types` is runtime-valid but should be deliberate; generic
  exceptions include SubWorkflow/generic utilities.
- Port names should be unique within each direction and stable because
  workflows and lineage refer to them.
- `run(inputs, config)` returns `dict[str, Collection]`; values crossing block
  boundaries should be DataObject refs inside homogeneous Collections.
- `ProcessBlock.process_item` should use the current
  `(self, item, config, state=None)` shape for new code.
- `setup(config)` must not depend on inputs; `teardown(state)` should release
  resources.
- Resource declarations are advisory CPU/GPU/palette metadata, not memory
  reservation or reproducibility truth.

### Data Transport And Runtime Boundary

- Blocks execute in subprocesses by default; engine passes JSON-friendly
  config and storage references, not raw scientific payloads.
- Collections are homogeneous transport wrappers; a single item is still a
  length-one Collection.
- DataObject instances crossing boundaries must be reference-only:
  `storage_ref` for ordinary persisted data or `file_path` for Artifact.
- Cross-boundary `_data` and `_arrow_table` monkey-patched payloads are invalid.
- IOBlock loaders should persist directly via `persist_array` /
  `persist_table`; auto-flush is a safety net, not a published package pattern.

### IOBlock And FormatCapability

- External formats are boundary capabilities, not DataObject attributes.
- Published IO packages should declare explicit `FormatCapability` records;
  legacy `supported_extensions` synthesis is migration scaffolding only.
- Capability fields: stable package-qualified id, direction, data_type,
  format_id, normalized lowercase dot extensions, label, block_type, handler,
  default/priority, roundtrip_group, metadata_fidelity.
- Capability validation must check referenced IOBlock exists, handler exists,
  direction matches block role, type is compatible with effective port, ids are
  globally stable/unique, defaults do not conflict, roundtrip claims have both
  sides, and typed_meta fields exist on the type Meta model.
- Capability lookup must be deterministic and fail on ambiguity unless an
  explicit capability_id or valid default resolves it.
- `find_loader_capability`, `find_saver_capability`, and
  `list_format_capabilities` are canonical; legacy finder names are removed.

### Dynamic, Variadic, And Config Schema

- Dynamic ports are fixed-name ports whose type changes from a config enum.
  Registry must validate descriptor shape and runtime must use effective ports.
- Variadic ports store user-declared port lists in node config; allowed type
  lists and min/max constraints must be exposed and enforced.
- Config schemas are MRO-merged by the registry; child property overrides are
  atomic, `required` is unioned/deduped, and IO path widget is direction-aware.

### AppBlock And CodeBlock Boundaries

- AppBlock/CodeBlock file exchange uses type + extension + optional
  capability_id; extension alone is never semantic truth.
- Inputs require saver capability resolution before external process/script
  start.
- Outputs require loader capability resolution before execution when the port
  contract is known, and required output folders fail if no matching files are
  produced.
- Duplicate output extensions on the same variadic output block are invalid
  because file binning would be ambiguous.
- Script paths for CodeBlock must be project-local for lineage/git portability.

### Previewer Contracts

- Package previewers register through `scistudio.previewers` and return
  `PreviewerSpec` records.
- `PreviewerSpec` needs globally unique stable id, correct owner_kind,
  owner_name, target_type, collection support flag, priority, capabilities,
  backend_provider, optional frontend_manifest, and API version.
- `target_type` should resolve against registered type chains; routing depends
  on exact type, parent type, collection support, owner tier, priority, and
  project defaults.
- Routing must fail with typed ambiguity, not registration-order selection.
- Backend providers must use `PreviewDataAccess` for bounded reads and return
  typed error envelopes for routine failures.
- Frontend manifests must be same-origin/backend-relative, versioned or
  fingerprinted, API-version compatible, path-confined by asset_root, and
  excluded from leaking backend filesystem paths to the frontend.
- Package wheel must include previewer Python modules and frontend assets when
  it ships a custom UI.
- Preview failures must not mutate workflows, DataObjects, lineage, or
  downstream outputs.

### Plot Jobs

- Plot jobs are project-local preview-only artifacts, not package registry
  surfaces and not workflow nodes.
- If validator later covers project packages/examples, `plot.yaml` requires
  stable workflow path, node id, output port, script entrypoint, allowed output
  format, target reachability, path traversal checks, and render smoke test.

## Existing Coverage

- `BlockTestHarness` validates a single block subclass, non-abstract status,
  `input_ports` / `output_ports` list shapes, port object classes, non-empty
  block name, `PackageInfo`, entry-point return shape, and basic smoke
  execution.
- `BlockRegistry` entry-point scan accepts package tuples, plain block lists,
  and legacy direct block classes. Invalid entry points, abstract blocks, and
  bad payload items are logged/skipped instead of returned as a structured
  package report.
- `BlockRegistry` spec construction validates dynamic-port descriptor shape,
  distribution version resolution, IO capability declaration type, capability
  direction, `block_type`, handler existence, package-qualified capability IDs,
  duplicate capability IDs, and conflicting default capabilities.
- `FormatCapability` / `MetadataFidelity` validate non-empty fields,
  normalized extensions, valid direction and fidelity level, `lossless`
  roundtrip-group requirement, and typed-meta field existence.
- Capability lookup already uses deterministic matching and raises typed
  missing/ambiguous capability errors rather than falling back to registration
  order.
- `TypeRegistry` validates plugin `Meta` classes for Pydantic inheritance,
  no `PrivateAttr`, and best-effort JSON round-trip. Bad type entry points or
  bad type classes are warning/skipped, not install-blocking.
- `PreviewerRegistry` validates only coarse factory shape, item type, empty ID,
  and duplicate ID. Broken previewer entry points are diagnostics/skips.
- `previewers.assets.validate_manifest` checks same-origin frontend manifest
  shape, rejects remote module/CSS URLs, reports API-version mismatch, and
  requires version/fingerprint. `resolve_asset` path-confines asset serving.
- `PreviewRouter` and tests cover deterministic previewer routing, priority
  ties, project defaults, and ambiguity behavior.
- Workflow validation already checks dynamic/effective port connections,
  variadic cardinality, AppBlock duplicate output extensions, CodeBlock v2
  declarations, and ADR-043 boundary capability resolution for
  AppBlock/CodeBlock.
- Contract tests exist for core IO capabilities, registry capability lookup,
  package capability declarations, previewer registration, docs/scaffold
  guidance, and wheel asset packaging in current in-repo packages.

## Current Gaps For A Unified Package Validator

- There is no single validator entry point that evaluates one candidate
  package and returns a structured `PackageValidationReport`.
- Registry scan is tolerant by design. Most broken package surfaces become
  warnings, diagnostics, or skipped registrations; this is acceptable for app
  startup resilience but insufficient for production install refusal.
- Registry scan mutates live registries while scanning. Install validation
  needs an isolated dry-run registry and atomic commit/quarantine semantics.
- Current checks are split by surface. Cross-surface consistency is partial:
  block port types vs package type entry points, previewer target types vs
  registered type chains, IO capability types vs effective IO ports, and
  package metadata vs entry-point owner names need one combined pass.
- Previewer spec validation is the weakest surface: target type resolution,
  owner_kind/owner_name consistency, api_version compatibility,
  backend-provider importability, provider callable protocol, manifest
  ID/spec ID consistency, and wheel asset inclusion are not enforced at
  registry registration.
- Type validation does not hard-enforce `Meta` frozen configuration, and it
  only best-effort checks required-field Meta JSON round-trip.
- Block contract validation is shallow: it does not fully validate run
  signature, return value shape, Collection/reference-only output contract,
  unique port names, accepted type registration, config schema widget
  contracts, ProcessBlock hook signatures, or IOBlock load/save signatures.
- ADR-043 migration scaffolding remains a policy question: synthesized
  capabilities from legacy `supported_extensions` can still exist in
  compatibility paths, but published packages should be explicit.
- AppBlock/CodeBlock boundary validation is workflow-node scoped. A package
  validator needs package-level static checks plus optional fixture-based
  smoke checks for candidate AppBlock/CodeBlock templates/examples.
- Runtime reference-only and subprocess-boundary guarantees cannot be proven
  statically. They require smoke fixtures or instrumented execution against
  temporary storage to catch returned `_data`, `_arrow_table`, missing
  `storage_ref`, malformed `Collection`, and non-JSON metadata.
- ADR-037 `[tool.scistudio]` plugin manifest is documented as a future desktop
  contract. Validator design should include it, but activation needs an owner
  decision on version/permission/resource enforcement timing.
- Optional heavy dependencies and per-plugin venv isolation need explicit
  policy: dev validation can allow skipped optional checks; production install
  should validate within the same isolated environment used for execution.

## Open Questions

- Should production install reject legacy-but-loadable package shapes, or allow
  with warnings under a compatibility profile?
- Should install-time validation execute package code in the main SciStudio
  process, an isolated validation subprocess, or the per-plugin venv worker
  path from ADR-037?
- Should invalid package validation disable the entire distribution or only the
  invalid entry-point surface/specs?
- How should validator handle packages with optional heavy dependencies absent
  at validation time?
- Should previewer provider importability be hard-required at install time, or
  can backend-only provider absence degrade to a diagnostic until first use?
- What is the migration policy for existing in-repo packages that still rely on
  ADR-043 compatibility synthesis?
