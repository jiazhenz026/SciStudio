---
spec_id: adr-042-gate-ledger-runtime
title: "ADR-042 Gate Ledger And Single-Source Governance Runtime Specification"
status: Planned
feature_branch: track/adr-042-add6/umbrella
created: 2026-05-29
input: "Owner-approved ADR-042 Addendum 6: replace the split gate-record/receipt/guard/wrapper/CI implementation with an append-only gate ledger and one shared evaluator that local hooks, the PR wrapper, and CI all call."
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
related_specs: []
scope:
  in:
    - Append-only gate ledger schema (Addendum 6 §7.2) and its Pydantic models.
    - Single shared evaluator that observes the git diff, reconciles declared
      scope/docs/test claims against it, derives strictness tier and obligations,
      runs tier-selected CI-equivalent checks, and runs every guard calculator.
    - Workflow CLI contract (init / plan / amend / check / finalize) per §7.5.
    - Compatibility aliases for the old subcommands.
    - Evaluator-owned guard calculators replacing all independent guard rule sets.
    - One surface classifier resolving the `_sentrux_applies` divergence.
    - "`--mode` dispatch (local / pre-commit / commit-msg / pre-push / pre-pr / ci)."
    - Hook, PR-wrapper, and workflow-gate CI mapping to the single evaluator call.
    - Minimal worktree-write-guard logic.
    - Tool-version and environment parity mechanism (§7.10).
    - Ledger sanitization rules (§7.2).
    - Label migration `admin-approved:ai-override` -> `admin-approved:bypass`.
    - Test ownership for ledger, evaluator, guards, hooks, and the PR wrapper.
  out:
    - Changing the repository CI quality bar; CI stays authoritative and unchanged.
    - Weakening branch protection, Sentrux, governance, or quality thresholds.
    - Applying GitHub labels or administrator approvals automatically.
    - Authoring the new persona guide / specific-rule docs (`live-implementer.md`,
      `guided-work.md`); those are tracked by the ADR doc workstream.
    - Designing new audit (`scistudio.qa.audit`) or schema (`scistudio.qa.schemas`)
      tools beyond consuming `qa.schemas.report`.
