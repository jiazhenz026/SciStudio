# ADR-042 Addendum 6 — Implementation Plan & Checklist

Owner: @jiazhenz026 · Manager: Claude (claude-opus-4-8) · Runtime: claude-code

## Goal (owner-set)

All tasks ruled by ADR-042 Addendum 6 and its spec pass. Specifically:
- The governance subsystem is rewritten to the new ledger + single shared evaluator model.
- gate record is the single source of truth; all hooks/guards/CI read it (no independent rule sets).
- Nearly all checking is consolidated into `gate_record check`; no duplicate checks / no duplicate rework.
- New CI (`workflow-gate.yml`) and new AI-developer behavior are aligned to the new spec.
- CI passes on the umbrella.

## Design intent — the success bar (owner-set)

The whole point of this design is **enough automation + agent guidance that one
pass through the workflow does everything that needs doing** — the agent is NOT
left to "forget X, forget Y, get blocked, go back and patch, break CI, go fix."
That is why `init` emits task-specific instructions, why `check` auto-runs the
tier-selected checks (ruff/mypy/pytest/etc.) instead of making the agent invoke
them by hand, and why obligations are reported up front with repair hints.

So the implementation and the Phase D test are judged against this bar:
- The agent is **reminded** of everything it must provide (init instructions +
  unsatisfied-obligation hints), and
- Everything that **can be automated is done by the tool** (no manual
  ruff/mypy/pytest; `check` runs them), and
- A correct single pass reaches PR-readiness **without** mid-flow "did half →
  blocked by error → went back to rework" cycles.

Any "did half, got blocked, had to go back and redo" episode in Phase D is a
**design defect to record** (not an agent mistake). Phase D must log each one.

## Owner corrections (authoritative — override the digest where they differ)

- **Worktree write guard intent.** The guard exists to catch an agent that
  **forgot to create a worktree** and is editing the **main (primary) repo
  working tree** directly. Fire (block) when the target write path resolves into
  the main working tree; **allow** all linked worktrees and all non-repo paths
  (memory dir, temp). The decision does NOT depend on the agent's cwd — only on
  whether the target is in the main checkout. This supersedes the investigation
  digest's earlier "block an agent in a worktree from reaching into main"
  framing. Spec §6.1 is the authoritative version.

## Branch model (safety net)

- Umbrella: `track/adr-042-add6/umbrella` (off `origin/main`). Stays **[DO NOT MERGE]**; only the owner removes the prefix and merges to `main`.
- Foundation: `track/adr-042-add6/foundation` → PR into umbrella (spec + docs + persona + rule + this plan + digest).
- Implementation sub-branches → PR into umbrella.
- **Never** merge to `main`. Never touch `main` directly.

## Phases

### Phase A — Foundation (manager + spec author)
- [ ] A1 `docs/specs/adr-042-gate-ledger-runtime.md` — implementation spec (ledger schema, event types, evaluator inputs/modes, tier derivation+escalation, task-kind profiles, CLI contract, compat aliases, guard→calculator mapping, hook/CI mapping).
- [ ] A2 `docs/ai-developer/personas/live-implementer.md` — new persona doc (style of existing persona docs).
- [ ] A3 `docs/ai-developer/specific_rules/guided-work.md` — new task rule for `guided`.
- [ ] A4 Update all AI-developer docs to the new model (CLI commands + new rule definitions, **content update only, no trimming**): `docs/ai-developer/rules.md`, `specific_rules/*.md`, `personas/*.md`, `templates/*.md`, skills; plus `AGENTS.md` and the three rules indexes (`.agents/.claude/.codex/rules/rules.md`).
- [ ] A5 This plan + the investigation digest (`docs/planning/adr-042-add6-investigation-digest.md`).

