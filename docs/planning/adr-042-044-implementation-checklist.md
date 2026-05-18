# ADR-042/043/044 Implementation Checklist

> Mandatory local tracking document for the ADR-042/043/044 rewrite.
> Each implementation round appends its plan, agent branches, test outcome,
> approval state, and local merge state here.

## Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Agents work in self-owned worktrees.
- Agent branches are created from local `umbrella/adr-042-044-implementation`.
- No agent pushes remote branches or opens PRs during local implementation.
- Manager merges an agent branch back into the local umbrella branch only after owner approval.
- Out-of-scope or deferred behavior must be tagged in repo with `TODO(#1113)` and an ADR section reference.

## Global State

| Item | Status | Notes |
|---|---:|---|
| Umbrella branch | [~] | `umbrella/adr-042-044-implementation` |
| Remote push / PR | [ ] | Deferred until owner explicitly requests it |
| Owner audit | [ ] | Owner will personally audit implementation rounds |
| Feature freeze | [~] | Only ADR-042/043/044 cascade implementation work allowed |

## Section Implementation Tracking

| ADR section | Status | Current owner | Branch / worktree | Merge status | Notes |
|---|---:|---|---|---|---|
| ADR-043 §2 Implementation Monitoring | [~] | Agent Mendel | `local/adr043-s2-skeleton` / `C:\Users\jiazh\Desktop\workspace\SciEasy-adr043-s2-skeleton` | Not merged | Skeleton + historical-code investigation in progress |
| ADR-043 §5 CLAUDE.md / AGENTS.md Layered Design | [~] | §5 scaffold agent | `local/adr043-s5-layered-scaffold` / `C:\Users\jiazh\Desktop\workspace\SciEasy-adr043-s5-layered` | Not merged | Owner approved safe parallel scaffold on 2026-05-18 |

## Deferred File Tracking

| File / path | Status | Deferred reason | Implement when | Owner |
|---|---:|---|---|---|
| `src/scieasy/qa/schemas/__init__.py` | [!] | ADR-043 §2 skeleton owns QA schema package initialization; parallel §5 edits could conflict. | After §2 skeleton is merged into local umbrella. | §2 / later integration agent |
| `src/scieasy/qa/schemas/report.py` | [!] | §5/§6 lint tools should consume the §2 `Finding` / `AuditReport` primitives rather than inventing a second report model. | After §2 skeleton defines report primitives. | §2 / §6 lint agent |
| `src/scieasy/qa/schemas/classification.py` | [!] | Belongs to ADR-043 §6.1-6.3 data classification / rubric / path boundary schema, not §5 scaffold alone. | When ADR-043 §6 implementation starts. | §6 agent |
| `src/scieasy/qa/classification/lint.py` | [!] | Depends on ADR-043 §6 semantics and §2 report primitives. | When ADR-043 §6 implementation starts after §2 schema foundation lands. | §6 agent |
| `scripts/audit/classification_lint.py` | [!] | Full implementation needs ADR-043 §6.1-6.3 semantics and §2 report primitives. | When ADR-043 §6 implementation starts after §2 skeleton merge. | §6 agent |
| `CLAUDE.md` symlink / full pointer replacement | [!] | High governance blast radius; current file carries active policy and should not be replaced without owner audit of the new root `AGENTS.md`. | After §5 scaffold is audited and owner explicitly approves the migration step. | Manager / owner-approved §5 followup |
| `docs/contributing/**` workflow docs | [!] | ADR-044 owns the four-category doc set; skill-as-pointer closure needs real target docs that do not exist yet. | During ADR-044 documentation-set implementation. | ADR-044 docs agent |
| Full skill-pointer closure enforcement | [!] | Depends on ADR-044 `docs/contributing/` targets and `skill_pointer_sync.py`. | After ADR-044 doc skeleton and §2 report primitives land. | ADR-044 / QA audit agent |

## Round 1: ADR-043 Section 2 Implementation Monitoring

### Scope

Implement ADR-043 section 2: implementation tracker, tracker schema,
phase-gate validator, tool self-test runner, addendum propagation / governance
drift inventory hooks, and the initial tracker artifact.

### Plan