governs:
  modules:
    - scistudio.qa.governance
    - scistudio.qa.governance.gate_record
  contracts: []
  entry_points: []
  files:
    # NOTE: limited to file patterns the base ADR-042.md already governs, because
    # doc_drift.missing-adr-governance resolves only one document per ADR number
    # (the base ADR wins over addenda). The docs/hooks/PR-wrapper surfaces this
    # spec also touches are governed by ADR-042 Addendum 6 (a planning-phase ADR,
    # exempt from the spec-alignment check). See implementation plan: doc_drift
    # addendum-aggregation is a known limitation to revisit.
    - src/scistudio/qa/governance/**
    - tests/qa/**
    - .github/workflows/**
  excludes: []
tests:
  - tests/qa/test_gate_record.py
  - tests/qa/test_gate_ledger.py
  - tests/qa/test_gate_evaluator.py
  - tests/qa/test_gate_record_ci.py
  - tests/qa/test_gate_record_hooks.py
  - tests/scripts/test_scistudio_pr_create.py
acceptance_source: adr
language_source: en
---

# ADR-042 Gate Ledger And Single-Source Governance Runtime Specification

## 1. Change Summary

This spec is the implementation contract for ADR-042 Addendum 6. The addendum
keeps the ADR-042 gate workflow as a hard standard but replaces the
implementation of Section 7: the gate record becomes a single append-only
ledger, receipt behaviour folds into ledger events, and one shared evaluator is
the only authority that local hooks, the PR wrapper, and CI consult. This spec
turns that decision into precise module, schema, evaluator, CLI, hook, and test
contracts that four implementation agents build against.

The status is `Planned`: the code described here does not exist yet. Where this
spec names files that will be created during implementation, it governs them
only through globs that already resolve (for example `src/scistudio/qa/governance/**`
and `tests/qa/**`). It deliberately does not list not-yet-created module files or
new contract symbols in `governs`, because the `doc_drift` audit would treat
those as phantom references. The authoritative end-state surface lives in
ADR-042 Addendum 6; this spec is the build plan that lands inside that surface.

A note for the ADR doc workstream: ADR-042 Addendum 6 governs two doc files that
do not exist yet (`docs/ai-developer/specific_rules/guided-work.md` and
`docs/ai-developer/personas/live-implementer.md`). They are intentionally out of
this code spec's `governs` and `scope`. When the ADR and this spec are committed,
those two files must already exist (or be added in the same change) so the
ADR<->spec alignment audit stays green; that is the doc workstream's obligation,
flagged here for traceability.

The addendum sections this spec implements are cited inline. Section 7.6
(strictness tiers), Section 7.7 (task/persona obligation matrix), and Section 7.8
(repository rule protection) are the obligation source the evaluator reads; this
spec references those matrices rather than re-deriving them.

## 2. Module Layout

### 2.1 What The New Subsystem Looks Like

Everything lives under `src/scistudio/qa/governance/`. The redesign collapses the
two parallel "evaluator-like" flows that exist today (the governance-guard
orchestration in `gate_record/workflow.py` + `workflow_gate.py`, and the
command-execution flow in `gate_receipt.py`) into one evaluator, and turns every
guard into a calculator that the evaluator drives. The `gate_record` package
keeps its name and its `python -m scistudio.qa.governance.gate_record` entry
point because hooks, the PR wrapper, CI, and AGENTS.md all reference it; only the
internals and the CLI surface change.

The target package layout, with the disposition the investigation digest assigned
to each existing component:

| New module | Role | Built from |
|---|---|---|
| `gate_record/ledger.py` | Append-only ledger Pydantic models (top-level identity + event arrays + commit/PR/label/issue/scope fields). `schema_version` bumped to 2. | **rewrite** of `gate_record/models.py`. Ports `IssueRef`, `Scope`, `CommitEvidence`, `PullRequestEvidence`; reshapes `AdminLabelEvidence` (adds actor provenance), `SentruxEvidence` (becomes a `guard_event`/`check_event` variant), `FullAuditEvidence` (becomes a `check_event` variant); `CheckEvidence` becomes an append-only `check_event`. |
| `gate_record/io.py` | Disk I/O, git observation helpers, deterministic ledger discovery, append-only event writers, local-session state under `.git/scistudio/gates/`. | **modify** of current `gate_record/io.py`. Ports git diff helpers, `_slugify`, `_record_path`, `_discover_gate_record`, JSON read. Replaces `_write_record`/`_mark_stage`/`_upsert_check` (overwrite semantics) with append-only event writers. |
| `gate_record/surfaces.py` | The single file-surface classifier and protected/governance/sentrux/test/implementation path predicates. Absorbs `paths.is_gate_record_path`. The one canonical sentrux-applicability predicate. | **modify/port** of `gate_record/paths.py` + `paths.py` + the surface predicates copied across `docs_landing`, `core_change_guard`, `mod_guard`, `sentrux_gate`, `gate_receipt`. |
| `gate_record/evaluator.py` | The single shared evaluator (§3). Observes diff, classifies surfaces, reconciles scope/docs/tests, derives tier + obligations, infers and runs the tier-selected check set, runs every guard calculator, writes a reconcile event, sanitizes committed events. | **rewrite** consolidating `gate_record/validation.py` (`validate_gate_record`, the four `check_*` entry points), `gate_record/workflow.py` (`run_ci`), and `gate_receipt.py` (`infer_required_checks`, `build_candidate`, `append_check`, `validate_receipt`). |
| `gate_record/checks.py` | CI-graph parser + tier-selected check-set inference + check execution in the parity environment (§7). Produces sanitized `check_event`s and writes raw transcripts to ignored local paths. | **new** (no current equivalent; supersedes `gate_receipt.infer_required_checks` and its hand-written `CHECK_COMMANDS`). |
| `gate_record/parity.py` | Tool-version + environment parity (§7.10): resolve CI tool versions, set up/validate the isolated per-worktree environment or the `PYTHONPATH=src` invocation, fail closed when parity cannot be reproduced. | **new**. |
| `gate_record/guards/` | Each guard as an evaluator-owned calculator returning `AuditReport`/`Finding` via `qa.schemas.report`. One module per guard. No guard keeps its own task-kind rules, required-check sets, local/CI differences, bypass vocab, or protected-path lists. | **rewrite/modify** of the current top-level guard modules (see §4). |
| `gate_record/labels.py` | Single label vocabulary (`admin-approved:bypass`, `admin-approved:core-change`, `admin-approved:merge`, `human-authored`) and the bypass/authorization semantics. | **port** of the shared constants currently exported from `human_bypass_guard`. |
| `gate_record/instructions.py` | The `init` task-specific instruction generator (§5) rendering the §7.7.4/§7.7.5 argument profiles. | **new**. |
| `gate_record/workflow.py` | The five workflow command implementations (`init`/`plan`/`amend`/`check`/`finalize`) and the `--mode` dispatcher; thin orchestration over `evaluator`. | **rewrite** of current `stages.py` + `workflow.py`. |
| `gate_record/cli.py` | Argparse surface for the five commands plus compatibility aliases (§5.6). | **rewrite**. |
| `gate_record/__init__.py` | Public re-export surface. Drops deleted CLI subcommand symbols; adds ledger/evaluator public symbols. | **modify**. |
| `gate_record/__main__.py` | `python -m ...` entry point. | **keep** (two lines, unchanged). |

Deleted outright (no parallel authority survives, per ADR §3 "delete-and-replace"):

| Deleted | Reason |
|---|---|
| `gate_record/models.py` | Replaced by `ledger.py` (flat-document model is gone). |
| `gate_record/stages.py` | Per-subcommand overwrite mutators replaced by `workflow.py` + append-only writers. |
| `gate_record/validation.py` | Its `validate_gate_record` and four `check_*` modes collapse into `evaluator.reconcile(mode=...)`. |
| `gate_record/paths.py` | Folded into `surfaces.py`. |
| `gate_receipt.py` (+ `tests/qa/test_gate_receipt.py`) | Receipt subsystem folded into ledger `check_events`/`reconcile_events`. ADR §3 step 8. |
| `workflow_gate.py` | Second CLI entry point for `run_ci`; replaced by `gate_record check --mode ci`. |
| top-level `paths.py` | Its `is_gate_record_path` predicate moves into `surfaces.py`. |

Ported guard modules move under `gate_record/guards/` and lose their standalone
CLI entry points and independent rule sets; the evaluator becomes their only
caller. Compatibility command names may exist only as aliases implemented by the
new code.

## 3. The Shared Evaluator

The evaluator is the single source of truth. Hooks, the PR wrapper, and CI must
never re-implement scope, obligation, check-selection, or bypass logic; they call
the evaluator and forward its exit code.

### 3.1 Single Entry Point

```python
# scistudio/qa/governance/gate_record/evaluator.py
def reconcile(
    *,
    ledger: GateLedger,
    repo_root: Path,
    base: str,
    head: str,
    mode: EvaluatorMode,         # local | pre-commit | commit-msg | pre-push | pre-pr | ci
    pr_body: str | None = None,
    pr_context: PrContext | None = None,   # CI-only: labels, label-actor provenance, reviews
    run_checks: bool = True,     # False for --skip-execution
    only: Sequence[str] | None = None,
) -> ReconcileResult: ...
```

`ReconcileResult` carries the consolidated `AuditReport`, the derived
`strictness_tier`, the `required_obligations`, the unsatisfied-obligation list
with repair hints, the new `check_events`/`guard_events`, and the
`reconcile_event` to append. `reconcile()` is what every command, hook, wrapper,
and CI step ultimately calls. There is exactly one reconciliation code path; the
mode only changes which facts are required-now versus recorded as a pre-PR gap.

### 3.2 Inputs

| Input | Source | Notes |
|---|---|---|
| Ledger | `.workflow/records/<...>.json` via deterministic discovery | The declared facts: task kind, persona, runtime, scope, issues, docs/test claims, directives, prior events. |
| Observed git diff | `git diff <base>...<head>` (and `--staged` for pre-commit) | Objective changed-file set, base/head SHAs, diff fingerprint. This is the evidence; agent declarations are claims. |
| CI workflow graph + path filters | `.github/workflows/*.yml` parsed (or a generated manifest derived from them) | The source of command truth for tier-selected check inference (§7.5 CI snapshot table). |
| Repo config | `pyproject.toml`, `.pre-commit-config.yaml`, `uv.lock`, CI setup steps | Tool-version source for parity (§7.10) and protected/governance surface config. |
| PR context | GitHub event / `gh api` (CI mode only) | Observed labels, label-actor permission provenance, reviews, merge intent. Local modes record these as pre-PR gaps. |

### 3.3 Responsibilities (in order)

1. **Observe the git diff.** Derive the changed-file set, base/head SHAs, and a
   diff fingerprint from git, never from agent claims. Record this as
   `observed_diff`.
2. **Classify changed-file surfaces** through the single `surfaces.py` classifier:
   implementation, test, governance, protected-core, frontend, packaging,
   workflow/CI, docs, governed-docs (`docs/ai-developer/**` per §7.8),
   sentrux-applicable. The classifier is the only authority for these questions.
3. **Reconcile declared scope against the observed diff.** A changed file outside
   the effective include set (declared scope plus recorded owner-directive
   expansions) and not covered by an exclude is an out-of-scope finding. A
   declared include never seen in the diff is informational, not a failure.
4. **Reconcile declared docs/test claims against the observed diff.** A
   `docs_events` or `test_events` path that does not appear in the observed
   changed-file set is recorded as **claimed-but-unverified** and does not satisfy
   a docs or test obligation on its own. Git-observed facts win over declarations
   (ADR §7.2).
5. **Infer obligations** from task kind, persona, observed surfaces, and the
   §7.7 obligation matrix. Obligations include required docs landing, required
   test evidence, required checks, required guards, and required admin labels.
6. **Derive `strictness_tier`** by the corrected §7.6 rule: assign the baseline
   tier from `task_kind`, then **escalate (never lower)**. Any observed diff that
   touches protected core/runtime/engine paths, governance or workflow files, or
   constitutes a broad cross-module change raises the tier to Tier 1 regardless of
   `task_kind`. Agents never choose a tier.
7. **Infer the tier-selected required check set** from the CI workflow graph using
   the same path filters CI uses (§7.5). Tier 1 mirrors the full merge-blocking CI
   command surface; Tier 2 runs the governance/lint/audit baseline plus all
   changed-surface CI jobs; Tier 3 runs only mandatory checks for the observed
   diff. If a required CI job cannot be mapped to a local command, fail closed for
   PR readiness and report the missing parity mapping. PR-only automation
   (`ai-review.yml`) is recorded as PR-only and is never a local failure.
8. **Execute / validate checks with version + environment parity (§7.10).** Run
   the required commands at the CI-resolved tool versions in a CI-equivalent
   importable environment (see §7). Validate prior `check_events` by covered
   surface + input fingerprint; a later edit to a surface invalidates only that
   surface's evidence. `--only` runs a subset for recovery (never final
   readiness); `--skip-execution` reconciles existing valid events only.
9. **Run guard calculators** (§4). Each receives evaluator-provided inputs and
   returns findings. The evaluator deduplicates: each guard runs once.
10. **Write a reconcile event** capturing mode, tier, observed-diff fingerprint,
    obligation status, and pass/fail. Append `check_events` and `guard_events`.
11. **Sanitize committed events** (§8) before they are written to the ledger.

### 3.4 Mode Semantics

| `--mode` | Caller | Diff source | Behaviour |
|---|---|---|---|
| `local` | manual `gate_record check` | `base...head` | Full local CI-equivalent preflight at the selected tier; PR-state facts (labels, provenance) recorded as pre-PR gaps, not failures. |
| `pre-commit` | `.pre-commit-config.yaml` hook | staged diff | Fast structural reconciliation (scope, governance-touch, protected-path, weakened-CI on staged governance files); not the full check matrix. |
| `commit-msg` | `.pre-commit-config.yaml` commit-msg hook | n/a | Validate required commit trailers (`Gate-Record:`, `Assisted-by:`) via the evaluator's trailer rules. |
| `pre-push` | `scripts/hooks/check-gate-before-push.sh` | `origin/main...HEAD` | Pre-push reconciliation: replaces today's `gate_record pre-push` + `gate_receipt validate` two-step. |
| `pre-pr` | `scripts/hooks/check-gate-before-pr.sh` + PR wrapper | `origin/main...HEAD` | Pre-PR readiness with `--pr-body-file`; PR-state-impossible findings (core/merge/bypass label provenance) are internally classified as pre-PR gaps, not caller-filtered. |
| `ci` | `.github/workflows/workflow-gate.yml` | PR base...head | Authoritative mode with `pr_context`; verifies label provenance, runs every guard, enforces all obligations. The merge-blocking surface. |

Local modes must agree with CI mode at the strictness level the task kind
selects. The only difference is that CI mode has real PR metadata and verifies
label-actor provenance, while local modes record those as known pre-PR gaps.

## 4. Guard Calculator Interface

Every guard becomes an evaluator-owned calculator: a pure function that takes
evaluator-provided inputs (ledger facts + observed diff + classified surfaces +
repo state + PR context where applicable) and returns findings via the shared
`qa.schemas.report` types (`AuditReport` / `Finding`). No guard reads the ledger
itself, runs its own git diff, keeps its own task-kind rules, required-check
sets, local/CI differences, bypass vocabulary, or protected-path lists. The
evaluator owns those and supplies them.

```python
# scistudio/qa/governance/gate_record/guards/<name>.py
def check(inputs: GuardInputs) -> AuditReport: ...
```

`GuardInputs` is the evaluator-built bundle: classified surfaces, effective
scope, declared/observed docs and tests, issues, persona, runtime, task kind,
tier, `requested_admin_labels`, `observed_admin_labels`, `governance_touch`,
`pr_body`, and `pr_context`.

| Guard | Evaluator-supplied inputs | Findings produced |
|---|---|---|
| `core_change_guard` | protected-core surfaces, `observed_admin_labels`, `requested_admin_labels`, runtime, pr_context | AI-authored protected-core change lacks `admin-approved:core-change` provenance. |
| `human_bypass_guard` | pr_context (labels + actor permission), runtime, AI-evidence facts from `runtime`/`check_events` | `human-authored`/`admin-approved:bypass` claimed without verified maintainer/admin provenance. |
| `pr_merge_guard` | merge intent from the real GitHub event, `observed_admin_labels`, actor | AI merge attempt without authorized `admin-approved:merge` provenance. |
| `mod_guard` (`governance_mod_guard`) | governance surfaces, `governance_touch`, `requested/observed_admin_labels` | Governance-file change without declared governance-touch + verified authorization. Env-var bypass channels removed. |
| `weakened_ci_check` | staged/observed diff of governed CI/pre-commit/pyproject files, required-token set derived from the CI graph | Removal of required check tokens or addition of CI-weakening constructs. |
| `sentrux_gate` | sentrux-applicable surfaces (single classifier), sentrux evidence from a `check_event`, active addendum semantics | Advisory or blocking findings on missing/incorrect Sentrux free-tier evidence. |
| `test_engineer_scope_guard` | persona, effective scope, classified production/build/governance surfaces | `test_engineer` persona touched production/build/governance code without authorization. |
| `docs_landing` | governed surfaces, declared+observed `docs_events` | Governed change without docs/changelog/checklist landing or explicit N/A. |
| `issue_link` | `issues`, `pr_body` | No linked issue; structurally invalid issue; PR body missing closing keyword per issue. |
| `persona_policy` | `persona`, `runtime`, runtime config roots on disk | Unsupported persona; skill/constitution/root-policy pointer missing; runtime-specific policy. |

Additional evaluator-internal calculators (not "guards" historically but owned
the same way): scope reconciliation, obligation inference, and the optional
`skill_pointer_sync` verifier mentioned in §7.4 (new; verifies pointer validity
across runtime config roots) and `test_quality` (§7.9, where enabled).

### 4.1 Resolving The Sentrux Asymmetry

Today `gate_record._sentrux_applies` excludes `tests/**` while
`sentrux_gate.sentrux_applies_to_changes` includes it, so local and CI disagree
on test-only diffs (the documented `reference_sentrux_applies_asymmetry`
problem). The rewrite resolves this into **one** `surfaces.sentrux_applies(...)`
predicate owned by the evaluator and used by both local and CI reconciliation.
There is no second copy. The CI-inclusive definition is the canonical one; local
and CI become identical for the same diff.

### 4.2 Persona, Task-Kind, And Label Migrations

- Add `live_implementer` to `persona_policy`'s allowed personas, with its skill
  mapping (`live-implementer`). Fix the `implementer` skill mapping from the stale
  `implementation-worker` to the actual `implementer` skill.
- Add `guided` to the task kinds in the surface/obligation logic
  (`IMPLEMENTATION_TASK_KINDS` and the ledger `task_kind` literal).
- Migrate the label `admin-approved:ai-override` -> `admin-approved:bypass`
  **everywhere atomically**: `labels.py`, every guard, the hooks, the PR wrapper,
  `workflow-gate.yml`, and the tests. There must be no split vocabulary state.

## 5. Workflow CLI Contract

The agent-facing CLI is organized around the workflow, not low-level events. The
five commands are exactly per Addendum 6 §7.5. Internal facts (observed diff,
inferred obligations, guard results, sanitized check summaries) are recorded
automatically; agents never call one command per fact.

### 5.1 Common Rules

- **Deterministic ledger discovery.** When `--record` is omitted, discover the
  active ledger for the current branch. Exactly one match is accepted; zero
  matches prints "run init"; multiple matches prints the candidate paths and asks
  for `--record`. The same discovery rule is used by `plan`, `amend`, `check`,
  and `finalize`, and is the canonical discovery that `worktree_write_guard`
  delegates to (it must not reimplement discovery).
- **Append-only.** Every command appends events; none rewrites or deletes prior
  events. Corrections are new events (`amend`), and the evaluator interprets the
  latest effective state.
- **Additive field updates.** Every command supports adding scope/docs/test/check
  /issue/label fields so the agent never recreates the ledger from scratch.
- **Repair hints.** Any command that reconciles must print an
  "Unsatisfied obligations" section with the exact follow-up command/arguments
  (per the §7.7 matrix and the §7.5 example).
- **Optional-at-input is not optional-at-PR.** A CLI field marked optional may
  still be a required ledger fact before PR readiness, per the §7.6 tier table
  and §7.7.3 field semantics.

### 5.2 `init`

Creates or updates the ledger and prints task-specific instructions.

Required: `--task-kind` (one of `hotfix|bugfix|feature|refactor|docs|maintenance|manager|guided`),
`--persona` (one of `manager|implementer|adr_author|audit_reviewer|test_engineer|live_implementer`),
`--runtime`, `--branch`, `--owner-directive` (repeatable). Optional: `--record`,
`--slug`, `--session-id` (auto-generated under `.git/scistudio/gates/` when
omitted), `--issue` (repeatable), `--include`/`--exclude` (repeatable),
`--governance-touch`, `--print-instructions` (default true),
`--instructions-output`.

Generated path when `--record` is omitted: prefer
`.workflow/records/<issue>-<slug>.json`, else `.workflow/records/<branch-slug>-<slug>.json`;
derive a stable slug from the branch or owner directive when `--slug` is omitted.
`init` prints the chosen path, may be rerun to append, must not erase events, and
must accept being run with no issue yet (today's `start` requires `--issue` and
fails for not-yet-triaged tasks — that bug is fixed).

The instruction generator (`instructions.py`) renders, from task kind + persona +
tier + scope + issues + governance-touch + changed-file hints: task identity and
persona; issue-closure expectations; scope/owner-directive rules; likely
docs/tests/checks; whether implementation test changes are expected; whether
runtime/e2e evidence is expected; whether protected-path authorization is likely;
the `plan`/`amend`/`check`/`finalize` arguments likely needed (the §7.7.4/§7.7.5
profiles); and a reminder that `check` infers the final tier-selected obligations
from the real diff. Instructions are guidance; `check` remains authoritative.

### 5.3 `plan`

Append/amend planning fields without running the full check set. All fields
optional and repeatable: `--owner-directive`, `--include`, `--exclude`,
`--issue`, `--docs-updated`, `--docs-na` (`<class>:<rationale>`), `--test-path`,
`--test-na`, `--check`, `--check-na`, `--admin-label`. Observes the current diff
when available and recomputes provisional obligations; does not run expensive
checks. Uses branch discovery when `--record` is omitted.

### 5.4 `amend`

Dedicated low-cost, append-only correction command. Required `--reason`. Adds or
supersedes any field class: `--owner-directive`, `--task-kind`, `--persona`,
`--branch`, `--issue`/`--remove-issue`, `--include`/`--remove-include`,
`--exclude`/`--remove-exclude`, `--governance-touch`, `--docs-updated`,
`--docs-na`, `--test-path`, `--test-na`, `--check`, `--check-na`,
`--admin-label`. Removals are recorded as supersession events, never deletions.
Observes the diff only when the amended field affects scope/obligations/protected
-path evaluation; runs no expensive checks.

### 5.5 `check`

The main local CI-equivalent preflight. Arguments: `--base` (default
`origin/main`), `--head` (default `HEAD`), `--mode` (`local|pre-commit|commit-msg
|pre-push|pre-pr|ci`, default `local`), `--pr-body-file`, plus the additive field
flags from `plan`, plus `--only` (repeatable, recovery) and `--skip-execution`.

`check` runs the §3.3 pipeline: observe diff -> infer tier-selected check set
from the CI graph -> run required commands (unless `--only`/`--skip-execution`)
in the parity environment -> write raw transcripts to ignored local paths ->
record sanitized `check_event`s -> run all guards -> record a reconcile event ->
exit nonzero when obligations remain unsatisfied. A single `check` call must
cover every required local check for the selected tier; the agent must not have
to remember separate lint/type/test/docs/audit/frontend/guard commands.

`--only` and `--skip-execution` are recovery aids: a final PR-ready `check` must
run or validate the complete tier-selected set, and `--skip-execution` can only
reconcile already-recorded valid events.

### 5.6 `finalize`

Two modes:

- **pre-PR finalize**: records the current commit candidate and intended PR body
  before the PR exists. Must not require `--pr`. Re-observes the diff, validates
  the intended PR body's issue closure, reruns reconciliation. Requires
  `--commit`, `--pr-body-file`, `--closes` for each closing issue (per §7.6).
- **post-PR finalize**: records the PR URL/number after the PR exists. Must not be
  required before PR creation. Reruns reconciliation with PR metadata; fails when
  checks are stale, issue closure is missing from the PR body, required docs/tests
  are absent, or tier-selected obligations are unsatisfied.

Arguments: `--base`, `--head`, `--commit` (required, repeatable), `--pr`
(conditional: post-PR only), `--pr-body-file` (conditional: required pre-PR),
`--closes` (repeatable, integer issue numbers — not "Closes #N" strings), plus
the additive field flags. Branch discovery applies when `--record` is omitted.

### 5.7 Exit Codes (§7.5)

| Code | Meaning |
|---:|---|
| 0 | Command completed; current reconciliation passed where applicable. |
| 1 | Command completed; reconciliation failed (unsatisfied obligations / blocking findings). |
| 2 | Invalid CLI usage or unsupported argument combination. |
| 3 | Ledger schema or migration error. |
| 4 | Required external tool unavailable and no accepted N/A rationale exists. |
| 5 | Privacy/sanitization violation in a would-be committed ledger event. |

### 5.8 Compatibility Aliases

Aliases exist only during migration and must delegate to the new code (no alias
owns a validation decision). Mapping:

| Old subcommand | Delegates to |
|---|---|
| `start` | `init` |
| `plan` | `plan` |
| `amend` | `amend` |
| `docs` | `amend` (docs become a field class: `--docs-updated`/`--docs-na`) |
| `check` (passive) | `check` (now active; old passive evidence recording is internal event recording) |
| `sentrux` | `check` (sentrux becomes a `guard_event` inside `check`) |
| `finalize` | `finalize` |
| `pre-commit` | `check --mode pre-commit` |
| `commit-msg` | `check --mode commit-msg <message-file>` |
| `pre-push` | `check --mode pre-push` |
| `pr-ready` | `check --mode pre-pr` |
| `ci` | `check --mode ci` |

The `__init__.py` re-export surface drops the removed mutator/validator symbol
names and adds the ledger/evaluator public symbols; tests that import private
re-exports (`tests/qa/test_gate_record.py`) are rewritten against the new surface.

## 6. Hook / CI / Wrapper Mapping

Every enforcement surface collapses to one evaluator call. No hook keeps a bypass
vocabulary, a protected-path list, an issue-closure regex, or a receipt-validate
step.

| Surface | New behaviour |
|---|---|
| `scripts/hooks/check-gate-before-push.sh` | Thin shell: `gate_record check --mode pre-push --base origin/main --head HEAD`; forward exit code. Remove inline label/bypass Python. |
| `scripts/hooks/check-gate-before-pr.sh` | Thin shell: extract PR body file path from the `gh pr create` argv, then `gate_record check --mode pre-pr --pr-body-file <path> --base origin/main --head HEAD`. Remove inline closing-keyword regex and label extraction. |
| `scripts/hooks/check-ci-after-pr.sh` | **Keep**; update the reminder to mention `gate_record finalize --pr <url>` as the required post-creation step in addition to CI-watch guidance. |
| `.pre-commit-config.yaml` `scistudio-gate-record-pre-commit` | Thin entry calling `gate_record check --mode pre-commit --staged`. |
| `.pre-commit-config.yaml` `scistudio-gate-record-commit-msg` | Thin entry calling `gate_record check --mode commit-msg <message-file>`. |
| `.pre-commit-config.yaml` `scistudio-governance-mod-guard` | Thin entry routed through the evaluator (`mod_guard` calculator); no independent protected-path/bypass set. |
| `.pre-commit-config.yaml` `scistudio-weakened-ci-check` | Thin entry routed through the evaluator (`weakened_ci_check` calculator); required-token set derived from the CI graph. |
| `.github/workflows/workflow-gate.yml` | **Single** `gate_record check --mode ci` invocation (replacing the two-step "Validate committed gate records" + "Run ADR-042 guard orchestration"). The evaluator consumes PR metadata directly from the GitHub event/`gh api`; the `.workflow-pr-metadata.json` temp-file coupling is removed. Align the job to the same Python version CI uses elsewhere. |
| `scripts/scistudio_pr_create.py` | Thin shell: `gate_record check --mode pre-pr --pr-body-file <path>` (or `finalize` pre-PR); on exit 0, run `gh pr create`. Use `io._discover_gate_record` instead of its own `find_gate_record`. The `_FILTERED_GUARD_PREFIXES` allowlist is deleted — pre-PR-impossible findings are classified internally by the evaluator's pre-PR mode. Preserve `--dry-run` and the `SCISTUDIO_SKIP_PREFLIGHT` escape hatch, body/base extraction. |

### 6.1 Worktree Write Guard (minimal logic)

`worktree_write_guard` keeps its PreToolUse role but is reduced to one job: catch
the case where an AI agent **forgot to create a worktree** and is editing the
**main repo working tree** directly. AI-authored work must happen in a dedicated
worktree; this guard enforces that at write time. It is **not** about an agent
that already has a worktree reaching into main — it is about detecting that work
is happening in the main checkout at all (the common "forgot to `git worktree
add`" mistake). The current over-blocking (blocking writes to non-repo paths like
`~/.claude/memory/`, and blocking all writes when no gate record exists) is
removed. Revised algorithm (replaces `check_paths` entirely):

1. Resolve the target write path to an absolute path. If it is outside any git
   repository: **allow** unconditionally (the guard has no jurisdiction over
   non-repo paths such as the memory directory, temp files, or external logs).
2. Identify which registered git worktree the target belongs to using
   `git worktree list --porcelain`, selecting the **longest matching worktree
   root** so that a path under a nested linked worktree (e.g.
   `.claude/worktrees/<name>/...`) matches that worktree, not the main checkout.
3. **Block** when the target belongs to the **main (primary) working tree** —
   this is the "forgot to make a worktree" case. The message tells the agent
   that AI-authored edits must happen in a dedicated worktree and to create one
   (`git worktree add ...`) and work there.
4. Otherwise **allow** (any linked non-main worktree, or any non-repo path).

The decision does **not** depend on the agent's cwd; it depends only on whether
the target resolves into the **main working tree**. This is the owner-confirmed
intent: stop an agent that never set up a worktree from mutating the shared main
checkout, while leaving all legitimate worktree and non-repo writes untouched.

Removed from the guard: the gate-record precondition; write-time include/exclude
scope enforcement (scope enforcement moves entirely to `check` reconciliation);
the outside-repo block (inverted to allow); the standalone main-branch block
(now subsumed — a main-checkout write is blocked regardless of which branch the
main checkout has). Update `BROAD_OVERRIDE_LABELS` to `admin-approved:bypass`.
The guard records a `guard_event` on the ledger when it blocks **and** the ledger
is discoverable (it must never require a ledger to make the block decision). Wire
it in both `.claude/settings.json` and `.codex/hooks.json`.

### 6.2 Repository Hygiene

- Add `.audit/` to `.gitignore` (scratch audit output).
- Pin `ruff` and `mypy` versions in `.pre-commit-config.yaml` to the CI-resolved
  versions per §7.10 (derive from the same source CI uses — e.g. `uv.lock` /
  the CI setup), and align mypy `additional_dependencies` (stub packages) with
  CI. The evaluator validates version agreement and fails closed on drift it
  cannot reconcile.

## 7. Version And Environment Parity (§7.10)

CI is the single source of truth for both which checks run and which tool
versions run them, in which environment. `parity.py` implements this:

- **One tool-version source = CI.** Read the CI-resolved versions of `ruff`,
  `mypy`, `pytest` (+ plugins), and frontend tools from the same source CI uses
  (`uv.lock` / pinned setup / pyproject resolution). `check` installs those exact
  resolved versions into an **isolated per-worktree environment** (for example a
  `.git/scistudio/gates/<session>/venv` or a uv-managed environment), never
  relying on ambient developer-machine versions. When CI itself resolves an
  unpinned latest, local resolves the same latest at run time.
- **CI-equivalent importable environment without `pip install -e .`.** Several
  CI jobs import `scistudio`. The repo forbids editable installs because they
  pollute the *shared* environment, not because importing is wrong. `check`
  reproduces importability either through the isolated per-worktree environment
  or through the `PYTHONPATH=src` invocation CI's full-audit job already uses, so
  `import scistudio` works without polluting the shared environment.
- **Fail closed.** If `check` cannot reproduce the CI tool versions or a
  CI-equivalent importable environment, it must fail closed for PR readiness
  (exit 4) and report the parity gap, never silently run a looser local
  approximation.

This is what makes "green locally predicts green in CI" true: local checks are
the CI checks at the same versions in an equivalent environment.

## 8. Sanitization Rules

Committed ledger events record behaviour, not local-machine details. The
sanitizer runs on every would-be-committed event before write; a violation is
exit code 5.

Allowed: command names, argv in repo-relative form, exit codes, timestamps, tool
versions, repo-relative paths, git object ids, file-surface classes, content
fingerprints, compact sanitized summaries.

Forbidden in committed events:

- absolute local filesystem paths;
- local usernames, home directories, temp directories, virtualenv paths;
- environment-variable dumps;
- raw stdout/stderr transcripts;
- local browser profile paths, local service URLs with secrets, machine ids;
- dependency-cache or tool-installation paths.

Raw transcripts may be written only to ignored local paths under
`.workflow/local/**`; they are convenience artifacts and are never committed or
pushed. A transcript needed for review must be converted to a sanitized summary
or to an explicit audit artifact with no local environment details.

## 9. Tier Model, Task-Kind Profiles, Persona Obligations

The evaluator does not invent obligations. It reads them from the addendum
matrices, which this spec cites as the authoritative source:

- **Tiers** — ADR-042 Addendum 6 §7.6. Baseline tier from `task_kind`; escalate
  (never lower) by observed diff; Tier 1 = full CI mirror, Tier 2 = baseline +
  changed-surface jobs, Tier 3 = mandatory-only. `guided` defaults to Tier 2 and
  escalates to Tier 1 for feature/core/runtime/governance/broad-refactor work.
- **Task-kind obligations** — §7.7.1 (per-concern fields and gate obligations),
  §7.7.4 (CLI argument profiles the instruction generator renders).
- **Persona obligations** — §7.7.2 (per-concern obligations), §7.7.5 (CLI
  argument overlays).
- **Field semantics** — §7.7.3 (which field is required before PR readiness and
  when).
- **Protected surfaces and labels** — §7.8 (governance file list incl.
  `docs/ai-developer/**`; protected-core paths; the four GitHub-native labels and
  their meaning; AI-merge prohibition).

The implementer encodes these matrices as data (an obligation table / profile
registry) that both the instruction generator and `check` read, so instructions
and gate failures derive from the same source.

## 10. Migration And Verification

### 10.1 Delete-And-Replace Order (ADR §3)

Implementation proceeds as delete-and-replace, not parallel deprecation:

1. (This spec) define ledger schema, event types, evaluator inputs/modes,
   task-kind profiles, and compatibility aliases.
2. Inventory every current hook/guard/tool (done: the investigation digest); each
   capability is ported or explicitly mapped to a new responsibility.
3. Delete the old `src/scistudio/qa/governance/**` implementation files and the
   old behaviour-specific `tests/qa/**` in the same branch; port reusable
   behaviour only into the new design.
4. Delete/replace hook and wrapper entry points that call old validation
   semantics.
5. Implement the new ledger schema and shared evaluator.
6. Re-add guard capabilities as evaluator-owned calculators.
7. Port local hooks, PR wrapper, and workflow-gate CI to the evaluator.
8. Replace receipt files with ledger check/reconcile events.
9. Update AI developer rules, persona docs, and command examples.
10. Replace duplication-asserting tests with ledger-reconciliation and
    local/CI-agreement tests.
11. Validate representative fixtures (docs-only, bugfix, feature, maintenance,
    governance-touch, guided).

### 10.2 Deadlock / Chicken-Egg Cases To Avoid (digest watchlist)

The design must not be able to lock itself out:

- **Pre-PR vs post-PR finalize.** `finalize` must support pre-PR (no `--pr`,
  requires `--pr-body-file`) and post-PR (`--pr`) separately. Never require a PR
  URL before the PR exists.
- **Records dir always writable.** The worktree write guard must never block
  writing `.workflow/records/**` or `.git/scistudio/gates/**`; the gate-record
  precondition is removed, so a brand-new task can create its own ledger.
- **Bootstrapping.** `init` must succeed with no issue yet (issue may be added by
  `plan`/`amend`/`check`/`finalize`); `check` discovery must say "run init" (not
  crash) when zero ledgers exist.
- **Pre-commit on the rewrite commit.** The commit that deletes/rewrites the
  governance code will trip governance/mod/weakened-CI pre-commit hooks; this
  change is itself governance-touch and must be self-hosting (declare
  `--governance-touch true`, scope the QA paths, and carry `admin-approved:*`
  authorization where the owner approves). The hooks must route through the new
  evaluator so the rewrite branch can pass its own gates.
- **Deterministic discovery.** Exactly one current-branch ledger accepted; zero
  -> "run init"; multiple -> list candidates and require `--record`. No silent
  guessing; the same rule everywhere (CLI commands and the write guard).

### 10.3 Acceptance Criteria (ADR §4)

The rewrite is accepted only when tests prove:

- observed changed files derive from git, not agent declarations;
- declared docs/test evidence is reconciled against the observed diff (a claimed
  path not in the diff does not satisfy its obligation);
- local and CI modes use the same evaluator;
- local checks run the same resolved tool versions as CI in a CI-equivalent
  importable environment, and `check` fails closed when parity cannot be
  reproduced;
- hook, wrapper, and CI reports agree for the same fixture;
- required checks are inferred from actual changed surfaces;
- prior check evidence stays valid only for unchanged covered surfaces;
- gate-record edits invalidate reconciliation evidence when obligations change;
- governance weakening is still blocked;
- protected core paths still require authorization;
- task-kind profiles produce the expected obligations;
- `guided` work can expand through owner-directive events without bypassing final
  tier-selected check obligations;
- committed gate records contain no absolute local paths, raw transcripts,
  environment dumps, or other local-machine details.

### 10.4 Test Ownership

This spec's `tests` list owns the ledger/evaluator/CLI/hook/wrapper contracts.
The investigation digest's missing-test list (ADR §4 behaviours not yet covered)
maps to these files:

| Test file | Owns |
|---|---|
| `tests/qa/test_gate_record.py` | Rewritten CLI surface (init/plan/amend/check/finalize), alias delegation, deterministic discovery, label vocabulary (`bypass`), surface classification, governance-touch, sanitization (no absolute paths/transcripts/env dumps). |
| `tests/qa/test_gate_ledger.py` | New: append-only ledger schema, `schema_version` 2, event accumulation never overwriting, claimed-but-unverified docs/test reconciliation, incremental check-event validity by covered surface + input fingerprint. |
| `tests/qa/test_gate_evaluator.py` | New: git-observed diff over declarations, tier derivation + escalation, obligation inference from §7.7 matrix per task kind, CI-graph-driven check inference, single sentrux classifier, guards-run-once, parity fail-closed, mode equivalence (local == ci reconciliation path). |
| `tests/qa/test_gate_record_ci.py` | Rewritten CI-mode reconciliation: issue closure, scope, test-evidence, sentrux advisory semantics, guard aggregation, `test_engineer_scope_guard` invocation — as ledger-reconcile assertions. |
| `tests/qa/test_gate_record_hooks.py` | Rewritten structural wiring: hooks/pre-commit/CI call the single evaluator entry point and the new command names; no legacy entry points; minimal worktree-guard logic; `.audit/` gitignored. |
| `tests/scripts/test_scistudio_pr_create.py` | Rewritten wrapper: delegates to `check --mode pre-pr`/pre-PR `finalize`, uses shared discovery, no caller-side finding filter, preserves `--dry-run`/`SCISTUDIO_SKIP_PREFLIGHT`. |

Guard-specific tests (`test_core_change_guard`, `test_governance_mod_guard`,
`test_human_bypass_guard`, `test_pr_merge_guard`, `test_worktree_write_guard`,
`test_test_engineer_scope_guard`, `test_sentrux_gate`,
`test_governance_weakened_ci_check`, `test_docs_landing`, `test_issue_link`,
`test_persona_policy`, `test_governance_paths`) are kept/modified per the digest
classification (label rename, `live_implementer` persona, evaluator-supplied
inputs); they remain under `tests/qa/**` and are owned by the guard workstream
but covered by this spec's `governs` glob.

## 11. Consequences

Positive: the gate record becomes the single source of truth; receipt
duplication disappears; local and CI behaviour become explainably identical;
check evidence is incremental; task-kind profiles reduce ceremony without
weakening CI; owner-guided implementation is representable without pretending all
scope was known up front.

Risks: the rewrite touches critical governance, hook, wrapper, and CI paths;
docs/command examples may be stale during migration; compatibility aliases can
preserve old assumptions if kept too long; the ledger schema must stay small
enough for agents and reviewers to use.

## Appendix A. Concrete Ledger Example

The ledger is one append-only JSON object: top-level identity fields plus event
arrays. Events accumulate and are never overwritten or deleted; corrections are
new events. `schema_version` is bumped to `2`.

```json
{
  "schema_version": 2,
  "record_id": "1505-save-data-unified-io",
  "session_id": "0b1f3c2a-9d44-4e7a-8c11-2f6e5a0b9d10",
  "runtime": "claude-code",
  "task_kind": "bugfix",
  "strictness_tier": 2,
  "persona": "implementer",
  "branch": "hotfix-save-data-extension",
  "owner_directive": "Fix SaveData unified IO extension handling for #1505.",
  "governance_touch": false,
  "declared_scope": {
    "include": ["src/scistudio/blocks/save_data/**", "tests/blocks/test_save_data.py"],
    "exclude": ["src/scistudio/blocks/save_data/legacy/**"]
  },
  "required_obligations": {
    "checks": ["lint_format", "type_check", "python_tests"],
    "docs": ["docs_na:implementation:internal bugfix, no public contract change"],
    "tests": ["changed_test_required"],
    "guards": ["scope", "issue_link", "docs_landing"],
    "admin_labels": []
  },
  "issues": [{ "number": 1505, "url": "https://github.com/org/SciStudio/issues/1505" }],
  "directive_events": [
    {
      "at": "2026-05-29T12:01:33Z",
      "owner_directive": "Also cover the .csv.gz extension path.",
      "reason": "owner expanded scope during review"
    }
  ],
  "observed_diff": {
    "base": "origin/main",
    "head": "HEAD",
    "base_sha": "a1b2c3d4",
    "head_sha": "e5f6a7b8",
    "diff_fingerprint": "sha256:9f2c...",
    "changed_files": [
      "src/scistudio/blocks/save_data/io.py",
      "tests/blocks/test_save_data.py"
    ],
    "surfaces": { "implementation": 1, "test": 1, "governance": 0, "protected_core": 0 }
  },
  "check_events": [
    {
      "at": "2026-05-29T12:10:02Z",
      "name": "lint_format",
      "command": "ruff check . && ruff format --check .",
      "tool_versions": { "ruff": "0.11.4" },
      "covered_surface": "python",
      "input_fingerprint": "sha256:9f2c...",
      "exit_code": 0,
      "summary": "clean",
      "raw_log_ref": ".workflow/local/logs/lint_format-e5f6a7b8.log"
    }
  ],
  "docs_events": [
    { "at": "2026-05-29T12:05:00Z", "kind": "na", "class": "implementation",
      "rationale": "internal bugfix, no public contract change" }
  ],
  "test_events": [
    { "at": "2026-05-29T12:06:00Z", "kind": "path", "path": "tests/blocks/test_save_data.py",
      "verified_in_diff": true }
  ],
  "guard_events": [
    { "at": "2026-05-29T12:10:05Z", "guard": "issue_link", "status": "pass", "findings": [] }
  ],
  "reconcile_events": [
    {
      "at": "2026-05-29T12:10:06Z",
      "mode": "local",
      "tier": 2,
      "diff_fingerprint": "sha256:9f2c...",
      "result": "pass",
      "unsatisfied": []
    }
  ],
  "commit": { "sha": "e5f6a7b8", "trailers": ["Gate-Record: .workflow/records/1505-save-data-unified-io.json", "Assisted-by: Claude:claude-opus-4-8"] },
  "pull_request": { "url": null, "number": null, "closes": [1505] },
  "requested_admin_labels": [],
  "observed_admin_labels": []
}
```

Sub-model carry-forward summary:

| Current sub-model | In schema v2 |
|---|---|
| `IssueRef` | Carried forward (`issues`, `pull_request.closes`). |
| `Scope` | Carried forward as `declared_scope.include/exclude`; expansions recorded as `directive_events`, not overwrites. |
| `CommitEvidence` | Carried forward as `commit`. |
| `PullRequestEvidence` | Carried forward as `pull_request`; gains pre-PR/post-PR distinction. |
| `AdminLabelEvidence` | Split into `requested_admin_labels` (local, non-authoritative) and `observed_admin_labels` (CI, with actor/permission provenance). |
| `CheckEvidence` | Reshaped into append-only `check_events` with `covered_surface` + `input_fingerprint`. |
| `SentruxEvidence` | Recorded as a `guard_event`/`check_event` variant; `parse_sentrux_result` kept as the evidence normalizer. |
| `FullAuditEvidence` | Recorded as a `check_event` variant. |
| `GateStage` enum / fixed stages array | Removed; replaced by the six lifecycle concerns reconciled from events. |
