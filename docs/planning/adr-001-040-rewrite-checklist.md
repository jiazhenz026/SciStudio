---
title: "ADR-001 Through ADR-040 Rewrite Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# ADR-001 Through ADR-040 Rewrite Checklist

> Mandatory manager checklist for the owner-guided ADR rewrite.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Rewrite ADR-001 through ADR-040 one by one under the ADR-042
  document standard.
- Task kind: `docs`
- Manager persona: `manager`
- Issue: `#1289`
- Gate record: `.workflow/records/1289-adr-001-040-rewrite.json` (pending)
- Branch/worktree plan:
  `hotfix/rewrite-adr-001-040` at
  `C:/Users/jiazh/Desktop/workspace/SciEasy.wt/hotfix-rewrite-adr-001-040`
- Protected branch: `main`
- Umbrella branch: `hotfix/rewrite-adr-001-040`
- Umbrella PR: pending dedicated ADR rewrite PR
- Current prep PR: `#1295` for audit coverage and legacy workflow cleanup
- Final PR target: `main`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - Split `docs/adr/ADR_legacy.md` so ADR-001 through ADR-030 each has a
    standalone `docs/adr/ADR-<NNN>.md` file.
  - Normalize existing standalone ADR-031 through ADR-040 files to the ADR-042
    frontmatter and required first-section structure.
  - Preserve historical decisions, status, dates, alternatives, and tradeoffs
    unless the owner explicitly changes intent during review.
  - Make code and function signatures auditable when an ADR has normative code
    contracts.
  - Preserve the original mega-document as `docs/adr/ADR_legacy.md` for
    detailed historical reference while standalone ADR files become the
    governing targets.
- Out of scope:
  - Changing runtime behavior or source code for ADR content alignment.
  - Reinterpreting historical decisions without owner approval.
  - Broad link rewrites before the target standalone ADR exists.
  - Sentrux or CI rule changes.
  - Audit governance code changes, except the owner-authorized `legacy` ADR
    phase support added to keep historical ADRs out of active spec-alignment
    requirements.
- Protected paths:
  - Runtime source and CI/governance files are out of scope unless the owner
    separately authorizes a scoped fix.
- Deferred work:
  - N/A. Any new deferral must cite an issue, ADR, spec, PR, or follow-up ticket.

## 3. Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Every completed row MUST include an artifact:
  PR link, commit, test command, report path, gate-record entry, or owner review
  note.
- Chat messages are not checklist evidence.
- Scope changes require gate-record amendment before work continues.
- ADRs are reviewed one by one with the owner before moving to the next ADR.

## 4. Rewrite Rules

- Preserve the original decision unless owner review explicitly changes it.
- Use ADR-042-style frontmatter for every target ADR.
- Keep `agent_editable: false` unless the owner explicitly approves otherwise.
- Use `status: Accepted`, `Proposed`, `Superseded`, or `Deprecated` as
  appropriate for the historical decision.
- Include `tracking_issue: 1289` when no more specific issue owns the rewrite.
- If an ADR governs code, list auditable symbols under `governs.contracts`.
- If an ADR includes normative code or function signatures, place them under a
  `Signature-Level Contracts` section and use exact importable symbols.
- Put illustrative-only code under `Non-Normative Example` so audit does not
  treat it as a contract.
- Run frontmatter lint for each ADR before marking owner review complete.
- Run full audit and signature drift after each accepted batch.

## 5. Manager Preflight

- [x] Dedicated manager branch and worktree identified. -> branch
  `hotfix/rewrite-adr-001-040`
- [x] Existing issue linked. -> #1289
- [x] Gate record started. -> `.workflow/records/1289-adr-001-040-rewrite.json`
- [x] Scope include/exclude recorded in the gate record.
- [x] Source mega-document identified and renamed for reference. ->
  `docs/adr/ADR_legacy.md`
- [x] Existing standalone ADR range identified. -> `docs/adr/ADR-031.md`
  through `docs/adr/ADR-040.md`
- [ ] Umbrella/dedicated ADR rewrite PR opened.
- [ ] No `pip install -e .` environment pollution found.
- [x] Dispatch checklist copied from the template. -> this file
- [ ] Sentrux baseline recorded, or N/A reason recorded.

## 6. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scieasy.qa.governance.gate_record pre-commit --staged` | `N/A` | `[ ]` | pending |
| Commit message | `python -m scieasy.qa.governance.gate_record commit-msg <commit-msg-file>` | `N/A` | `[ ]` | pending |
| Pre-push | `python -m scieasy.qa.governance.gate_record pre-push` | `N/A` | `[ ]` | pending |

## 7. Dispatch Matrix

