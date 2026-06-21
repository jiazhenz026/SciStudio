# A2 Contracts, Storage, Lineage Alpha Audit

Baseline: `ab5f24e6`
Branch: `track/alpha-release-audit-20260621`
Role: `A2-contracts-storage`
Persona: `audit_reviewer`
Audit mode: `with-context`
Issue: `#1733`
Umbrella PR: `#1734` (`[DO NOT MERGE]`)

Recommendation: `pass-with-must-fix`

## Findings

### P0

None found in the targeted A2 scope.

### P1-01: Zarr overwrite is not failure-atomic and can erase the previous array store

`ZarrBackend.write()` documents an atomicity guarantee that "either the old data remains intact or the new data is fully committed" (`src/scistudio/core/storage/zarr_backend.py:54`). The implementation writes a temporary directory, but on overwrite it removes the existing target with `shutil.rmtree(target)` before renaming the temporary directory into place (`src/scistudio/core/storage/zarr_backend.py:69`). If the rename or process fails after the removal, the old array is already gone.

Evidence:

- `src/scistudio/core/storage/zarr_backend.py:54` promises crash/cancellation atomicity.
- `src/scistudio/core/storage/zarr_backend.py:69` removes the old target before the replacement rename.
- `tests/core/test_storage.py:83` covers failed first-write cleanup, and `tests/core/test_storage.py:95` covers successful overwrite, but there is no regression for failed overwrite preserving the prior target.
- Targeted probe:

```text
PYTHONPATH=src python - <<'PY'
...
caught simulated rename failure after old target removal
original_exists_before True
target_exists_after_failed_overwrite False
remaining_entries []
PY
```

Impact: Array storage is a representative core persistence path. The happy path works, but failed overwrite handling can leave neither the old nor new array store. This matches the alpha P1 criterion for a core path that has happy-path coverage but lacks failure-state handling.

Must fix or explicitly risk-accept before alpha: use a directory replacement helper that restores the old target on replacement failure, or add a dedicated Zarr-safe two-phase replacement path, then add a regression that simulates failure after old-target removal.

### P1-02: Unknown dynamic port type strings silently widen or skip runtime contract validation

Runtime port config conversion treats unknown type names as `DataObject`, while workflow boundary validation drops unknown type names and skips capability validation when the resulting type list is empty.

Evidence:

- `ports_from_config_dicts()` states unknown names fall back to `DataObject` (`src/scistudio/blocks/base/ports.py:109`) and implements that by returning `DataObject` after any resolution exception (`src/scistudio/blocks/base/ports.py:117`).
- `validate_connection()` accepts broadly when a target/source type is effectively wide enough (`src/scistudio/blocks/base/ports.py:152`).
- The registry validator checks dynamic port descriptor shape and type-name string-ness, but not whether those names resolve to registered core/plugin data types (`src/scistudio/blocks/registry/_capability.py:178`).
- `_boundary_config_types()` returns no type for unknown names (`src/scistudio/workflow/validator.py:119`), and validation skips entries with no resolved types (`src/scistudio/workflow/validator.py:495`, `src/scistudio/workflow/validator.py:512`).
- Existing unit coverage locks in the fallback behavior: `test_unknown_type_name_falls_back_to_dataobject` asserts that an unknown type resolves to `DataObject` (`tests/blocks/test_ports.py:298`).
- The historical ADR note for `LoadData` chose `ValueError` for unknown `core_type` specifically because falling back would mask typos silently (`docs/adr/ADR_legacy.md:6549`).
- Targeted probe:

```text
PYTHONPATH=src python - <<'PY'
...
dynamic_port_type DataObject
boundary_config_types []
PY
```

The probe also emitted an unrelated installed-entry-point warning for `scistudio_blocks_spectroscopy`, then exited 0.

Impact: A typo in a dynamic or user-configured port declaration can broaden type compatibility or avoid boundary capability checks instead of failing fast. This is runtime contract drift that can mislead alpha testers about block compatibility and IO support.

Must fix or explicitly risk-accept before alpha: reject unknown non-empty type strings during dynamic port conversion and workflow validation, or preserve compatibility only for missing/empty type lists while surfacing unknown strings as validation errors.

### P2-01: Lineage integrity is unknown for directory-backed array stores

Lineage records and can detect overwritten/deleted regular files, but directory-backed artifacts such as Zarr arrays are deliberately excluded from hashing.

Evidence:

- `hash_artifact_file()` returns `None` for non-regular files, including directory-backed Zarr stores, and defers recursive hashing to TODO `#1517` (`src/scistudio/core/lineage/store.py:61`).
- `upsert_data_object()` records `size_bytes`, `mtime_at_write`, and `content_hash` only when `storage_path` is a regular file (`src/scistudio/core/lineage/store.py:612`).
- `check_object_integrity()` returns `unknown` when there is no recorded hash or the path is not checkable (`src/scistudio/core/lineage/store.py:665`).
- Regular-file integrity behavior is well covered for unchanged, overwritten, and deleted files (`tests/core/test_lineage_store_integrity.py:62`, `tests/core/test_lineage_store_integrity.py:106`, `tests/core/test_lineage_store_integrity.py:133`).
- Targeted probe:

```text
PYTHONPATH=src python - <<'PY'
...
storage_path_is_dir True
integrity unknown
dangling []
PY
```

Impact: Representative Array outputs can be persisted and referenced, but the lineage store cannot currently prove whether a Zarr directory-backed output is intact, overwritten, or deleted. This is good-to-fix before broader testing, and already has a tracked follow-up reference.

Good-to-fix: implement recursive directory digests or backend-provided manifests for directory-backed storage, then add parity tests alongside the regular-file lineage integrity tests.

### P2-02: Block schema contract hardening remains intentionally incomplete

The contract test suite has expected failures for the stable block schema envelope and MCP/API schema parity.

Evidence:

- `test_schema_payload_exposes_stable_contract_fields` is marked xfail because schema payloads do not yet expose the desired unified ports envelope (`tests/contracts/test_block_schema_contract.py:101`).
- `test_mcp_and_api_schema_payloads_share_block_registry_source_of_truth` is marked xfail because MCP `get_block_schema` is not API-equivalent for identity and schema fields (`tests/contracts/test_block_schema_contract.py:153`).
- The targeted no-coverage test run passed functionally but reported both expected xfails.

Impact: This is not a direct core execution data-loss issue, but it means the block contract shape exposed to tool/API consumers is not fully hardened for alpha. If alpha depends on API/MCP schema parity, this should stay visible under issue `#1454` or be accepted explicitly for the umbrella release audit.

Good-to-fix: close the `#1454` contract gaps or add an explicit alpha risk note that runtime execution contracts are in scope while schema parity remains pre-alpha hardening.

## Command Evidence

Commands were run from `/Users/jiazhenz/SciStudio-alpha-audit-20260621` on branch `track/alpha-release-audit-20260621`.

- `git status --short --branch`
  - Result: on `track/alpha-release-audit-20260621...origin/track/alpha-release-audit-20260621`; no local diff before the report.
- `PYTHONPATH=src python -m pytest tests/blocks/test_ports.py tests/core/test_storage.py tests/core/test_lineage_store_integrity.py tests/core/test_serialization_roundtrip.py tests/core/test_lineage_store_4table.py tests/workflow/test_validator_dynamic_ports.py tests/workflow/test_serializer_durability.py tests/contracts/test_block_schema_contract.py -q`
  - Result: exited 1 only because the repository-wide coverage fail-under was applied to this narrow slice (`total of 27 is less than fail-under=70`). No functional test failures were reported; two contract tests were expected xfails for `#1454`.
- `PYTHONPATH=src python -m pytest --no-cov tests/blocks/test_ports.py tests/core/test_storage.py tests/core/test_lineage_store_integrity.py tests/core/test_serialization_roundtrip.py tests/core/test_lineage_store_4table.py tests/workflow/test_validator_dynamic_ports.py tests/workflow/test_serializer_durability.py tests/contracts/test_block_schema_contract.py -q`
  - Result: exited 0. Selected functional tests passed with the same two expected xfails.
- `PYTHONPATH=src python - <<'PY' ... ports_from_config_dicts/_boundary_config_types probe ... PY`
  - Result: exited 0 after an unrelated installed-entry-point warning; printed `dynamic_port_type DataObject` and `boundary_config_types []`.
- `PYTHONPATH=src python - <<'PY' ... ZarrBackend failed-overwrite probe ... PY`
  - Result: exited 0; simulated rename failure showed the old target existed before overwrite and did not exist after failed overwrite.
- `PYTHONPATH=src python - <<'PY' ... LineageStore Zarr-directory integrity probe ... PY`
  - Result: exited 0; printed `storage_path_is_dir True`, `integrity unknown`, and `dangling []`.

## Positive Evidence And Coverage Notes

- Serialization rejects non-Artifact data objects without a `storage_ref` before boundary transport (`src/scistudio/core/types/serialization.py:356`).
- `DataObject` validates free-form user metadata for JSON serializability (`src/scistudio/core/types/base.py:219`).
- `DataObject.to_memory()` fails when no storage reference is available, which prevents silent in-memory fallback at read time (`src/scistudio/core/types/base.py:401`).
- The selected core tests provide useful happy-path and representative coverage for ports, storage, regular-file lineage integrity, serialization round trips, lineage table shape, dynamic port validation, serializer durability, and block schema contract expectations.
- Core workflow source versioning (`src/scistudio/core/versioning/**`) was reviewed at a code/docs level. No A2-blocking finding was identified there; broader workflow state version semantics are covered by planned ADR-045 work and appear more API/frontend-facing than this storage-lineage scope.

## Recommendation

`pass-with-must-fix`.

Alpha should not be blocked outright by A2 because representative core paths execute and the targeted functional slice passes. However, the Zarr overwrite integrity gap and silent unknown-type fallback/skip behavior should be fixed before alpha, or explicitly accepted by the owner as bounded risks in the umbrella audit.
