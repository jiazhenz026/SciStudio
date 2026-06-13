# Gate Record CLI Command-Set Reference

This is the consolidated, agent-facing reference for the ADR-042 Addendum 6
gate-record ledger CLI. It gathers every workflow command, its arguments, the
`--mode` family, exit codes, strictness tiers, per-task-kind and per-persona
obligation profiles, and a soft-routing guide an agent can follow to self-route
a task end to end.

This document is a practical reference. The normative source is
`docs/adr/ADR-042-addendum6.md` (§7.5–§7.10) and the implementation spec
`docs/specs/adr-042-gate-ledger-runtime.md`. The procedure walkthrough lives in
`docs/ai-developer/specific_rules/gated-workflow.md`. Where this reference and an
older doc disagree on a CLI fact, prefer this reference and the implementation in
`src/scistudio/qa/governance/gate_record/`.

All commands are invoked as:

```bash
python -m scistudio.qa.governance.gate_record <command> [arguments]
```

## 1. Purpose And One-Pass Philosophy

The gate exists so that a single guided pass reaches PR-readiness. An agent does
not run lint, type, test, audit, or guard commands by hand and does not assemble
a bespoke checklist. Instead:

- `init` creates or updates the committed ledger and **prints task-specific
  instructions** derived from the task kind, persona, strictness tier, scope,
  issues, and governance-touch status. The instructions tell the agent which
  fields and evidence each later step will expect.
- `plan` / `amend` record scope, issues, docs, tests, checks, and owner
  directives as **append-only ledger events**. Nothing is overwritten or
  deleted; later events supersede earlier ones and the evaluator reads the
  latest effective state.
- `check` **observes the real git diff**, infers the tier-selected
  CI-equivalent check set, runs those checks at CI-resolved tool versions in a
  CI-equivalent importable environment, records sanitized check events, runs all
  applicable guards, and reports unsatisfied obligations with concrete repair
  hints. Agents never run `ruff` / `mypy` / `pytest` / full audit / guards one
  by one; `check` does it.
- `finalize` records commit and PR provenance and performs final reconciliation
  before (pre-PR) and after (post-PR) the PR exists.

The gate record is the **single source of truth**: an append-only ledger under
`.workflow/records/`. Receipt behavior is folded into the ledger as check and
reconcile events. Local hooks, the PR wrapper, and CI all call **one shared
evaluator** so passing the gate locally predicts a passing CI run.

Obligations always arrive with a repair hint. When `check` finds a missing
test, docs path, issue link, or guard authorization, it prints the exact
follow-up command, so the agent can fix it in the same pass without
guess-and-reject loops.

## 2. The Five Workflow Commands

The five normative workflow commands are `init`, `plan`, `amend`, `check`, and
`finalize`. Each command supports additive field updates; rerun a command with
extra fields rather than recreating the ledger. The common additive field flags
(`--owner-directive`, `--include`, `--exclude`, `--issue`, `--docs-updated`,
`--docs-na`, `--test-path`, `--test-na`, `--check`, `--check-na`,
`--admin-label`) are repeatable and shared by `plan` / `amend` / `check` /
`finalize`.

Every command accepts a top-level `--repo-root <path>` (defaults to the current
working directory).

### 2.1 `init`

Create or update the ledger for the current task and print task-specific
instructions.

```bash
python -m scistudio.qa.governance.gate_record init \
  --task-kind hotfix|bugfix|feature|refactor|docs|maintenance|manager|guided \
  --persona manager|implementer|adr_author|audit_reviewer|test_engineer|live_implementer \
  --runtime codex|claude-code|gemini|<runtime-id> \
  --branch <branch> \
  --owner-directive "<owner instruction>" \
  [--slug <short-task-slug>] \
  [--session-id <local-session-id>] \
  [--issue <number>] \
  [--include <path-or-glob>] \
  [--exclude <path-or-glob>] \
  [--governance-touch true|false] \
  [--record .workflow/records/<record>.json] \
  [--print-instructions true|false] \
  [--instructions-output <path>]
```

| Argument | Required | Repeatable | Meaning |
|---|---:|---:|---|
| `--task-kind` | yes | no | Task profile (one of the eight kinds) |
| `--persona` | yes | no | Persona profile (one of the six personas) |
| `--runtime` | yes | no | AI runtime executing the task (Codex, Claude Code, Gemini, or a local CLI agent) |
| `--branch` | yes | no | Branch this ledger governs |
| `--owner-directive` | yes | yes | Initial owner instruction; repeat for additional directives at init time |
| `--slug` | no | no | Short human-readable slug for the generated record path |
| `--session-id` | no | no | Local session id under `.git/scistudio/gates/`; generated automatically when omitted |
| `--issue` | no | yes | GitHub issue number linked to the task |
| `--include` | no | yes | Declared in-scope repo-relative path or glob |
| `--exclude` | no | yes | Declared out-of-scope repo-relative path or glob |
| `--governance-touch` | no | no | Whether governance surfaces may be changed |
| `--record` | no | no | Explicit committed ledger path under `.workflow/records/`; normally generated automatically |
| `--print-instructions` | no | no | Print task-specific instructions after init (default `true`) |
| `--instructions-output` | no | no | Repo-relative path to also write the generated instructions |

When `--record` is omitted, `init` generates the path automatically, preferring
`.workflow/records/<issue>-<slug>.json` when an issue is known and
`.workflow/records/<branch-slug>-<slug>.json` otherwise. `init` prints the
selected ledger path and may be rerun for the same task to append issues,
directives, or scope without erasing earlier events.

Compatibility alias: `start` delegates to `init` with identical arguments.

### 2.2 `plan`

Append planning fields without running the full check set.

