---
title: "Alpha Release Audit 20260621 Dispatch Prompts"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Alpha Release Audit 20260621 Dispatch Prompts

These prompts are filled from:

- `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
- `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

All agents must save a report under the assigned `docs/audit/2026-06-21-alpha-release-*` path. Reports must classify findings as:

- P0: alpha release block.
- P1: alpha can pass only after must-fix remediation or explicit owner risk acceptance.
- P2: alpha can pass; good to fix before broader testing.
- P3: improvement or polish.

Shared alpha standard:

- Read `docs/audit/2026-06-21-alpha-release-criteria.md`.
- Alpha is non-production, short-lived testing, and may carry breaking changes.
- Package and extension content completeness is out of scope unless it breaks core startup, import, execution, or release evidence.
- Core runtime readiness is in scope.

## A1-runtime-engine

```markdown
[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: with-context
- Issue: #1733
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1733
- Owner request: Audit latest remote core runtime readiness for a small internal alpha release in two weeks.
- Umbrella PR: pending `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/alpha-release-audit-20260621
- Audit branch: manager-spawned
- Audit worktree: agent workspace
- Gate record: .workflow/records/1733-alpha-release-audit.json
- Checklist: docs/planning/alpha-release-audit-20260621-checklist.md
- PRs or commits to audit: origin/main at 1948ab2c and current umbrella branch evidence
- Audit report path: docs/audit/2026-06-21-alpha-release-runtime-engine.md

## Required Reading

Read and follow:

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/personas/audit-reviewer.md
- docs/audit/2026-06-21-alpha-release-criteria.md
- docs/planning/alpha-release-audit-20260621-checklist.md
- docs/planning/alpha-release-audit-20260621-dispatch-prompts.md#A1-runtime-engine
- Governing ADRs/specs/docs discovered from the audited files.

## Audit Goal

Audit whether the core workflow runtime can qualify for alpha: graph validation, scheduler/run lifecycle, block terminal states, cancellation/error behavior, event/state truth, and minimal representative workflow execution.

## Scope

Audit these surfaces:

