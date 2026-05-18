# Implementation record: #1132

Phase 1A-c of the ADR-042/043/044 cascade — final 1A sub-wave. Ships
five additional pydantic schema modules covering ADR-043 §2.2 / §3 /
§4.2 / §6 and ADR-044 §5. Builds on [#1128](https://github.com/zjzcpj/SciEasy/pull/1128)
(1A-a) and [#1131](https://github.com/zjzcpj/SciEasy/pull/1131) (1A-b)
on the `track/adr-042/1a-schemas` tracking branch.

Implementation SHA: `2d95fbd`.

## Files modified

- `src/scieasy/qa/schemas/tracker.py` — NEW. ADR-043 §2.2 lines 268-313
  verbatim. Five symbols: `SectionStatus(StrEnum)` (4 lifecycle values),
  `RequiredArtifacts`, `VerificationCheck`, `TrackerEntry` (4 optional
  fields including `verified_at: datetime | None`), and
  `ImplementationTracker` envelope with `schema_version: int = 1` and
  `adr: ADRRef`. Imports `ADRRef`/`RepoRelativePath`/
  `FunctionOrClassPath` from `._common` directly (see deviation §1
  below).
- `src/scieasy/qa/schemas/governance.py` — NEW. Single consolidated
  module covering ADR-043 §3.2 (lines 532-549), §3.4.3 (lines 696-720),
  §3.6.1 (lines 791-814), §3.6.3 (lines 838-858), and §6.4.1 (lines
  1643-1675). Nine schemas total:
  - §3.2: `HoneypotRuleEntry`, `GovernancePaths` (with
    `version: Literal[1]` and `governance_paths: list[PathGlob] =
    Field(min_length=1)`).
  - §3.4.3: `LoosenedAxis` (axis unconstrained `str` per X1),
    `MonotonicCheckResult`.
  - §3.6.1: `GovernanceChangeLogEntry` (with three `Literal[...]`
    unions on `author_tier` and `monotonic_check_result`).
  - §3.6.3: `HoneypotRule`, `HoneypotViolation` (action_taken
    Literal of three values).
  - §6.4.1: `WeakeningKind(StrEnum)` (14 categories per ADR),
    `WeakeningFinding`.
- `src/scieasy/qa/schemas/test_quality.py` — NEW. ADR-043 §4.2 lines
  928-981 verbatim. Four symbols: `AntiPattern(StrEnum)` (10
  categories), `AntiPatternFinding`, `MutationScoreResult` (with
  `score: float = Field(ge=0.0, le=1.0)`), `TestQualityReport`. Added
  `__test__ = False` class attribute on `TestQualityReport` to suppress
  pytest's auto-collection of any class named `Test*` (deviation §2
  below).
- `src/scieasy/qa/schemas/classification.py` — NEW. ADR-043 §6.1
  (lines 1427-1453), §6.2 (lines 1489-1505), §6.3 (lines 1549-1568)
  verbatim. Eight symbols: `DataClass` / `DataClassificationEntry` /
  `DataClassification`; `RubricCriterion` / `AssessmentRubric`;
  `BoundaryLevel` / `PathBoundaryEntry` / `PathBoundary`. Dropped
  vestigial `Literal` import per X3 / Q1A.9 (recorded below).
- `src/scieasy/qa/docs/__init__.py` — NEW. Package marker. Re-exports
  every public symbol from `.schemas` and lists them in `__all__`.
- `src/scieasy/qa/docs/schemas.py` — NEW. ADR-044 §5.1-§5.5 lines
  394-556 verbatim, with the X3 / Q1A.10 vestigial-imports cleanup
  applied (`RepoRelativePath`, `AssistedByLine`, `LocaleCode`,
  `AgentEditable` dropped — none are used in the four schemas).
  Eight symbols: `Generation(StrEnum)`, `DocAudience(StrEnum)`,
  `DocCategory(StrEnum)`, `AutoGenSource`, `WorkflowDocFrontmatter`
  (with the `_exception_paired_with_issue` model_validator),
  `UserDocFrontmatter` (with the `_auto_requires_source`
  model_validator), `ProdAgentDocFrontmatter`, `DocGuideFrontmatter`.
- `src/scieasy/qa/schemas/__init__.py` — EXTEND. Adds re-exports for
  the 5 new tracker symbols, 9 new governance symbols, 4 new
  test_quality symbols, and 8 new classification symbols, with
  alphabetised `__all__`. Preserves all 1A-a + 1A-b re-exports and
  the `ADRFrontmatter.model_rebuild()` /
  `SpecFrontmatter.model_rebuild()` calls.
- `tests/qa/test_schemas_tracker.py` — NEW. 11 tests covering enum
  round-trip parametrisation, ADR-text exactness of the four
  `SectionStatus` values, `RequiredArtifacts` defaults,
  `VerificationCheck` extras-forbid, `TrackerEntry` optional fields,
  `ImplementationTracker` round-trip, and `ADRRef` range enforcement
  (ge=1, le=9999).
- `tests/qa/test_schemas_governance.py` — NEW. 27 tests covering
  every model in the consolidated governance module: GovernancePaths
  min_length-1, Literal[1] version rejection, LoosenedAxis
  unconstrained axis confirmation (manager-default X1 explicit
  verification), MonotonicCheckResult round-trip,
  GovernanceChangeLogEntry author_tier + monotonic_check_result
  Literal coverage, HoneypotRule, HoneypotViolation, and the 14
  WeakeningKind values exactness check + WeakeningFinding.
- `tests/qa/test_schemas_test_quality.py` — NEW. 13 tests covering
  the 10 AntiPattern enum values, severity Literal, score boundary
  (ge=0.0, le=1.0) verification, schema-only-no-cross-field-validator
  confirmation (deliberately constructs an inconsistent record per
  Q1A.8 manager default).
- `tests/qa/test_schemas_classification.py` — NEW. 17 tests
  covering the 7 DataClass values, 3 BoundaryLevel values, every
  model's round-trip and extras-forbid, and the three
  AGENTS.md-required sections (DataClassification, AssessmentRubric,
  PathBoundary) as composite shapes.
- `tests/qa/test_schemas_docs.py` — NEW. 24 tests covering: every
  Generation / DocAudience / DocCategory enum value; AutoGenSource
  parametrised across all 7 kind Literals; WorkflowDocFrontmatter
  `_exception_paired_with_issue` validator (positive + negative);
  UserDocFrontmatter `_auto_requires_source` validator (AUTO and
  HYBRID both rejected without source); ProdAgentDocFrontmatter
  governs_adr=40 Literal + related_addenda A1-A4 Literal;
  DocGuideFrontmatter required `applies_to_categories`; and the
  `Translation` re-export-path verification per Q1A.10 Q7.

## Deviations from ADR text

1. **Import path for `ADRRef` / `GitHandle` / `IssueRef`**
   (`src/scieasy/qa/schemas/tracker.py` and
   `src/scieasy/qa/docs/schemas.py`):

   ADR-043 §2.2 and ADR-044 §5.1 import these from
   `scieasy.qa.schemas.frontmatter`. The 1A-a-shipped `frontmatter.py`
   imports them from `._common` without explicit `as` re-export
   markers, so `mypy --strict` raises
   `[attr-defined]` on
   `from scieasy.qa.schemas.frontmatter import ADRRef, GitHandle, IssueRef`.

   Since `frontmatter.py` is in 1A-a's owned-files set (frozen for
   this sub-wave), the fix is to import from `_common` directly —
   functionally equivalent. `Translation` is genuinely defined in
   `frontmatter.py` (not re-imported), so that import path works as
   the ADR specifies.

   Recommended errata: add explicit `as X` re-exports for `ADRRef`,
   `GitHandle`, `IssueRef`, `RepoRelativePath` in 1A-a's
   `frontmatter.py` (one-line trivial change), at which point future
   modules can use the ADR-stated import path.

