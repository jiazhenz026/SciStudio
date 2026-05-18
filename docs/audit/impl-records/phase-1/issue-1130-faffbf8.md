# Implementation record: #1130

Phase 1A-b of the ADR-042/043/044 cascade — schemas + workflow-gate
shapes wave. Builds directly on the foundation shipped in
[#1128](https://github.com/zjzcpj/SciEasy/pull/1128) (1A-a) on the
`track/adr-042/1a-schemas` tracking branch.

## Files modified

- `src/scieasy/qa/schemas/facts.py` — NEW. ADR-042 §7.5.2 (lines
  1142-1196) verbatim. Five sub-models (`WorkflowFacts`, `ToolFacts`,
  `ADRFacts`, `MaintainersFacts`, `SkillFacts`) plus the
  `FactsRegistry` envelope with `schema_version: Literal[1]`,
  `generated_at: datetime`, `source_shas: dict[str, str]`, and one
  field per sub-model. Every model carries `model_config =
  ConfigDict(extra="forbid")`. Field constraints (`ge=1` for
  `WorkflowFacts.stage_count`, `ge=0, le=100` for
  `ToolFacts.min_coverage_percent`) are preserved verbatim.
- `src/scieasy/qa/schemas/identity.py` — NEW. ADR-042 §25.3 (lines
  2957-3010) verbatim, with one deviation noted below:
  - `HumanTier(StrEnum)` with the two `contributor`/`maintainer` values
    of ADR-042 §25.4.
  - `SigningKey = Annotated[str, Field(pattern=...)]` enforcing the
    `^(ed25519|rsa|ecdsa|gpg):[A-Za-z0-9+/=._-]+$` shape.
  - `HumanIdentity` with `github: GitHandle`, `email: EmailStr`,
    `tier: HumanTier`, `signing_key: SigningKey | None`,
    `joined: date`, `notes: str | None`, plus the
    `requires_signing_key` property.
  - `IdentityRegistry` with `version: Literal[1]`,
    `humans: list[HumanIdentity]`, plus the two lookup methods
    (`lookup_by_email`, `lookup_by_github`).
- `src/scieasy/qa/workflow/__init__.py` — NEW. Package marker (no
  re-exports yet — the public surface is `scieasy.qa.workflow.gate`).
- `src/scieasy/qa/workflow/gate.py` — NEW. ADR-042 §19.5 (lines
  2317-2366) verbatim with the manager-default `@runtime_checkable`
  decorator applied to `Validator` (SUMMARY X2). Contains
  `StageContext`, `ValidationResult`, the `Validator` Protocol, and
  the `StageDefinition` dataclass.
- `src/scieasy/qa/schemas/__init__.py` — EXTEND. Adds re-exports for
  the 6 facts symbols and 4 identity symbols; updates `__all__`
  alphabetically; preserves the 1A-a `ADRFrontmatter.model_rebuild()`
  / `SpecFrontmatter.model_rebuild()` calls. No regressions to 1A-a
  re-exports.
- `tests/qa/test_schemas_facts.py` — NEW. 27 tests including
  parametrised boundary checks for `ge`/`le` field constraints,
  `Literal[1]` schema-version rejection on `[0, 2, 99]`,
  `extra="forbid"` rejection on every sub-model, round-trip via
  `model_dump_json` / `model_validate_json`, and JSON Schema export
  verifying `$defs` carries every sub-model.
- `tests/qa/test_schemas_identity.py` — NEW. 29 tests covering
  `HumanTier` enum, `SigningKey` regex (5 accept + 7 reject cases),
  the `requires_signing_key` property on both tiers, both lookup
  methods (hit + miss), `version: Literal[1]` rejection, `EmailStr`
  validation, `str_strip_whitespace` on `notes`, and the deferred
  semantic check (Q1A.5: schema accepts MAINTAINER without
  signing_key; enforcement is 1C.3's job).
- `tests/qa/test_schemas_workflow_gate.py` — NEW. 16 tests covering
  `StageContext` fields (including the `declared_data` arbitrary inner
  shape), `ValidationResult` `Literal` status + default `blocking`,
  the `@runtime_checkable` Protocol behavior (one accept + two reject
  cases + actually-callable check), and `StageDefinition` dataclass
  semantics (including the critical "default_factory is per-instance"
  shared-mutable-default regression test).

## Implementation rationale

The three TCs all live in `_common`/`frontmatter` downstream territory
and share no public state. They are dispatched together as the second
wave of 1A because each one is small (≤100 LOC of pydantic body), each
needs its own dedicated test file per the SUMMARY's convention
(`tests/qa/test_schemas_<area>.py`), and they have no inter-module
dependency that would force a sequential merge.

The dispatch boundary between 1A-b and 1A-c (`tracker`, `governance`,
`test_quality`, `classification`, `doc` schemas) is purely "what fits
under 100 LOC of pydantic body per module" — there is no semantic
coupling either side.

## Deviations from the original investigation spec

1. **Q1A.5 (HumanIdentity model_validator)**: manager default applied
   — no `model_validator` enforcing MAINTAINER → signing_key. The
   `requires_signing_key` property reports the schema-level tier
   discrimination; file-level enforcement is 1C.3's responsibility.
   `test_human_identity_schema_only_allows_maintainer_without_key`
   asserts the deferral is honest.
2. **X2 (Validator runtime_checkable)**: manager default applied. The
   `@runtime_checkable` decorator is the only behavioural addition not
   present in the ADR-042 §19.5 verbatim. Without it the stage loader
   cannot `isinstance`-check registered Validator implementations
   against the protocol — a hard requirement for the dynamic
   validator-registration pattern in §19.5's prose.
3. **X3 (vestigial imports)**: ADR-042 §7.5.2 / §25.3 / §19.5 verbatim
   imports were already lean — no dead `Literal` / `Field` symbols to
   trim. The deviation policy was applied successfully (no F401
   violations); recording the policy compliance here so the cycle
   auditor can see it was checked.
4. **GitHandle import source**: ADR-042 §25.3 line 2963 reads
   `from .frontmatter import GitHandle`, but the authoritative
   declaration site is `._common` (post-audit-fix-C1). `frontmatter.py`
   imports `GitHandle` from `._common` without explicit re-export, so
   mypy --strict's `no_implicit_reexport` policy rejected
   `from .frontmatter import GitHandle`. Changed the import to
   `from ._common import GitHandle` (semantically identical;
   `GitHandle` is the same `Annotated` alias in both places). This is
   the smallest correctness-preserving deviation; it has no runtime
   effect. Recorded in commit message + this file.

## Tests added

- 27 tests in `test_schemas_facts.py`
- 29 tests in `test_schemas_identity.py`
- 16 tests in `test_schemas_workflow_gate.py`

Total: 72 new tests. All three new modules reach **100% line coverage**:

```
src/scieasy/qa/schemas/facts.py    40 statements, 0 missed, 100%
src/scieasy/qa/schemas/identity.py 35 statements, 0 missed, 100%
src/scieasy/qa/workflow/gate.py    31 statements, 0 missed, 100%
```

## Known TODOs left in code

None. The `Q1A.5` deferral (MAINTAINER → signing_key enforcement) is
intentionally NOT inlined as a `TODO(#...)` because the enforcement
location is `src/scieasy/qa/identity/registry.py` (TC-1C.3), which
does not yet exist. The deferral is tracked by the cascade umbrella
issue #1113 and recorded in this impl record. When TC-1C.3 lands, its
implementation will be the natural place to verify the deferred check
becomes a hard error.

## Local CI before push

- `ruff format --check` on changed files: passing (8 files already
  formatted).
- `ruff check` on changed files: passing (all checks passed).
- `mypy --strict src/scieasy/qa/`: passing (no issues in 10 source
  files).
- `pytest -q --timeout=60 tests/qa/test_schemas_{facts,identity,workflow_gate}.py`:
  passing (85 passed).
- `python scripts/audit/temp_review.py`: passing (0 findings, 10 files
  checked).
- New-code coverage: 100% on facts.py / identity.py / workflow/gate.py.