No agents are dispatched yet. The current mode is owner-guided, one-ADR-at-a-time
rewrite and review.

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| manager | manager | N/A | N/A | Maintain checklist and sequence owner review | `hotfix/rewrite-adr-001-040` | dedicated hotfix worktree | `docs/planning/adr-001-040-rewrite-checklist.md` | ADR body rewrite until owner selects an ADR | #1289 | `[~]` |

## 8. Global Tracks

### 8.1 Track A - ADR-001 Through ADR-030 Extraction

- Owner: `manager` until owner dispatches ADR authors.
- In scope:
  - Extract each ADR from `docs/adr/ADR_legacy.md`.
  - Normalize frontmatter and required first sections.
  - Preserve source content while improving structure, traceability, and audit
    contract placement.
- Out of scope:
  - Deletion of `docs/adr/ADR_legacy.md`; owner directed it to remain as the
    detailed reference.
- Required docs:
  - `docs/adr/ADR-001.md` through `docs/adr/ADR-030.md`
- Required checks:
  - Per-ADR frontmatter lint.
  - Batch full audit.
  - Batch signature drift check when any ADR has normative signatures.

### 8.2 Track B - ADR-031 Through ADR-040 Normalization

- Owner: `manager` until owner dispatches ADR authors.
- In scope:
  - Normalize the existing standalone files.
  - Preserve current body content unless owner review changes intent.
  - Add ADR-042-compatible frontmatter and first-section structure.
- Out of scope:
  - Runtime implementation of any ADR-031 through ADR-040 decision.
- Required docs:
  - `docs/adr/ADR-031.md` through `docs/adr/ADR-040.md`
- Required checks:
  - Per-ADR frontmatter lint.
  - Batch full audit.
  - Batch signature drift check when any ADR has normative signatures.

### 8.3 Track C - ADR Legacy Decomposition Closure

- Owner: `manager`
- In scope:
  - Verify every ADR-001 through ADR-030 section has a standalone successor.
  - Preserve the mega-document as `docs/adr/ADR_legacy.md` after owner
    approval.
  - Check inbound links and update links intentionally.
- Out of scope:
  - Blind repository-wide string replacement without checking target context.
- Required docs:
  - `docs/adr/ADR_legacy.md` final disposition.
- Required checks:
  - Link/closure audit.
  - Full audit.

## 9. ADR Rewrite Matrix

