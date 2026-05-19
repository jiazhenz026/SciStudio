---
spec_id: adr-042-documentation-tools
title: "ADR-042 Documentation Tooling Specification"
status: Draft
feature_branch: docs/adr-042-repository-governance-v2
created: 2026-05-18
input: "Manual owner request to specify ADR-042 custom documentation normalization and generation tools."
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
related_specs:
  - adr-042-code-quality-tools
  - adr-042-consistency-tools
  - adr-042-ai-governance-tools
scope:
  in:
    - Documentation frontmatter and first-section structure validation.
    - Short-form documentation limits for hand-authored docs.
    - Generated documentation freshness and hand-edit protection.
    - Skill pointer synchronization with canonical workflow docs.
    - SciEasy-specific documentation generators listed by ADR-042.
  out:
    - Reimplementation of Sphinx, griffe, markdownlint, codespell, or linkcheck.
    - Translation workflow implementation beyond generated-marker enforcement.
    - Full content rewrite of existing historical docs.
governs:
  modules:
    - scieasy.qa.docs
    - scieasy.qa.audit
  contracts:
    - scieasy.qa.audit.frontmatter_lint.lint_file
    - scieasy.qa.audit.doc_length_lint.check
    - scieasy.qa.audit.auto_generated_lint.check
    - scieasy.qa.audit.skill_pointer_sync.check
    - scieasy.qa.docs.llms_txt.generate
    - scieasy.qa.docs.entry_point_catalog.generate
    - scieasy.qa.docs.cli_reference.generate
    - scieasy.qa.docs.openapi_reference.generate
    - scieasy.qa.docs.schema_reference.generate
  files:
    - src/scieasy/qa/docs/**
    - src/scieasy/qa/audit/frontmatter_lint.py
    - src/scieasy/qa/audit/doc_length_lint.py
    - src/scieasy/qa/audit/auto_generated_lint.py
    - src/scieasy/qa/audit/skill_pointer_sync.py
    - docs/specs/**
    - docs/adr/**
    - docs/user/reference/**
    - docs/user/llms.txt
    - docs/contributing/workflows/**
    - docs/doc-guide/**
    - docs/sphinx/conf.py
tests:
  - tests/qa/test_audit_frontmatter_lint.py
  - tests/qa/test_doc_length_lint.py
  - tests/qa/test_auto_generated_lint.py
  - tests/qa/test_skill_pointer_sync.py
  - tests/qa/test_docs_generators.py
acceptance_source: adr
language_source: en
---

# ADR-042 Documentation Tooling Specification

## 1. Change Summary

This spec defines the custom documentation normalization and generated-reference
tools required by ADR-042. It covers `frontmatter_lint`, `doc_length_lint`,
`auto_generated_lint`, `skill_pointer_sync`, and SciEasy-specific generators
for `llms.txt`, entry points, CLI, OpenAPI, schemas, blocks, and runners.

The spec comes from ADR-042 and the owner request to split custom tooling into
four implementation specs. Sphinx, griffe, markdownlint, codespell, and
linkcheck remain common tools. The custom tools only encode SciEasy-specific
policy that those tools cannot decide by themselves.

## 2. User Scenarios & Testing

### User Story 1 - Governed documents validate their metadata and first section (Priority: P1)

As a maintainer, I need ADRs and specs to have valid frontmatter and the
required first H2 so that automated governance can classify each document.

Why this priority: ADR-042 Section 3 makes frontmatter, ADR summary structure,
and spec `## 1. Change Summary` machine-checkable prerequisites for later
drift detection.

Independent Test: Run `frontmatter_lint.lint_file` on valid and invalid ADR and
spec fixtures.

Acceptance Scenarios:

1. Given an ADR without `## 1. Decision Summary`, when `frontmatter_lint` runs,
   then it emits a structure finding.
2. Given a spec without `## 1. Change Summary` as the first H2, when
   `frontmatter_lint` runs, then it emits a structure finding.
3. Given a valid ADR-042-style spec, when `frontmatter_lint` runs, then it
   emits no findings.

### User Story 2 - Hand-authored docs stay concise (Priority: P2)

As a contributor, I need docs that should be short to fail or report clearly
when they exceed ADR-042 length limits.

Why this priority: ADR-042 Section 3.6 sets default source-line and prose-word
limits for hand-authored contributor, user, production-agent, and doc-guide
documents.

Independent Test: Run `doc_length_lint.check` against over-limit, exempt, and
valid fixture documents.

Acceptance Scenarios:

1. Given a hand-authored guide over 120 non-empty source lines, when
   `doc_length_lint` runs after rollout, then it emits an over-line finding.
2. Given a generated reference doc, when `doc_length_lint` runs, then it is
   exempt from the hand-authored length rule.
3. Given a concise contributor workflow doc, when `doc_length_lint` runs, then
   it emits no findings.

### User Story 3 - Generated documentation is reproducible and protected (Priority: P3)

As a maintainer, I need generated reference docs to match generator output so
that exact API, CLI, schema, and entry-point references do not drift.

Why this priority: ADR-042 Section 6 requires generated references and
`auto_generated_lint` hard-fail semantics once wired.

Independent Test: Run generator fixtures and `auto_generated_lint.check` on
matching, stale, and hand-edited generated outputs.

Acceptance Scenarios:

1. Given a generated file that differs from generator output, when
   `auto_generated_lint` runs, then it emits a stale generated-doc finding.
2. Given a generated file manually edited after generation, when
   `auto_generated_lint` runs, then it emits a hand-edit finding.
3. Given generated output that matches the committed file, when the lint runs,
   then it emits no findings.

### User Story 4 - AI skills point to canonical workflow docs (Priority: P4)

As an agent manager, I need short runtime skill files to point to canonical
workflow docs instead of duplicating policy.

Why this priority: ADR-042 Section 7.4 requires skills to be pointers and
workflow helpers, while canonical procedures live under
`docs/contributing/workflows/`.

Independent Test: Run `skill_pointer_sync.check` on runtime config fixtures
with valid pointers, missing pointers, and stale targets.

Acceptance Scenarios:

1. Given a persona skill that omits its canonical workflow pointer, when
   `skill_pointer_sync` runs, then it emits a missing-pointer finding.
2. Given a pointer to a missing workflow doc, when the check runs, then it emits
   a stale-pointer finding.
3. Given equivalent pointers across supported runtime roots, when the check
   runs, then it emits no findings.

### Edge Cases

- YAML frontmatter is syntactically valid but violates ADR-042 field rules.
- A document has frontmatter fences inside a code block.
- A generated doc is renamed without updating the manifest.
- A generated output depends on optional runtime plugins that are not installed.
- A runtime config root exists for one AI runtime but not another.

## 3. Requirements

### Functional Requirements

- FR-001: `frontmatter_lint` MUST validate ADR frontmatter against the
  ADR-042 ADR schema.
- FR-002: `frontmatter_lint` MUST validate spec frontmatter against the
  ADR-042 spec schema.
- FR-003: `frontmatter_lint` MUST verify ADR first-section structure, including
  `## 1. Decision Summary` and `### 1.1 Problems Addressed` when applicable.
- FR-004: `frontmatter_lint` MUST verify spec first-section structure, requiring
  `## 1. Change Summary` as the first H2 after the H1.
- FR-005: `frontmatter_lint` MUST verify that ADR `Detailed section` references
  point to later sections in the same ADR.
- FR-006: `doc_length_lint` MUST enforce the ADR-042 default limits of 120
  non-empty source lines and 600 prose words for hand-authored docs in scoped
  directories.
- FR-007: `doc_length_lint` MUST exempt generated reference docs.
- FR-008: `auto_generated_lint` MUST detect stale generated docs by comparing
  committed files with generator output.
- FR-009: `auto_generated_lint` MUST detect hand edits to generated docs using
  generated markers, manifests, source hashes, or equivalent metadata.
- FR-010: Custom generators MUST produce deterministic output for `llms.txt`,
  entry-point catalogs, CLI reference, OpenAPI reference, schema reference,
  block catalogs, and runner catalogs.
- FR-011: Documentation generation MUST run in the ADR-042 order: facts,
  generated references, `llms.txt`, Sphinx, generated-doc lint, then consistency
  checks.
- FR-012: `skill_pointer_sync` MUST verify that runtime skills point to
  canonical workflow docs and do not duplicate or override root policy.
- FR-013: Documentation tool findings MUST use the shared `AuditReport` shape
  defined by the consistency tooling spec.
- FR-014: Documentation tools MUST avoid hidden network dependencies except
  explicit Sphinx linkcheck execution.

### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `DocumentLintFinding` | Frontmatter, structure, length, or generated-doc finding | file, rule id, severity, message, location | Emitted by documentation lint tools |
| `GeneratedDocManifest` | Generated output inventory | target path, generator id, source inputs, source SHA, generated marker | Used by `auto_generated_lint` |
| `GeneratorResult` | Result of one documentation generator | target path, content hash, inputs, warnings | Feeds Sphinx and generated-doc lint |
| `SkillPointer` | Runtime skill to workflow-doc link | runtime root, persona, skill path, workflow target | Checked by `skill_pointer_sync` |
| `DocLengthProfile` | Length policy for a document class | path pattern, line limit, word limit, exemption rule | Used by `doc_length_lint` |

## 4. Implementation Plan

### 4.1 Technical Approach

Implement documentation tooling as small validators and deterministic generators.
Markdown parsing should be structural enough to ignore YAML fences and code
blocks while reading headings. Frontmatter validation should use the shared
Pydantic schemas rather than ad hoc dictionary checks.

Generated docs should use a manifest-driven approach: each generated target
records the generator id, source inputs, source SHA or content hash, and an
explicit generated marker. `auto_generated_lint` compares committed files to
fresh generator output and reports stale or manually edited files.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scieasy/qa/audit/frontmatter_lint.py` | create | ADR/spec frontmatter and first-section validator |
| `src/scieasy/qa/audit/doc_length_lint.py` | create | Short-form documentation length checker |
| `src/scieasy/qa/audit/auto_generated_lint.py` | create | Generated-doc freshness and hand-edit checker |
| `src/scieasy/qa/audit/skill_pointer_sync.py` | create | Runtime skill pointer validator |
| `src/scieasy/qa/docs/**` | create | SciEasy-specific documentation generators |
| `docs/sphinx/conf.py` | modify | Integrate generated references and warning-as-error behavior |
| `docs/user/reference/**` | generate | API, schema, CLI, OpenAPI, entry-point, block, and runner reference targets |
| `docs/user/llms.txt` | generate | LLM context output derived from docs and generated references |
| `tests/qa/test_docs_generators.py` | create | Generator determinism and output-shape fixtures |

### 4.3 Implementation Sequence

1. Implement shared frontmatter schema imports and Markdown heading extraction.
2. Implement `frontmatter_lint` for ADR and spec fixtures.
3. Implement `doc_length_lint` path profiles and generated-doc exemptions.
4. Define generated-doc manifest format and marker convention.
5. Implement deterministic generators for `llms.txt`, entry points, CLI,
   OpenAPI, schemas, blocks, and runners.
6. Implement `auto_generated_lint` against generator output and manifests.
7. Implement `skill_pointer_sync` across supported AI runtime roots.
8. Wire documentation checks into docs CI and pre-commit only where fast.
9. Integrate generated references into Sphinx with warnings as errors.

### 4.4 Verification Plan

- Run unit fixtures for valid and invalid ADR/spec frontmatter.
- Run heading-structure fixtures with frontmatter, fenced code blocks, and
  missing first H2.
- Run length fixtures for hand-authored docs, generated docs, and exempt paths.
- Run generator determinism tests twice and compare byte-for-byte output.
- Run `auto_generated_lint` against fresh, stale, and hand-edited generated
  outputs.
- Run `skill_pointer_sync` against valid and stale runtime config fixtures.
- Run Sphinx build with warnings-as-errors once generated references exist.

### 4.5 Risks And Rollback

The main risk is treating historical docs as immediately invalid. Mitigate this
by following ADR-042 Section 2.2: report-only until the schema baseline is known
and owner approval moves a check to hard-fail, except where ADR-042 declares a
stricter rule.

If generators are incomplete, rollback is to keep generated docs out of the
Sphinx toctree until their outputs are deterministic and tested. Do not permit
hand edits to generated targets as a workaround; fix the source or generator.

### 4.6 Signature-Level Contracts

Implementers MUST use the shared `AuditReport` and `AuditFinding` models from
`scieasy.qa.schemas.report`. Documentation tools may define additional local
models, but public functions return `AuditReport` or deterministic generator
results.

Markdown and generated-doc models:

```python
from pathlib import Path
from typing import Literal, Mapping, Sequence
from pydantic import BaseModel, Field

DocumentKind = Literal[
    "adr",
    "spec",
    "architecture",
    "contributor",
    "user",
    "prod-agent",
    "doc-guide",
    "audit",
    "generated",
    "unknown",
]


class MarkdownHeading(BaseModel):
    level: int
    text: str
    line: int
    slug: str


class MarkdownDocument(BaseModel):
    path: str
    kind: DocumentKind
    frontmatter: Mapping[str, object] = Field(default_factory=dict)
    headings: list[MarkdownHeading]
    body_line_count: int
    prose_word_count: int


class DocLengthProfile(BaseModel):
    path_glob: str
    max_non_empty_lines: int = 120
    max_prose_words: int = 600
    generated_exempt: bool = True


class GeneratedDocManifestEntry(BaseModel):
    target_path: str
    generator_id: str
    source_paths: list[str]
    source_sha: str
    content_sha256: str
    marker: str


class GeneratedDocManifest(BaseModel):
    schema_version: str = "1"
    entries: list[GeneratedDocManifestEntry]


class GeneratorResult(BaseModel):
    generator_id: str
    target_path: str
    content: str
    source_paths: list[str]
    warnings: list[str] = Field(default_factory=list)
    manifest_entry: GeneratedDocManifestEntry
```

Markdown parsing and frontmatter linting:

```python
def parse_markdown_document(path: Path, *, repo_root: Path) -> MarkdownDocument: ...

def parse_markdown_text(
    text: str,
    *,
    path: str,
    kind: DocumentKind = "unknown",
) -> MarkdownDocument: ...

def lint_file(
    path: Path,
    *,
    repo_root: Path,
    expected_kind: DocumentKind | None = None,
) -> AuditReport: ...

def lint_paths(
    paths: Sequence[Path],
    *,
    repo_root: Path,
) -> AuditReport: ...
```

`frontmatter_lint.lint_file` MUST validate both metadata and structure. For
ADRs it calls `ADRFrontmatter`; for specs it calls `SpecFrontmatter`; for other
document kinds it validates the first-section rule only until that kind has a
dedicated schema.

Length and generated-file checks:

```python
def check(
    paths: Sequence[Path] | None = None,
    *,
    repo_root: Path,
    profiles: Sequence[DocLengthProfile] | None = None,
) -> AuditReport: ...

def load_manifest(path: Path) -> GeneratedDocManifest: ...

def write_manifest(manifest: GeneratedDocManifest, path: Path) -> None: ...

def check_generated(
    *,
    repo_root: Path,
    manifest_path: Path = Path("docs/user/reference/generated-docs.yaml"),
    update: bool = False,
    generators: Sequence[str] | None = None,
) -> AuditReport: ...
```

`scieasy.qa.audit.auto_generated_lint.check` is the public entry point and MUST
delegate to `check_generated`. The public entry point keeps the ADR-042 name:

```python
def check(
    *,
    repo_root: Path,
    manifest_path: Path = Path("docs/user/reference/generated-docs.yaml"),
    update: bool = False,
    generators: Sequence[str] | None = None,
) -> AuditReport: ...
```

Generator module signatures:

```python
# scieasy.qa.docs.llms_txt
def generate(
    repo_root: Path,
    *,
    output_path: Path = Path("docs/user/llms.txt"),
) -> GeneratorResult: ...


# scieasy.qa.docs.entry_point_catalog
def generate(
    repo_root: Path,
    *,
    output_path: Path = Path("docs/user/reference/entry-points.md"),
    group_prefix: str = "scieasy",
) -> GeneratorResult: ...


# scieasy.qa.docs.cli_reference
def generate(
    repo_root: Path,
    *,
    output_path: Path = Path("docs/user/reference/cli.md"),
    command_import: str = "scieasy.cli:app",
) -> GeneratorResult: ...


# scieasy.qa.docs.openapi_reference
def generate(
    repo_root: Path,
    *,
    output_path: Path = Path("docs/user/reference/server-api.md"),
    app_import: str = "scieasy.api.app:create_app",
) -> GeneratorResult: ...


# scieasy.qa.docs.schema_reference
def generate(
    repo_root: Path,
    *,
    output_dir: Path = Path("docs/user/reference/schemas"),
    package_prefixes: Sequence[str] = ("scieasy",),
) -> list[GeneratorResult]: ...


# scieasy.qa.docs.block_catalog
def generate(
    repo_root: Path,
    *,
    output_dir: Path = Path("docs/user/reference/blocks"),
) -> list[GeneratorResult]: ...


# scieasy.qa.docs.runner_catalog
def generate(
    repo_root: Path,
    *,
    output_dir: Path = Path("docs/user/reference/runners"),
) -> list[GeneratorResult]: ...
```

Skill pointer synchronization:

```python
class SkillPointer(BaseModel):
    runtime: str
    skill_path: str
    persona: str
    workflow_doc: str
    root_policy_ref: str


def discover_skill_pointers(
    repo_root: Path,
    *,
    runtime_roots: Sequence[Path] = (
        Path(".agents"),
        Path(".claude"),
        Path(".codex"),
        Path(".gemini"),
    ),
) -> list[SkillPointer]: ...

def check(
    *,
    repo_root: Path,
    runtime_roots: Sequence[Path] | None = None,
) -> AuditReport: ...
```

Required CLI behavior:

```text
python -m scieasy.qa.audit.frontmatter_lint docs/adr/ADR-042.md --format json
python -m scieasy.qa.audit.frontmatter_lint docs/specs --recursive --format json
python -m scieasy.qa.audit.doc_length_lint docs --format json
python -m scieasy.qa.docs.generate_reference --target all --check
python -m scieasy.qa.docs.generate_reference --target all --write
python -m scieasy.qa.audit.auto_generated_lint --check --format json
python -m scieasy.qa.audit.skill_pointer_sync --format json
```

All CLIs MUST use the uniform ADR-042 audit exit codes: 0 for no
error-severity findings, 1 for error-severity findings, and 2 for usage or tool
errors.

## 5. Success Criteria

### Measurable Outcomes

- SC-001: Valid ADR-042-style specs pass `frontmatter_lint` with no findings.
- SC-002: Invalid ADR/spec frontmatter and first-section fixtures produce stable
  findings.
- SC-003: Over-limit hand-authored docs are detected while generated references
  are exempt.
- SC-004: Generated docs are reproducible from source inputs and stale committed
  outputs are detected.
- SC-005: Runtime skill fixtures without canonical workflow pointers fail
  `skill_pointer_sync`.
- SC-006: Documentation generators produce deterministic output across repeated
  runs in the same repository state.

## 6. Assumptions

- The shared ADR and spec frontmatter schemas will land before or with
  `frontmatter_lint`.
- Sphinx and griffe remain the extraction and build backends; custom tools
  enforce repository policy around their output.
- Some generated targets may be empty at first if the corresponding source
  surface does not yet exist.
- Linkcheck may require a separate baseline because external URLs can fail for
  reasons outside the repository.
