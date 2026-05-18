# AGENTS.md — SciEasy canonical agent instructions

> **⛔ FEATURE FREEZE IN EFFECT — ADR-042/043/044 cascade (2026-05-18 → Phase 4 close).**
> ALLOWED: Phase 1–3 cleanup work, bug fixes for shipped regressions, hotfix mode (see §Hotfix mode below), CI/build unblockers, security fixes, ADR/spec/doc errata per ADR-042 §27.4. BLOCKED: new user-visible features, new ADRs unrelated to the cascade, refactors not driven by Phase 3 cleanup, performance optimisation without correctness motive. Freeze exceptions require Tier-2 sign-off in `docs/audit/freeze-exceptions.log`. Umbrella: #1113.

Canonical, always-loaded instructions for every agent runtime (Claude, Codex, Cursor, Aider, Gemini). `CLAUDE.md`, `CURSOR.md`, `GEMINI.md`, `.aiderrc` are pointer files that include this document (ADR-042 §12.1). Per-subtree `**/AGENTS.md` files add narrower rules and never duplicate this content (ADR-042 §12.2).

## Identity

This repository builds an **AI-native, inclusive workflow runtime for multimodal scientific data**: typed objects, standardized block I/O, Python/R/CLI/GUI/manual-review in one graph, serial/parallel/batch/interactive execution, plugin extensibility, AI-assisted orchestration. It is **not** a replacement for every existing tool, a monolithic end-user app, a script collection, or a no-code toy.

## Policy (non-negotiable, always applies)

1. **Workflow graph is the source of truth** — runtime owns graph definition, lineage, contracts; frontend is editor/viewer.
2. **Data flows as references** — typed handles / persisted artifacts, not large in-memory payloads.
3. **Core stays small and stable** — minimal contracts; domain logic layered via plugins/wrappers.
4. **Everything is connectable, not everything is native** — code blocks, AppBlocks, manual-review blocks, import/export bridges.
5. **Manual steps are first-class** — implemented as `AppBlock` (Fiji/Napari/QuPath) per `docs/block-development/block-contract.md`.
6. **AI may propose; runtime validates and executes** — generated graphs/blocks/parameters MUST pass formal schemas before run.
7. **Every meaningful change is traceable**: Idea → Issue → Spec/ADR → Branch → Commit → PR → Review → CI/Test → Merge → Release.
8. **No direct push to protected branches.** All changes go through PR.
9. **One branch = one task.** Branch naming: `feat/issue-N/short-description`, `fix/issue-N/short-description`, `docs/short-description`.
10. **Out-of-scope work MUST leave an in-repo TODO with tracking link** (see §Out-of-scope format below). Verbal deferrals are protocol violations.
11. **CI must pass before review.** Failing checks are not "ready for review".
12. **Tests and documentation are part of the change**, not optional follow-ups.
13. **Hard guarantees live in git hooks + CI + branch protection**, not in agent prompts (ADR-043 §5.1 row 2).

## Routing

Multi-step procedures live in skills; this file routes to them. Invoke skills via your runtime's mechanism (`Skill <name>` on Claude; see ADR-042 §17.2 for cross-runtime equivalents).

| Task | Skill / Tool | Path |
|---|---|---|
| 6-stage workflow gate | `.workflow/gate.py` (binary) | `python .workflow/gate.py start "title"` |
| SpecKit feature design | `speckit-*` skills | `.claude/skills/speckit-*` |
| Hotfix live-debugging | See `## Hotfix mode` below (verbatim, per ADR-042 §27.3) | this file |
| ADR routing | `adr-router` | `src/scieasy/_skills/qa/adr-router/` |
| Doc-drift detection | `doc-drift-guard` | `src/scieasy/_skills/qa/doc-drift-guard/` |
| Provenance tagging on commits | `provenance-tagger` + `scripts/committer.py` | `src/scieasy/_skills/qa/provenance-tagger/` |
| PR maintenance | `pr-maintainer` | `src/scieasy/_skills/qa/pr-maintainer/` |
| Session logs | `session-logs` | `src/scieasy/_skills/qa/session-logs/` |
| Release coordination | `release-maintainer` | `src/scieasy/_skills/qa/release-maintainer/` |
| Mantis-proof audit | `mantis-proof` | `src/scieasy/_skills/qa/mantis-proof/` |
| Skill authoring | `scieasy-skill-creator` | `src/scieasy/_skills/qa/scieasy-skill-creator/` |
| Codemod with ADR ref | `codemod-with-adr` | `src/scieasy/_skills/qa/codemod-with-adr/` |
| Hallucination guard | `hallucination-guard` | `src/scieasy/_skills/qa/hallucination-guard/` |
| MAINTAINERS reverse lookup | `maintainers-reverse` | `src/scieasy/_skills/qa/maintainers-reverse/` |
| Multi-agent dispatch | `agent-manager` | `~/.claude/skills/agent-manager/` |