| ADR | Source | Target | Rewrite status | Owner review | Audit notes |
|---|---|---|---|---|---|
| ADR-001: Six base data types with inheritance | `docs/adr/ADR_legacy.md`; draft exists | `docs/adr/ADR-001.md` | `[x]` | `[x]` | Owner approved; frontmatter lint pass; ADR-001 signature drift smoke pass |
| ADR-002: Named axes on Array types | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-002.md` | `[x]` | `[x]` | Owner approved; captures ADR-027 axes refinement; frontmatter lint pass; ADR-002 signature drift smoke pass |
| ADR-003: Broadcast as explicit utility, not implicit type-system behaviour | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-003.md` | `[x]` | `[x]` | Owner approved; frontmatter lint pass; ADR-003 signature drift smoke pass |
| ADR-004: Five block categories plus SubWorkflowBlock | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-004.md` | `[x]` | `[x]` | Owner approved; batch frontmatter lint pass; batch signature drift smoke pass |
| ADR-005: CodeBlock supports inline and script execution modes | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-005.md` | `[x]` | `[x]` | Owner approved; notes ADR-041 CodeBlock v2 narrowing; batch frontmatter lint pass; batch signature drift smoke pass |
| ADR-006: External software integration via file-exchange bridge | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-006.md` | `[x]` | `[x]` | Owner approved; batch frontmatter lint pass; batch signature drift smoke pass |
| ADR-007: Lazy loading by default via ViewProxy | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-007.md` | `[x]` | `[x]` | Owner approved; notes ADR-031 ViewProxy elimination; batch frontmatter lint pass; batch signature drift smoke pass |
| ADR-008: Two-tier block and type distribution | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-008.md` | `[x]` | `[x]` | Owner approved; batch frontmatter lint pass; batch signature drift smoke pass |
| ADR-009: Registry stores specs, not class references | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-009.md` | `[x]` | `[x]` | Owner approved; batch frontmatter lint pass; batch signature drift smoke pass |
| ADR-010: Batch execution mode declared per block | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-010.md` | `[x]` | `[x]` | Owner approved; rewritten as Superseded by ADR-020; batch frontmatter lint pass; inactive ADR skipped by signature extraction |
| ADR-011: Workflow definition as declarative YAML, decoupled from frontend | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-011.md` | `[x]` | `[x]` | Owner approved; batch frontmatter lint pass; batch signature drift smoke pass |
| ADR-012: Checkpoint-based pause and resume | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-012.md` | `[x]` | `[x]` | Owner approved; batch frontmatter lint pass; batch signature drift smoke pass |
| ADR-013: AI as a four-tier service layer, not embedded in the core | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-013.md` | `[x]` | `[x]` | Owner approved; batch frontmatter lint pass; batch signature drift smoke pass |
| ADR-014: ReactFlow + FastAPI as the frontend-backend stack | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-014.md` | `[x]` | `[x]` | Owner approved; notes ADR-039 project state update; batch frontmatter lint pass; batch signature drift smoke pass |
| ADR-015: Inclusive strategy - wrap existing tools, never replace | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-015.md` | `[x]` | `[x]` | Owner approved; batch frontmatter lint pass; batch signature drift smoke pass |
| ADR-016: Per-port InputDelivery for CodeBlock data handoff | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-016.md` | `[x]` | `[x]` | Owner approved; rewritten as Superseded by ADR-020; batch frontmatter lint pass; inactive ADR skipped by signature extraction |
| ADR-017: Subprocess isolation for all block execution | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-017.md` | `[x]` | `[x]` | Owner approved; detailed rewrite; frontmatter lint pass; signature/doc drift smoke pass |
| ADR-018: Block cancellation, graceful workflow degradation, and event-driven runtime | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-018.md` | `[x]` | `[x]` | Owner approved; detailed rewrite including scheduler concurrency clarification; frontmatter lint pass; signature/doc drift smoke pass |
| ADR-019: ProcessHandle, ProcessRegistry, and cross-platform process lifecycle | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-019.md` | `[x]` | `[x]` | Owner approved; detailed rewrite preserving historical Proposed status; frontmatter lint pass; signature/doc drift smoke pass |
| ADR-020: Collection-based data transport - eliminate engine-level batch iteration | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-020.md` | `[x]` | `[x]` | Owner approved; detailed rewrite; frontmatter lint pass; signature/doc drift smoke pass |
| ADR-021: MergeCollection and Collection operation blocks | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-021.md` | `[x]` | `[x]` | Owner approved; frontmatter lint pass; targeted full-audit findings 0 |
| ADR-022: OS-level memory monitoring replaces estimated memory budget | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-022.md` | `[x]` | `[x]` | Owner approved; frontmatter lint pass; targeted full-audit findings 0 |
| ADR-023: Frontend layout redesign | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-023.md` | `[x]` | `[x]` | Owner approved; frontmatter lint pass; targeted full-audit findings 0 |
| ADR-024: Frontend bundling, SPA serving, and `scieasy gui` command | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-024.md` | `[x]` | `[x]` | Owner approved; frontmatter lint pass; targeted full-audit findings 0 |
| ADR-025: Block package distribution protocol with entry-points | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-025.md` | `[x]` | `[x]` | Owner approved; frontmatter lint pass; targeted full-audit findings 0 |
| ADR-026: Block SDK - scaffolding, test harness, and developer documentation | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-026.md` | `[x]` | `[x]` | Owner approved; frontmatter lint pass; targeted full-audit findings 0 |
| ADR-027: Phase 10 core type system and block runtime refinements | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-027.md` | `[x]` | `[x]` | Owner approved; deprecated Addendum 1 preserved and ADR-031 supersession note; frontmatter lint pass; targeted full-audit findings 0 |
| ADR-028: IOBlock architectural refactor - plugin-owned IO pattern | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-028.md` | `[x]` | `[x]` | Owner approved; Addendum 1 folded in and D3 supersession noted; frontmatter lint pass; targeted full-audit findings 0 |
| ADR-029: Variadic port count and per-instance port editor | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-029.md` | `[x]` | `[x]` | Owner approved; Addendum 1 port-count limits; frontmatter lint pass; targeted full-audit findings 0 |
| ADR-030: config_schema MRO merge and base-class field injection | `docs/adr/ADR_legacy.md` | `docs/adr/ADR-030.md` | `[x]` | `[x]` | Owner approved; frontmatter lint pass; targeted full-audit findings 0 |
| ADR-031: Data Object Reference-Only Contract, ViewProxy Elimination, and Lazy Loading Enforcement | standalone legacy file | `docs/adr/ADR-031.md` | `[ ]` | `[ ]` | Normalize frontmatter; preserve ADR-007/017/027 links |
| ADR-032: Project-Level Metadata Store - SQLite Persistent Mirror of DataObject Metadata | standalone legacy file | `docs/adr/ADR-032.md` | `[ ]` | `[ ]` | Normalize frontmatter; check storage contracts |
| ADR-033: Embedded Coding Agent via Claude Code / Codex Subprocess | standalone legacy file | `docs/adr/ADR-033.md` | `[ ]` | `[ ]` | Preserve supersession relationship with ADR-034 |
| ADR-034: Embedded Coding Agent UI - PTY + Terminal Embed | standalone legacy file | `docs/adr/ADR-034.md` | `[ ]` | `[ ]` | Normalize PTY/UI contracts |
| ADR-035: AI Block as a PTY-tab variant of AppBlock | standalone legacy file | `docs/adr/ADR-035.md` | `[ ]` | `[ ]` | Preserve proposed/accepted status accurately |
| ADR-036: Embedded code editor for project files | standalone legacy file | `docs/adr/ADR-036.md` | `[ ]` | `[ ]` | Normalize editor scope and safety boundaries |
| ADR-037: Desktop Application Packaging, Plugin Distribution, and First-Run Dependency Management | standalone legacy file | `docs/adr/ADR-037.md` | `[ ]` | `[ ]` | Check packaging contracts and external tool claims |
| ADR-038: Unified Run Lineage Database - Reproducibility through Recipe, Not Storage | standalone legacy file | `docs/adr/ADR-038.md` | `[ ]` | `[ ]` | Normalize lineage schema contracts |
| ADR-039: Git-Backed Source Version Control for SciEasy Projects | standalone legacy file | `docs/adr/ADR-039.md` | `[ ]` | `[ ]` | Normalize git/project boundary contracts |
| ADR-040: Production-environment agent reliability | standalone legacy file | `docs/adr/ADR-040.md` | `[ ]` | `[ ]` | Normalize prod-agent contracts; keep dev/prod boundary explicit |

