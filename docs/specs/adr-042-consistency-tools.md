---
spec_id: adr-042-consistency-tools
title: "ADR-042 Code Documentation Consistency Tooling Specification"
status: Implemented
feature_branch: docs/adr-042-repository-governance-v2
created: 2026-05-18
input: "Manual owner request to specify ADR-042 custom code-documentation cross-check tools."
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
related_specs:
  - adr-042-code-quality-tools
  - adr-042-documentation-tools
  - adr-042-ai-governance-tools
scope:
  in:
    - Shared schemas and audit report envelopes for ADR-042 tools.
    - Fact generation from docs, code, workflows, maintainers, skills, and tool configs.
    - Drift classification and bidirectional coverage closure.
    - Signature fact extraction and signature drift checks for spec-defined implementation contracts.
    - Aggregate audit reporting.
  out:
    - Natural-language proof of arbitrary prose claims.
    - Automatic acceptance of implementation work without owner review.
    - Self-iterating ADR or governance-rule modification.
governs:
  modules:
    - scistudio.qa.schemas
    - scistudio.qa.audit
  contracts:
    - scistudio.qa.schemas.frontmatter.ADRFrontmatter
    - scistudio.qa.schemas.frontmatter.SpecFrontmatter
    - scistudio.qa.schemas.maintainers.MaintainerRule
    - scistudio.qa.schemas.maintainers.Maintainers
    - scistudio.qa.schemas.report.AuditReport
    - scistudio.qa.schemas.report.Finding
    - scistudio.qa.schemas.facts.FactsRegistry
    - scistudio.qa.schemas.signatures.ParameterSpec
    - scistudio.qa.schemas.signatures.ExpectedSignature
    - scistudio.qa.schemas.signatures.ExpectedModelField
    - scistudio.qa.schemas.signatures.ExpectedCliCommand
    - scistudio.qa.audit.frontmatter_lint.lint_file
    - scistudio.qa.audit.facts.generate_facts
    - scistudio.qa.audit.facts.write_facts
    - scistudio.qa.audit.facts.check_generated_facts
    - scistudio.qa.audit.griffe_facts.extract_symbol_facts
    - scistudio.qa.audit.griffe_facts.generate_registry
    - scistudio.qa.audit.signature_contracts.extract_signature_contracts
    - scistudio.qa.audit.doc_drift.classify_repo
    - scistudio.qa.audit.fact_drift.check_substitutions
    - scistudio.qa.audit.closure.check_bidirectional
    - scistudio.qa.audit.signature_drift.check_expected_signatures
    - scistudio.qa.audit.full_audit.run
    - scistudio.qa.audit.full_audit.render_markdown
    - scistudio.qa.audit.loaders.load_adr_frontmatter
    - scistudio.qa.audit.loaders.load_spec_frontmatter
    - scistudio.qa.audit.loaders.load_maintainers
  files:
    - docs/adr/ADR-042.md
    - AGENTS.md
    - MAINTAINERS
    - pyproject.toml
    - .pre-commit-config.yaml
    - .github/workflows/ci.yml
    - .github/workflows/workflow-gate.yml
    - .github/workflows/ai-review.yml
    - .claude/**
    - docs/architecture/**
    - docs/block-development/**
    - src/scistudio/qa/schemas/**
    - src/scistudio/qa/audit/loaders.py
    - src/scistudio/qa/audit/doc_drift.py
    - src/scistudio/qa/audit/fact_drift.py
    - src/scistudio/qa/audit/closure.py
    - src/scistudio/qa/audit/signature_drift.py
    - src/scistudio/qa/audit/facts.py
    - src/scistudio/qa/audit/governed.py
    - src/scistudio/qa/audit/griffe_facts.py
    - src/scistudio/qa/audit/signature_contracts.py
    - src/scistudio/qa/audit/full_audit.py
    - scripts/audit/generate_facts.py
    - docs/audit/**
    - tests/qa/test_schemas_maintainers.py
    - tests/qa/test_schemas_report.py
    - tests/qa/test_schemas_signatures.py
    - tests/qa/test_griffe_facts.py
    - tests/qa/test_generate_facts_cli.py
    - tests/qa/test_audit_doc_drift.py
    - tests/qa/test_audit_fact_drift.py
    - tests/qa/test_audit_closure.py
    - tests/qa/test_audit_signature_drift.py
    - tests/qa/test_audit_full_audit.py
tests:
  - tests/qa/test_schemas_maintainers.py
  - tests/qa/test_schemas_report.py
  - tests/qa/test_schemas_signatures.py
  - tests/qa/test_griffe_facts.py
  - tests/qa/test_generate_facts_cli.py
  - tests/qa/test_audit_doc_drift.py
  - tests/qa/test_audit_fact_drift.py
  - tests/qa/test_audit_closure.py
  - tests/qa/test_audit_signature_drift.py
  - tests/qa/test_audit_full_audit.py
acceptance_source: adr
language_source: en
---

# ADR-042 Code Documentation Consistency Tooling Specification

## 1. Change Summary

This spec defines the custom fact, drift, closure, report-envelope, and
implementation-tracking tools required by ADR-042. It comes from ADR-042 and
the owner request to split custom tooling into four implementation specs.

The consistency tools are the strictest ADR-042 category: once a consistency
checker is wired, non-`match` findings hard-fail immediately. Existing drift is
technical debt to fix or track explicitly, not debt to grandfather silently.

Issue #1240 completes the existing consistency-tool implementation surface:
`AuditFinding` accepts the ADR-042 report-field aliases while preserving
existing callers, `frontmatter_lint` now has an `AuditReport` and CLI wrapper,
signature contracts include model-field and CLI-command fact shapes, signature
drift compares those facts when implementation evidence exists, closure uses
`MAINTAINERS` ownership input, and `full_audit` preserves frontmatter lint as a
child report. ADR-042 AI governance, code scoring, test-quality, and generated
documentation tools remain separate implementation tasks.

## 2. User Scenarios & Testing

### User Story 1 - Repository facts are generated from authoritative sources (Priority: P1)

As a maintainer, I need a generated facts registry so that docs and audit tools
compare against the same repository state.

Why this priority: ADR-042 Section 5.2 defines facts as machine-verifiable
statements, and Section 6.5 requires `generate_facts` to run before generated
reference docs and consistency checks.

Independent Test: Run `generate_facts` against fixtures with ADR frontmatter,
spec frontmatter, code symbols, entry points, and CI config; verify stable fact
ids and schema validation.

Acceptance Scenarios:

1. Given an ADR frontmatter `governs.contracts` entry, when facts are generated,
   then the facts registry contains a normative contract fact.
2. Given a Python public symbol extracted by griffe, when facts are generated,
   then the registry contains a generated symbol fact.
3. Given a malformed facts registry, when schema validation runs, then
   `FactsRegistry` validation fails.

### User Story 2 - Drift classes fail consistently (Priority: P2)

As a reviewer, I need behavior drift, phantom references, and missing
documentation to be classified consistently so that remediation is clear.

Why this priority: ADR-042 Section 5.4 defines exactly four drift classes and
requires all non-`match` findings to be errors once wired.

Independent Test: Run `doc_drift` and `fact_drift` against fixtures for
`match`, `behavior-drift`, `phantom-reference`, and `missing-documentation`.

Acceptance Scenarios:

1. Given prose that references a missing symbol, when `doc_drift` runs, then it
   emits `phantom-reference`.
2. Given prose that contains a stale fact substitution, when `fact_drift` runs,
   then it emits a stale-substitution finding.
3. Given facts and prose that agree, when the check runs, then it emits `match`
   or no error finding.
4. Given an implementation ADR governs a module that no active related spec
   covers, when `doc_drift` runs, then it emits
   `doc-drift.missing-spec-governance`.
5. Given an active spec governs a module that its related ADR does not cover,
   when `doc_drift` runs, then it emits `doc-drift.missing-adr-governance`.

### User Story 3 - Ownership coverage closes in both directions (Priority: P3)

As an architect, I need every governed code path and public surface to have an
owner, and every governed claim to resolve to a real artifact.

Why this priority: ADR-042 Section 5.6 defines bidirectional closure between
governed surfaces, ADRs/specs, maintainers, public symbols, and generated docs.

Independent Test: Run `closure.check_bidirectional` against fixtures with
complete ownership, missing ownership, and phantom governed paths.

Acceptance Scenarios:

1. Given a public symbol with no ADR, spec, or maintainer owner, when closure
   runs, then it emits `missing-documentation`.
2. Given an ADR claim for a missing file, when closure runs, then it emits
   `phantom-reference`.
3. Given a future-work record with a tracked issue and machine-readable status,
   when closure runs, then it treats the claim as tracked future work.

### User Story 4 - Aggregate reports are trustworthy (Priority: P4)

As an agent manager, I need one aggregate audit envelope that preserves child
tool evidence and fails when any required consistency child fails.

Why this priority: ADR-042 Section 8.7 makes implementation order explicit, but
owner review and GitHub issues remain the source of work tracking.

Independent Test: Run `full_audit.run` with passing child reports, failing child
reports, skipped optional children, and malformed child reports.

Acceptance Scenarios:

1. Given any child consistency report with an error, when `full_audit` runs,
   then the aggregate `AuditReport` fails.
2. Given optional child checks are disabled by explicit arguments, when
   `full_audit` runs, then the aggregate report records the skipped child.
3. Given a child tool emits malformed output, when `full_audit` runs, then it
   emits an error-severity finding for that child.

### Edge Cases

- Facts generated from a dirty working tree versus CI source SHA.
- A prose reference is intentionally future work and has a valid linked issue.
- `MAINTAINERS` has overlapping ownership rules.
- A generated doc exists for a private symbol that should not be public.
- Sphinx finds a broken link that is already captured by a baseline.

## 3. Requirements

### Functional Requirements

- FR-001: `generate_facts` MUST produce `docs/facts/generated.yaml` from ADRs,
  specs, `MAINTAINERS`, workflow files, tool config files, code symbols, entry
  points, CLI definitions, OpenAPI schemas, Pydantic schemas, generated docs,
  CI/tool outputs, code-score reports, and audit reports where available.
- FR-002: Every fact MUST include `id`, `kind`, `source`, `subject`, `value`,
  `owner`, `generated_at`, `source_sha`, `confidence`, and `stability`.
- FR-003: Fact confidence MUST be one of `normative`, `generated`, or
  `observed`.
- FR-004: Fact stability MUST be one of `stable`, `experimental`,
  `deprecated`, or `unknown`.
- FR-005: `FactsRegistry` validation MUST fail malformed generated fact output.
- FR-006: `doc_drift` MUST classify documentation/fact mismatches as
  `behavior-drift`, `phantom-reference`, `missing-documentation`, or `match`.
- FR-007: `fact_drift` MUST validate prose substitutions against the current
  facts registry and fail stale or invalid substitutions.
- FR-008: `closure` MUST verify that every governed code path or public surface
  has an owning ADR/spec or maintainer entry.
- FR-009: `closure` MUST verify that every ADR/spec `governs` file or symbol
  claim resolves to a real path or symbol.
- FR-010: Future-work records MUST be explicit in `planned_governs`, using the
  same GovernedSurfaces shape as `governs`, so audit can distinguish tracked
  future work from stale or hallucinated claims.
- FR-011: `full_audit` MUST aggregate child reports into the shared
  `AuditReport` envelope and fail when any consistency child has an error.
- FR-012: `generate_facts` MUST extract expected signature facts from
  signature-level spec code blocks for functions, classes, Pydantic model
  fields, CLI commands, and exit-code tables.
- FR-013: `signature_drift` MUST compare expected signature facts against
  implementation symbols collected through griffe, import inspection, Pydantic
  `model_fields`, and CLI dry-runs.
- FR-014: `signature_drift` MUST classify missing symbols, parameter mismatch,
  return annotation mismatch, model-field mismatch, missing CLI command, and
  exit-code mismatch as `signature-drift`.
- FR-015: `signature_drift` MUST treat ADR-042 and signature-level specs as
  normative sources; implementation may satisfy or deliberately revise them, but
  may not silently diverge.
- FR-016: All consistency tools MUST have deterministic inputs and outputs and
  no hidden network dependency.
- FR-017: Once wired into pre-commit or CI, non-`match` consistency findings
  MUST hard-fail immediately.
- FR-018: `doc_drift` MUST compare active ADR/spec governed surfaces and report
  active specs that point to missing ADRs.
- FR-019: `doc_drift` MUST report ADR governed modules, contracts,
  entry-points, and files that are not covered by any active related spec once
  the ADR phase is `implementation`, `complete`, or `maintenance`. It MUST NOT
  require active spec coverage for ADRs with phase `legacy`.
- FR-020: `doc_drift` MUST report active spec governed modules, contracts,
  entry-points, and files that are not covered by their related ADRs.
- FR-021: `doc_drift` and `closure` MUST report unresolved `planned_governs` in
  planning/pre-implementation documents as informational, but MUST fail when a
  planned surface already resolves or when a non-planning document still
  declares planned surfaces.
- FR-022: `full_audit` MUST include a `developer_docs` child report by default
  for `docs/block-development/**`, validating developer-doc frontmatter, local
  links/anchors, and stale block/package contract references.

### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `Fact` | Machine-verifiable repository statement | id, kind, source, subject, value, owner, generated_at, source_sha, confidence, stability | Belongs to a `FactsRegistry` |
| `FactsRegistry` | Generated YAML snapshot of facts | facts, source SHA, generator version | Input to drift, closure, and docs generation |
| `AuditReport` | Shared report envelope | tool id, status, findings, generated_at, source SHA, summary | Output of audit and lint tools |
| `AuditFinding` | One machine-readable finding | id, severity, class, path, subject, message, remediation | Contained by `AuditReport` |
| `DriftFinding` | Consistency-specific finding | drift class, source fact, document reference, owner action | Specialized `AuditFinding` |
| `SignatureFact` | Expected implementation contract extracted from a spec | symbol or command, parameters, return annotation, model fields, exit codes, source spec | Stored as facts with kind `expected-signature`, `expected-model-field`, or `expected-cli-command` |
| `SignatureDriftFinding` | Mismatch between expected signature fact and implementation | mismatch kind, expected shape, actual shape, source spec, implementation path | Specialized `AuditFinding` with class `signature-drift` |

## 4. Implementation Plan

### 4.1 Technical Approach

Start with shared Pydantic schemas because every other ADR-042 custom tool uses
the same frontmatter, facts, maintainer, and audit report shapes. Then implement
fact extraction as a deterministic pipeline with small extractors per source
type. Drift tools should consume only normalized facts and parsed docs, not raw
tool-specific output.

`full_audit` should run the consistency suite and preserve every child report
inside a single `AuditReport` envelope. Work tracking remains outside this
tooling in GitHub issues and owner review.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/qa/schemas/frontmatter.py` | create | ADR and spec frontmatter models |
| `src/scistudio/qa/schemas/maintainers.py` | create | Maintainer ownership model |
| `src/scistudio/qa/schemas/report.py` | create | Shared audit report envelope |
| `src/scistudio/qa/schemas/facts.py` | create | Fact and facts registry models |
| `scripts/audit/generate_facts.py` | create | CLI entry point for fact generation |
| `src/scistudio/qa/audit/doc_drift.py` | create | Documentation/fact contradiction classifier |
| `src/scistudio/qa/audit/fact_drift.py` | create | Fact substitution checker |
| `src/scistudio/qa/audit/closure.py` | create | Ownership and coverage closure checker |
| `src/scistudio/qa/audit/developer_docs.py` | create | Strong checks for block/package developer guides |
| `src/scistudio/qa/audit/full_audit.py` | create | Aggregate consistency runner |
| `docs/facts/generated.yaml` | generate | Generated fact snapshot |
| `tests/qa/test_audit_*.py`, `tests/docs/test_block_development_docs.py` | create | Focused fixtures for facts, drift, closure, developer docs, and aggregate reports |

### 4.3 Implementation Sequence

1. Implement `AuditReport`, `AuditFinding`, `FactsRegistry`, `ADRFrontmatter`,
   `SpecFrontmatter`, and `Maintainers` schemas.
2. Implement facts registry validation fixtures.
3. Implement extractors for ADR/spec frontmatter, maintainers, workflow files,
   tool configs, and generated docs.
4. Add signature-level spec extraction for fenced Python signatures, model
   fields, CLI command blocks, and exit-code tables.
5. Add griffe-backed symbol extraction and entry-point extraction.
6. Implement `fact_drift` substitution validation.
7. Implement `doc_drift` drift classification fixtures.
8. Implement `closure` bidirectional coverage checks.
9. Implement `signature_drift` comparisons for expected versus actual public
   contracts.
10. Implement `full_audit` as an aggregate runner with child report preservation.
11. Wire consistency checks directly to hard-fail after owner-approved wiring.

### 4.4 Verification Plan

- Validate good and bad ADR/spec frontmatter fixtures through shared schemas.
- Validate facts registry required fields, enum values, and source SHA handling.
- Test each fact extractor with minimal fixtures and stable output ordering.
- Test each drift class with positive and negative fixtures.
- Test ADR/spec governance alignment in both directions, including Draft spec
  skipping and active specs linked to missing ADRs.
- Test closure in both directions: missing owner and phantom governed claim.
- Test signature fact extraction from signature-level specs.
- Test signature drift for missing symbol, parameter mismatch, return mismatch,
  Pydantic model-field mismatch, missing CLI, and exit-code mismatch.
- Test future-work records with valid and invalid tracking evidence.
- Test `full_audit` aggregation preserves child failures and fails on child
  errors.

### 4.5 Risks And Rollback

The main risk is false positives from shallow prose parsing. Mitigate this by
starting with explicit references, frontmatter claims, generated facts, and
structured substitutions instead of broad natural-language inference.

Rollback for noisy checks is to narrow their input scope, not to make wired
consistency findings report-only. ADR-042 explicitly says that consistency
checks hard-fail once wired.

### 4.6 Signature-Level Contracts

Implementers MUST treat the signatures in this subsection as the public
contract. Internal helpers may vary, but tests and downstream tools should
target these symbols.

Shared scalar aliases:

```text
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

AuditSeverity = Literal["info", "warning", "error"]
AuditStatus = Literal["passed", "failed", "skipped", "error"]
FactKind = Literal[
    "adr",
    "spec",
    "file",
    "symbol",
    "entry-point",
    "cli",
    "openapi",
    "schema",
    "workflow",
    "maintainer",
    "skill",
    "tool-output",
    "generated-doc",
    "expected-signature",
    "expected-model-field",
    "expected-cli-command",
]
FactConfidence = Literal["normative", "generated", "observed"]
FactStability = Literal["stable", "experimental", "deprecated", "unknown"]
DriftClass = Literal[
    "match",
    "behavior-drift",
    "phantom-reference",
    "missing-documentation",
    "signature-drift",
]
```

Shared report envelope in `scistudio.qa.schemas.report`:

```text
from datetime import datetime
from pydantic import BaseModel, Field


class AuditFinding(BaseModel):
    id: str
    tool: str
    severity: AuditSeverity
    finding_class: str
    message: str
    path: str | None = None
    line: int | None = None
    subject: str | None = None
    expected: Any | None = None
    actual: Any | None = None
    remediation: str | None = None
    evidence: Mapping[str, Any] = Field(default_factory=dict)


class AuditReport(BaseModel):
    tool: str
    status: AuditStatus
    generated_at: datetime
    source_sha: str
    findings: list[AuditFinding] = Field(default_factory=list)
    summary: Mapping[str, Any] = Field(default_factory=dict)
    child_reports: list["AuditReport"] = Field(default_factory=list)

    @property
    def blocks_merge(self) -> bool: ...

    def error_findings(self) -> list[AuditFinding]: ...
```

Fact schemas in `scistudio.qa.schemas.facts`:

```text
class Fact(BaseModel):
    id: str
    kind: FactKind
    source: str
    subject: str
    value: Any
    owner: str | None = None
    generated_at: datetime
    source_sha: str
    confidence: FactConfidence
    stability: FactStability = "unknown"


class FactsRegistry(BaseModel):
    schema_version: str = "1"
    generated_at: datetime
    source_sha: str
    facts: list[Fact]

    def by_id(self) -> dict[str, Fact]: ...

    def find(self, *, kind: FactKind | None = None, subject: str | None = None) -> list[Fact]: ...
```

Signature facts in `scistudio.qa.schemas.signatures`:

```text
SignatureKind = Literal["function", "class", "method", "pydantic-model", "cli-command"]


class ParameterSpec(BaseModel):
    name: str
    kind: Literal[
        "positional-only",
        "positional-or-keyword",
        "var-positional",
        "keyword-only",
        "var-keyword",
    ]
    annotation: str | None = None
    default: str | None = None
    required: bool = True


class ExpectedSignature(BaseModel):
    symbol: str
    kind: SignatureKind
    parameters: list[ParameterSpec] = Field(default_factory=list)
    return_annotation: str | None = None
    source_spec: str
    source_line: int


class ExpectedModelField(BaseModel):
    model_symbol: str
    field_name: str
    annotation: str
    default: str | None = None
    required: bool = True
    source_spec: str
    source_line: int


class ExpectedCliCommand(BaseModel):
    command: list[str]
    module: str | None = None
    expected_exit_codes: dict[int, str] = Field(default_factory=dict)
    source_spec: str
    source_line: int
```

Frontmatter and ownership schemas:

```text
from datetime import date
from typing import Any, Literal, Mapping
from pydantic import BaseModel, Field


class GovernedSurfaces(BaseModel):
    modules: list[str]
    contracts: list[str]
    entry_points: list[str] = Field(default_factory=list)
    files: list[str]
    excludes: list[str] = Field(default_factory=list)


class ADRFrontmatter(BaseModel):
    adr: int
    title: str
    status: Literal["Proposed", "Accepted", "Deprecated", "Superseded"]
    date_created: date
    date_accepted: date | None
    date_superseded: date | None
    supersedes: list[int]
    superseded_by: int | None
    related: list[int]
    closes_issues: list[int]
    tracking_issue: int | None
    is_code_implementation: bool
    governs: GovernedSurfaces
    planned_governs: GovernedSurfaces = Field(default_factory=GovernedSurfaces)
    tests: list[str]
    agent_editable: bool | Literal["owner-only"]
    assisted_by: list[str]
    phase: Literal["planning", "implementation", "complete", "maintenance", "legacy"]
    tags: list[str]
    owner: str
    co_authors: list[str]
    language_source: str = "en"
    translations: list[Mapping[str, Any]]


class SpecScope(BaseModel):
    in_: list[str] = Field(alias="in")
    out: list[str]


class SpecFrontmatter(BaseModel):
    spec_id: str
    title: str
    status: Literal["Draft", "Clarifying", "Planned", "Implemented", "Deprecated"]
    feature_branch: str
    created: date
    input: str
    owners: list[str]
    related_adrs: list[int]
    related_specs: list[str]
    scope: SpecScope
    governs: GovernedSurfaces
    planned_governs: GovernedSurfaces = Field(default_factory=GovernedSurfaces)
    tests: list[str]
    acceptance_source: Literal["speckit", "issue", "adr", "manual"]
    language_source: str = "en"


class MaintainerRule(BaseModel):
    pattern: str
    owners: list[str]
    required_reviewers: int = 1
    protected: bool = False


class Maintainers(BaseModel):
    schema_version: str = "1"
    rules: list[MaintainerRule]
```

Fact generation and schema loading:

```python
def load_adr_frontmatter(path: Path) -> ADRFrontmatter | ADRAddendumFrontmatter: ...

def load_spec_frontmatter(path: Path) -> SpecFrontmatter: ...

def load_maintainers(path: Path) -> Maintainers: ...

def load_facts(path: Path) -> FactsRegistry: ...

def generate_facts(
    repo_root: Path,
    *,
    source_sha: str | None = None,
    include_observed: bool = False,
    include_signature_contracts: bool = True,
    package: str = "scistudio",
    generated_at: datetime = DEFAULT_GENERATED_AT,
) -> FactsRegistry: ...

def write_facts(registry: FactsRegistry, path: Path) -> None: ...

def check_generated_facts(
    repo_root: Path,
    *,
    facts_path: Path = Path("docs/facts/generated.yaml"),
    update: bool = False,
    package: str = "scistudio",
    source_sha: str | None = None,
    generated_at: datetime = DEFAULT_GENERATED_AT,
) -> AuditReport: ...
```

Drift, closure, and aggregate audit:

```python
def check_substitutions(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    docs: Sequence[Path] | None = None,
) -> AuditReport: ...

def classify_repo(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    docs: Sequence[Path] | None = None,
) -> AuditReport: ...

def check_bidirectional(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    maintainers: Maintainers | None = None,
) -> AuditReport: ...

def extract_signature_contracts(
    spec_paths: Sequence[Path],
    *,
    repo_root: Path,
    source_sha: str,
) -> list[Fact]: ...

def check_expected_signatures(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    check_cli: bool = True,
    cli_timeout_seconds: int = 10,
) -> AuditReport: ...

def run(
    repo_root: Path,
    *,
    facts_path: Path = Path("docs/facts/generated.yaml"),
    check_stale: bool = True,
    include_frontmatter_lint: bool = True,
    include_doc_drift: bool = True,
    include_developer_docs: bool = True,
    include_fact_drift: bool = True,
    include_closure: bool = True,
    include_signature_drift: bool = True,
    include_architecture_drift: bool = True,
    include_vulture: bool = True,
    include_semantic_dup: bool = False,
    semantic_dup_model: str = "BAAI/bge-base-en-v1.5",
) -> AuditReport: ...
```

Required CLI behavior:

```text
python scripts/audit/generate_facts.py --check
python scripts/audit/generate_facts.py --write
python -m scistudio.qa.audit.fact_drift --facts docs/facts/generated.yaml --format json
python -m scistudio.qa.audit.doc_drift --facts docs/facts/generated.yaml --format json
python -m scistudio.qa.audit.closure --facts docs/facts/generated.yaml --format json
python -m scistudio.qa.audit.signature_drift --facts docs/facts/generated.yaml --format json
python -m scistudio.qa.audit.full_audit --format json
```

CLI exit codes are uniform across ADR-042 audit tools:

| Exit code | Meaning |
|---:|---|
| 0 | Valid input and no error-severity findings |
| 1 | Valid input with one or more error-severity findings |
| 2 | Usage error, invalid arguments, unreadable input, or unexpected tool error |

## 5. Success Criteria

### Measurable Outcomes

- SC-001: Facts generated from the same source SHA are stable across repeated
  runs.
- SC-002: Malformed facts and audit reports fail schema validation.
- SC-003: Fixtures cover `match`, `behavior-drift`, `phantom-reference`, and
  `missing-documentation`.
- SC-004: Closure detects both missing ownership and phantom governed claims.
- SC-005: `full_audit` returns one aggregate report and fails when any child
  consistency report fails.
- SC-006: `signature_drift` detects missing symbols, parameter mismatches,
  return mismatches, Pydantic field mismatches, missing CLI commands, and
  exit-code mismatches from signature-level spec facts.
- SC-007: `doc_drift` detects active ADR/spec governed-surface mismatches in
  both directions and ignores Draft specs for current implementation closure.
- SC-008: `planned_governs` unresolved future surfaces are non-blocking in
  planning/pre-implementation documents, while resolved planned surfaces fail
  until the document state and `governs` metadata are advanced.
- SC-009: `full_audit` includes `developer_docs` by default and fails stale or
  broken `docs/block-development/**` developer guide content.

## 6. Assumptions

- Initial drift detection will focus on structured claims and explicit
  references before attempting broader prose analysis.
- Sphinx and griffe provide generated inputs, but SciStudio policy decisions stay
  in custom consistency tools.
- Future-work records must be issue-linked structured TODOs or explicit
  owner-approved scope exclusions that the checker can read.
- The owner will decide when each consistency checker is wired; once wired, it
  is an immediate hard-fail checker.

## 7. Appendix

`legacy` is the ADR phase for historical decisions being preserved or
normalized after their original implementation window. `doc_drift` still checks
their governed symbols and files, but it does not require an active related
implementation spec.
