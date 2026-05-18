---
title: "Phase 1.5 Pre-Checkpoint Cleanup Checklist"
phase: 1.5
status: active
date: 2026-05-18
relates_to:
  - ADR-042
  - ADR-043
  - ADR-044
tracks: "#1113"
agent_editable: true
---

# Phase 1.5 Pre-Checkpoint Cleanup Checklist

> Single source of truth for the cleanup waves that close out Phase 1
> before the owner records the §26.3 decision. Plan:
> `~/.claude/plans/polished-zooming-shell.md`.
>
> **Manager-maintained for Wave 1** (5 agents already in flight at file
> creation time). **Agent-edited from Wave 2 onward** if any further
> waves dispatch (per `agent-manager` skill).

## Conventions
- `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked
- Every tick MUST append `→ <PR-or-commit-link>` or `→ <test-name>`.
- Drift = protocol violation. Logged below.

## Wave 1 — Parallel implementation (5 agents)

### Track A — P1 CI-correctness fixes (Closes #1178 #1179 #1180 #1109)
Branch: `fix/phase-1-5-cleanup/p1-followups` → `consolidate/phase-1-preview`.
- [~] #1178 path_filter fail-closed → _<PR link>_
- [~] #1179 workflow_sync_check YAML walk → _<PR link>_
- [~] #1180 three-dot diff (weakened_ci_check + monotonic_check + path_filter) → _<PR link>_
- [~] #1109 BlockRegistry compound-extension fallback → _<PR link>_
- [~] Tests ≥95% branch coverage → _<test-name>_
- [~] Impl record `docs/audit/impl-records/track-a-<sha>.md` → _<commit>_

### Track B — 1E inherited CI failures (Closes #1174)
Branch: `fix/phase-1-5-cleanup/1e-ci-recovery` → `consolidate/phase-1-preview`.
- [~] Type Check (`callable` → `Callable`) → _<commit>_
- [~] Lint & Format (resolved by Type Check fix) → _<commit>_
- [~] recursive-self-check (`expanded-noqa-usage` false positives) → _<commit>_
- [~] Encoding hardening (`utf-8` + `errors='replace'`) → _<commit>_
- [~] Coordinated with Track A on `path_filter.py` → _<note>_
- [~] Impl record `docs/audit/impl-records/track-b-<sha>.md` → _<commit>_

### Track C — 1D Sphinx directives + 5 generators (Closes #1184)
Branch: `feat/phase-1-5-cleanup/1d-directives-generators` → `consolidate/phase-1-preview`.
- [~] TC-1D.3 `ScieasyBlockCatalog` directive body [ADR-044 §10.2] → _<commit>_
- [~] TC-1D.4a `ScieasyRunnerCatalog` directive body [§10.2] → _<commit>_
- [~] TC-1D.4b `ScieasyAIBlockCatalog` directive body [§10.2] → _<commit>_
- [~] TC-1D.5 `llms_txt.generate` generator [§10.3] → _<commit>_
- [~] TC-1D.5 wrap as Sphinx builder in `llms_txt_builder.py` → _<commit>_
- [~] TC-1D.6a `entry_point_catalog.generate` → _<commit>_
- [~] TC-1D.6b `cli_reference.generate` → _<commit>_
- [~] TC-1D.6c `openapi_reference.generate` → _<commit>_
- [~] TC-1D.6d `schema_reference.generate` → _<commit>_
- [~] Tests per ADR-044 §11.5 test list → _<test-names>_
- [~] `sphinx-build -b html docs/sphinx _build/html` succeeds → _<note>_
- [~] Impl record `docs/audit/impl-records/track-c-<sha>.md` → _<commit>_

### Track D1 — Doc skeletons: contributing/ + doc-guide/ (Closes #1185)
Branch: `feat/phase-1-5-cleanup/1d-skeletons-contributing` → `consolidate/phase-1-preview`.
- [x] `docs/contributing/index.md` (routing hub) → PR #1189
- [x] `docs/contributing/onboarding.md` → PR #1189
- [x] `docs/contributing/first-pr.md` → PR #1189
- [x] `docs/contributing/configuring-your-agent.md` → PR #1189
- [x] `docs/contributing/workflows/_template.md` + 6 workflow files → PR #1189
- [x] `docs/contributing/policy/ai-assistance.md` → PR #1189
- [x] `docs/contributing/reference/{gate-cli,trailer-conventions}.md` → PR #1189
- [x] `docs/contributing/handbooks/README.md` (placeholder) → PR #1189
- [x] `docs/doc-guide/` 3 files per ADR-044 §9.1 → PR #1189
- [!] `doc_length_lint` + `frontmatter_lint` + `auto_generated_lint` PASS → **DEFERRED** to Track C (lint modules raise NotImplementedError; activate when Track C ships full impls)
- [x] Impl record `docs/audit/impl-records/track-d1-b168037c.md` → PR #1189

### Track D2 — Doc skeletons: user/ + prod-agent/ (Closes #1186)
Branch: `feat/phase-1-5-cleanup/1d-skeletons-user-prod` → `consolidate/phase-1-preview`.
- [~] `docs/user/` 7 root files (index, install, quickstart, plugin-authoring, glossary, faq, prod-env-artifacts) → _<commit>_
- [~] `docs/user/user-guide/` 6 concept files → _<commit>_
- [~] `docs/user/tutorials/{01,02}/README.md` placeholders → _<commit>_
- [~] `docs/user/reference/{api,blocks,schemas}/.gitkeep` → _<commit>_
- [~] `docs/user/reference/{cli,server-api,entry-points}.md` (generated-marker stubs) → _<commit>_
- [~] `docs/user/llms.txt` placeholder → _<commit>_
- [~] `docs/prod-agent/README.md` per ADR-044 §8.2 → _<commit>_
- [~] `doc_length_lint` + `frontmatter_lint` + `auto_generated_lint` PASS → _<note>_
- [~] Impl record `docs/audit/impl-records/track-d2-<sha>.md` → _<commit>_

## Wave 2 — Sequential finalization (manager-led)

### Track F — First full-audit report
- [ ] `python -m scieasy.qa.audit.full_audit --self-check --output docs/audit/reports/<sha>/full.json` → _<artifact>_
- [ ] 0 critical findings (or 2 fix-iteration cycles to reach 0) → _<note>_
- [ ] `ci-implementability.json` artifact at same path → _<artifact>_
- [ ] PR `chore/phase-1-5-cleanup/first-full-audit` opens + merges → _<PR>_

### Track G — Brief refresh + temp_review decommission (Closes #1187)
Branch: `chore/phase-1-5-cleanup/brief-refresh-and-decommission`.
- [ ] Brief §3.1 deferred rows struck → _<commit>_
- [ ] Brief §3.2 marked resolved with Track F report link → _<commit>_
- [ ] Brief §3.3 marked resolved with Track B PR link → _<commit>_
- [ ] Brief §3.4 marked accepted-open → Phase 3 → _<commit>_
- [ ] Brief §5 upgraded "(a) Conditional" → "(a) Clean — recommended" → _<commit>_
- [ ] `git rm scripts/audit/temp_review.py` → _<commit>_
- [ ] `git rm tests/audit/test_temp_review.py` → _<commit>_
- [ ] `.pre-commit-config.yaml` temp-review hook removed → _<commit>_
- [ ] `.github/workflows/ci.yml` temp-review step removed → _<commit>_
- [ ] `docs/audit/decommission-log.md` final entry → _<commit>_

### Track H — Owner §26.3 decision unblock
- [ ] Manager posts recommendation summary on #1113 → _<comment URL>_
- [ ] Owner records decision in `docs/audit/phase-1-5-decisions.log` → _<commit>_
- [ ] Owner comments decision summary on #1113 → _<comment URL>_
- [ ] #1113 closes → _<event>_
- [ ] Phase 2 CI flip authorized → _<note>_

## Acceptance criteria (whole cleanup)
- [ ] All 5 Wave-1 PRs merged into `consolidate/phase-1-preview`.
- [ ] CI green on `consolidate/phase-1-preview` HEAD.
- [ ] `docs/audit/reports/<umbrella-sha>/full.json` exists with `critical=0`.
- [ ] `temp_review.py` + tests + hooks gone.
- [ ] Brief §5 says "(a) Clean — recommended".
- [ ] Owner decision recorded; #1113 closed.

## Drift log (append-only)
(empty until first violation)

## Notes
- Wave-1 agents were dispatched BEFORE this checklist existed (manager-side protocol error 2026-05-18). Manager will tick rows from agent task-notifications + PR URLs. From Wave 2 onward, agents edit their own rows per `agent-manager` skill convention.
- Per owner directive 2026-05-18, the per-sub-phase batched audit cadence catch-up (formerly "Track E") is intentionally skipped; deferred to Phase 3 cleanup sprint.