| Step | Status | Owner | Artifact / Notes |
|---|---:|---|---|
| Read ADR-043 section 2 and supporting ADR-042 schema/report sections | [x] | Manager | Used for initial implementation plan |
| Create skeleton worktree and local branch | [x] | Manager | `C:\Users\jiazh\Desktop\workspace\SciEasy-adr043-s2-skeleton`, `local/adr043-s2-skeleton` |
| Skeleton implementation and historical-code investigation | [~] | Agent Mendel | Agent id `019e3c69-8976-77d2-b468-572a0be48766`; no remote push |
| Review skeleton commit and test result | [ ] | Manager | Pending agent completion |
| Create second implementation worktree from approved skeleton | [ ] | Manager | Branch name TBD after skeleton result |
| Complete remaining ADR-043 section 2 implementation | [ ] | Implementation agent | Pending skeleton handoff |
| Owner audit | [ ] | Owner | No separate audit agent per owner instruction |
| Merge approved branch into local umbrella | [ ] | Manager | Only after owner approval |

### Planned Files

| Path | Status | Notes |
|---|---:|---|
| `src/scieasy/qa/schemas/_common.py` | [~] | Minimal ADR-042 primitive types needed by section 2 |
| `src/scieasy/qa/schemas/frontmatter.py` | [~] | Minimal `Phase` / frontmatter support needed by section 2 |
| `src/scieasy/qa/schemas/report.py` | [~] | Minimal `Finding` / `AuditReport` support |
| `src/scieasy/qa/schemas/tracker.py` | [~] | ADR-043 section 2 tracker schema |
| `src/scieasy/qa/tracker/adr_implementation_check.py` | [~] | Tracker-to-code validation |
| `src/scieasy/qa/tracker/phase_gate.py` | [~] | Phase transition readiness check |
| `src/scieasy/qa/tracker/tool_self_test_runner.py` | [~] | QA tool self-test artifact validation |
| `scripts/audit/adr_implementation_check.py` | [~] | CLI wrapper |
| `scripts/audit/phase_gate.py` | [~] | CLI wrapper |
| `scripts/audit/tool_self_test_runner.py` | [~] | CLI wrapper |
| `docs/audit/adr-042-implementation-tracker.yaml` | [~] | Initial machine-readable tracker |
| `tests/qa/test_implementation_tracker.py` | [~] | Schema and tracker validation |
| `tests/qa/test_phase_gate.py` | [~] | Blocking behavior |
| `tests/qa/test_tool_self_test_runner.py` | [~] | Missing artifact / diff behavior |

### Required Tests

| Command | Status | Notes |
|---|---:|---|
| `pytest --timeout=60 tests/qa/test_implementation_tracker.py tests/qa/test_phase_gate.py tests/qa/test_tool_self_test_runner.py` | [ ] | Pending skeleton agent |

### Historical-Code Investigation

| Candidate | Status | Decision |
|---|---:|---|
| Reverted ADR-042/043 tracker code in git history | [~] | Skeleton agent investigating |
| Old `src/scieasy/qa/schemas/tracker.py` if found | [~] | Cherry-pick only if current ADR-compliant |
| Old `src/scieasy/qa/tracker/*` if found | [~] | Cherry-pick only small compliant fragments |
| Old `docs/audit/adr-042-implementation-tracker.yaml` if found | [~] | Reuse only if it does not claim false implementation status |

### Owner Approval / Merge

| Item | Status | Notes |
|---|---:|---|
| Skeleton branch approved | [ ] | Pending |
| Implementation branch approved | [ ] | Pending |
| Merged into local umbrella | [ ] | Pending |

## Round 2: ADR-043 Section 5 Layered Instructions Scaffold

### Scope

Implement the currently safe, parallelizable part of ADR-043 section 5:
layered instruction-carrier scaffold, subtree `AGENTS.md` scaffold,
path-scoped rule scaffold, pointer-style skill scaffold, and hook scaffold.

### Plan

| Step | Status | Owner | Artifact / Notes |
|---|---:|---|---|
| Owner approval for parallel §5 scaffold | [x] | Owner | Approved in chat on 2026-05-18 |
| Create §5 worktree and branch | [x] | Manager | `C:\Users\jiazh\Desktop\workspace\SciEasy-adr043-s5-layered`, `local/adr043-s5-layered-scaffold` |
| Implement safe §5 scaffold | [~] | §5 agent | Must avoid deferred files listed above |
| Run focused checks | [ ] | §5 agent | No full lint gate until §2/§6 foundations land |
| Owner audit | [ ] | Owner | No separate audit agent |
| Merge approved branch into local umbrella | [ ] | Manager | Only after owner approval |

