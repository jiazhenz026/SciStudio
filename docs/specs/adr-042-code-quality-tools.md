---
spec_id: adr-042-code-quality-tools
title: "ADR-042 Code Quality Tooling Specification"
status: Draft
feature_branch: docs/adr-042-repository-governance-v2
created: 2026-05-18
input: "Manual owner request to specify ADR-042 custom code normalization tools."
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
related_specs:
  - adr-042-documentation-tools
  - adr-042-consistency-tools
  - adr-042-ai-governance-tools
scope:
  in:
    - Custom code scoring for changed modules and scheduled module health audits.
    - Test-quality checks for weak tests, mutation gaps, and test-first evidence.
    - Report shapes and CI/pre-commit placement for code quality tooling.
  out:
    - Reimplementation of ruff, mypy, pyright, pytest, coverage, import-linter, vulture, xenon, or pip-audit.
    - Product code refactors driven only by score output.
    - Human review replacement.
governs:
  modules:
    - scistudio.qa.code_score
    - scistudio.qa.test_quality
  contracts:
    - scistudio.qa.code_score.score_module
    - scistudio.qa.code_score.score_changed_modules
    - scistudio.qa.test_quality.ast_lint.check_test_file
    - scistudio.qa.test_quality.test_first_check.verify_ordering
    - scistudio.qa.test_quality.mutation_runner.run_targeted
  files:
    - src/scistudio/qa/code_score/**
    - src/scistudio/qa/test_quality/**
    - tests/qa/test_code_score.py
    - tests/qa/test_test_quality_ast.py
    - tests/qa/test_test_quality_test_first.py
    - tests/qa/test_mutation_runner.py
    - docs/audit/code-score/**
    - pyproject.toml
    - .pre-commit-config.yaml
    - .github/workflows/**
tests:
  - tests/qa/test_code_score.py
  - tests/qa/test_test_quality_ast.py
  - tests/qa/test_test_quality_test_first.py
  - tests/qa/test_mutation_runner.py
acceptance_source: adr
language_source: en
---

# ADR-042 Code Quality Tooling Specification

## 1. Change Summary

This spec defines the custom code normalization tools required by ADR-042:
`code_score` and the `test_quality` tool family. It comes from ADR-042 and the
owner request to split custom tooling into four implementation specs.

The spec intentionally treats common tools such as `ruff`, `mypy`, `pyright`,
`pytest`, `coverage`, `import-linter`, `griffe`, `vulture`, `xenon`, and
`pip-audit` as inputs, not as code to rewrite. Custom code-quality tools must
aggregate and interpret those signals for SciStudio policy without hiding the
underlying tool output.

## 2. User Scenarios & Testing

### User Story 1 - Changed modules receive deterministic gate grades (Priority: P1)

As a maintainer, I need every code change to receive an A/B/C/D/F deterministic
grade so that objectively unsafe changes cannot enter `main`.

Why this priority: ADR-042 makes deterministic `code_score` F grades blocking
in pre-commit and CI once the tool exists.

Independent Test: Run `code_score --changed --fast` and
`code_score --changed --full` against fixtures containing passing, warning, and
F-grade changes; verify the expected grade and blocking flag.

Acceptance Scenarios:

1. Given a changed module with a syntax error, when `code_score` runs, then the
   report assigns F and sets `blocks_merge=true`.
2. Given a small bugfix in a historically weak module, when the change does not
   worsen existing findings, then the change score is not F only because of
   historical module debt.
3. Given an unavailable AI advisory CLI, when `code_score` runs, then the AI
   advisory section is recorded as skipped and does not block.

### User Story 2 - Weak tests are reported mechanically (Priority: P2)

As a reviewer, I need weak-test anti-patterns to be surfaced before review so
that AI-written or rushed tests do not merely confirm implementation shape.

Why this priority: ADR-042 Section 7.7 requires supervision for empty
assertions, mocked-away behavior, snapshot-only checks, broad exception
swallowing, skipped tests without tracked rationale, mutation gaps, and
test-first evidence where required.

Independent Test: Run `test_quality.ast_lint.check_test_file` against fixture
tests containing each anti-pattern and against a clean behavior test.

Acceptance Scenarios:

1. Given a test with no meaningful assertion, when `test_quality.ast_lint` runs,
   then it emits a finding with the affected file and node location.
2. Given a skipped test without a tracked issue or approved rationale, when the
   AST lint runs, then it emits a hard anti-pattern finding after rollout.
3. Given a behavior-focused test, when the AST lint runs, then it emits no
   weak-test finding.

### User Story 3 - Mutation gaps are visible for critical code (Priority: P3)

As a maintainer, I need targeted mutation runs for QA tools and selected
critical logic so that passing tests cannot hide untested branches.

Why this priority: ADR-042 requires mutation testing for QA tools and selected
critical logic, but keeps full mutation runs scheduled/manual because they are
too expensive for every PR.

Independent Test: Run `test_quality.mutation_runner.run_targeted` against a
small fixture module and verify that mutation results are normalized into the
shared report envelope.

Acceptance Scenarios:

1. Given a changed QA module with a configured mutation target, when targeted
   mutation runs, then the report lists surviving mutants and threshold status.
2. Given no configured target for the changed module, when mutation runs, then
   the report records `not-applicable` instead of failing spuriously.

### Edge Cases

- AI advisory CLI exists but times out, exits non-zero, or returns invalid JSON.
- A changed file maps to multiple logical modules.
- A file deletion removes a previously F-scored module.
- Module health data is missing because the weekly audit has not run yet.
- Generated files are staged; `code_score` must defer generated-file freshness
  to documentation tooling instead of scoring generated output as source code.

## 3. Requirements

### Functional Requirements

- FR-001: `code_score.score_changed_modules` MUST score only changed files,
  changed hunks, and changed symbols for the PR or local commit gate.
- FR-002: `code_score.score_module` MUST support scheduled module-health audits
  over complete modules or packages.
- FR-003: `code_score` MUST emit deterministic grades A, B, C, D, or F with a
  machine-readable reason list.
- FR-004: Deterministic F grades MUST set `blocks_merge=true` for pre-commit and
  PR CI.
- FR-005: Historical module-health F grades MUST NOT block a safe change whose
  change score is C or better and does not worsen the known finding.
- FR-006: Touching the exact function or class that owns an existing F finding
  without improving it MAY lower the change score.
- FR-007: AI advisory scoring MUST be optional and best-effort; missing,
  timed-out, non-zero, or invalid CLI output MUST record `skipped`.
- FR-008: AI advisory scoring MUST never block unless ADR-042 is amended by the
  owner.
- FR-009: Local pre-commit reports MUST be written under
  `.git/scistudio/code-score/` and MUST NOT be committed.
- FR-010: CI change-score reports MUST be uploaded as artifacts and MAY be
  committed under `docs/audit/code-score/changes/` when the owner wants
  persistent history.
- FR-011: Weekly module-health reports MUST be written or published under
  `docs/audit/code-score/module-health/`.
- FR-012: AI advisory reports MUST be stored separately under
  `docs/audit/code-score/ai/`.
- FR-013: `test_quality.ast_lint` MUST detect empty assertions, mocked-away
  behavior, snapshot-only tests, broad exception swallowing, and skipped tests
  without tracked rationale.
- FR-014: `test_quality.test_first_check` MUST verify ordering evidence for
  scopes that require test-first work and otherwise report `not-required`.
- FR-015: `test_quality.mutation_runner` MUST normalize targeted mutation
  results into the shared audit report envelope.
- FR-016: The tools MUST consume common tool reports without replacing the
  common tools that produced them.

### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `CodeScoreReport` | Machine-readable result for a changed-code scoring run | deterministic scores, AI advisory status, final gate score, findings, report paths | Consumes common tool reports and may reference module-health reports |
| `ModuleHealthReport` | Scheduled whole-module score snapshot | module id, grade, findings, generated date, source SHA | Used as non-blocking context by change scoring |
| `AIAdvisoryScore` | Optional headless CLI review result | provider, score, confidence, status, summary, findings | Stored separately from deterministic scoring |
| `TestQualityFinding` | Weak-test or mutation finding | file, line, rule id, severity, message, tracked rationale | Feeds `code_score` and audit reports |
| `MutationReport` | Targeted mutation result | target, threshold, killed, survived, status | Produced by `mutation_runner` |

## 4. Implementation Plan

### 4.1 Technical Approach

Implement code-quality tooling as deterministic Python modules under
`src/scistudio/qa/`. `code_score` should collect normalized inputs from existing
tool outputs, git diff metadata, and optional module-health reports. It should
then apply ADR-042 scoring rules in a small policy layer with explicit weights,
hard F triggers, and stable report JSON.

`test_quality` should be split by cost and purpose:

- `ast_lint` is fast and suitable for pre-commit or PR CI.
- `test_first_check` reads commit ordering or gate evidence and is report-only
  unless the declared scope requires test-first work.
- `mutation_runner` wraps targeted `mutmut` or equivalent execution and runs in
  scheduled/manual or targeted CI contexts.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/qa/code_score/**` | create | Scoring engine, report models, CLI, and adapters for common tool reports |
| `src/scistudio/qa/test_quality/**` | create | Test AST lint, test-first evidence checker, and mutation wrapper |
| `tests/qa/test_code_score.py` | create | Grade, F-trigger, AI-skip, and historical-debt fixtures |
| `tests/qa/test_test_quality_ast.py` | create | Weak-test anti-pattern fixtures |
| `tests/qa/test_test_quality_test_first.py` | create | Test-first required and not-required ordering fixtures |
| `tests/qa/test_mutation_runner.py` | create | Mutation report normalization and not-applicable behavior |
| `.pre-commit-config.yaml` | modify | Add `code_score --changed --fast` when fast enough |
| `.github/workflows/**` | modify | Add `code-score` CI and scheduled module-health workflow |
| `docs/audit/code-score/**` | generate | Store persistent CI and scheduled audit reports when configured |

### 4.3 Implementation Sequence

1. Define report models and JSON serialization shared by `code_score` and
   `test_quality`.
2. Implement deterministic changed-file scoring with hard F triggers.
3. Add common-tool report adapters for ruff, type checks, tests, coverage,
   import boundaries, security, and test-quality output.
4. Implement optional AI advisory scoring with timeout, JSON validation, and
   `skipped` fallback.
5. Implement scheduled module-health scoring and storage.
6. Implement `test_quality.ast_lint` fixtures and rules.
7. Implement `test_first_check` as report-only unless gate scope requires it.
8. Implement targeted mutation wrapper and threshold reporting.
9. Wire fast changed scoring into pre-commit and full changed scoring into CI.

### 4.4 Verification Plan

- Run focused unit tests for every grade boundary and F-trigger.
- Run fixtures for AI advisory `completed`, `skipped-missing-cli`,
  `skipped-timeout`, `skipped-nonzero`, and `skipped-invalid-json`.
- Run AST lint fixtures for each weak-test rule and clean control tests.
- Run mutation wrapper tests without requiring repository-wide mutation runs.
- Run `ruff check`, `mypy` or `pyright` where configured, and targeted `pytest`.
- Verify `code_score --changed --fast` writes only under `.git/scistudio/`.

### 4.5 Risks And Rollback

The main risk is over-blocking small safe changes because historical debt is
confused with introduced debt. Mitigate this by keeping change scoring separate
from module-health scoring and by writing fixtures for weak historical modules.

If scoring becomes noisy, rollback is to keep `code_score` in report-only mode
except for deterministic hard failures such as syntax errors, test failures,
critical security findings, and invalid import boundaries. ADR-042 still
requires deterministic F to block once the scoring tool exists, so rollback must
be narrow and owner-approved.

### 4.6 Signature-Level Contracts

Implementers MUST keep deterministic scoring separate from AI advisory scoring.
Only deterministic F grades may block. All scoring and test-quality tools MUST
emit or embed the shared `AuditReport` shape from `scistudio.qa.schemas.report`.

Score and finding models:

```python
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence
from pydantic import BaseModel, Field

Grade = Literal["A", "B", "C", "D", "F"]
ScoreMode = Literal["fast", "full", "module-health"]
AIAdvisoryStatus = Literal[
    "completed",
    "skipped-missing-cli",
    "skipped-timeout",
    "skipped-nonzero",
    "skipped-invalid-json",
    "disabled",
]


class ToolSignal(BaseModel):
    tool: str
    status: Literal["passed", "failed", "skipped", "missing"]
    severity: Literal["info", "warning", "error"]
    path: str | None = None
    subject: str | None = None
    message: str
    raw: Mapping[str, Any] = Field(default_factory=dict)


class CodeScoreFinding(BaseModel):
    id: str
    grade_impact: Grade
    reason: str
    path: str | None = None
    symbol: str | None = None
    source_tool: str
    introduced_by_change: bool
    blocks_merge: bool = False


class AIAdvisoryScore(BaseModel):
    provider: str | None
    score: Grade | None = None
    confidence: Literal["low", "medium", "high"] | None = None
    status: AIAdvisoryStatus
    summary: str | None = None
    findings: list[CodeScoreFinding] = Field(default_factory=list)
    raw_path: str | None = None


class ModuleScore(BaseModel):
    module: str
    grade: Grade
    findings: list[CodeScoreFinding] = Field(default_factory=list)
    historical_health_grade: Grade | None = None
    worsens_historical_findings: bool = False


class CodeScoreReport(BaseModel):
    schema_version: str = "1"
    mode: ScoreMode
    generated_at: datetime
    source_sha: str
    base_ref: str | None = None
    head_ref: str | None = None
    modules: list[ModuleScore]
    deterministic_final_grade: Grade
    ai_advisory: AIAdvisoryScore | None = None
    blocks_merge: bool
    reason: str
    audit_report: AuditReport
```

Tool report collection and scoring:

```python
class ToolReportBundle(BaseModel):
    signals: list[ToolSignal] = Field(default_factory=list)
    report_paths: list[str] = Field(default_factory=list)


def collect_tool_reports(
    repo_root: Path,
    *,
    report_paths: Sequence[Path] | None = None,
    include_missing: bool = True,
) -> ToolReportBundle: ...

def changed_modules(
    repo_root: Path,
    *,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
) -> list[str]: ...

def score_module(
    module: str,
    *,
    repo_root: Path,
    tool_reports: ToolReportBundle,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
    module_health: ModuleScore | None = None,
) -> ModuleScore: ...

def score_changed_modules(
    repo_root: Path,
    *,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
    mode: Literal["fast", "full"] = "fast",
    tool_reports: ToolReportBundle | None = None,
    module_health_path: Path | None = None,
    ai_advisory: bool = False,
    ai_provider: Literal["codex", "claude"] | None = None,
    output_path: Path | None = None,
) -> CodeScoreReport: ...

def score_module_health(
    repo_root: Path,
    *,
    modules: Sequence[str] | None = None,
    output_path: Path = Path("docs/audit/code-score/module-health/latest.json"),
) -> CodeScoreReport: ...

def write_report(report: CodeScoreReport, path: Path) -> None: ...
```

AI advisory contract:

```python
class AIAdvisoryInput(BaseModel):
    diff: str
    touched_files: Mapping[str, str]
    deterministic_report: CodeScoreReport
    max_chars: int = 120_000


def run_ai_advisory(
    advisory_input: AIAdvisoryInput,
    *,
    provider: Literal["codex", "claude"],
    timeout_seconds: int = 60,
) -> AIAdvisoryScore: ...
```

`run_ai_advisory` MUST return a skipped status instead of raising when the CLI
is unavailable, times out, exits non-zero, or returns invalid JSON. Tool usage
errors in deterministic scoring may still raise before report generation and
MUST map to CLI exit code 2.

Test-quality models and APIs:

```python
TestQualityRule = Literal[
    "empty-assertion",
    "mocked-away-behavior",
    "snapshot-only",
    "broad-exception",
    "untracked-skip",
    "test-first-missing",
    "mutation-survivor",
]


class TestQualityFinding(BaseModel):
    rule: TestQualityRule
    severity: Literal["info", "warning", "error"]
    path: str
    line: int | None = None
    message: str
    tracked_rationale: str | None = None


class MutationTarget(BaseModel):
    module: str
    test_selector: str | None = None
    threshold: float


class MutationReport(BaseModel):
    schema_version: str = "1"
    generated_at: datetime
    source_sha: str
    targets: list[MutationTarget]
    killed: int
    survived: int
    timed_out: int = 0
    score: float
    threshold: float
    status: Literal["passed", "failed", "not-applicable", "error"]
    audit_report: AuditReport


def check_test_file(
    path: Path,
    *,
    source: str | None = None,
) -> AuditReport: ...

def check_test_paths(
    paths: Sequence[Path],
    *,
    repo_root: Path,
) -> AuditReport: ...

def verify_ordering(
    repo_root: Path,
    *,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
    required: bool = False,
) -> AuditReport: ...

def run_targeted(
    changed_modules: Sequence[str],
    *,
    repo_root: Path,
    config_path: Path | None = None,
    timeout_seconds: int = 900,
) -> MutationReport: ...
```

Required CLI behavior:

```text
python -m scistudio.qa.code_score --changed --fast --format json
python -m scistudio.qa.code_score --changed --full --base origin/main --head HEAD --format json
python -m scistudio.qa.code_score --module-health --write docs/audit/code-score/module-health/latest.json
python -m scistudio.qa.test_quality.ast_lint tests --format json
python -m scistudio.qa.test_quality.test_first_check --base origin/main --head HEAD --required false --format json
python -m scistudio.qa.test_quality.mutation_runner --changed --base origin/main --head HEAD --format json
```

Exit code rules:

| Command family | Exit 0 | Exit 1 | Exit 2 |
|---|---|---|---|
| `code_score --changed` | No deterministic F | Deterministic F | Usage/tool error |
| `code_score --module-health` | Report written | Reserved for configured hard failure | Usage/tool error |
| `test_quality.ast_lint` | No error findings | Error findings after rollout | Usage/tool error |
| `test_quality.test_first_check` | Not required or evidence present | Required evidence missing | Usage/tool error |
| `test_quality.mutation_runner` | Threshold met or not applicable | Threshold missed for configured hard-fail scope | Usage/tool error |

## 5. Success Criteria

### Measurable Outcomes

- SC-001: A changed module with a syntax error, failing test, critical security
  finding, or invalid import boundary receives deterministic F in fixtures.
- SC-002: A small safe change in a historical F-health module can receive a
  non-F change score when it does not worsen the known finding.
- SC-003: Missing or invalid AI advisory CLI output is recorded as skipped and
  never blocks.
- SC-004: Weak-test AST fixtures produce stable findings with file and location.
- SC-005: Mutation runner fixtures produce a normalized report without requiring
  a repository-wide mutation run.
- SC-006: Pre-commit writes local score output under `.git/scistudio/code-score/`
  only.

## 6. Assumptions

- The owner will approve the exact hard-F trigger list before hard-fail rollout.
- Common tool outputs can be collected from CI logs, JSON reports, or local
  command wrappers without reimplementing the tools.
- AI advisory providers may be absent on many machines; skipped advisory output
  is expected and valid.
- Module-health scoring will start as scheduled/report-only context before it is
  used by reviewers as a routine signal.
