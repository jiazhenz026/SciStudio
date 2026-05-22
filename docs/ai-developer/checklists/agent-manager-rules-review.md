---
title: "AI Developer Documentation Checklist"
status: Approved
owners: ["@jiazhenz026"]
related_adrs: [42]
language_source: en
---

# AI Developer Documentation Checklist

## 1. Change Summary

This checklist tracks the compact AI-developer documentation set required for
the current drafting round. It is a manager-facing planning document: it records
which documents we intend to write, what each document owns, and which open
decisions must be settled before the document becomes canonical.

Owner decision for this drafting round: AI-only operational docs should live
under `docs/ai-developer/**` rather than `docs/contributing/**`, so human
contributors do not mistake AI harness procedures for human rules.
Human-facing contributor docs may point to `docs/ai-developer/**`, but should
not duplicate AI-only policy.

## 2. Document Set Checklist

### 2.1 Canonical Policy And Runtime Entry Points

| Status | Path | Purpose | ADR basis | Notes |
|---|---|---|---|---|
| Drafted | `AGENTS.md` | Canonical hard policy entry point for all AI agents | ADR-042 Section 7.4 root policy; Addendum 1 gate supersession | Single hard-policy source and points to the docs below. |
| Drafted | `CLAUDE.md` | Claude runtime pointer | ADR-042 Section 7.4 runtime config parity | Short pointer to `AGENTS.md` and `docs/ai-developer/**`. |
| Approved | `.agents/rules/rules.md` | Runtime-neutral AI rules pointer | ADR-042 Section 7.4 AI-agnostic runtime config | Pointer only; no independent policy. |
| Approved | `.claude/rules/rules.md` | Claude runtime rule pointer | ADR-042 Section 7.4; `skill_pointer_sync` | Runtime mechanics only; no independent policy. |
| Approved | `.codex/rules/rules.md` | Codex runtime rule pointer | ADR-042 Section 7.4 runtime parity | Mirrors Claude pointer at equivalent fidelity. |

### 2.2 Canonical AI Developer Docs

| Status | Path | Purpose | ADR basis | Notes |
|---|---|---|---|---|
| Approved | `docs/ai-developer/rules.md` | Common AI developer rules for all personas | ADR-042 Section 7 AI governance; Addendum 1 | Shared AI-specific rules before routing into specific rule or persona docs. |

### 2.3 AI Specific Rule Docs

| Status | Path | Purpose | ADR basis | Notes |
|---|---|---|---|---|
| Approved | `docs/ai-developer/specific_rules/gated-workflow.md` | General six-stage AI gated rule | Addendum 1 Section 3.1 | Scope And Issue, Plan, Implement, Update Docs, Test And Checks, Commit And Submit PR. |
| Approved | `docs/ai-developer/specific_rules/document-standards.md` | ADR-042 document standards reference | ADR-042 Sections 3.2-3.6 | Contains the copied ADR-042 reference excerpt for agent use. |
| Approved | `docs/ai-developer/specific_rules/new-feature.md` | AI feature-specific rules | ADR-042 task kind `feature`; SpecKit integration | Explains when SpecKit, spec, and ADR are required before implementation. |
| Approved | `docs/ai-developer/specific_rules/bug-fix.md` | AI bugfix-specific rules | ADR-042 task kind `bugfix`; Appendix C spirit | Covers reproduction, scope, regression tests, and separate issues for unrelated bugs. |
| Approved | `docs/ai-developer/specific_rules/hotfix.md` | AI hotfix-specific rules | AGENTS hotfix mode; ADR-042 task kind `hotfix`; Addendum 1 | Preserves architectural reread requirements and retroactive gate record. |
| Approved | `docs/ai-developer/specific_rules/docs-change.md` | AI documentation-specific rules | ADR-042 task kind `docs`; documentation normalization | Covers truth, document type, scope, frontmatter, audit, and N/A rationales. |
| Approved | `docs/ai-developer/specific_rules/agent-dispatch.md` | Multi-agent manager-specific rules | ADR-042 persona `manager`; current agent-manager discipline | Should include sub-agent scope, disjoint write sets, TODO tracking, and review. |
| Approved | `docs/ai-developer/specific_rules/test-engineering.md` | AI test-engineering-specific rules | ADR-042 Addendum 4 persona `test_engineer` | Covers test architecture, tests, runtime validation, e2e evidence, and production-code stop conditions. |

### 2.4 Persona Docs

| Status | Path | Purpose | ADR basis | Notes |
|---|---|---|---|---|
| Approved | `docs/ai-developer/personas/manager.md` | Manager persona behavior | ADR-042 Section 7.3 | Coordinates agents, checklist status, scope boundaries, PR readiness. |
| Approved | `docs/ai-developer/personas/implementer.md` | Implementer persona behavior | ADR-042 Section 7.3 | Implements scoped code/docs/tests under gate record. |
| Approved | `docs/ai-developer/personas/adr-author.md` | ADR/spec author behavior | ADR-042 Section 7.3 and Section 3 schemas | Writes governance text without bypassing schemas or owner decisions. |
| Approved | `docs/ai-developer/personas/audit-reviewer.md` | Audit reviewer behavior | ADR-042 Section 7.3 | Review-only by default; finding-first reports; fix only when assigned. |
| Approved | `docs/ai-developer/personas/test-engineer.md` | Test engineer persona behavior | ADR-042 Addendum 4 | Designs tests, adds test artifacts, runs runtime validation/e2e, and stops before production fixes. |

### 2.5 Skill Documents

