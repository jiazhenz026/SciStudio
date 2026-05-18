# AGENTS.md

This is the canonical always-loaded instruction file for every agent runtime
working in SciEasy. It owns hard policy, architectural boundaries, and routing.
Procedures belong in skills, path-scoped rules, hooks, or contributor docs.

> FEATURE FREEZE: ADR-042/043/044 cascade implementation is frozen from
> 2026-05-18 until Phase 4 close. Allowed work: cascade cleanup-track work,
> shipped-regression bug fixes, explicit hotfixes, CI/build unblockers, security
> fixes, and ADR/spec/doc errata under ADR-042 §27.4. Blocked work: new
> user-visible features, unrelated ADRs, unrelated refactors, and performance
> optimization without correctness motive. Exceptions require Tier-2 sign-off
> and an entry in `docs/audit/freeze-exceptions.log`. Umbrella: #1113.

TODO(#1113): Retarget temporary legacy procedure references from `CLAUDE.md`
to `docs/contributing/**` after ADR-044 contributor docs exist.
Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.

## Identity

SciEasy is an AI-native, inclusive workflow runtime for multimodal scientific
data. The workflow graph, runtime state, block contracts, lineage, and execution
semantics belong to backend/runtime layers. The frontend edits and views runtime
truth; it does not own it.

Core stays small and stable: primitive object types, block contracts, execution
semantics, and validation surfaces. Domain behavior belongs in adapters,
metadata, wrappers, or plugins. Manual GUI steps are first-class `AppBlock`
workflows, not informal pauses.

## Policy

- Preserve traceability: idea -> issue/spec/ADR -> branch -> commit -> PR ->
  review -> CI/test -> merge -> release. Local-only cascade slices may stop at a
  local commit only when the dispatch explicitly forbids push/PR; they are not
  repository delivery.
- Create or use a non-main branch before editing. Never push directly to `main`,
  never merge into local `main`, and never use destructive git commands unless
  the human explicitly requests them.
- Agents must never run `pip install -e .`, `python -m pip install -e .`, or an
  equivalent editable install from any worktree. Use per-command source
  isolation instead, for example PowerShell
  `$env:PYTHONPATH=(Resolve-Path src).Path; pytest ...; Remove-Item Env:PYTHONPATH`.
  Editable installs contaminate sibling worktrees and are a protocol violation.
- Keep work scoped to the accepted issue, ADR, dispatch, or hotfix round. Do not
  silently broaden a bug fix into a feature, redesign, or unrelated cleanup.
- Runtime contracts, storage behavior, API contracts, plugin contracts, major UI
  semantics, and AI orchestration behavior require a spec or ADR when the
  current artifacts do not already decide the change.
- AI may propose graphs, blocks, parameters, and code, but runtime validation
  and formal schemas must execute them. Do not bypass contracts, lineage, or
  execution policy to make a path pass.
- Data should flow as typed references, lazy handles, or persisted artifacts.
  Do not design new paths around large in-memory payload transfer.
- Tests and docs are part of the change. A bug fix should include a regression
  test or a written reason tests are not possible. Behavior changes update
  relevant docs and CHANGELOG unless the dispatch explicitly scopes them out.
- Out-of-scope work must be marked in the file with a tracked `TODO(#...)` entry.
  Silent deferrals are protocol violations.

## Routing

| Trigger | Route | Current pointer |
|---|---|---|
| Multi-step implementation workflow | Skill: `workflow-gate` | Temporary: `CLAUDE.md` Appendix A |
| Explicit hotfix request only | Skill: `hotfix-mode` | Temporary: `CLAUDE.md` §11.5 |
| Bug or audit finding | Skill: `bug-fix-workflow` | Temporary: `CLAUDE.md` Appendix C |
| Feature/spec planning | Skill: `speckit-feature` | Existing `.claude/skills/speckit-*` plus `CLAUDE.md` Appendix B |
| Test creation or review | Skill: `test-author`; rule: `test-discipline.md` | ADR-043 §4.4 |
| Docs, ADRs, changelog | Rules: `adr-edits.md`, `changelog-format.md`, `governance-edits.md` | ADR-042/043/044 |
| Frontend changes | Rule: `frontend-smoke-test.md`; `frontend/AGENTS.md` | Browser smoke required |
| Core, block, QA, CI paths | Nearest subtree `AGENTS.md` plus matching `.claude/rules/*` | Root policy still applies |

When a skill pointer still targets `CLAUDE.md`, read only the named legacy
section and preserve the hard policy in this root file.

## Data classification

| Path | Class | Handling |
|---|---|---|
| `src/**`, `tests/**`, `docs/specs/**` | public | Normal review, tests, and docs rules apply |
| `docs/adr/**`, `AGENTS.md`, `.claude/**`, `.workflow/**` | internal | Governance-sensitive; preserve traceability |
| `docs/audit/**` | internal | Append-only or session-owned unless an ADR says otherwise |
| `frontend/dist/**`, generated references | generated-code | Do not hand edit; regenerate through owning tooling |
| `data/fixtures/**`, `tests/fixtures/**` | test-fixtures | Keep small; never commit large private binaries |
| `.github/secrets/**`, env files, credentials | secrets | Do not read, print, commit, or synthesize values |
| `docs/identity/humans.yml` | user-data | CODEOWNERS/Tier-2 governed; do not auto-edit |
| `_skills/**`, `agent_provisioning/templates/**` | internal | Treat as repo data assets and preserve provenance |

## Assessment rubric

Before declaring a task complete, verify the criteria that apply to the touched
scope:

| ID | Criterion | Verify with |
|---|---|---|
| R1 | Work stayed inside the issue/ADR/dispatch scope | `git diff --stat` |
| R2 | No unrelated user or agent work was reverted | `git status --short` and diff review |
| R3 | Behavior changes have focused tests or a written test gap | focused `pytest` / frontend test command |
| R4 | Test changes assert observable behavior | `test-author` review |
| R5 | Docs or CHANGELOG changed when behavior/user surface changed | `git diff -- docs CHANGELOG.md` |
| R6 | ADR/spec updated when contracts or architecture changed | `git diff -- docs/adr docs/specs` |
| R7 | No untracked out-of-scope deferral lacks `TODO(#...)` | `rg "TODO\\(#" <changed paths>` |
| R8 | Local whitespace and scaffold checks pass | `git diff --check` |
| R9 | Agent-authored commits use meaningful scoped messages and trailers when required | `git log -1 --pretty=full` |
| R10 | No editable install pollution was introduced by agent work | `python -m pip show scieasy` should not report an editable project location unless owner explicitly permits it |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ✅ | `src/scieasy/{api,engine,workflow,testing,utils}/**` | Normal implementation paths; tests required |
| ✅ | `src/scieasy/blocks/**` except `blocks/ai/**` | Block implementation under block contracts |
| ✅ | `tests/**` | Test code; use `test-author` discipline |
| ✅ | `docs/specs/**`, session-owned `docs/audit/**` | Normal docs/spec work under traceability rules |
| ⚠️ | `src/scieasy/core/**` | Frozen contracts; ADR/spec review required |
| ⚠️ | `src/scieasy/blocks/ai/**` | AI orchestration constraints; ADR-035 applies |
| ⚠️ | `src/scieasy/qa/**` | ADR-042/043/044 cascade-owned; coordinate with QA agents |
| ⚠️ | `.workflow/**`, `.claude/**`, `AGENTS.md`, `CURSOR.md`, `GEMINI.md`, `.aiderrc` | Agent governance and runtime setup |
| ⚠️ | `docs/adr/**`, `.github/workflows/**`, `pyproject.toml`, `.pre-commit-config.yaml` | Governance, CI, or contract surface |
| 🚫 | `frontend/dist/**`, `frontend/node_modules/**`, generated references | Generated or vendored outputs |
| 🚫 | `.github/secrets/**`, credential files | Secret material |
| 🚫 | `MAINTAINERS`, `.github/CODEOWNERS`, `docs/identity/humans.yml` | Ownership/identity gates |
| 🚫 | `docs/audit/overrides.log`, `docs/audit/governance-changes.log`, `docs/audit/commit-log.jsonl` | Append-only audit records |

## Out-of-scope

Use this exact tracked form in source, docs, rules, hooks, and tests whenever a
behavior is intentionally deferred:

```text
TODO(#NNN): <one-line description of what is deferred and why>
Out of scope per <ADR-XXX §Y / spec §Z / PR #M discussion>.
Followup: <issue URL or #NNN>.
```

Current ADR-043 §5 scaffold deferrals:

- TODO(#1113): Implement full cross-runtime hook activation and settings
  wiring after runtime-specific verification exists. Out of scope per ADR-043
  §5 / ADR-044 §11. Followup: #1113.
- TODO(#1113): Replace temporary `CLAUDE.md` procedure targets with
  `docs/contributing/**` workflow/reference targets after ADR-044 lands them.
  Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.