### Planned Files

| Path | Status | Notes |
|---|---:|---|
| `AGENTS.md` | [ ] | Root canonical policy scaffold; must not silently loosen current policy |
| `CURSOR.md` | [ ] | Pointer to `AGENTS.md` if implemented as plain file |
| `GEMINI.md` | [ ] | Pointer to `AGENTS.md` if implemented as plain file |
| `.aiderrc` | [ ] | Pointer config if safe and minimal |
| `src/scieasy/core/AGENTS.md` | [ ] | Frozen contract path-scope scaffold |
| `src/scieasy/blocks/AGENTS.md` | [ ] | Block contract path-scope scaffold |
| `src/scieasy/blocks/ai/AGENTS.md` | [ ] | ADR-035 pointer scaffold |
| `src/scieasy/qa/AGENTS.md` | [ ] | ADR-042/043 QA scope scaffold |
| `frontend/AGENTS.md` | [ ] | Frontend smoke-test pointer scaffold |
| `.workflow/AGENTS.md` | [ ] | Workflow gate semantics scaffold |
| `docs/AGENTS.md` | [ ] | Doc authoring rules scaffold |
| `.github/AGENTS.md` | [ ] | CI/workflow rules scaffold |
| `.claude/rules/*.md` | [ ] | Path-scoped rules from ADR-043 §5.3 |
| `.claude/skills/*/SKILL.md` | [ ] | Pointer-style skills only; no long duplicated workflows |
| `scripts/hooks/*.sh` | [ ] | Hook scaffolds from ADR-043 §5.3 |

### Required Checks

| Command | Status | Notes |
|---|---:|---|
| `git diff --check` | [ ] | Pending §5 agent |
| Manual line-count check for root `AGENTS.md` / skill bodies | [ ] | Pending §5 agent; root target ≤200 lines, skills pointer-only |

## Parallelization Assessment: ADR-043 Section 5

### Question

Can ADR-043 section 5 (`CLAUDE.md / AGENTS.md Layered Design`) run in
parallel with Round 1 (`ADR-043 §2 Implementation Monitoring`)?

### Decision

| Item | Status | Notes |
|---|---:|---|
| Parallel with ADR-043 §2 | [~] | Safe only for disjoint scaffold/docs/rules work |
| Full section 5 completion | [!] | Depends on ADR-044 doc set and §6 classification details |
| Recommended merge order | [~] | Merge §2 skeleton/foundation before §5 lint/tool code |

### Safe Parallel Slice

| Path group | Status | Notes |
|---|---:|---|
| Root and subtree `AGENTS.md` scaffold | [ ] | Must not silently loosen current policy |
| `.claude/rules/*.md` path-scoped rule scaffold | [ ] | New files; low conflict with §2 |
| Pointer-style `.claude/skills/*/SKILL.md` scaffold | [ ] | Must honor ADR-044 §11 skill-as-pointer discipline |
| `scripts/hooks/*` best-effort hook scaffold | [ ] | New hook files only; no destructive hook rewiring yet |
| `scripts/hooks/instructions-loaded-audit.sh` | [ ] | Can scaffold, but runtime-specific enablement deferred |

### Do Not Parallelize Yet

| Path group | Status | Reason |
|---|---:|---|
| `src/scieasy/qa/schemas/__init__.py` edits | [!] | §2 skeleton is creating schema package foundations |
| `src/scieasy/qa/schemas/report.py` edits | [!] | §5/§6 lint tools should consume §2's `Finding` model after it lands |
| `scripts/audit/classification_lint.py` full implementation | [!] | §5.6 depends on ADR-043 §6.1-6.3 semantics and §2 report primitives |
| Full skill-pointer closure | [!] | ADR-044 requires `docs/contributing/` targets, which do not exist yet |
| Replacing `CLAUDE.md` with a symlink/pointer | [!] | High governance blast radius; owner should approve after scaffold review |

## Drift Log

- 2026-05-18: Initial skeleton agent `019e3c62-7ed1-7c30-9c0a-0bd7fd5e1dc4` was interrupted/shutdown before producing worktree changes. Re-dispatched as `019e3c69-8976-77d2-b468-572a0be48766`.
