# Implementation record: #1079 — AppBlock typed-reconstruction binner

Phase -1 D8 bug-fix sprint. ADR-028 §D8 follow-up. Branch:
`fix/issue-1079/appblock-bin-outputs-typed-reconstruction`. Initial
implementation commit: `cea007d`.

## Files modified

- `src/scieasy/blocks/app/app_block.py` — rewrote
  `_bin_outputs_by_extension` to call
  `scieasy.engine.materialisation.reconstruct_from_file` per port. Removed
  the precomputed `port_item_types` table and the
  `"declared type ... not constructible from a file path"` warning.
  Dropped the now-unused `_guess_mime` import. Added explicit
  `DataObject`-root and empty-`accepted_types` branches that fall back
  to `Artifact` so legacy wildcard-port behavior survives.
- `tests/blocks/app/test_appblock_bin_outputs.py` (NEW) — three test
  classes covering typed reconstruction, legacy Artifact passthrough,
  and the missing-loader `LookupError`.
- `tests/blocks/test_app_block.py` — replaced
  `test_binner_falls_back_to_artifact_for_non_constructible_type` with
  `test_binner_raises_lookup_error_for_non_constructible_type` to match
  the new contract (the old test asserted the pre-#1079 silent
  downgrade + the removed warning).

## Implementation rationale

The pre-#1079 binner unconditionally downgraded any non-Artifact
declared port type to `Artifact` and emitted a warning, which broke the
FijiBlock → SaveImage edge (user declares `accepted_types=[Image]` and
gets an `Artifact` that downstream rejects). The fix routes each output
file through `reconstruct_from_file(path, target_type=declared,
extension=ext)`, which (per #1078) handles three documented outcomes:
typed loader present → typed instance; declared Artifact + no loader →
`Artifact` fallback; declared concrete non-Artifact + no loader →
`LookupError`. The binner now propagates that `LookupError` so the run
fails fast rather than silently violating the declared port contract.

The `Collection.item_type` per port is computed from the actual first
constructed item (or the declared target when the port is empty), so
the #690 homogeneity guarantee still holds even when
`reconstruct_from_file` falls back to `Artifact` on a port that
declared an Artifact subclass.

## Deviations from the spec

One small clarification added beyond the planning-doc bullet list:
when the declared port type is the `DataObject` *root* (or
`accepted_types` is empty/malformed), the binner maps the target to
`Artifact` before calling `reconstruct_from_file`. `DataObject` declared
as the target is the "wildcard / no specific type required" sentinel,
not a real domain type — `reconstruct_from_file` would raise
`LookupError` for it because the root is neither a known core type for
the dynamic-port fallback nor an `Artifact` subclass. The mapping
preserves the legacy semantics that the existing extension-binner
tests (`TestAppBlockExtensionBinner` in `tests/blocks/test_app_block.py`)
rely on.

## Tests added

- `tests/blocks/app/test_appblock_bin_outputs.py::TestTypedReconstruction::test_typed_dataframe_port_returns_dataframe_instance`
  — port declares `DataFrame` + `.csv`; binner returns a typed
  `DataFrame` (not `Artifact`); `Collection.item_type` is `DataFrame`.
- `tests/blocks/app/test_appblock_bin_outputs.py::TestTypedReconstruction::test_no_warning_emitted_for_typed_reconstruction`
  — the pre-#1079 `"not constructible from a file path"` warning never
  appears on the new path.
- `tests/blocks/app/test_appblock_bin_outputs.py::TestLegacyArtifactPort::test_legacy_artifact_port_returns_artifact`
  — port declares `Artifact` + `.pdf`; binner returns an `Artifact` with
  `file_path` populated; `Collection.item_type` is `Artifact`. No
  regression vs. pre-#1079.
- `tests/blocks/app/test_appblock_bin_outputs.py::TestMissingLoaderForConcreteType::test_no_loader_for_concrete_type_raises`
  — port declares `DataFrame` + a deliberately-unregistered extension;
  binner propagates `LookupError`.
- `tests/blocks/test_app_block.py::TestAppBlockExtensionBinner::test_binner_raises_lookup_error_for_non_constructible_type`
  (REPLACES `test_binner_falls_back_to_artifact_for_non_constructible_type`)
  — same `LookupError` contract for an `Array`-typed port + unregistered
  extension; documents that the old silent-downgrade behavior is gone.

## Known TODOs left in code

None. All Phase -1 D8 acceptance criteria for #1079 are implemented in
this PR.