```bash
python -m scistudio.qa.governance.gate_record plan \
  [--owner-directive "<scope or plan update>"] \
  [--include <path-or-glob>] [--exclude <path-or-glob>] \
  [--issue <number>] \
  [--docs-updated <path>] [--docs-na "<class>:<rationale>"] \
  [--test-path <path>] [--test-na "<class>:<rationale>"] \
  [--check <check-name>] [--check-na "<check-name>:<rationale>"] \
  [--admin-label admin-approved:bypass|admin-approved:core-change|admin-approved:merge] \
  [--record .workflow/records/<record>.json]
```

| Argument | Required | Repeatable | Meaning |
|---|---:|---:|---|
| `--record` | no | no | Explicit ledger path; normally auto-discovered from the current branch |
| `--owner-directive` | no | yes | Owner/manager instruction that changes plan or scope |
| `--include` / `--exclude` | no | yes | Add declared in-scope / out-of-scope path or glob |
| `--issue` | no | yes | Add issue link |
| `--docs-updated` | no | yes | Repo-relative docs/spec/ADR/changelog/checklist path |
| `--docs-na` | no | yes | Documentation class plus rationale (`"<class>:<rationale>"`) |
| `--test-path` | no | yes | Changed or expected test/runtime/e2e evidence path |
| `--test-na` | no | yes | Test class plus rationale |
| `--check` | no | yes | Add an expected check beyond inferred tier-selected obligations |
| `--check-na` | no | yes | Check name plus accepted N/A rationale |
| `--admin-label` | no | yes | Requested/expected admin label (local record is not authoritative) |

`plan` discovers the active ledger for the current branch when `--record` is
omitted (it errors if zero or multiple ledgers match). It observes the current
diff when available and recomputes provisional obligations but does not run
expensive checks.

### 2.3 `amend`

Append a correction or field update to the ledger. `amend` is append-only: it
records what changed and why and never silently rewrites or deletes old events.

```bash
python -m scistudio.qa.governance.gate_record amend \
  --reason "<why the ledger is being corrected>" \
  [--owner-directive "<new or corrected instruction>"] \
  [--task-kind <kind>] [--persona <persona>] [--branch <branch>] \
  [--issue <number>] [--remove-issue <number>] \
  [--include <path-or-glob>] [--remove-include <path-or-glob>] \
  [--exclude <path-or-glob>] [--remove-exclude <path-or-glob>] \
  [--governance-touch true|false] \
  [--docs-updated <path>] [--docs-na "<class>:<rationale>"] \
  [--test-path <path>] [--test-na "<class>:<rationale>"] \
  [--check <check-name>] [--check-na "<check-name>:<rationale>"] \
  [--admin-label <label>] \
  [--record .workflow/records/<record>.json]
```

| Argument | Required | Repeatable | Meaning |
|---|---:|---:|---|
| `--reason` | yes | no | Human-readable reason for the amendment |
| `--owner-directive` | no | yes | Add or correct owner instruction |
| `--task-kind` | no | no | Correct task kind when the original classification was wrong |
| `--persona` | no | no | Correct persona when routing changes |
| `--branch` | no | no | Correct branch metadata |
| `--issue` / `--remove-issue` | no | yes | Add an issue link / mark one superseded |
| `--include` / `--remove-include` | no | yes | Add / supersede an include pattern |
| `--exclude` / `--remove-exclude` | no | yes | Add / supersede an exclude pattern |
| `--governance-touch` | no | no | Correct governance-touch declaration |
| `--docs-updated` / `--docs-na` | no | yes | Add docs landing path / docs N/A rationale |
| `--test-path` / `--test-na` | no | yes | Add test evidence path / test N/A rationale |
| `--check` / `--check-na` | no | yes | Add expected check / check N/A rationale |
| `--admin-label` | no | yes | Add expected admin label |
| `--record` | no | no | Explicit ledger path; normally auto-discovered |

`amend` observes the current diff only when the amended field affects scope,
obligations, or protected-path evaluation. It does not run expensive checks.

Compatibility alias: the old `docs` subcommand maps to
`amend --docs-updated <path>` / `amend --docs-na "<class>:<rationale>"`.

### 2.4 `check`

Run tier-selected local CI-equivalent checks and reconcile the ledger. This is
the main local preflight.

```bash
python -m scistudio.qa.governance.gate_record check \
  [--base <ref>] [--head HEAD] \
  [--mode local|pre-commit|commit-msg|pre-push|pre-pr|ci] \
  [--pr-body-file .workflow/local/pr-body.md] \
  [--owner-directive "<late scope update>"] \
  [--include <path-or-glob>] [--exclude <path-or-glob>] \
  [--issue <number>] \
  [--docs-updated <path>] [--docs-na "<class>:<rationale>"] \
  [--test-path <path>] [--test-na "<class>:<rationale>"] \
  [--check <check-name>] [--check-na "<check-name>:<rationale>"] \
  [--admin-label <label>] \
  [--only <check-name>] [--skip-execution] \
  [--record .workflow/records/<record>.json]
```