2. **`__test__ = False` on `TestQualityReport`**
   (`src/scieasy/qa/schemas/test_quality.py`):

   pytest auto-collects any class named `Test*` as a test container,
   producing a `PytestCollectionWarning` ("cannot collect test class
   'TestQualityReport' because it has a __init__ constructor") on
   every test run. Added `__test__ = False` to suppress the
   false-positive collection. Standard pytest pattern; the class
   remains a regular pydantic model.

3. **`audit fix F6` block-shadow imports consolidated**
   (`src/scieasy/qa/schemas/governance.py`):

   ADR-043 §3.2 / §3.4.3 / §3.6.1 / §3.6.3 / §6.4.1 each re-state
   `from … import …` blocks inside each fenced code sample because
   pytest-examples treats each fenced block as independent. The real
   module collapses these to one module-top import block.

## Manager defaults applied

| ID | Applied | Note |
|---|---|---|
| **X1** | `LoosenedAxis.axis: str` (unconstrained) | semantic enforcement in TC-1E.3 tool layer |
| **X3 / Q1A.9** | dropped vestigial `Literal` / `Field` imports | recorded above |
| **Q1A.6** | `tests/qa/test_schemas_tracker.py` ships un-listed in ADR-043 frontmatter | flagged in PR body as §27.4 errata candidate |
| **Q1A.7** | `HoneypotRuleEntry` ships as nested supporting model NOT in ADR-043 `governs.contracts` | flagged in PR body as §27.4 errata candidate |
| **Q1A.8** | `TestQualityReport` purely structural — no `mutations_total == killed + survived + timeout` validator | tested by `test_test_quality_report_purely_structural_no_cross_field_validator` |
| **Q7.2** | `tests/qa/test_schemas_governance.py` ships un-listed in ADR-043 frontmatter | flagged in PR body as §27.4 errata candidate |
| **Q1A.10 Q7** | `Translation` imported from `frontmatter.py`; scalars from `_common` | deviation §1 above |
| **F6** | governance.py collapses fenced-block imports to one module-top block | deviation §3 above |

## Local CI run

- `ruff format --check src/scieasy/qa/ tests/qa/`: ✓ 28 files already formatted.
- `ruff check src/scieasy/qa/ tests/qa/`: ✓ All checks passed.
- `mypy --strict src/scieasy/qa/schemas/{tracker,governance,test_quality,classification,__init__}.py src/scieasy/qa/docs/`: ✓ Success, 7 source files.
- `pytest -q --timeout=60 tests/qa/ --no-cov`: ✓ 341 tests passed.
- `python scripts/audit/temp_review.py`: ✓ 0 findings, 16 files checked.

## Coverage

- `src/scieasy/qa/schemas/tracker.py`: 100% (35/35 stmts).
- `src/scieasy/qa/schemas/governance.py`: 100% (83/83 stmts).
- `src/scieasy/qa/schemas/test_quality.py`: 100% (44/44 stmts).
- `src/scieasy/qa/schemas/classification.py`: 100% (42/42 stmts).
- `src/scieasy/qa/docs/schemas.py`: 100% (93/93 stmts).

Combined ≥ 95% target for new code per ADR-042 §21.6: met (100% across
all five new modules).

## Tests added

- `test_schemas_tracker.py` — 11 tests, SectionStatus / RequiredArtifacts
  / VerificationCheck / TrackerEntry / ImplementationTracker.
- `test_schemas_governance.py` — 27 tests, 9 schemas covered including
  Literal-union coverage on author_tier + monotonic_check_result +
  action_taken, exactness of the 14 WeakeningKind values.
- `test_schemas_test_quality.py` — 13 tests, AntiPattern (10 values
  exactness), score boundary, AntiPatternFinding,
  MutationScoreResult, TestQualityReport (incl. explicit
  purely-structural confirmation).
- `test_schemas_classification.py` — 17 tests, three required
  AGENTS.md sections.
- `test_schemas_docs.py` — 24 tests, 4 doc-category frontmatters
  including both `model_validator`s + Translation import path.

Total: 92 new tests across 5 new files; full `tests/qa/` suite passes
(341 tests).

## Follow-ups (not in this PR)

- **Errata for ADR-043 frontmatter**: add `tests/qa/test_schemas_tracker.py`
  and `tests/qa/test_schemas_governance.py` to `tests:`; add
  `HoneypotRuleEntry` to `governs.contracts`. Track via the §27.4
  errata mechanism.
- **Errata for 1A-a `frontmatter.py`**: add explicit `as X` re-exports
  for `ADRRef`, `GitHandle`, `IssueRef`, `RepoRelativePath` so that
  future modules can use the ADR-stated import path.
- **Semantic LoosenedAxis enforcement**: TC-1E.3 monotonic_check tool
  layer (Phase 1E).
- **Cross-field MutationScoreResult validator** (`mutations_total ==
  killed + survived + timeout`): tool-layer concern per Q1A.8 manager
  default.
