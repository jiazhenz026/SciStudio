---
spec_id: adr-042-ai-governance-tools
title: "ADR-042 AI Governance Tooling Specification"
status: Draft
feature_branch: docs/adr-042-repository-governance-v2
created: 2026-05-18
input: "Manual owner request to specify ADR-042 custom AI restriction and human exemption tools."
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
related_specs:
  - adr-042-code-quality-tools
  - adr-042-documentation-tools
  - adr-042-consistency-tools
scope:
  in:
    - AI local gate sessions and AI-authored commit metadata.
    - Issue linkage, scope evidence, docs landing, persona policy, and runtime skill parity.
    - Human-authored and administrator authorization label provenance.
    - Protected core change, governance modification, CI weakening, and AI merge guards.
    - AI-only governed-change artifact and codemod checks.
  out:
    - Human local workflow enforcement beyond ADR-042 human exemption semantics.
    - Automatic application of GitHub labels or reviews by AI agents.
    - Replacement of branch protection or owner review.
governs:
  modules:
    - scistudio.qa.governance
    - scistudio.qa.audit
  contracts:
    - scistudio.qa.governance.local_gate.GateSession
    - scistudio.qa.governance.local_gate.TaskKind
    - scistudio.qa.governance.local_gate.record_stage
    - scistudio.qa.governance.local_gate.check_pre_commit
    - scistudio.qa.governance.local_gate.check_commit_msg
    - scistudio.qa.governance.issue_link.resolve_or_create
    - scistudio.qa.governance.docs_landing.check
    - scistudio.qa.governance.persona_policy.check
    - scistudio.qa.governance.human_bypass_guard.check
    - scistudio.qa.governance.pr_merge_guard.check
    - scistudio.qa.governance.core_change_guard.check
    - scistudio.qa.governance.mod_guard.check
    - scistudio.qa.governance.weakened_ci_check.verify_no_weakening
    - scistudio.qa.audit.complete_artifacts.check
    - scistudio.qa.audit.codemod_lint.check
    - scistudio.qa.audit.trailer_lint.run
    - scistudio.qa.audit.committer_enforce.check
  files:
    - src/scistudio/qa/governance/**
    - src/scistudio/qa/audit/complete_artifacts.py
    - src/scistudio/qa/audit/codemod_lint.py
    - src/scistudio/qa/audit/trailer_lint.py
    - src/scistudio/qa/audit/committer_enforce.py
    - scripts/audit/instructions_loaded_audit.py
    - .pre-commit-config.yaml
    - .github/workflows/**
    - AGENTS.md
    - .agents/**
    - .claude/**
    - .codex/**
    - .gemini/**
    - docs/contributing/workflows/**
tests:
  - tests/qa/test_local_gate.py
  - tests/qa/test_issue_link.py
  - tests/qa/test_docs_landing.py
  - tests/qa/test_persona_policy.py
  - tests/qa/test_human_bypass_guard.py
  - tests/qa/test_pr_merge_guard.py
  - tests/qa/test_core_change_guard.py
  - tests/qa/test_audit_complete_artifacts.py
  - tests/qa/test_audit_codemod_lint.py
acceptance_source: adr
language_source: en
---

# ADR-042 AI Governance Tooling Specification

## 1. Change Summary

This spec defines the custom AI restriction and human exemption tools required
by ADR-042. It covers local gate sessions, issue linkage, docs landing, persona
policy, runtime configuration parity, protected-path guards,
`governance_mod_guard` policy checks through the
`scistudio.qa.governance.mod_guard.check` entry point, governance weakening
checks, AI merge protection, trailer validation, human-bypass label provenance,
and AI-only governed-change artifact checks.

The spec comes from ADR-042 and the owner request to split custom tooling into
four implementation specs. The tools constrain AI-authored work without granting
AI agents special authority and without exempting humans from repository
correctness checks.

## 2. User Scenarios & Testing

### User Story 1 - AI-authored commits have a local gate session (Priority: P1)

As a repository owner, I need AI-authored commits to declare scope, issue,
checks, docs landing, persona, and metadata before the commit exists.

Why this priority: ADR-042 Section 7.2 makes the local gate an error gate for
AI-authored work and stores temporary session state under `.git/scistudio/gates/`.

Independent Test: Run `local_gate.check_pre_commit` against staged-file and
gate-session fixtures for valid scope, missing session, branch mismatch, denied
path, missing checks, and missing docs landing.

Acceptance Scenarios:

1. Given no active gate session for an AI-authored commit, when pre-commit runs,
   then `local_gate` fails.
2. Given staged files outside `scope.include`, when pre-commit runs, then
   `local_gate` fails.
3. Given all required stages and check evidence, when pre-commit runs, then
   `local_gate` passes.

### User Story 2 - AI work links issues before commit (Priority: P2)

As a maintainer, I need AI tasks, including manager and docs tasks, to link an
existing or newly created issue before commit.

Why this priority: ADR-042 Section 7.2 requires issue linkage for hotfix,
bugfix, feature, docs, maintenance, and manager task kinds.

Independent Test: Run `issue_link.resolve_or_create` fixtures that prefer an
existing issue, create only when none exists, and fail when issue resolution is
unavailable.

Acceptance Scenarios:

1. Given a matching open issue, when issue linkage runs, then it records that
   issue instead of creating a duplicate.
2. Given no matching issue and owner permission to create one, when linkage
   runs, then it records the new issue.
3. Given a manager task with no issue linkage, when the commit gate runs, then
   it fails.

### User Story 3 - AI persona and runtime configuration stay AI-agnostic (Priority: P3)

As an agent manager, I need every AI task to declare one supported persona and
for runtime config roots to carry equivalent constitution, skill, and root
policy pointers.

Why this priority: ADR-042 Sections 7.3 and 7.4 define exactly four personas
and require AI-agnostic runtime support.

Independent Test: Run `persona_policy.check` fixtures for supported personas,
unsupported personas, missing skill pointers, missing constitution pointers,
and runtime-specific-only rules.

Acceptance Scenarios:

1. Given persona `adr_author` with matching skill and root-policy pointer, when
   `persona_policy` runs, then it passes.
2. Given an unsupported persona, when the check runs, then it fails.
3. Given a rule committed only for `.claude/**` without an equivalent supported
   runtime path or shared `.agents/**` representation, when the check runs, then
   it fails or reports a configured parity diagnostic.

### User Story 4 - Human exemptions use maintainer-applied labels (Priority: P4)

As a human maintainer, I need AI-only checks to be bypassable only by
administrator-controlled labels or reviews, not by self-attested PR text.

Why this priority: ADR-042 Section 9 makes `human-authored` and admin approval
labels the durable bypass signals and requires actor permission validation.

Independent Test: Run `human_bypass_guard.check` against PR metadata fixtures
with valid maintainer labels, labels from unauthorized actors, missing labels,
and conflicting AI evidence.

Acceptance Scenarios:

1. Given a `human-authored` label applied by a maintainer and no AI evidence,
   when CI runs AI-only checks, then they report `skipped-human`.
2. Given `human-authored` applied by an unauthorized actor, when
   `human_bypass_guard` runs, then the bypass is invalid.
3. Given explicit `Assisted-by` trailers, when `human-authored` exists, then
   normal AI evidence or a separate administrator override is still required.

### User Story 5 - Protected changes and merges require administrator authorization (Priority: P5)

As a repository owner, I need AI agents blocked from protected core changes,
governance weakening, and PR merges unless administrator authorization is
visible.

Why this priority: ADR-042 Section 7.6 protects core paths, governance rules,
CI thresholds, and merge authority.

Independent Test: Run guard fixtures for protected core files, governance files,
CI weakening diffs, AI merge attempts, valid admin labels, and missing labels.

Acceptance Scenarios:

1. Given an AI-authored change to `src/scistudio/core/**` without
   `admin-approved:core-change`, when `core_change_guard` runs, then it fails.
2. Given a workflow diff that removes a required check, when
   `weakened_ci_check` runs, then it fails.
3. Given an AI-initiated merge attempt without `admin-approved:merge`, when
   `pr_merge_guard` runs, then it fails.

### Edge Cases

- A human uses `--no-verify` locally but CI still runs repository quality checks.
- A PR has both human-authored labels and AI-authored commit trailers.
- A protected core change is approved by review rather than label.
- A runtime config root is missing because that runtime is not yet supported.
- A docs-only AI task touches governance text and therefore needs governance
  scope and review.

## 3. Requirements

### Functional Requirements

- FR-001: `GateSession` MUST store local temporary state under
  `.git/scistudio/gates/` and MUST NOT be committed.
- FR-002: `TaskKind` MUST support `hotfix`, `bugfix`, `feature`, `docs`,
  `maintenance`, and `manager`.
- FR-003: `local_gate.check_pre_commit` MUST fail missing session, branch
  mismatch, staged files outside scope, denied paths, unauthorized governance
  touches, missing check evidence, deterministic F code score, wired
  consistency errors, missing docs landing, and untracked deferrals.
- FR-004: `local_gate.check_commit_msg` MUST require AI-authored commit trailers
  for `Gate-Session`, `Task-Kind`, `Issue`, and `Assisted-by`.
- FR-005: `issue_link.resolve_or_create` MUST prefer existing issues and create
  a new issue only when none applies.
- FR-006: Manager tasks MUST require issue linkage.
- FR-007: `docs_landing.check` MUST verify required docs, specs, ADRs,
  changelog, checklist updates, or explicit N/A rationale.
- FR-008: `persona_policy.check` MUST allow only `manager`, `implementer`,
  `adr_author`, and `audit_reviewer`.
- FR-009: `persona_policy.check` MUST verify runtime config roots reference
  root policy, AI constitution, persona skills, and canonical workflow docs.
- FR-010: No committed AI runtime policy may privilege one supported runtime
  over another unless it degrades into the same report-only diagnostic for all.
- FR-011: `human_bypass_guard.check` MUST verify `human-authored` and admin
  approval labels or reviews were applied by maintainers or administrators.
- FR-012: Human bypass MUST apply only to AI-only checks and MUST NOT bypass
  repository quality checks, deterministic `code_score` F, security checks,
  branch protection, tests required by scope, or wired consistency failures.
- FR-013: `core_change_guard.check` MUST require
  `admin-approved:core-change` label or administrator approving review for
  AI-authored changes to protected core paths.
- FR-014: `pr_merge_guard.check` MUST block AI-initiated merge attempts unless
  `admin-approved:merge` is present.
- FR-015: `governance_mod_guard` is the policy/tool name for
  `mod_guard.check`, and it MUST fail unauthorized weakening of governance rules
  or unauthorized changes to governance files.
- FR-016: `weakened_ci_check.verify_no_weakening` MUST detect removed or
  weakened checks, tests, thresholds, and exemptions.
- FR-016a: The initial P0 implementation MUST run both tools as scoped local
  pre-commit hooks in staged-diff mode. `mod_guard` MAY accept the explicit
  local override `SCISTUDIO_GOVERNANCE_CHANGE_APPROVED=1` only after maintainer
  authorization; this is an escape hatch for legitimate governance edits, not
  self-authorization by an AI agent.
- FR-017: `instructions_loaded_audit` MUST record loaded instruction metadata as
  a report-only diagnostic unless owner policy later changes it.
- FR-018: `trailer_lint.run` MUST validate AI provenance trailers across a
  commit range when commit workflow support is enabled.
- FR-019: `committer_enforce.check` MUST remain deferred until the owner
  declares the approved AI commit path stable.
- FR-020: `complete_artifacts.check` MUST verify required tests, docs,
  changelog, ownership, and generated artifacts for AI-authored governed
  changes and allow `human-authored` bypass only for AI-only artifact checks.
- FR-021: `codemod_lint.check` MUST verify codemod metadata and idempotence for
  AI-authored contract migrations and allow `human-authored` bypass only for
  AI-only codemod requirements.

### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `GateSession` | Local AI task state | session id, task kind, branch, owner directive, scope, issues, checks, docs landing, persona, runtime, admin labels, amendments | Read by local gate and docs landing |
| `IssueLink` | Resolved or created GitHub issue reference | number, URL, source, matched query, status | Required by every task kind |
| `PersonaDeclaration` | AI role and runtime declaration | persona, runtime, skill path, constitution pointer, root-policy pointer | Checked by `persona_policy` |
| `AuthorizationSignal` | Maintainer-applied label or review | operation, label or review id, actor, permission, source | Checked by bypass and protected-change guards |
| `DocsLandingRecord` | Required documentation landing evidence | changed docs, N/A rationale, changelog status, checklist status | Checked before AI commit |
| `GovernedChangeFinding` | Missing artifact or codemod issue | changed surface, missing artifact, bypass status, severity | Produced by `complete_artifacts` and `codemod_lint` |

## 4. Implementation Plan

### 4.1 Technical Approach

Implement AI governance tools as deterministic validators over three evidence
sources: local gate session JSON, git staged or PR diffs, and durable GitHub
metadata such as labels, reviews, actors, and commit trailers. Local hooks may
make fast decisions from `.git/scistudio/gates/`, but remote CI is the durable
authority for label provenance and PR-level bypass semantics.

Keep human bypass explicit and narrow. Human labels skip only AI-only harness
checks. Repository quality checks still run and fail normally.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/qa/governance/local_gate.py` | create | Gate session schema, stage recording, pre-commit, and commit-msg checks |
| `src/scistudio/qa/governance/issue_link.py` | create | Existing issue resolution and issue linkage records |
| `src/scistudio/qa/governance/docs_landing.py` | create | Required docs/changelog/checklist landing checker |
| `src/scistudio/qa/governance/persona_policy.py` | create | Persona, runtime config, constitution, and skill parity checker |
| `src/scistudio/qa/governance/human_bypass_guard.py` | create | Human/admin label and review provenance validator |
| `src/scistudio/qa/governance/pr_merge_guard.py` | create | AI merge-attempt guard |
| `src/scistudio/qa/governance/core_change_guard.py` | create | Protected core path authorization checker |
| `src/scistudio/qa/governance/mod_guard.py` | create | `governance_mod_guard` entry point for governance rule modification checks |
| `src/scistudio/qa/governance/weakened_ci_check.py` | create | CI/test/lint threshold weakening detector |
| `src/scistudio/qa/audit/complete_artifacts.py` | create | Governed-change artifact completion checker |
| `src/scistudio/qa/audit/codemod_lint.py` | create | Codemod metadata and idempotence checker |
| `src/scistudio/qa/audit/trailer_lint.py` | create | AI trailer validator |
| `src/scistudio/qa/audit/committer_enforce.py` | create | Deferred approved-commit-path enforcement |
| `scripts/audit/instructions_loaded_audit.py` | create | Runtime instruction loading diagnostic |
| `.pre-commit-config.yaml` | modify | Wire fast local AI gate and allowed quality checks |
| `.github/workflows/**` | modify | Wire durable PR checks and label provenance validation |

### 4.3 Implementation Sequence

1. Implement `TaskKind`, `GateSession`, and local gate session read/write.
2. Implement pre-commit staged-scope validation and commit-msg trailer
   validation.
3. Implement issue resolution and docs landing checks.
4. Implement persona policy and runtime config parity fixtures.
5. Implement human/admin authorization signal validation from GitHub metadata.
6. Implement protected core, AI merge, governance modification, and weakening
   guards.
7. Implement `complete_artifacts` and `codemod_lint` with human-label bypass
   semantics for AI-only requirements.
8. Implement trailer lint and deferred committer enforcement stubs.
9. Implement `instructions_loaded_audit` as report-only diagnostic.
10. Wire local hooks and remote CI with distinct local and durable evidence
    semantics.

### 4.4 Verification Plan

- Run local gate fixtures for every required failure condition in ADR-042
  Section 7.2.
- Run commit message fixtures with missing and valid AI trailers.
- Run issue-link fixtures that prefer existing issues.
- Run docs-landing fixtures for docs changed, docs missing, and N/A rationale.
- Run persona-policy fixtures for every supported persona and unsupported
  runtime-specific-only rules.
- Run human-bypass fixtures for valid maintainer labels, unauthorized labels,
  and conflicting AI evidence.
- Run protected-path, governance-modification, weakening, and AI-merge fixtures.
- Run complete-artifacts and codemod-lint fixtures with and without valid
  `human-authored` bypass.

### 4.5 Risks And Rollback

The main risk is confusing local convenience with durable authorization. Mitigate
this by treating local `.git/scistudio/gates/` as AI commit-boundary evidence only
and treating GitHub labels/reviews as CI authority for human and administrator
bypass.

If a local hook blocks legitimate work because local evidence is unavailable,
the rollback is to narrow the local hook to fast AI-only checks while keeping CI
hard-fail validation for durable evidence. Do not weaken repository quality
checks or allow AI self-attested human bypass.

### 4.6 Signature-Level Contracts

Implementers MUST keep local-only gate evidence separate from durable PR
evidence. Functions that need GitHub metadata MUST accept explicit metadata
objects or a client protocol; they must not infer authorization from prose,
branch names, or commit authors.

Gate and authorization models:

```python
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol, Sequence
from pydantic import BaseModel, Field

TaskKind = Literal["hotfix", "bugfix", "feature", "docs", "maintenance", "manager"]
Persona = Literal["manager", "implementer", "adr_author", "audit_reviewer"]
GateStage = Literal[
    "scope",
    "issue",
    "implement",
    "test_and_checks",
    "documentation_landing",
    "commit",
]


class GateScope(BaseModel):
    include: list[str]
    exclude: list[str] = Field(default_factory=list)


class CheckResult(BaseModel):
    command: str
    exit_code: int
    timestamp: datetime
    output_path: str | None = None
    summary: str | None = None


class DocsLandingRecord(BaseModel):
    docs_updated: list[str] = Field(default_factory=list)
    changelog_updated: bool | None = None
    checklist_updated: bool | None = None
    not_applicable_rationale: str | None = None


class IssueRecord(BaseModel):
    number: int
    url: str
    source: Literal["existing", "created"]
    closes: bool = False


class GateSession(BaseModel):
    session_id: str
    task_kind: TaskKind
    branch: str
    owner_directive: str
    scope: GateScope
    governance_touch: bool = False
    issues: list[IssueRecord] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    check_results: list[CheckResult] = Field(default_factory=list)
    docs_landing: DocsLandingRecord | None = None
    persona: Persona
    runtime: str
    admin_labels: list[str] = Field(default_factory=list)
    amendments: list[Mapping[str, Any]] = Field(default_factory=list)


class ActorPermission(BaseModel):
    login: str
    permission: Literal["none", "read", "triage", "write", "maintain", "admin"]


class AuthorizationSignal(BaseModel):
    operation: Literal[
        "human-authored",
        "core-change",
        "merge",
        "ai-override",
    ]
    signal_type: Literal["label", "review"]
    name: str
    actor: str
    actor_permission: ActorPermission
    created_at: datetime
    valid: bool


class PullRequestMetadata(BaseModel):
    repo: str
    number: int
    head_sha: str
    base_ref: str
    head_ref: str
    labels: list[str]
    reviews: list[Mapping[str, Any]] = Field(default_factory=list)
    commits: list[Mapping[str, Any]] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    actors: list[ActorPermission] = Field(default_factory=list)
```

Local gate public API in `scistudio.qa.governance.local_gate`:

```python
def start_session(
    repo_root: Path,
    *,
    task_kind: TaskKind,
    owner_directive: str,
    scope: GateScope,
    persona: Persona,
    runtime: str,
    branch: str | None = None,
    governance_touch: bool = False,
) -> GateSession: ...

def load_session(
    repo_root: Path,
    *,
    session_id: str | None = None,
    branch: str | None = None,
) -> GateSession | None: ...

def save_session(repo_root: Path, session: GateSession) -> Path: ...

def record_stage(
    repo_root: Path,
    session_id: str,
    stage: GateStage,
    data: Mapping[str, Any],
) -> GateSession: ...

def staged_files(repo_root: Path) -> list[Path]: ...

def check_pre_commit(
    repo_root: Path,
    *,
    session_id: str | None = None,
    staged: Sequence[Path] | None = None,
) -> AuditReport: ...

def check_commit_msg(
    message: str,
    *,
    require_ai_trailers: bool = True,
) -> AuditReport: ...
```

Issue, docs landing, and persona contracts:

```python
class IssueQuery(BaseModel):
    repo: str
    title: str
    body: str
    labels: list[str] = Field(default_factory=list)
    close_existing: bool = True


class IssueClient(Protocol):
    def search_issues(self, query: IssueQuery) -> list[IssueRecord]: ...

    def create_issue(self, query: IssueQuery) -> IssueRecord: ...


def resolve_or_create(
    query: IssueQuery,
    *,
    client: IssueClient,
    create_if_missing: bool,
) -> IssueRecord: ...

def check(
    *,
    repo_root: Path,
    session: GateSession,
    staged: Sequence[Path] | None = None,
) -> AuditReport: ...

def check_persona_policy(
    *,
    repo_root: Path,
    session: GateSession,
    runtime_roots: Sequence[Path] | None = None,
) -> AuditReport: ...
```

The public `docs_landing` entry point is
`scistudio.qa.governance.docs_landing.check`. The public `persona_policy` entry
point is `scistudio.qa.governance.persona_policy.check`; it may delegate to
`check_persona_policy`.

GitHub provenance and protected-operation guards:

```python
def check_human_bypass(
    pr: PullRequestMetadata,
    *,
    required_label: str = "human-authored",
) -> AuditReport: ...

def check_pr_merge(
    *,
    pr: PullRequestMetadata,
    actor: ActorPermission,
    intent: Literal["merge", "squash", "rebase", "enable-auto-merge"],
) -> AuditReport: ...

def check_core_change(
    *,
    pr: PullRequestMetadata | None,
    changed_files: Sequence[str],
    session: GateSession | None,
    protected_globs: Sequence[str] = (
        "src/scistudio/core/**",
        "src/scistudio/engine/**",
        "src/scistudio/blocks/**",
        "src/scistudio/workflow/**",
        "src/scistudio/utils/**",
    ),
) -> AuditReport: ...

def check_governance_modification(
    *,
    base_ref: str,
    head_ref: str,
    repo_root: Path,
    session: GateSession | None = None,
) -> AuditReport: ...

def verify_no_weakening(
    *,
    repo_root: Path,
    base_ref: str,
    head_ref: str,
) -> AuditReport: ...
```

The public ADR-042 names map as follows:

| ADR-042 tool name | Public Python entry point |
|---|---|
| `human_bypass_guard` | `scistudio.qa.governance.human_bypass_guard.check` delegates to `check_human_bypass` |
| `pr_merge_guard` | `scistudio.qa.governance.pr_merge_guard.check` delegates to `check_pr_merge` |
| `core_change_guard` | `scistudio.qa.governance.core_change_guard.check` delegates to `check_core_change` |
| `governance_mod_guard` | `scistudio.qa.governance.mod_guard.check` delegates to `check_governance_modification` |
| `weakened_ci_check` | `scistudio.qa.governance.weakened_ci_check.verify_no_weakening` |

Governed-change and provenance audit tools:

```python
def check_complete_artifacts(
    *,
    repo_root: Path,
    session: GateSession | None,
    pr: PullRequestMetadata | None = None,
    changed_files: Sequence[str] | None = None,
) -> AuditReport: ...

def check_codemod_lint(
    *,
    repo_root: Path,
    changed_files: Sequence[str],
    pr: PullRequestMetadata | None = None,
    run_idempotence: bool = True,
) -> AuditReport: ...

def run_trailer_lint(
    *,
    repo_root: Path,
    rev_range: str,
    require_ai_trailers: bool,
) -> AuditReport: ...

def check_committer_enforce(
    *,
    repo_root: Path,
    rev_range: str,
    approved_committers: Sequence[str],
) -> AuditReport: ...

def audit_loaded_instructions(
    *,
    repo_root: Path,
    runtime: str,
    metadata_path: Path | None = None,
) -> AuditReport: ...
```

Public wrappers MUST keep the ADR-042 names:

```python
complete_artifacts.check = check_complete_artifacts
codemod_lint.check = check_codemod_lint
trailer_lint.run = run_trailer_lint
committer_enforce.check = check_committer_enforce
```

Required CLI behavior:

```text
python -m scistudio.qa.governance.mod_guard --base origin/main --head HEAD --format json
python -m scistudio.qa.governance.mod_guard --staged
python -m scistudio.qa.governance.local_gate start --kind docs --persona adr_author --scope docs/specs/**
python -m scistudio.qa.governance.local_gate record --stage issue --issue 1113
python -m scistudio.qa.governance.local_gate pre-commit
python -m scistudio.qa.governance.local_gate commit-msg .git/COMMIT_EDITMSG
python -m scistudio.qa.governance.persona_policy --format json
python -m scistudio.qa.governance.human_bypass_guard --pr 1195 --format json
python -m scistudio.qa.governance.core_change_guard --base origin/main --head HEAD --format json
python -m scistudio.qa.governance.weakened_ci_check --base origin/main --head HEAD --format json
python -m scistudio.qa.governance.weakened_ci_check --staged
python -m scistudio.qa.audit.complete_artifacts --base origin/main --head HEAD --format json
python -m scistudio.qa.audit.codemod_lint --base origin/main --head HEAD --format json
python -m scistudio.qa.audit.trailer_lint --range origin/main..HEAD --format json
```

All CLIs MUST use uniform ADR-042 audit exit codes: 0 for no error-severity
findings, 1 for error-severity findings, and 2 for usage or tool errors.

## 5. Success Criteria

### Measurable Outcomes

- SC-001: AI-authored staged changes without a valid gate session fail the local
  pre-commit fixture.
- SC-002: Every task kind, including `manager`, fails without issue linkage.
- SC-003: Only the four ADR-042 personas are accepted.
- SC-004: `human-authored` bypass is valid only when applied by an authorized
  maintainer or administrator and does not bypass quality checks.
- SC-005: Protected core changes fail without administrator authorization.
- SC-006: CI weakening fixtures fail when required checks or thresholds are
  removed or weakened.
- SC-007: AI merge-attempt fixtures fail without `admin-approved:merge`.
- SC-008: `complete_artifacts` and `codemod_lint` apply human-label bypass only
  to AI-only requirements.

## 6. Assumptions

- GitHub metadata is available in CI for label, review, and actor-permission
  validation.
- Local pre-commit cannot prove human authorship before a PR exists; CI remains
  the source of truth for human bypass.
- Runtime config parity may start with `.agents/**` as the shared source and
  runtime-specific roots as mirrors or pointers.
- `committer_enforce` remains deferred until the owner defines an approved AI
  commit path that can be checked reliably.