| Argument | Required | Repeatable | Meaning |
|---|---:|---:|---|
| `--base` | no | no | Base ref for diff; default `git merge-base <upstream> HEAD` falling back to the raw upstream. When `--base` is omitted, `<upstream>` is the `SCISTUDIO_GATE_BASE` env var if set, else `origin/main`. Set `SCISTUDIO_GATE_BASE=origin/track/<name>` so the commit-msg / pre-commit framework hooks of a **track-stacked sub-PR** diff against their track (not `origin/main`, which would misread the whole track delta as authored here) — the same var the push/PR wrappers already honor (#1627). An explicit `--base` still wins. Deeply-stacked branches may need an explicit `--base` |
| `--head` | no | no | Head ref for diff; default `HEAD` |
| `--mode` | no | no | One of `local` (default), `pre-commit`, `commit-msg`, `pre-push`, `pre-pr`, `ci` |
| `--pr-body-file` | no | no | Intended PR body file for pre-PR issue-closure checks |
| `--owner-directive` | no | yes | Late owner instruction or scope update |
| `--include` / `--exclude` | no | yes | Add scope before reconciliation |
| `--issue` | no | yes | Add issue link before reconciliation |
| `--docs-updated` / `--docs-na` | no | yes | Record docs landing / N/A before reconciliation |
| `--test-path` / `--test-na` | no | yes | Record test evidence / N/A before reconciliation |
| `--check` | no | yes | Add a task-specific required check before inference |
| `--check-na` | no | yes | Record accepted N/A rationale for a check (see §9 for the ci.yml-owned caveat) |
| `--admin-label` | no | yes | Requested/expected admin label (local records intent only; CI verifies provenance) |
| `--only` | no | yes | Run only selected checks for recovery; reconciliation still reports missing obligations |
| `--skip-execution` | no | no | Reconcile without running commands; never sufficient for final PR readiness when required evidence is absent or stale |
| `--record` | no | no | Explicit ledger path; normally auto-discovered |

`check` automatically: (1) observes the current git diff; (2) infers required
checks from changed files, task kind, persona, plan, and CI configuration;
(3) runs all required local commands unless `--only` / `--skip-execution`;
(4) writes raw transcripts only under ignored local paths (`.workflow/local/**`);
(5) records sanitized check events in the committed ledger; (6) runs all
applicable guards through the shared evaluator; (7) records a reconciliation
event; (8) exits nonzero when required obligations remain unsatisfied.

Ledger discovery is deterministic: exactly one current-branch ledger is
accepted; zero ledgers reports "run init"; multiple ledgers reports the
candidate paths and asks for `--record`.

Finalized post-PR ledgers are excluded from normal local discovery so a
completed record is not reused as active work. `check --mode ci` may include
finalized records because CI validates the submitted PR record. Local hook
modes may include only finalized ledger paths that are actually staged or in the
pre-push changed-file set, so the final provenance commit can pass without
reopening unrelated completed records. A temporarily unreadable ledger is a
schema/retry error, not "no ledger found".

### 2.5 `finalize`

Record commit and PR provenance and perform final reconciliation. `finalize`
has two modes.

**Pre-PR finalize** (before the PR exists) requires `--pr-body-file`, must not
require `--pr`:

```bash
python -m scistudio.qa.governance.gate_record finalize \
  [--base <ref>] [--head HEAD] \
  --commit <sha> \
  --pr-body-file .workflow/local/pr-body.md \
  --closes "#<issue>" \
  [--owner-directive "<final instruction>"] \
  [--include <path-or-glob>] [--exclude <path-or-glob>] \
  [--issue <number>] \
  [--docs-updated <path>] [--docs-na "<class>:<rationale>"] \
  [--test-path <path>] [--test-na "<class>:<rationale>"] \
  [--admin-label <label>]
```

**Post-PR finalize** (after the PR is created) requires `--pr`, must not be
required before PR creation:

```bash
python -m scistudio.qa.governance.gate_record finalize \
  --commit <sha> \
  --pr <url-or-number> \
  --pr-body-file .workflow/local/pr-body.md
```

| Argument | Required | Repeatable | Meaning |
|---|---:|---:|---|
| `--base` | no | no | Base ref for final diff; same default as `check` |
| `--head` | no | no | Head ref for final diff; default `HEAD` |
| `--commit` | yes | yes | Commit SHA included in the candidate or PR |
| `--pr` | conditional | no | PR URL or number; required only for post-PR finalize |
| `--pr-body-file` | conditional | no | Intended/actual PR body for issue-closure validation; required before PR creation |
| `--closes` | no | yes | Issue closure token, e.g. `#1234` |
| `--owner-directive` | no | yes | Final owner instruction or rationale |
| `--include` / `--exclude` | no | yes | Last scope additions before reconciliation |
| `--issue` | no | yes | Add issue link before final reconciliation |
| `--docs-updated` / `--docs-na` | no | yes | Record docs landing / N/A before final reconciliation |
| `--test-path` / `--test-na` | no | yes | Record test evidence / N/A before final reconciliation |
| `--admin-label` | no | yes | Expected admin label (authoritative only when CI observes it) |
| `--record` | no | no | Explicit ledger path; normally auto-discovered |

Pre-PR `finalize` re-observes the diff, validates the intended PR body's issue
closure, and reruns reconciliation without requiring a PR URL/number. Post-PR
`finalize` records the PR URL or number and reruns reconciliation with PR
metadata; it fails when checks are stale, required issue closure is missing from
the PR body, required docs/tests are absent, or tier-selected check obligations
are unsatisfied.

After post-PR `finalize`, commit and push the ledger update. CI-mode ledger
discovery includes finalized ledgers so the committed PR provenance is still
validated by `gate_record check --mode ci`; only ordinary local active-session
discovery excludes finalized ledgers.

## 3. The `--mode` Family

`check` (and the mode-specific compatibility aliases) dispatch on `--mode`. All
modes call the same shared evaluator; the mode only changes which facts are
required now versus recorded as a pre-PR gap.

| Mode | Caller | What it validates |
|---|---|---|
| `local` | Manual `gate_record check` (default) | Full local CI-equivalent preflight at the selected tier. PR-state facts (issue, label provenance) are recorded as pre-PR gaps, not hard failures |
| `pre-commit` | Pre-commit hook | Fast structural reconciliation on the **staged** diff |
| `commit-msg` | Commit-msg hook | Validate required commit trailers; does not run checks |
| `pre-push` | Pre-push hook | Pre-push reconciliation: scope/diff coherence and recorded-check freshness. Does **not** block a WIP push on PR-readiness obligations (issue link, docs/test landing) — those belong to `pre-pr` / `ci` |
| `pre-pr` | PR wrapper and pre-PR hook | Pre-PR readiness with `--pr-body-file`; issue/docs/test obligations are required-now; parity gaps fail closed |
| `ci` | CI workflow (`workflow-gate.yml` / "Verify Workflow Compliance") | Authoritative governance + guard validation with real PR context and label-actor provenance |

Important `ci` mode split: `ci` mode validates **governance and guards**
(scope, issue linkage, docs landing, persona policy, core/mod/merge/human-bypass
guards, weakened-CI, Sentrux, etc.). It does **not** re-require ledger check
events for the `ci.yml` quality matrix (lint/format, type check, architecture
tests, full audit, python tests, import contracts, frontend, wheel release
smoke, semantic-dup). Those run as **separate authoritative `ci.yml` jobs** on
the same PR. `local` and `pre-pr` modes still run the full CI-equivalent
preflight selection, so the local pass predicts the `ci.yml` matrix result.

In `ci` mode, documentation that **landed** and tests that **changed** are taken
directly from the observed git diff, so a docs/test obligation can be satisfied
from the diff without a separately declared `docs_event` / `test_event`.

## 4. Exit Codes

| Exit code | Meaning |
|---:|---|
| 0 | Command completed and current reconciliation passed (when applicable) |
| 1 | Command completed but current reconciliation failed (unsatisfied obligations) |
| 2 | Invalid CLI usage or unsupported argument combination |
| 3 | Ledger schema or migration error |
| 4 | Required external tool unavailable / local env not CI-equivalent, and no accepted N/A rationale exists |
| 5 | Privacy/sanitization violation in a would-be-committed ledger event |

Exit code 4 is also how parity fail-closed surfaces (see §9): when only
environment-parity gaps remain in `pre-pr` / `ci` modes, the command exits 4
rather than 1, because the local environment could not be made CI-equivalent.

## 5. Strictness Tiers

The evaluator derives `strictness_tier` from `task_kind` and then **escalates
based on the observed diff. It never lowers.** Agents never choose a tier
directly. Tier numbers run from strict (1) to light (3).

Baseline tier by task kind:

| Tier | Baseline task kinds | Meaning |
|---|---|---|
| Tier 1 (Strict) | `feature`, `refactor` | Plan before implementation. Scope, issue, expected tests, docs impact, and expected checks declared early. `check` must run a full local mirror of merge-blocking CI command surfaces |
| Tier 2 (Standard) | `bugfix`, `hotfix`, `maintenance`, `guided` (default) | May discover details during debugging. `hotfix` / `guided` may delay full gate completion during the live session, but everything must reconcile before commit/push/PR |
| Tier 3 (Lightweight) | `docs`, `manager` | May start with a sparse plan. `check` runs only mandatory checks for the observed diff |

Escalation (raises to Tier 1 regardless of starting kind) triggers when the
observed diff touches:

- protected core / runtime / engine paths
  (`src/scistudio/{core,engine,blocks,workflow,utils}/**`);
- governance or workflow files; or
- three or more distinct top-level surfaces (implementation + frontend +
  packaging), i.e. a broad cross-module change.

A Tier 3 `docs` task that ends up editing protected core code, or a Tier 2
`maintenance` task that rewrites a governance surface, is evaluated at Tier 1.
Beyond tier escalation, changed files may add specific obligations such as
protected-path authorization, governance checks, frontend checks, or
runtime/e2e evidence.

Per-concern tier behavior:

| Concern | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|
| `init` | Issue (when known), branch, owner directive, persona, task kind, and initial scope | Branch, owner directive, persona, task kind; issue/scope may be completed later | Branch, owner directive, persona, task kind; issue/scope may be completed later |
| `plan` | Required before implementation; declare expected docs/tests/checks or N/A | Required before final check; may be partial during debugging | Optional unless the evaluator needs early docs/tests/scope guidance |
| `amend` | Allowed; every scope/obligation correction needs a `--reason` | Normal way to add discovered scope/tests/docs/issues | Normal way to record live directives and late fields |
| `check` | Full merge-blocking CI mirror; `--only`/`--skip-execution` recovery-only | Governance/lint/audit baseline plus all changed-surface CI checks | Mandatory checks for the observed diff only; sparse planning does not reduce mandatory checks |
| `finalize` | Fails if any plan/test/docs/check/issue field is missing | Fails if observed diff lacks issue/test/docs/check reconciliation | Fails if observed diff lacks issue/test/docs/check reconciliation |
| Admin label | Required for protected core, gate bypass, or merge automation | Same | Same |

Tier 3 is **not** a quality bypass. Final `check` and `finalize` reconciliation
still enforce mandatory obligations and repository protection rules.

The tier-selected check baselines the evaluator actually runs are:

| Tier | Baseline checks (before surface-specific additions) |
|---|---|
| Tier 1 | `lint_format`, `format_check`, `type_check`, `architecture_tests`, `full_audit`, `python_tests`, `import_contracts`, `semantic_dup` |
| Tier 2 | `lint_format`, `format_check`, `full_audit` |
| Tier 3 | `full_audit` |

Surface-specific additions (all tiers) per the CI graph: Python source under
`src/**` adds lint/format/type/python-tests/import-contracts; Python tests add
lint/format/python-tests; QA/governance source under `src/scistudio/qa/**` adds
those plus `full_audit`; ADR/spec/architecture/governed-docs and
`docs/block-development/**` developer docs add `full_audit`; frontend surfaces
add `frontend`; workflow/CI files add `full_audit`; packaging surfaces add
`wheel_release_smoke`; Sentrux-applicable changes add `semantic_dup`. The
`codex_review` check is PR-only review automation and is never a local `check`
failure.

## 6. Per-Task-Kind Profiles

For each of the eight task kinds: baseline tier, `init` fields, the obligation
shape across `plan` / `check` / `finalize`, and a concrete CLI argument profile.
`<base>` is the diff base (defaults to `git merge-base origin/main HEAD`).

### `hotfix` — Tier 2

- **`init` fields**: `task_kind`, `persona`, `branch`, owner directive; issue
  and scope when known. Full gate may be incomplete during live diagnosis.
- **Obligations**: before commit/push/PR the actual diff must be explained by
  directive/scope; targeted regression test or owner-approved N/A; Tier 2
  baseline plus changed-surface checks; docs landing or N/A; close every fixed
  issue (batch hotfix records the full issue list).
- **CLI profile**:
  - `init --task-kind hotfix --persona <persona> --runtime <id> --branch <branch> --owner-directive "<hotfix directive>" [--issue <n>] [--include <path>] [--governance-touch true]`
  - `plan --owner-directive "<bug list>" --include <path> [--issue <n>] (--test-path <path> | --test-na "<class>:<rationale>") (--docs-updated <path> | --docs-na "<class>:<rationale>")`
  - `amend --reason "<new bug/scope/test/docs found>" [--owner-directive ...] [--issue <n>] [--include <path>] [--test-path <path>] [--docs-updated <path>]`
  - `check --base <base> --head HEAD [--owner-directive "<late directive>"] [--include <path>] [--issue <n>] [--test-path <path>]`
  - pre-PR `finalize --base <base> --head HEAD --commit <sha> --pr-body-file <path> --closes "#<n>"`; post-PR `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>`

### `bugfix` — Tier 2

- **`init` fields**: `task_kind`, `persona`, `branch`, owner directive, issue
  (required unless owner says the issue is being created).
- **Obligations**: regression test required unless N/A is explicit;
  implementation changes require test evidence; Tier 2 baseline plus
  changed-surface checks; docs landing when behavior or public contract changes;
  PR closes the bug issue.
- **CLI profile**:
  - `init --task-kind bugfix --persona <persona> --runtime <id> --branch <branch> --owner-directive "<bug directive>" --issue <n> [--include <path>]`
  - `plan --include <path> (--test-path <regression-test> | --test-na "<class>:<rationale>") (--docs-updated <path> | --docs-na "<class>:<rationale>") [--check <name>]`
  - `amend --reason "<debugging changed scope/evidence>" [--include <path>] [--test-path <path>] [--docs-updated <path>]`
  - `check --base <base> --head HEAD [--test-path <path>]`
  - pre-PR `finalize ... --closes "#<issue>"`; post-PR `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>`

### `feature` — Tier 1

- **`init` fields**: `task_kind`, `persona`, `branch`, owner directive, issue,
  initial feature scope (`--include` required at init).
- **Obligations**: implementation tests required; docs/spec/ADR required when
  contracts, schemas, runtime behavior, API, UI semantics, or storage change;
  full local CI mirror required; PR closes the feature issue.
- **CLI profile**:
  - `init --task-kind feature --persona <persona> --runtime <id> --branch <branch> --owner-directive "<feature directive>" --issue <n> --include <path>`
  - `plan --include <implementation-path> --test-path <test-path> --docs-updated <doc-or-spec-path> [--check <name>] [--admin-label <label>]`
  - `amend --reason "<feature scope changed>" [--include <path>] [--test-path <path>] [--docs-updated <path>]`
  - `check --base <base> --head HEAD [--include <path>] [--test-path <path>] [--docs-updated <path>]`
  - pre-PR `finalize ... --closes "#<issue>"`; post-PR `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>`

### `refactor` — Tier 1

- **`init` fields**: `task_kind`, `persona`, `branch`, owner directive, issue,
  refactor scope.
- **Obligations**: tests must cover affected contracts, or an N/A must explain
  how unchanged behavior is otherwise proven; full local CI mirror required;
  docs only when architecture or public shape changes; PR states
  behavior-preserving intent and closes the issue.
- **CLI profile**:
  - `init --task-kind refactor --persona <persona> --runtime <id> --branch <branch> --owner-directive "<refactor directive>" --issue <n> --include <path>`
  - `plan --include <path> (--test-path <behavior-preservation-test> | --test-na "<class>:<rationale>") (--docs-updated <path> | --docs-na "<class>:<rationale>")`
  - `amend --reason "<refactor affected additional surface>" [--include <path>] [--exclude <path>] [--test-path <path>]`
  - `check --base <base> --head HEAD [--test-path <path>]`
  - pre-PR `finalize ... --closes "#<issue>"`; post-PR `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>`

### `docs` — Tier 3

- **`init` fields**: `task_kind`, `persona` (`adr_author` / `manager` /
  `audit_reviewer`), `branch`, owner directive, issue when known, docs scope.
  Note: editing `docs/ai-developer/**` is a governance-surface change — use
  `--governance-touch true` and expect Tier-1-style governance checks.
- **Obligations**: frontmatter/structure/full-audit checks as applicable;
  implementation tests N/A by default unless code changes appear in the diff;
  PR closes the docs issue.
- **CLI profile**:
  - `init --task-kind docs --persona adr_author|manager|audit_reviewer --runtime <id> --branch <branch> --owner-directive "<docs directive>" [--issue <n>] --include <docs-path>`
  - `plan --docs-updated <path> [--docs-updated <path>] --test-na "implementation:<docs-only rationale>" [--check full_audit]`
  - `amend --reason "<docs scope changed>" [--include <docs-path>] [--docs-updated <path>] [--test-na "implementation:<rationale>"]`
  - `check --base <base> --head HEAD [--docs-updated <path>] [--test-na "implementation:<rationale>"]`
  - pre-PR `finalize --base <base> --head HEAD --commit <sha> --pr-body-file <path> [--closes "#<issue>"]`; post-PR `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>`

### `maintenance` — Tier 2

- **`init` fields**: `task_kind`, `persona`, `branch`, owner directive, issue,
  maintenance surface.
- **Obligations**: Tier 2 baseline plus changed-surface checks; escalates to
  full local CI mirror when the diff touches protected/governance/runtime/
  workflow surfaces; governance weakening / protected checks when applicable;
  tests for tooling behavior when implementation changes; PR closes the issue.
- **CLI profile**:
  - `init --task-kind maintenance --persona <persona> --runtime <id> --branch <branch> --owner-directive "<maintenance directive>" --issue <n> --include <path> [--governance-touch true]`
  - `plan --include <path> (--test-path <tooling-test> | --test-na "<class>:<rationale>") (--docs-updated <path> | --docs-na "<class>:<rationale>") [--check <name>] [--admin-label <label>]`
  - `amend --reason "<maintenance surface changed>" [--include <path>] [--test-path <path>] [--docs-updated <path>] [--admin-label <label>]`
  - `check --base <base> --head HEAD [--test-path <path>] [--docs-updated <path>] [--admin-label <label>]`
  - pre-PR `finalize ... --closes "#<issue>"`; post-PR `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>`

### `manager` — Tier 3

- **`init` fields**: `task_kind`, `persona=manager`, branch, owner directive,
  tracking issue.
- **Obligations**: product-code changes fail unless an explicit owner directive
  changes the task shape; manager evidence/checklist docs must be recorded;
  mandatory changed-file checks required; PR closes or updates the tracking
  issue.
- **CLI profile**:
  - `init --task-kind manager --persona manager --runtime <id> --branch <branch> --owner-directive "<manager directive>" --issue <n> --include <planning-or-report-path>`
  - `plan --docs-updated <checklist-or-report-path> --test-na "implementation:<manager-only rationale>" [--check <integration-check>]`
  - `amend --reason "<coordination update>" [--issue <n>] [--include <path>] [--docs-updated <path>] [--owner-directive ...]`
  - `check --base <base> --head HEAD [--docs-updated <path>] [--test-na "implementation:<rationale>"]`
  - pre-PR `finalize ... --closes "#<tracking-issue>"`; post-PR `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>`

### `guided` — Tier 2 by default (Tier 1 when escalated)

- **`init` fields**: `task_kind=guided`, `persona=live_implementer`, branch,
  owner directive, issue/scope when known. Full gate may be incomplete during
  live owner-guided work. Escalates to Tier 1 for feature / core / runtime /
  governance / broad-refactor work.
- **Obligations**: before commit/push/PR the actual diff must be explainable by
  recorded owner-directive events; Tier 2 baseline plus changed-surface checks
  by default, or full local CI mirror when escalated to Tier 1; PR cannot open
  until current diff, issue linkage, docs/tests/checks, and closure intent
  reconcile.
- **CLI profile**:
  - `init --task-kind guided --persona live_implementer --runtime <id> --branch <branch> --owner-directive "<live owner directive>" [--issue <n>] [--include <path>] [--governance-touch true]`
  - `plan --owner-directive "<current instruction>" [--include <path>] [--issue <n>] [--test-path <path>] [--test-na "<class>:<rationale>"] [--docs-updated <path>] [--docs-na "<class>:<rationale>"]`
  - `amend --reason "<owner redirected live work>" --owner-directive "<new instruction>" [--issue <n>] [--include <path>] [--test-path <path>] [--docs-updated <path>]`
  - `check --base <base> --head HEAD [--owner-directive "<late instruction>"] [--include <path>] [--issue <n>] [--test-path <path>] [--docs-updated <path>]`
  - pre-PR `finalize ... --closes "#<issue>"`; post-PR `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>`

## 7. Per-Persona Overlays

Persona overlays add or constrain arguments on top of the selected task-kind
profile.

### `manager`

Coordinate agents, maintain checklists, prepare merges. Product-code changes are
blocked unless separately authorized.

- `init --persona manager --task-kind manager|guided|maintenance --owner-directive "<coordination directive>" --issue <tracking-issue> --include <planning-or-report-path>`
- `plan --docs-updated <checklist-or-report-path> --test-na "implementation:<manager-only rationale>"`
- `check --docs-updated <path> --test-na "implementation:<rationale>"`
- `finalize --closes "#<tracking-issue>"`

### `implementer`

Implement code, tests, tool wiring, docs generated from implementation.
Implementation changes require test evidence; docs/spec updates required for
contract/runtime/API/storage/UI changes.

- `init --persona implementer --task-kind hotfix|bugfix|feature|refactor|maintenance --owner-directive "<implementation directive>" --issue <n> --include <implementation-path>`
- `plan --test-path <path> (--docs-updated <path> | --docs-na "<class>:<rationale>")`
- `amend --include <path> --test-path <path>` when implementation scope expands
- `check --test-path <path>`
- `finalize --closes "#<issue>"`

### `adr_author`

Draft or revise ADR/spec governance text and schemas. Source changes fail unless
scope explicitly includes tooling/schema implementation.

- `init --persona adr_author --task-kind docs|feature|maintenance --owner-directive "<ADR/spec directive>" (--include docs/adr/<path> | --include docs/specs/<path>) [--issue <n>]`
- `plan --docs-updated <adr-or-spec-path> --test-na "implementation:<docs-only rationale>" --check full_audit`
- `check --docs-updated <path> --test-na "implementation:<rationale>"`
- `finalize [--closes "#<issue>"]`

### `audit_reviewer`

Inspect diffs, audit findings, CI failures, conformance gaps. Read-only scope by
default; product changes blocked unless the owner changes persona/scope.

- `init --persona audit_reviewer --task-kind manager|docs|maintenance --owner-directive "<audit directive>" --issue <tracking-issue> --include <audit-report-path>`
- `plan --docs-updated <audit-report-path> --test-na "implementation:<audit-only rationale>"`
- `amend --docs-updated <finding-report-path> --issue <followup-issue>`
- `check --docs-updated <path> --test-na "implementation:<rationale>"`
- `finalize (--closes "#<tracking-issue>" | --closes "#<audit-issue>")`

### `test_engineer`

Design tests, add test evidence, run runtime/e2e validation. Production code is
blocked by `test_engineer_scope_guard` unless explicitly authorized.

- `init --persona test_engineer --task-kind bugfix|maintenance|manager --owner-directive "<test directive>" --issue <n> (--include tests/** | --include frontend/e2e/** | --include docs/audit/**)`
- `plan --test-path <path> [--docs-updated <validation-report>] --docs-na "<class>:<rationale>"`
- `amend --test-path <path> --docs-updated <path> [--admin-label admin-approved:core-change]` if an owner-approved production-code exception applies
- `check --test-path <path>`
- `finalize --closes "#<issue>"`

### `live_implementer`

Carry out owner-directed live implementation (`guided` task kind). Same quality
obligations as `implementer` for the selected tier; dynamic scope is allowed
only through recorded directive events.

- `init --persona live_implementer --task-kind guided --owner-directive "<live owner directive>" [--issue <n>] [--include <path>]`
- `plan --owner-directive "<current instruction>" [--include <path>] [--test-path <path>] [--docs-updated <path>] [--docs-na "<class>:<rationale>"]`
- `amend --reason "<owner redirected live work>" --owner-directive "<new instruction>" [--include <path>] [--issue <n>] [--test-path <path>] [--docs-updated <path>]`
- `check [--owner-directive "<late instruction>"] [--include <path>] [--test-path <path>]`
- `finalize --closes "#<issue>"`

## 8. Soft Routing — The Agent Decision Guide

Pick the row that matches the work. It gives the task kind, persona, baseline
tier, and the command sequence. `<base>` defaults to
`git merge-base origin/main HEAD`; `<id>` is the runtime id (`claude-code`,
`codex`, `gemini`, …).

| If your task is… | task_kind | persona | tier | Command sequence |
|---|---|---|---|---|
| A new feature / new behavior | `feature` | `implementer` | 1 | `init … --issue <n> --include <path>` → `plan --include <path> --test-path <test> --docs-updated <doc>` → implement → `check --base <base>` → pre-PR `finalize --commit <sha> --pr-body-file <path> --closes "#<n>"` → push + PR → post-PR `finalize --pr <url>` |
| Fixing one known bug | `bugfix` | `implementer` | 2 | `init … --issue <n>` → `plan --include <path> --test-path <regression-test>` → fix → `check --base <base>` → pre-PR `finalize … --closes "#<n>"` → push + PR → post-PR `finalize` |
| Live owner-directed debugging of a bug batch | `hotfix` | `implementer` | 2 | `init … --owner-directive "<directive>" [--issue <n>]` → diagnose → `amend --reason … --issue <n> --include <path> --test-path <test>` per fix → `check --base <base>` → pre-PR `finalize … --closes "#<n>" [--closes "#<m>"]` → push + PR → post-PR `finalize` |
| Behavior-preserving cleanup / code movement | `refactor` | `implementer` | 1 | `init … --issue <n> --include <path>` → `plan --include <path> --test-path <behavior-test>` → refactor → `check --base <base>` → pre-PR `finalize … --closes "#<n>"` → push + PR → post-PR `finalize` |
| Owner-directed live session, scope evolving | `guided` | `live_implementer` | 2 (→1 if escalated) | `init … --owner-directive "<directive>" [--issue <n>]` → `amend --reason … --owner-directive "<new>" --include <path>` per directive → `check --base <base>` → pre-PR `finalize … --closes "#<n>"` → push + PR → post-PR `finalize` |
| Writing/revising an ADR, spec, or addendum | `docs` | `adr_author` | 3 | `init … --include docs/adr/<path>` → `plan --docs-updated <path> --test-na "implementation:docs-only" --check full_audit` → write → `check --base <base>` → pre-PR `finalize … [--closes "#<n>"]` → push + PR → post-PR `finalize` |
| Editing non-governance product docs | `docs` | `adr_author`/`manager` | 3 | `init … --include <docs-path>` → `plan --docs-updated <path> --test-na "implementation:docs-only"` → write → `check --base <base>` → pre-PR `finalize …` → push + PR → post-PR `finalize` |
| Editing `docs/ai-developer/**` (rules, personas, skills) | `docs` | `adr_author` | 3 (governance-surface) | `init … --include docs/ai-developer/<path> --governance-touch true` → `plan --docs-updated <path> --test-na "implementation:docs-only"` → write → `check --base <base>` (expect governance/full-audit checks) → pre-PR `finalize … --closes "#<n>"` → push + PR → post-PR `finalize` |
| Dependency / config / tooling hygiene | `maintenance` | `implementer` | 2 | `init … --issue <n> --include <path> [--governance-touch true]` → `plan --include <path> (--test-path <test> | --test-na …) (--docs-updated <path> | --docs-na …)` → change → `check --base <base>` → pre-PR `finalize … --closes "#<n>"` → push + PR → post-PR `finalize` |
| Coordinating agents / checklists / merge prep | `manager` | `manager` | 3 | `init … --issue <tracking> --include <planning-path>` → `plan --docs-updated <checklist> --test-na "implementation:manager-only"` → coordinate → `check --base <base>` → pre-PR `finalize … --closes "#<tracking>"` → push + PR → post-PR `finalize` |
| Auditing a diff / claimed work (read-only) | `manager` or `docs` | `audit_reviewer` | 3 | `init … --issue <tracking> --include <audit-report-path>` → `plan --docs-updated <report> --test-na "implementation:audit-only"` → audit → `check --base <base>` → pre-PR `finalize … --closes "#<tracking>"` → push + PR → post-PR `finalize` |
| Adding tests / runtime / e2e evidence | `bugfix`/`maintenance` | `test_engineer` | 2 | `init … --issue <n> --include tests/**` → `plan --test-path <path>` → add tests → `check --base <base>` → pre-PR `finalize … --closes "#<n>"` → push + PR → post-PR `finalize` |
| Changing protected core (`src/scistudio/{core,engine,blocks,workflow,utils}/**`) | match the work; escalates to Tier 1 | `implementer` | 1 | as above + `--admin-label admin-approved:core-change` (owner applies the label on the PR; CI verifies provenance) |

Open the PR with the gate-aware wrapper
`python scripts/scistudio_pr_create.py --title "<type>(#<issue>): <summary>" --body "<body>"`,
which runs `gate_record check --mode pre-pr` (or pre-PR `finalize`) before
invoking `gh pr create`. The PR body must close every gate-listed issue with a
GitHub closing keyword (`Closes #N` / `Fixes #N` / `Resolves #N`).

## 9. Behaviors To Know

- **Isolated per-worktree venv auto-provisioning (§7.10).** In its local
  preflight modes (`local`, `pre-commit`, `pre-push`, `pre-pr`), `check`
  **auto-provisions** a CI-equivalent environment before running checks: an
  isolated, gitignored, per-worktree venv at `<worktree>/.workflow/local/venv`
  with `-e ".[dev]"` installed at the CI-resolved tool versions. It prefers `uv`
  (`uv venv` + `uv pip install`) and falls back to `python -m venv` + `pip`. The
  package is editable-installed inside the venv, so `mypy`/`pytest` import
  `scistudio` with no `PYTHONPATH` hack, and `ruff`/`mypy`/`pytest`/`lint-imports`
  run at the same versions as CI. Provisioning is cached by a marker hash of the
  `[dev]` extras + tool pins + Python version: a warm venv is reused near-instantly
  and re-provisioned only when that marker changes. Executable resolution is
  cross-platform (`Scripts/` on Windows, `bin/` on POSIX). The first cold provision
  takes a minute or two (downloads); after that it is effectively free. Each
  worktree has its own venv, so parallel worktrees never share a writable env.
  The `python_tests` check also mirrors CI's `SCISTUDIO_DEV=1` environment so
  plugin/dev-only tests behave the same locally and in GitHub Actions.

- **CRITICAL — `--mode ci` never provisions.** `ci.yml` owns the quality matrix
  and runs in its own environment; `check --mode ci` validates governance and
  guards only and does NOT create a venv or run the quality checks. The escape
  hatch `SCISTUDIO_GATE_NO_PROVISION=1` also disables real provisioning (CI sets
  it; the self-hosting subprocess smoke uses it), falling back to the
  `PYTHONPATH=src` importable validation.

- **Parity fail-closed (exit 4).** If `check` cannot reproduce the CI tool
  versions or a CI-equivalent importable environment — venv creation or the
  install fails (no network, `uv`/`pip` error), or importability cannot be
  validated — then in `pre-pr` / `ci` modes it fails closed for PR readiness with
  exit 4 and an actionable "local env not CI-equivalent" message, rather than
  running a looser local approximation. A nonzero check caused by a missing
  module/plugin/tool (a parity gap) is reported distinctly from a genuine code
  failure. Gap messages and committed ledger events are sanitized, so no
  absolute/home/venv path leaks.

- **`--check-na` has no force for `ci.yml`-owned checks.** An N/A for a check
  the standalone `ci.yml` job owns (`lint_format`, `format_check`, `type_check`,
  `architecture_tests`, `full_audit`, `python_tests`, `import_contracts`,
  `frontend`, `wheel_release_smoke`, `semantic_dup`) does **not** waive the
  obligation for PR readiness — `ci.yml` runs the check regardless. The tool
  emits a loud non-blocking warning and ignores the N/A for that check. Fix the
  check or rely on CI. `--check-na` does waive task-specific / non-`ci.yml`-owned
  checks.

- **`--only` / `--skip-execution` are recovery-only.** They run a subset (or no)
  checks for recovery and print a "RECOVERY MODE … NOT final PR readiness"
  banner listing the mandatory tier-selected checks not run this invocation. In
  `pre-pr` / `ci` modes recovery cannot create final readiness. A final PR-ready
  `check` must run or validate the complete tier-selected check set.

- **Default base is the merge-base.** When `--base` is omitted, the diff base is
  `git merge-base origin/main HEAD`, falling back to raw `origin/main` if the
  merge-base cannot be computed. A branch's delta is its own commits; this is
  correct for normal branches and better for stacked branches. Deeply-stacked
  branches may still need an explicit `--base`.

- **`gate_receipt` is gone.** Receipt behavior is folded into the ledger as
  check and reconcile events; there is no separate `gate_receipt` command. Use
  `gate_record check --mode pre-pr` and `gate_record finalize` instead.

- **Compatibility aliases.** Older subcommand names remain only as aliases that
  delegate to the new ledger implementation and own no validation decision:
  `start` -> `init`; `pre-commit` -> `check --mode pre-commit`;
  `commit-msg <file>` -> `check --mode commit-msg`; `pre-push` ->
  `check --mode pre-push`; `pr-ready` -> `check --mode pre-pr`; `ci` ->
  `check --mode ci`. Record docs with `amend --docs-updated` / `--docs-na`;
  Sentrux applicability is handled by `check` as a guard event.

- **Admin / bypass labels.** The valid labels are `admin-approved:bypass`
  (one-off AI gate workflow bypass), `admin-approved:core-change` (protected
  core path authorization only), `admin-approved:merge` (AI merge automation),
  and the PR-level `human-authored` (human AI-harness bypass). Locally
  recorded requested labels are intent only; CI verifies the observed PR label
  and the actor's administrator/maintainer permission. None of these bypass
  branch protection, normal repository CI, or owner review.