- src/scistudio/workflow/**
- src/scistudio/engine/**
- runtime-facing block lifecycle code under src/scistudio/blocks/**
- tests/workflow/**, tests/engine/**, tests/integration/** where relevant
- docs/specs, docs/architecture, and ADRs that govern workflow runtime behavior

Do not write feature code.
MUST write only docs/audit/2026-06-21-alpha-release-runtime-engine.md.
Package and extension content completeness is out of scope unless it breaks core runtime.

## Checks

Run or verify targeted commands that materially support the audit, for example relevant pytest subsets, import probes, or static searches. Do not use pip install -e.

## Output Required

- Findings ordered by P0/P1/P2/P3.
- Evidence with file paths, line references, and command results.
- Missing tests/docs/gate evidence.
- Recommendation: block, pass-with-must-fix, pass, or pass-with-good-to-fix.
```

## A2-contracts-storage

```markdown
[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: with-context
- Issue: #1733
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1733
- Owner request: Audit latest remote core runtime readiness for a small internal alpha release in two weeks.
- Umbrella PR: pending `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/alpha-release-audit-20260621
- Audit branch: manager-spawned
- Audit worktree: agent workspace
- Gate record: .workflow/records/1733-alpha-release-audit.json
- Checklist: docs/planning/alpha-release-audit-20260621-checklist.md
- PRs or commits to audit: origin/main at 1948ab2c and current umbrella branch evidence
- Audit report path: docs/audit/2026-06-21-alpha-release-contracts-storage-lineage.md

## Required Reading

Read and follow AGENTS.md, common AI rules, audit reviewer persona, the manager checklist, and docs/audit/2026-06-21-alpha-release-criteria.md.

## Audit Goal

Audit whether core contracts and persistence are alpha-ready: block contract shape, schemas, artifact storage, lineage, serialization, workflow versioning, and data integrity for representative core execution.

## Scope

Audit these surfaces:

- src/scistudio/blocks/**
- src/scistudio/core/**
- src/scistudio/qa/schemas/** when it governs runtime artifacts
- tests/blocks/**, tests/core/**, tests/contracts/**, tests/workflow/** where relevant
- docs/specs, docs/architecture, and ADRs for block contracts, storage, lineage, and versioning

Do not write feature code.
MUST write only docs/audit/2026-06-21-alpha-release-contracts-storage-lineage.md.
Package and extension content completeness is out of scope unless it breaks core runtime.

## Checks

Run or verify targeted commands that materially support the audit. Do not use pip install -e.

## Output Required

- Findings ordered by P0/P1/P2/P3.
- Evidence with file paths, line references, and command results.
- Missing tests/docs/gate evidence.
- Recommendation.
```

## A3-api-desktop-ai

```markdown
[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: with-context
- Issue: #1733
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1733
- Owner request: Audit latest remote core runtime readiness for a small internal alpha release in two weeks.
- Umbrella PR: pending `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/alpha-release-audit-20260621
- Audit branch: manager-spawned
- Audit worktree: agent workspace
- Gate record: .workflow/records/1733-alpha-release-audit.json
- Checklist: docs/planning/alpha-release-audit-20260621-checklist.md
- PRs or commits to audit: origin/main at 1948ab2c and current umbrella branch evidence
- Audit report path: docs/audit/2026-06-21-alpha-release-api-desktop-ai.md

## Required Reading

Read and follow AGENTS.md, common AI rules, audit reviewer persona, the manager checklist, and docs/audit/2026-06-21-alpha-release-criteria.md.

## Audit Goal

Audit whether runtime-facing API, desktop bridge, manual review, and AI orchestration boundaries are alpha-ready and keep backend/runtime as workflow truth.

## Scope

Audit these surfaces:

- src/scistudio/api/**
- src/scistudio/desktop/**
- src/scistudio/ai/**
- frontend runtime bridge files only when needed to verify backend-truth semantics
- tests/api/**, tests/desktop/**, tests/ai/**, tests/e2e/** where relevant
- ADRs/specs/docs for manual review, AI orchestration, runtime API, and desktop MVP

Do not write feature code.
MUST write only docs/audit/2026-06-21-alpha-release-api-desktop-ai.md.
UI polish and package/extension content completeness are out of scope unless they break core runtime.

## Checks

Run or verify targeted commands that materially support the audit. Do not use pip install -e.

## Output Required

- Findings ordered by P0/P1/P2/P3.
- Evidence with file paths, line references, and command results.
- Missing tests/docs/gate evidence.
- Recommendation.
```

## A4-test-ci-governance

```markdown
[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio
- Persona: test_engineer
- Audit mode: with-context
- Issue: #1733
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1733
- Owner request: Audit latest remote core runtime readiness for a small internal alpha release in two weeks.
- Umbrella PR: pending `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/alpha-release-audit-20260621
- Audit branch: manager-spawned
- Audit worktree: agent workspace
- Gate record: .workflow/records/1733-alpha-release-audit.json
- Checklist: docs/planning/alpha-release-audit-20260621-checklist.md
- PRs or commits to audit: origin/main at 1948ab2c and current umbrella branch evidence
- Audit report path: docs/audit/2026-06-21-alpha-release-test-ci-governance.md

## Required Reading

Read and follow:

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/personas/test-engineer.md
- docs/ai-developer/specific_rules/test-engineering.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/audit/2026-06-21-alpha-release-criteria.md

## Audit Goal

Audit test, CI, governance, gate ledger, audit tooling, and Sentrux posture for alpha readiness. Identify whether existing evidence can support a small internal alpha of the core runtime.

## Scope

Audit these surfaces:

- tests/**
- .github/workflows/**
- .workflow/**
- scripts/audit/** and scripts/scistudio_pr_create.py
- src/scistudio/qa/**
- docs/audit/**, docs/planning/**, and release/governance docs relevant to evidence

Do not edit production code.
MUST write only docs/audit/2026-06-21-alpha-release-test-ci-governance.md.

## Checks

Run or verify feasible CI-equivalent or representative checks. If a full check is too expensive or blocked, record the exact blocker and the minimal command evidence that was run.

## Output Required

- Findings ordered by P0/P1/P2/P3.
- Test and check commands with pass/fail/blocked status.
- Missing release evidence and gate/CI risks.
- Recommendation.
```

## A5-docs-spec-drift

```markdown
[DISPATCH-TEMPLATE-V1: audit-no-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: no-context
- Audit branch: manager-spawned
- Audit worktree: agent workspace
- Allowed audit surfaces:
  - docs/adr/**
  - docs/specs/**
  - docs/architecture/**
  - docs/block-development/**
  - src/scistudio/workflow/**
  - src/scistudio/engine/**
  - src/scistudio/blocks/**
  - src/scistudio/core/**
  - src/scistudio/api/**
  - src/scistudio/ai/**
  - tests/**
- Audit report path: docs/audit/2026-06-21-alpha-release-docs-spec-drift.md

## Context Limits

You must not read or use:

- The current owner request.
- The current GitHub issue.
- Manager checklist files for the current work.
- Dispatch prompts for the current work.
- PR descriptions, PR comments, or commit messages for the current work.
- Chat summaries or manager summaries of what changed.

You may read only repository docs, repository code, tests, committed generated facts or audit outputs, and tool output from commands you run yourself.

## Required Reading

Read and follow:

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/personas/audit-reviewer.md
- Governing ADRs, specs, and docs discovered from the allowed audit surfaces.

## Audit Goal

Independently check whether core runtime docs, specs, ADRs, code, and tests agree. Do not assume manager intent.

## Coordination

- MUST NOT edit implementation files.
- MUST NOT edit the manager checklist.
- MUST write only docs/audit/2026-06-21-alpha-release-docs-spec-drift.md.

## Checks

Run or verify targeted static searches, docs/test drift checks, or lightweight tests that materially support the audit. Do not use pip install -e.

## Output Required

- Findings ordered by severity.
- Evidence from docs, code, tests, or tool output.
- No statement about manager intent unless visible in repository docs.
- Recommendation.
```

## A6-security-ops

```markdown
[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: with-context
- Issue: #1733
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1733
- Owner request: Audit latest remote core runtime readiness for a small internal alpha release in two weeks.
- Umbrella PR: pending `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/alpha-release-audit-20260621
- Audit branch: manager-spawned
- Audit worktree: agent workspace
- Gate record: .workflow/records/1733-alpha-release-audit.json
- Checklist: docs/planning/alpha-release-audit-20260621-checklist.md
- PRs or commits to audit: origin/main at 1948ab2c and current umbrella branch evidence
- Audit report path: docs/audit/2026-06-21-alpha-release-security-ops.md

## Required Reading

Read and follow AGENTS.md, common AI rules, audit reviewer persona, the manager checklist, and docs/audit/2026-06-21-alpha-release-criteria.md.

## Audit Goal

Audit core runtime security and operational readiness for internal alpha: path handling, project isolation, subprocess/PTY boundaries, secret/log leakage risk, artifact/data integrity, local service startup/shutdown, and failure diagnostics.

## Scope

Audit these surfaces:

- src/scistudio/api/**
- src/scistudio/desktop/**
- src/scistudio/ai/**
- src/scistudio/engine/**
- src/scistudio/core/**
- src/scistudio/cli/**
- tests/security-like, tests/api, tests/desktop, tests/ai, tests/engine, tests/core where relevant
- security, governance, and operational docs discovered from code/docs

Do not write feature code.
MUST write only docs/audit/2026-06-21-alpha-release-security-ops.md.
Package and extension content completeness is out of scope unless it breaks core runtime or security posture.

## Checks

Run or verify targeted commands that materially support the audit. Do not use pip install -e.

## Output Required

- Findings ordered by P0/P1/P2/P3.
- Evidence with file paths, line references, and command results.
- Missing tests/docs/gate evidence.
- Recommendation.
```