For procedural details (6-gate stages, branch naming, conflict resolution, branch cleanup), invoke the relevant skill. **This file does not duplicate procedures.**

## Data classification

| Path | Class | Handling |
|---|---|---|
| `src/**`, `tests/**`, `docs/**` (excl. below) | public | None special |
| `.github/secrets/**`, env files | secrets | Never read in code; only inject via GH Actions / local env |
| `frontend/dist/**`, generated bundles | generated-code | Do not edit directly; regenerate via build |
| `data/fixtures/**`, `tests/**/fixtures/**` | test-fixtures | May edit; never commit large binaries |
| `.claude/skills/**`, `src/scieasy/_skills/**`, `src/scieasy/agent_provisioning/templates/**` | internal | Templates / data assets; edit with awareness |
| `docs/identity/humans.yml`, `MAINTAINERS` | user-data | Edit-blocked; CODEOWNERS-gated (ADR-043 §3.2) |
| `docs/audit/**` | internal | Append-only logs; do not rewrite history |
| `docs/facts/generated.yaml` | generated-code | Auto-generated; hand-edit rejected |

## Assessment rubric

Before declaring any task complete, verify ALL applicable criteria:

| ID | Criterion | Verify with |
|---|---|---|
| R1 | All new code has docstrings | `interrogate src/` |
| R2 | All new tests assert behavior (no anti-patterns) | `python -m scieasy.qa.test_quality src/` |
| R3 | Mutation score meets threshold (≥0.75 default, ≥0.90 for `src/scieasy/qa/**`) | `mutmut run --paths-to-mutate <changed>` |
| R4 | ADR `governs` updated if public surface changed | `python -m scieasy.qa.audit.doc_drift` |
| R5 | MAINTAINERS bidirectional closure passes | `python -m scieasy.qa.audit.closure` |
| R6 | Trailer `Assisted-by:` present on all agent commits | `python -m scieasy.qa.audit.trailer_lint` |
| R7 | RBP attached if change touches `src/scieasy/{blocks,engine,api,workflow}/**` or `frontend/**` | Visual review |
| R8 | CHANGELOG entry added for any user-visible change | `git diff CHANGELOG.md` |
| R9 | `docs/zh-CN/<mirror>.md` regenerated if any English doc changed | Translation workflow CI |
| R10 | Workflow v2 gate completed locally before push | `python .workflow/gate.py status <task>` |
| R11 | All 6 stages reachable; no `[LOCK]` on advancement | `python .workflow/gate.py validate <task> <stage>` |

Per-subtree AGENTS.md may tighten thresholds; never loosen (ADR-043 §3.4 monotonic strengthening).

## Paths

Three-tier boundary convention (ADR-043 §6.3). ✅ free edit · ⚠️ ask first · 🚫 never.

| Boundary | Path | Reason |
|---|---|---|
| ✅ | `src/scieasy/**` (excluding `core/`, `qa/`) | Free edit; tests required |
| ✅ | `tests/**` | Free edit; pytest timeout=60 required |
| ✅ | `docs/specs/**`, `docs/audit/<own-session>/**` | Free edit |
| ✅ | `frontend/src/**` (non-generated) | Free edit; Chrome smoke test required |
| ⚠️ | `src/scieasy/core/**` | Frozen contracts; requires ADR |
| ⚠️ | `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/**` | Governance per ADR-043 §3.2 |
| ⚠️ | `docs/adr/**` | Requires Tier-2 approval per ADR-043 §3.3 |
| ⚠️ | `CHANGELOG.md` | Append-only; format-checked |
| 🚫 | `src/scieasy/qa/**` (outside ADR-042/043/044 implementation phase) | QA tooling owned exclusively |
| 🚫 | `MAINTAINERS`, `docs/identity/humans.yml`, `.github/CODEOWNERS` | Identity/ownership — never auto-edit |
| 🚫 | `docs/audit/overrides.log`, `docs/audit/governance-changes.log`, `docs/audit/commit-log.jsonl` | Append-only audit logs |
| 🚫 | `.governance-paths.yaml` canary lines | Honeypot tripwire (ADR-043 §3.6.3) |
| 🚫 | `docs/facts/generated.yaml` | Auto-generated; hand-edit rejected |
| 🚫 | `main` branch (direct push) | All changes via PR |