| Status | Path | Purpose | ADR basis | Notes |
|---|---|---|---|---|
| Approved | `.agents/skills/manager/SKILL.md` | Runtime-neutral manager persona skill pointer | ADR-042 Section 7.3 and Section 7.4 | Points to `rules.md`, `personas/manager.md`, and `specific_rules/agent-dispatch.md`. |
| Approved | `.agents/skills/implementer/SKILL.md` | Runtime-neutral implementer persona skill pointer | ADR-042 Section 7.3 and Section 7.4 | Points to `rules.md`, `personas/implementer.md`, and `specific_rules/gated-workflow.md`. |
| Approved | `.agents/skills/adr-author/SKILL.md` | Runtime-neutral ADR author persona skill pointer | ADR-042 Section 7.3 and Section 7.4 | Points to `rules.md` and `personas/adr-author.md`. |
| Approved | `.agents/skills/audit-reviewer/SKILL.md` | Runtime-neutral audit reviewer persona skill pointer | ADR-042 Section 7.3 and Section 7.4 | Points to `rules.md` and `personas/audit-reviewer.md`. |
| Approved | `.claude/skills/manager/SKILL.md` | Claude manager persona skill pointer | ADR-042 Section 7.3 | Points to `rules.md`, `personas/manager.md`, and `specific_rules/agent-dispatch.md`. |
| Approved | `.claude/skills/implementer/SKILL.md` | Claude implementer persona skill pointer | ADR-042 Section 7.3 | Points to `rules.md`, `personas/implementer.md`, and `specific_rules/gated-workflow.md`. |
| Approved | `.claude/skills/adr-author/SKILL.md` | Claude ADR author persona skill pointer | ADR-042 Section 7.3 | Points to `rules.md` and `personas/adr-author.md`. |
| Approved | `.claude/skills/audit-reviewer/SKILL.md` | Claude audit reviewer persona skill pointer | ADR-042 Section 7.3 | Points to `rules.md` and `personas/audit-reviewer.md`. |
| Approved | `.codex/skills/manager/SKILL.md` | Codex manager persona skill pointer | ADR-042 Section 7.3 and Section 7.4 | Mirrors Claude manager skill at equivalent fidelity. |
| Approved | `.codex/skills/implementer/SKILL.md` | Codex implementer persona skill pointer | ADR-042 Section 7.3 and Section 7.4 | Mirrors Claude implementer skill at equivalent fidelity. |
| Approved | `.codex/skills/adr-author/SKILL.md` | Codex ADR author persona skill pointer | ADR-042 Section 7.3 and Section 7.4 | Mirrors Claude ADR author skill at equivalent fidelity. |
| Approved | `.codex/skills/audit-reviewer/SKILL.md` | Codex audit reviewer persona skill pointer | ADR-042 Section 7.3 and Section 7.4 | Mirrors Claude audit reviewer skill at equivalent fidelity. |
| Approved | `.agents/skills/test-engineer/SKILL.md` | Runtime-neutral test engineer persona skill pointer | ADR-042 Addendum 4 | Points to canonical test-engineer docs and rules. |
| Approved | `.claude/skills/test-engineer/SKILL.md` | Claude test engineer persona skill pointer | ADR-042 Addendum 4 | Mirrors runtime-neutral test engineer pointer at equivalent fidelity. |
| Approved | `.codex/skills/test-engineer/SKILL.md` | Codex test engineer persona skill pointer | ADR-042 Addendum 4 | Mirrors runtime-neutral test engineer pointer at equivalent fidelity. |

### 2.6 Templates

| Status | Path | Purpose | ADR basis | Notes |
|---|---|---|---|---|
| Approved | `docs/ai-developer/templates/agent-dispatch-checklist-template.md` | Agent dispatch checklist file template | ADR-042 manager checklist discipline | Manager copies this to `docs/planning/<scope>-checklist.md` before dispatch. |
| Approved | `docs/ai-developer/templates/agent-dispatch-prompt-template.md` | Agent dispatch work prompt template | ADR-042 manager persona routing | Manager uses this for non-audit dispatched agent prompts. |
| Approved | `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md` | Audit prompt with context | ADR-042 audit reviewer persona | Auditor may read issue, checklist, PRs, and claimed work. |
| Approved | `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md` | Audit prompt without context | ADR-042 audit reviewer persona | Auditor must not read current issue, checklist, PR claims, or manager summaries. |

## 3. Out Of Current Round

These topics may be referenced inside the compact docs above, but they are not
separate documents in this drafting round:

- `docs/ai-developer/index.md`;
- separate gate-record reference docs;
- separate runtime-pointer docs;
- separate human-boundary docs;
- maintenance-specific rules;
- PR-readiness-specific rules;
- human-facing bridge docs;
- examples for gate record, commit message, and PR body.

## 4. Open Decisions

- [x] Confirm `docs/ai-developer/**` as the AI-only documentation root even
      though ADR-042 originally mentioned `docs/contributing/workflows/**`.
- [x] Confirm `docs/ai-developer/specific_rules/gated-workflow.md` as the single
      place for gate-record workflow details in this round.
- [x] Decide whether `CLAUDE.md` should be reduced to a pointer in the same PR
      as the new AI docs.

## 5. Review Status Legend

| Status | Meaning |
|---|---|
| New | Document does not exist yet and is proposed by this checklist. |
| Drafted | Document exists as a draft and is ready for owner review. |
| Approved | Document exists and has owner approval for this drafting round. |
| Existing, revise | Document exists but must be aligned with ADR-042 pointer or gate rules. |
| Existing, review | Document exists and may need links or wording changes. |
| New or defer | Proposed document whose timing is an owner decision. |
| New or confirm | Proposed document whose location or existence needs owner confirmation. |