### Phase B — Implementation (≤4 agents, worktree-isolated, off umbrella)
Dependency note: the **core** (ledger + evaluator + CLI) is the substrate. Build B1 first; B2/B3/B4 build to the spec's interfaces.
- [ ] B1 **Core** — ledger schema (append-only event log), I/O (append, never overwrite), the shared evaluator (git-diff observation, surface classification, obligation inference, tier derivation + observed-diff escalation, check inference + execution + CI-parity, reconciliation, sanitization), workflow CLI (`init/plan/amend/check/finalize` + `--mode local|pre-commit|commit-msg|pre-push|pre-pr|ci`), compat aliases.
- [ ] B2 **Guards as evaluator-owned calculators** — port core_change_guard, human_bypass_guard, pr_merge_guard, mod_guard, weakened_ci_check, sentrux_gate, test_engineer_scope_guard, docs_landing, issue_link, persona_policy; reconcile the `_sentrux_applies` asymmetry; add `live_implementer` to persona_policy; label rename `ai-override`→`bypass`.
- [ ] B3 **Hooks + CI + wrapper** — rewrite `scripts/hooks/*`, `.pre-commit-config.yaml` entries, `scripts/scistudio_pr_create.py`, `workflow-gate.yml` as thin callers of the evaluator; worktree-guard minimal-logic rewrite + re-enable in `.claude`; label rename in CI; add `.audit/` to `.gitignore`; pin ruff/mypy versions to CI (§7.10).
- [ ] B4 **Tests** — delete old receipt/duplication tests; port still-valid guard tests; add new tests for: observed-diff-from-git, declared docs/test reconciliation, local==CI evaluator, version-parity fail-closed, incremental check validity, ledger sanitization, per-task-kind obligations, guided expansion.

### Phase C — Integration
- [ ] Merge B1..B4 sub-PRs into umbrella; resolve conflicts.
- [ ] `gate_record check`, full_audit, frontmatter_lint, ruff/mypy/pytest all green locally on umbrella.
- [ ] CI green on umbrella; `workflow-gate.yml` validates with the new evaluator.

### Phase D — Dogfood acceptance (manager, personal)
For EACH task kind (`hotfix bugfix feature refactor docs maintenance manager guided`): open a mock PR, follow that kind's gate flow, make a minimal non-functional change. After the full PR lands, personally run each flow and record every:
- **one-pass failures** (the headline criterion): any "did half → blocked by error → had to go back and rework" episode; any obligation the tool did NOT remind me of up front; anything I had to run manually that `check` should have auto-run (ruff/mypy/pytest/etc.); any CI-fix-and-push cycle after a green local — each is a **design defect**, recorded as such (not an agent mistake)
- unreasonable / wrong / over-blocking interception
- added hassle; repeated discipline-driven edits/retries
- local-passes-but-CI-fails rework
- deadlock (chicken-and-egg) issues
- anything else unreasonable
→ deliver a **test summary** to the owner, with each item tagged design-defect vs working-as-intended.

## Deadlock / chicken-egg watchlist (verify the new design avoids each)

1. `finalize` needs PR URL, but you can't open the PR without finalize → addendum6 splits **pre-PR finalize** (no `--pr`) vs **post-PR finalize**. VERIFY in practice.
2. worktree-guard required a gate record before ANY write — including writing the gate record file itself → new minimal logic removes the precondition. VERIFY the records dir is always writable.
3. Bootstrapping: hooks/CI call the new CLI that doesn't exist yet → land core + hook/CI rewrites so each commit's own pre-commit/gate check runs the new code.
4. pre-commit gate check fires on the very commit that rewrites gate_record → ensure the new pre-commit hook passes on its own change.
5. Every PR must close an issue → create tracking issue(s) before PRs (don't duplicate an existing open one).
6. Discovery error must be deterministic: zero ledgers → "run init"; multiple → ask for `--record` (don't hard-fail mid-flow).

## Hook total list (owner-reviewed; detail in digest)

Pre-commit: gate-record-pre-commit / gate-record-commit-msg / governance-mod-guard / weakened-ci-check → REWRITE to evaluator calls; ruff+ruff-format / mypy → MODIFY (version-pin to CI); standard hooks + commitizen → KEEP.
Harness: check-gate-before-push / check-gate-before-pr → REWRITE; check-worktree-write-guard → REWRITE (minimal logic, re-enable in .claude); check-ci-after-pr → KEEP (+finalize reminder); check-agent-template / remind-checklist-discipline → MODIFY; run_python_module.py → KEEP.
CI: workflow-gate.yml Verify Workflow Compliance → REWRITE to single `gate_record check --mode ci`.
Principle: no hook keeps its own bypass-label vocab or protected-path list; none calls `gate_receipt` or `gate_record ci` separately.