## Out-of-scope format

Any behavior/branch/edge-case judged out-of-scope for the current PR MUST leave an in-repo TODO with tracking link:

```python
# TODO(#NNN): <one-line description of what's deferred and why>
#   Out of scope per <ADR-XXX §Y / spec §Z / PR #M discussion>.
#   Followup: <issue URL or "open as part of ADR-XXX Phase Z">.
```

A reviewer must be able to `grep -rn "TODO(#" src/` and see every deferred item with a tracking link. A `TODO` without a tracking link is itself a protocol violation — open the issue first, then write the TODO. Applies to v1→v2 deferrals, ADR-explicit out-of-scope items, heuristic approximations, `NotImplementedError` placeholders, skipped tests (also requires `@pytest.mark.skip(reason=...)`). Equally binding on AI agents and human contributors. Sub-agent dispatch prompts must restate this rule.

## Hotfix mode (live-debugging exception)

Hotfix mode is a narrow exception to the gate workflow for live debugging sessions where the user is interactively guiding the fix. Preserved verbatim per ADR-042 §27.3.

**When it applies.** Only when the user explicitly invokes it ("hotfix this", "进入 hotfix 模式", "let's hotfix", or equivalent). Claude must not auto-promote a normal bugfix. If unsure, ask. Default to the standard 6-gate workflow.

**On entering (MANDATORY).** Before touching any code, re-read the architectural artefacts governing the bug:
1. The relevant ADR(s) named in the bug report or apparent from file paths being touched (e.g. fixes under `src/scieasy/blocks/ai/` → ADR-035).
2. `docs/architecture/ARCHITECTURE.md` and `docs/architecture/PROJECT_TREE.md` for changes crossing subsystem boundaries.
3. This `AGENTS.md` §Policy and §Paths.

Quote the section you read in your first edit-mode response so the user can see you grounded yourself. This is non-negotiable because hotfix mode suspends the "write a change plan first" step; without that checkpoint, inline edits to a miscontract'd surface compound into design drift.

**What it permits (single round = one bug or tightly-related cluster):**
1. Create a `hotfix/<short-description>` branch off `main`.
2. `git checkout` it.
3. Open the user's Chrome (Chrome MCP) and drive live reproductions.
4. Iterate edits + live re-tests freely — gate workflow is **suspended**; do not `gate.py advance` per edit.
5. Commit progress as you go (small commits fine).

**Round end (user says done, or bug fixed and verified live):**
1. Run the **full 6-gate workflow retroactively in one batch**: `start → create_issue → write_change_plan → create_branch → update_docs → update_changelog → submit_pr`.
2. Open the PR against `main`.
3. Wait for CI green, address Codex review, merge.

**Constraints still apply.** Out-of-scope file rules from §Paths still hold (no touching frozen core without ADR). No direct push to `main` — always PR at the end. Hotfix mode does NOT extend to refactors, new features, or architecture changes — those use the full process from the start. Log the round as `feedback` or `project` memory if it surfaced rules worth carrying forward.

## Per-subtree AGENTS.md

Each governed subtree carries its own `AGENTS.md` with frontmatter (`scope`, `parent_agents_md`, `applies_to_agents`, `governing_adrs`) declaring narrower rules (ADR-042 §12.2). Sub-files MUST NOT duplicate this root content; the `agents-md-lint` pre-commit hook enforces this (ADR-042 §12.4, scheduled for Phase 1F).

Active sub-files:

- `src/scieasy/AGENTS.md` — Python-source rules
- `src/scieasy/core/AGENTS.md` — frozen-contract invariants
- `src/scieasy/blocks/AGENTS.md` — block-development rules
- `src/scieasy/qa/AGENTS.md` — QA infrastructure rules (ADR-042/043/044)
- `frontend/AGENTS.md` — React/TS rules; Chrome smoke test mandatory
- `docs/AGENTS.md` — doc authoring rules
- `.github/AGENTS.md` — CI/workflow rules
- `.workflow/AGENTS.md` — gate state machine semantics