## 10. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Per-ADR frontmatter | `python -m scieasy.qa.audit.frontmatter_lint docs/adr/ADR-<NNN>.md --format text` | `[x]` | ADR-001 through ADR-016 passed after `phase: legacy` update |
| Signature drift | `PYTHONPATH=src python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` | `[!]` | Full audit still fails on known pre-existing ADR-031..040/spec/architecture/signature debt; ADR-001 through ADR-016 no longer emit `doc-drift.adr-without-implementation-spec` |
| Per-ADR frontmatter | `PYTHONPATH=src python -m scieasy.qa.audit.frontmatter_lint docs/adr/ADR-026.md docs/adr/ADR-027.md docs/adr/ADR-028.md docs/adr/ADR-029.md docs/adr/ADR-030.md --format text` | `[x]` | ADR-026 through ADR-030 passed |
| Targeted full audit | `PYTHONPATH=src python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` | `[!]` | ADR-026 through ADR-030 targeted findings 0; overall audit remains red on pre-existing ADR-031..040/spec/architecture debt |
| Legacy source rename | `Test-Path docs/adr/ADR.md; Test-Path docs/adr/ADR_legacy.md` | `[x]` | `ADR.md` absent; `ADR_legacy.md` present as owner-approved detailed reference |
| Sentrux | `mcp__sentrux__.rescan` plus `mcp__sentrux__.check_rules` | `[ ]` | pending or N/A if docs-only rules do not apply |
| Link/closure audit | full audit closure check | `[ ]` | pending |
| Gate record CI | `python -m scieasy.qa.governance.gate_record ci ...` | `[ ]` | pending |

## 11. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-05-20 | manager | Main checkout is dirty and behind origin/main | Use dedicated hotfix worktree only | N/A |
| 2026-05-20 | manager | Full audit reported `doc-drift.adr-without-implementation-spec` for historical ADRs | Owner authorized `phase: legacy`; add ADR-042/spec/schema/doc_drift/tests support and mark ADR-001 through ADR-016 legacy | Continue ADR-017+ rewrite with `legacy` unless owner selects another phase |
| 2026-05-20 | manager | `docs/adr/ADR.md` still acted as the historical mega-document | Owner approved preserving it as `docs/adr/ADR_legacy.md` for detailed reference; standalone ADRs are governing targets | Keep `ADR_legacy.md` as reference only while normalizing ADR-031 through ADR-040 |

## 12. Final Readiness

- [ ] All ADR-001 through ADR-030 sections have standalone files.
- [ ] ADR-031 through ADR-040 are normalized to ADR-042 document standard.
- [x] `docs/adr/ADR_legacy.md` is retained as detailed reference and no longer
      acts as the governing mega-document.
- [ ] Every ADR with normative signatures has auditable `governs.contracts`
      entries and a `Signature-Level Contracts` section.
- [ ] Every ADR has owner review evidence.
- [ ] Gate record includes issue, scope, plan, docs, checks, Sentrux evidence or
      N/A rationale, commit, and PR evidence.
- [ ] PR closes #1289.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
