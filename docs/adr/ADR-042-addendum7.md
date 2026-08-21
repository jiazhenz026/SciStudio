---
adr: 42
addendum: 7
title: "Local Gate Checks Prove The Diff; CI Proves The Surface"
status: Proposed
date_created: 2026-08-21
date_accepted: null
date_superseded: null

supersedes: []
superseded_by: null
related: [42]
closes_issues: []
tracking_issue: 2102

is_code_implementation: true
governs:
  modules:
    - scistudio.qa.governance
    - scistudio.qa.governance.gate_record
  contracts: []
  entry_points: []
  files:
    - docs/adr/ADR-042-addendum7.md
    - docs/specs/gate-local-incremental-checks.md
    - docs/ai-developer/rules.md
    - docs/ai-developer/specific_rules/gated-workflow.md
    - docs/ai-developer/specific_rules/guided-work.md
    - docs/ai-developer/gate-cli-command-set.md
    - src/scistudio/qa/governance/**
    - tests/qa/**
  excludes: []

tests:
  - tests/qa/test_gate_incremental_checks.py
agent_editable: false
assisted_by:
  - "claude-code:claude-opus-5"

phase: planning
tags: [qa, ci, ai-governance, workflow-gate, gate-record, incremental-checks]
owner: "@jiazhenz026"
co_authors: ["@claude"]
language_source: en
translations: []
---

# ADR-042 Addendum 7: Local Gate Checks Prove The Diff; CI Proves The Surface

## 1. Decision Summary

Addendum 6 gave the gate incremental *evidence*: a check event is valid only for
the covered surface and input fingerprint it recorded, so an unrelated later edit
no longer discards earlier valid checks. That mechanism works. Measured over the
130 committed ledgers and their 2,316 recorded check executions, 1,029 re-runs
happened because the fingerprint genuinely changed and only 278 re-ran on an
unchanged one.

What Addendum 6 did not make incremental is the *command*. Every entry in the
check catalog is a whole-repository invocation: `ruff check .`, `mypy
src/scistudio/`, the entire pytest suite. The fingerprint decides whether a check
runs; once it runs, it runs over everything. An agent actively editing a file
changes the covered surface on nearly every iteration, so the reuse branch almost
never fires and each iteration pays the full-repository cost again.

The consequence is measurable. Across the same ledgers, `python_tests` executed
308 times and failed 222 of them, `format_check` executed 304 times and failed 98
times on deviations a single formatter run would have fixed, and
`architecture_tests` and `semantic_dup` dominated wall clock while catching 9 and
16 failures respectively.

This addendum makes the command incremental as well. Each check keeps its
whole-repository CI-mirror command and gains a local variant narrowed to the
observed diff. Local modes run the narrow variant; `ci` mode and an explicit
`--force-checks` run the mirror.

The reasoning this rests on is not new to the repository, and that is the point.
Addendum 6 §7.5 already established that the `workflow-gate` job does not own the
`ci.yml` quality matrix: the evaluator drops all eleven quality checks from
required obligations in `ci` mode because the separate `ci.yml` jobs are
authoritative for them on the same PR. That was recorded as a role split, not a
weakening. This addendum applies the identical argument to the local side. The
local gate does not need to re-prove what `ci.yml` proves before merge; it needs
to tell the agent quickly whether the code it just wrote is broken.

The distinction that keeps this safe is which question a check answers. Checks
that answer *did you break what you just wrote* — lint, types, the tests covering
the changed modules — stay local, because their failure rate scales directly with
iteration count and deferring them to CI would produce exactly the fix-and-push
loop this addendum exists to reduce. Checks that answer *does the repository
still hold an invariant* — architecture constraints, semantic duplication, the
deferral ratchet, wheel packaging — are either violated from the first commit or
not at all; their failure rate does not scale with iteration count, so proving
them once in CI costs no extra round trips.

One asymmetry is deliberate and load-bearing: narrowing must never under-select.
Whenever the selection cannot prove which tests or files an edit affects — a
changed pytest or coverage configuration, a shared `conftest.py`, a fixture file,
a module with no mirrored test location — the local run widens to the full
surface rather than reporting a narrow pass. A slow correct answer is acceptable;
a fast wrong one is not.

### 1.1 Problems Addressed

| Problem | Risk | ADR response | Detailed section |
|---|---|---|---|
| Check evidence is incremental but check commands are whole-repository | Every iteration pays full-repository cost because the fingerprint almost always changes, so the reuse branch built in Addendum 6 rarely fires | Give each check a diff-scoped local variant alongside the retained CI-mirror command | Section 2.1 |
| The Python test suite cannot run as a subset at all | A repository-wide coverage floor makes any subset run fail by construction, so no test selection is possible however good | Disable the floor for the local variant only; CI keeps the floor and the full suite | Section 2.2 |
| Five checks share one `python` covered surface | A formatting-only edit invalidates type and test evidence it cannot possibly affect | Split the Python surface so each check is invalidated only by inputs it reads | Section 2.3 |
| `full_audit` and `deferral_discipline` treat every changed file as an input | A frontend-only or docs-only edit invalidates evidence for checks that never read those trees | Narrow each to the file classes it actually reads | Section 2.3 |
| `format_check` fails on deviations a formatter would fix | 98 recorded gate failures, each costing a cycle, none indicating a defect | Rewrite the changed files locally; CI keeps the failing form | Section 2.4 |
| Addendum 6 states local `check` proves a full CI mirror | The governance documents would describe behavior the runtime no longer has | Supersede those statements and state the local/CI role split explicitly | Section 3 |

## 2. Decision Details

### 2.1 Two Commands Per Check

A check specification carries two commands. The CI-mirror command is the
whole-repository invocation that `ci.yml` runs; it is unchanged and remains the
definition of the check. The diff-scoped command is built from the observed
changed files at invocation time.

Only some checks have a meaningful narrow form. Linting, formatting, and type
checking take a file list. The test suite takes a selected node set. The full
audit, the semantic-duplication ratchet, the architecture suite, and the wheel
smoke build have no natural file-list form and keep their repository-scoped
command; their cost is governed by mode selection instead.

Local, pre-commit, and pre-PR modes request the narrow variant. The `ci` mode and
an explicit `--force-checks` request the mirror. When a narrow variant is
requested but cannot be built safely, the mirror runs instead and the recorded
event says so: an event always names the command that actually ran, never the one
that was requested.

Every recorded check event carries the scope it ran at. Diff-scoped evidence is a
valid local signal but is never accepted in place of a CI-mirror obligation, so
the `ci`-mode contract established in Addendum 6 is unchanged. Events recorded
before this field existed read as repository-scoped, which is what they were.

### 2.2 The Coverage Floor Moves To CI Only

The repository configures a coverage floor in `pyproject.toml` that applies to
every pytest invocation. Any subset run necessarily reports lower coverage than
the whole suite, so the floor makes subset runs fail regardless of whether the
selected tests pass. Test selection is therefore impossible while the floor
applies locally.

The local test variant disables coverage per invocation. The configured floor is
unchanged and `ci.yml` continues to enforce it across both interpreter versions
on the same PR. Coverage is a repository-level invariant of exactly the kind
Section 1 assigns to CI: a coverage regression is not caused by the current
iteration in a way that iterating locally would reveal sooner.

Test selection maps a changed module to the longest mirrored test directory that
exists, or to a mirrored test file, and includes changed test files directly. A
changed `conftest.py` selects its whole directory. Every unresolved case widens to
the full suite.

### 2.3 Surfaces Match What Each Check Reads

The single `python` covered surface is split so that lint, type, import-contract,
test, semantic-duplication, and deferral evidence are invalidated only by inputs
the corresponding check reads. Type checking and import contracts read the source
tree and their configuration, so a change confined to tests no longer invalidates
them. The full audit reads documentation, source, and its own configuration, so a
change confined to the frontend or desktop trees no longer invalidates it. The
deferral ratchet reads Python files and its baseline and nothing else.

This is the same principle Addendum 6 §7.5 already states — evidence is valid for
the surface it covered — applied at the granularity the checks actually have,
rather than at the granularity of the language they are written in.

### 2.4 Formatting Is Fixed, Not Reported

The local formatting variant rewrites the changed files. The CI job keeps the
checking form, so a PR still cannot merge with unformatted code. This removes a
class of gate failure that never indicated a defect.

## 3. Superseded Addendum 6 Statements

The following statements in Addendum 6 are superseded by this addendum. They
described local `check` as proving a full mirror of the merge-blocking CI command
surface. Local `check` now selects that full set and proves it against the
observed diff; `ci.yml` proves it against the full surface.

| Addendum 6 location | Superseded statement | Replacement |
|---|---|---|
| §7.5 | Tier 1 runs a full local mirror of the repository's merge-blocking CI command surface | Tier 1 selects the full merge-blocking set; local modes run it diff-scoped, `ci.yml` runs it whole |
| §7.6 tier table | `check` must run a full local mirror of merge-blocking CI command surfaces | `check` must select the full merge-blocking set; scope is a mode concern |
| §7.7 per-persona table | `check` must run the full merge-blocking CI mirror | Same replacement as §7.6 |
| §7.10 summary | Local checks run the same resolved tool versions as CI in a CI-equivalent environment | Unchanged as to versions and environment; the implication that the local command is byte-identical to the CI command no longer holds |

Everything else in Addendum 6 stands. In particular the ledger schema, the single
shared evaluator, observed-diff-over-declaration reconciliation, guard ownership,
issue linkage, docs and test obligations, sanitization, protected-path
authorization, label provenance, and the authority of CI are unchanged.

## 4. Verification And Tooling Impact

Tests assert the properties that make the change safe rather than the speedup
itself: that unresolvable selection widens instead of narrowing, that diff-scoped
evidence cannot satisfy a CI-mirror obligation, that events recorded before the
scope field read as repository-scoped, that a test-only edit no longer
invalidates type evidence, that the configured coverage floor is unchanged, and
that `ci.yml` still runs both test phases over the whole suite.

The implementation PR records measured before-and-after wall clock for a
single-file diff and a broad diff. The ledger-derived figures quoted in Section 1
are proxies computed from adjacent event timestamps and include agent think time;
they establish relative magnitude and are not offered as runtimes.

No CI workflow changes. `ci.yml` already runs the full matrix on every PR, which
is what makes the local narrowing safe.

## 5. Consequences

Local gate invocations get materially faster in the common case of an agent
iterating on a small number of files, and a formatting deviation stops costing a
cycle. Agents see explicitly which checks proved only their diff.

A repository-wide invariant broken by a narrow edit now surfaces in CI rather
than locally. This is the accepted cost, bounded by the widening rule and by
keeping every iteration-sensitive check local.

The gate's own change is validated by the gate at Tier 1, since it touches
`src/scistudio/qa/**`.

## 6. Alternatives Considered

**Leave the local gate as a full mirror.** Preserves the strongest local
guarantee and needs no change. Rejected because the measured cost is paid on
every iteration while the checks responsible for most of it catch failures that
do not scale with iteration count.

**Drop the slow checks from the local gate entirely.** Simpler than narrowing and
saves more. Rejected for the checks that answer whether the current edit is
broken: deferring those to CI produces the fix-and-push loop this addendum exists
to reduce. Narrowing keeps the signal and removes the cost.

**Adopt an import-graph test-selection dependency.** More precise than mirrored
paths and would select fewer tests. Rejected for now because it puts a stateful
database in the gate's execution path, where a stale or broken database would
under-select — the one failure mode the widening rule exists to prevent. The
mirrored-path mapping is coarser and fails toward running more.

**Relax the coverage floor instead of disabling it per invocation.** Would let
subset runs pass locally. Rejected because it weakens a merge-blocking threshold
to buy local speed; disabling coverage for one local invocation leaves the
threshold untouched where it is enforced.
