---
title: "Phase -0.5 — Temporary Simplified Review System (Design)"
phase: "-0.5"
status: draft
date: 2026-05-18
relates_to:
  - ADR-042
  - ADR-043
  - ADR-044
tracks: "#1113"
agent_editable: true
---

# Phase -0.5 Temporary Review System — Design

> **Purpose.** Bridge the gap between the Phase -1 freeze and the eventual
> Phase 1 full ADR-042/043/044 QA regime. The full regime cannot review its
> own implementation while it is being built (~57 toolchains, multi-week).
> This temporary system enforces a small, well-defined subset of the full
> regime so Phase 1 implementation PRs ship under *some* automated review.
>
> **Lifecycle.** Lives from the merge of P-0.5.B until the end of Phase 1,
> at which point a single decommission PR removes the entire surface in
> one clean cut (git rm scripts/audit/temp_review.py,
> tests/audit/test_temp_review.py, plus surgical reverts in
> .pre-commit-config.yaml and .github/workflows/ci.yml).
>
> **Non-goal.** This is not the ADR-042 §21.1 stack. It is intentionally
> weaker. Anything not in §2 is deferred to the full system.

---

## 1. Scope

### 1.1 What the temp system enforces (the entire list)

1. Ruff lint + Ruff format (existing config; no rule changes).
2. Mypy --strict on src/scieasy/qa/** only.
3. Pytest with --timeout=60 and --cov-fail-under=70 (existing baseline).
4. Importlinter contracts for new scieasy.qa.* layers.
5. Module docstring presence on every new file under src/scieasy/qa/**.
6. Public class docstring presence on every new public class under
   src/scieasy/qa/**.
7. Commit-level attribution: every commit on a track/adr-042/** branch
   carries an Assisted-by: or Co-Authored-By: trailer.
8. Frontmatter presence (regex, not pydantic) on any new ADR/spec file
   under docs/adr/** or docs/spec/**.
9. PR body Closes #N (already enforced by Verify Workflow Compliance;
   listed here for completeness — the temp system relies on the
   existing check, does not duplicate it).
10. No "git add -A" / "git add ." / "git add *" patterns in commit
    message bodies of agent-authored commits.

### 1.2 What the temp system explicitly does NOT enforce

Each "not enforced" item names the ADR section that defines the full
check and the Phase 1 TC that builds it.

| Deferred check | ADR § | Built by TC |
|---|---|---|
| Bidirectional MAINTAINERS ↔ governs closure | ADR-042 §11 + ADR-044 §12.3 | 1B.4 + 1C.2 |
| Fact substitution registry / fact-drift | ADR-042 §10 + §7.5 | 1B.3 + 1H.8 |
| a/b/c1/c2/c3/d drift classification | ADR-042 §9 | 1B.1 |
| Governance hard blocks (monotonic / honeypot / weakened-CI) | ADR-043 §3.3, §3.4, §3.6, §6.4 | 1E.1 – 1E.6 |
| Mutation testing / test-quality AST anti-patterns | ADR-043 §4 | 1F.1 – 1F.3 |
| Codemod application check | ADR-042 §20.3 | 1B.9 |
| Doc-length lint / skill-as-pointer / auto-generated lint | ADR-044 §11.5 | 1B.10 |
| Sphinx nitpicky + pytest-examples + doc cross-reference | ADR-042 §23 + ADR-044 §10.1 | 1D.1 – 1D.7 |
| Strict ADR/spec frontmatter pydantic validation | ADR-042 §5 + ADR-044 §5 | 1B.2 |
| Bidirectional closure for ADR/spec/MAINTAINERS | ADR-042 §11 | 1B.4 |
| Trailer strict form (Runtime:ModelID) per ADR-042 §13.2 | ADR-042 §13 | 1B.5 (full); temp accepts looser form per §2.7 |
| Committer-only mode (scripts/committer.py enforced) | ADR-042 §16 | 1B.6 + 1H.8 |
| Three-layer trailer enforcement (commit-msg / pre-push / CI) | ADR-042 §13.3 | 1B.5 |
| SARIF + ratchet wrapper | ADR-042 §21.4 + ADR-043 §6.2 | 1G.1 – 1G.4 |
| Workflow v2 (7-stage) gate validators | ADR-042 §19 | 1H.1 + 1H.2 |
| AGENTS.md hierarchy enforcement | ADR-042 §12 + ADR-043 §5 | 1H.3 + 1H.4 |
| Doc-set Sphinx build / linkcheck / language policy | ADR-042 §22 + §23 | 1D.1 + 1D.5 |

The single ruling principle for deferral: **if the full check requires
schemas that do not yet exist** (i.e., depends on 1A), or **requires
auxiliary registries that do not yet exist** (MAINTAINERS,
FactsRegistry, identity registry, .governance-paths.yaml), then the
temp system intentionally does not approximate it. Approximate checks
would risk false negatives (silent acceptance of patterns the real
check would catch) and false positives (blocking work the real check
would pass).

---

## 2. Enforced Checks — Detailed

For each, the format is: **name** — *fires where* — *piggybacks on* —
*output shape* — *how to read it*.

### 2.1 Ruff lint + format

- **Rule.** Existing [tool.ruff] config in pyproject.toml
  (target py311, line-length 120, selects E,W,F,I,N,UP,B,SIM,RUF).
- **Where.** pre-commit (existing astral-sh/ruff-pre-commit@v0.11.4) + CI
  (lint job in .github/workflows/ci.yml). No new wiring.
- **Output.** Standard ruff output (file:line:col: code: message).
- **How to read.** Failing lines in CI Lint & Format job log; locally
  ruff check . and ruff format --check ..

### 2.2 Mypy --strict on src/scieasy/qa/**

- **Rule.** Mypy --strict (no --ignore-missing-imports) applied
  *only* to the new src/scieasy/qa/ package; legacy paths continue to
  use the existing config (disallow_untyped_defs=true,
  ignore_missing_imports=true).
- **Where.** pre-commit existing mirrors-mypy hook stays as-is (legacy
  config). A new step inside temp_review.py runs
  mypy --strict src/scieasy/qa/ *if and only if* the package exists
  and at least one file matches. Wired into CI's existing typecheck
  job as an additional step (after the existing mypy invocation).
- **Output.** path:line: error: <message> [<rule-id>].
- **How to read.** CI Type Check job, mypy strict stanza; or local
  python -m scripts.audit.temp_review --ci src/scieasy/qa/.

### 2.3 Pytest with --timeout=60 --cov-fail-under=70

- **Rule.** Existing [tool.pytest.ini_options] already pins
  --cov-fail-under=70 and timeout=60. No change.
- **Where.** pre-commit does NOT run pytest (would violate the §21.3
  "≤ 5s wall time" goal). CI existing test job runs it.
- **Output.** Standard pytest report; coverage failure shows
  "FAIL Required test coverage of 70% not reached. Total coverage: X%".
- **How to read.** CI Test job log; local pytest --timeout=60.

### 2.4 Importlinter contracts for scieasy.qa.*

- **Rule.** The existing three contracts in pyproject.toml cover
  core, blocks, and engine. The temp system adds *zero* new
  contracts for scieasy.qa.* until 1A schemas land (the layer
  boundaries inside qa/ are defined by 1A modules; we cannot lint
  layers that do not yet exist). However, temp_review.py runs
  lint-imports so that any **new** code added to scieasy.qa.* is at
  least checked against the existing three contracts (cross-layer
  leak into scieasy.core / blocks / engine is forbidden by transitive
  inheritance: qa may not depend on engine, api, ai).
- **Where.** Existing CI import-lint job. No new wiring. temp_review.py
  shells out to lint-imports as a sanity invocation when
  src/scieasy/qa/ is present.
- **Output.** Importlinter contract violation report (rich text).
- **How to read.** CI Import Contracts job log.

> **Note.** Per-layer contracts inside scieasy.qa.* (e.g.
> qa.schemas → qa.audit direction) ship with TC-1A.1 onwards.
> The temp system intentionally does not pre-empt that design.

### 2.5 Module docstring on every new src/scieasy/qa/** file

- **Rule.** temp_review.py parses each .py file under
  src/scieasy/qa/ via ast.parse, then inspects ast.get_docstring(tree).
  Empty (None) → finding QA001: missing module docstring.
  Exception: __init__.py with zero non-import statements is allowed
  to skip (re-export shims).
- **Where.** pre-commit local hook + CI temp_review step.
- **Output.** src/scieasy/qa/<path>:1: error: QA001: missing module docstring.

### 2.6 Public class docstring on every new src/scieasy/qa/** public class

- **Rule.** AST walk: every ast.ClassDef whose name does NOT start
  with underscore must have ast.get_docstring(node) non-empty. Else
  QA002: missing public class docstring: <ClassName>.
- **Where.** Same as §2.5.
- **Output.** src/scieasy/qa/<path>:<lineno>: error: QA002: ....

### 2.7 Assisted-by: OR Co-Authored-By: trailer on Phase 1 tracking branches

- **Rule.** For each commit reachable from HEAD but not from
  origin/main on any branch matching track/adr-042/**, the commit
  message body must contain at least one line matching (case-insensitive):

      ^(Assisted-by|Co-Authored-By):\s+.+$

  Either trailer satisfies the temp check; ADR-042 §13.2 strict
  Runtime:ModelID form is deferred to TC-1B.5.
- **Where.** CI only (needs git log against origin/main; pre-commit
  cannot see un-pushed siblings). Step in temp_review.py --ci.
- **Output.** commit <sha12>: error: QA003: missing Assisted-by/Co-Authored-By trailer.

### 2.8 Frontmatter presence on new ADR/spec files (regex)

- **Rule.** For any new file under docs/adr/**.md or docs/spec/**.md
  in the PR diff, the file must contain a YAML frontmatter block
  delimited by two --- lines, parsed by the DOTALL regex
  ^---\s*\n.*?\n---\s*\n. Schema validation is **explicitly NOT
  performed** (deferred to TC-1A.1 + TC-1B.2).
- **Where.** pre-commit + CI (both can inspect file content).
- **Output.** docs/adr/ADR-NNN.md:1: error: QA004: missing YAML frontmatter block.

### 2.9 PR body Closes #N (delegated)

- **Rule.** Already enforced by the existing Verify Workflow
  Compliance job (regex (closes|fixes|resolves)\s+#[0-9]+). The
  temp system does NOT re-implement this. Listed in §1.1 for
  completeness.
- **Where.** Existing .github/workflows/workflow-gate.yml.
- **Output.** ::error::PR must link an issue (e.g. Closes #42).

### 2.10 No git add -A / git add . in commit messages

- **Rule.** For each commit in the PR diff, the commit message body
  must NOT contain any of the regexes:
  - \bgit\s+add\s+-A\b
  - \bgit\s+add\s+\.(\s|$)
  - \bgit\s+add\s+\*
  This catches agents pasting their shell session into commit
  messages as evidence of broad staging (anti-pattern: hides what
  was committed inside the wrong PR).
- **Where.** CI only (uses git log against base ref).
- **Output.** commit <sha12>: error: QA005: forbidden git-add-all reference in commit message.

### 2.11 Severity & rule-id table (summary)

| Rule ID | Severity | Description |
|---|---|---|
| QA001 | error | Missing module docstring under src/scieasy/qa/** |
| QA002 | error | Missing public-class docstring under src/scieasy/qa/** |
| QA003 | error | Missing Assisted-by:/Co-Authored-By: trailer on track/adr-042/** commit |
| QA004 | error | Missing YAML frontmatter on new docs/adr/** or docs/spec/** file |
| QA005 | error | git add -A / git add . / git add * reference in commit message |

(QA001–QA005 are the temp system net-new rules. Ruff / mypy / pytest /
importlinter retain their own rule IDs.)

---

## 3. Implementation Layout

### 3.1 Code

- **Single entry point.** All temp checks live in
  scripts/audit/temp_review.py. No package, no submodules. The file
  is a self-contained python -m scripts.audit.temp_review script.
  Justification: a single file with a single CLI is trivial to
  git rm at decommission. Splitting into a package would create
  cross-import surface that the decommission PR has to chase.

- **No src/scieasy/qa/ reuse.** The temp system MUST NOT live under
  src/scieasy/qa/ (where the real system will live). Keeping the
  temp logic outside the real tree means the decommission PR never
  touches the real package tree; it deletes a sibling.

- **Stdlib only.** temp_review.py uses only the Python stdlib
  (ast, pathlib, re, subprocess, argparse) plus subprocess-invoked
  mypy, ruff, lint-imports, git. No new PyPI dependency.

### 3.2 Tests

- tests/audit/test_temp_review.py — one unit test per rule (QA001
  through QA005), plus a "happy path" integration test that points
  the script at the current repo and asserts exit 0.
- Per ADR-042 §21.6 *95% coverage applies only to* src/scieasy/qa/.
  Temp scripts live under scripts/ and are exempt from the 95% bar
  but should still meet the existing 70% baseline.

### 3.3 Pre-commit wiring

One new local hook block appended to .pre-commit-config.yaml:

    - repo: local
      hooks:
        - id: temp-review
          name: Phase -0.5 temporary review (decommissioned end of Phase 1)
          entry: python -m scripts.audit.temp_review --changed-files-only
          language: system
          pass_filenames: false
          stages: [pre-commit]

The hook deliberately uses --changed-files-only to stay under the
ADR-042 §21.3 "≤ 5s typical edit" budget.

### 3.4 CI wiring

One new step appended to the existing lint job in
.github/workflows/ci.yml (cheapest job, already on PR). Co-locating
inside lint avoids creating a brand-new job that would have to be
deleted at decommission:

    - name: Phase -0.5 temporary review
      run: python -m scripts.audit.temp_review --ci

No branch-protection change. Branch protection currently does not
require temp-review; the job runs but is advisory until manager
manually flips it (this happens in P-0.5.C activation).

### 3.5 Decommission cleanliness

Boundary summary:

- All temp code: scripts/audit/temp_review.py (delete).
- All temp tests: tests/audit/test_temp_review.py (delete).
- One hook block in .pre-commit-config.yaml (revert).
- One step in .github/workflows/ci.yml (revert).
- One entry in docs/audit/decommission-log.md (append).

No other file is touched. See §6 for the exact decommission PR shape.

---

## 4. CLI Contract for scripts/audit/temp_review.py

### 4.1 Argv shape

    python -m scripts.audit.temp_review
        [--changed-files-only]      # pre-commit fast path: staged files only
        [--ci]                      # CI mode: enable commit-trailer + PR-diff checks
        [--base-ref REF]            # default: origin/main; only with --ci
        [paths...]                  # explicit paths to check (overrides default scan)

### 4.2 Exit codes

| Code | Meaning |
|---|---|
| 0 | All checks passed |
| 1 | One or more findings |
| 2 | Config / environment error (e.g. git not on PATH, malformed pyproject.toml) |

### 4.3 Output format

One finding per line, machine-parseable:

    <path>:<line>: <severity>: <rule-id>: <message>

For commit-level findings (QA003, QA005) the <path> is rendered as
commit <sha12> and <line> as 1.

Examples:

    src/scieasy/qa/audit/__init__.py:1: error: QA001: missing module docstring
    src/scieasy/qa/schemas/report.py:42: error: QA002: missing public class docstring: AuditReport
    commit a1b2c3d4e5f6:1: error: QA003: missing Assisted-by/Co-Authored-By trailer
    docs/adr/ADR-045.md:1: error: QA004: missing YAML frontmatter block
    commit 1234567890ab:1: error: QA005: forbidden git-add-all reference in commit message

Trailing summary on stderr:

    temp_review: 5 finding(s), 4 file(s) checked, 0.32s

### 4.4 Configuration

- Zero-config preferred. No new config file is introduced.
- Reads pyproject.toml only if needed (e.g., to resolve [tool.ruff]
  paths for piggyback invocations).
- No environment variables. No --config flag. The intent: the temp
  system has no knobs; tuning knobs are deferred to the real system.

---

## 5. Test Coverage Plan

tests/audit/test_temp_review.py contains:

| Test | Asserts |
|---|---|
| test_qa001_missing_module_docstring | tmpfile under src/scieasy/qa/foo.py with no docstring → exit 1 and QA001 in output |
| test_qa001_init_with_only_imports_passes | __init__.py with only imports → exit 0 |
| test_qa002_missing_public_class_docstring | class without docstring → QA002 in output |
| test_qa002_private_class_is_allowed | _Hidden class without docstring → exit 0 |
| test_qa003_missing_trailer_on_tracking_branch | mock branch track/adr-042/1a-schemas, commit without trailers → QA003 |
| test_qa003_assisted_by_satisfies | commit with only Assisted-by: → exit 0 |
| test_qa003_co_authored_by_satisfies | commit with only Co-Authored-By: → exit 0 |
| test_qa003_not_enforced_off_tracking_branch | feat/issue-NNN/... branch → exit 0 |
| test_qa004_missing_frontmatter_on_new_adr | new docs/adr/ADR-099.md with no frontmatter → QA004 |
| test_qa004_existing_adr_unchanged_is_skipped | unchanged ADR file → exit 0 |
| test_qa005_git_add_dash_a_blocked | commit message containing git add -A → QA005 |
| test_qa005_git_add_dot_blocked | commit message containing git add . → QA005 |
| test_cli_exit_code_2_on_missing_git | bogus --base-ref to a non-repo → exit 2 |
| test_repo_sanity_passes | run the script against the current repo → exit 0 |

Coverage target: 70% on scripts/audit/temp_review.py (default repo
threshold; the 95% bar applies only to src/scieasy/qa/**).

Fixtures use pytest tmp_path + subprocess.run([sys.executable, "-m",
"scripts.audit.temp_review", ...]) to exercise the real CLI surface.

---

## 6. Decommissioning Plan (MANDATORY)

### 6.1 Files the decommission PR deletes

| Path | Action |
|---|---|
| scripts/audit/temp_review.py | git rm |
| tests/audit/test_temp_review.py | git rm |

### 6.2 Files the decommission PR modifies (surgical revert)

| Path | Change |
|---|---|
| .pre-commit-config.yaml | Remove the temp-review local hook block (introduced in P-0.5.B) |
| .github/workflows/ci.yml | Remove the "Phase -0.5 temporary review" step inside lint job |
| docs/audit/decommission-log.md | Append one entry naming the SHA and replacement stack |

No other path is touched. The PR is small (~30 line revert) and
purely subtractive.

### 6.3 Migration: where temp logic lands in the full system

Each QA00x rule maps to a Phase 1 TC that builds the strict equivalent:

| Temp rule | Migrates into | Phase 1 TC |
|---|---|---|
| QA001 module docstring | Ruff D100 rule under §21.1 ruff config | 1A (config) + 1B.10 (doc_length_lint covers harder cases) |
| QA002 public class docstring | Ruff D101 rule under §21.1 ruff config | 1A (config) |
| QA003 trailer presence | scieasy.qa.audit.trailer_lint strict-form Runtime:ModelID check | TC-1B.5 |
| QA004 frontmatter presence | scieasy.qa.audit.frontmatter_lint (multi-schema pydantic dispatch) | TC-1B.2 (uses 1A.1 schemas) |
| QA005 git-add-all ban | scieasy.qa.audit.committer_enforce (forces all agent commits through scripts/committer.py) | TC-1B.6 + TC-1H.8 |

The piggyback checks (ruff / mypy / pytest / importlinter) do not
migrate — they are already in place. The only change is rule-selection
expansion (ruff adds D,S,ANN,PTH,RET,PT,DOC), mypy widening to
--strict repo-wide, and the pytest coverage ratchet to 80% then 90%.

### 6.4 Decommission trigger

The decommission PR opens **only when all of the following hold**:

1. All ~57 Phase 1 toolchains (1A–1H) have merged into their tracking
   branches AND those tracking branches have merged into main.
2. docs/audit/ci-implementability.json exists and shows green (per
   ADR-042 §26.2 implementability verification).
3. A first docs/audit/reports/<phase-1-end-sha>/full.json exists and
   contains 0 critical findings.
4. Phase 1.5 brief exists at docs/audit/phase-1-5-brief.md.

The manager opens the decommission PR; it is logged in
docs/audit/freeze-exceptions.log as a Phase 1 cleanup-track exit event.

---

## 7. Risks & Open Questions

### 7.1 Risks

- **False negatives (too lax).** QA003 accepts either Assisted-by:
  OR Co-Authored-By:. ADR-042 §13.2 only accepts the strict
  Runtime:ModelID form on Assisted-by:. Mitigation: the trailing
  migration step (TC-1B.5) will catch and surface every commit that
  the temp regime let through with a lax format — re-formatting
  trailers post-hoc is cheap.
- **False positives (blocking legitimate work).** QA005 regex matches
  git add -A *inside* commit messages, including documentation
  snippets that legitimately reference the command (e.g., a CHANGELOG
  entry about *not* using it). Mitigation: scan is restricted to
  commit-message body of the *current commits in the PR diff*, not
  the working tree; documentation files containing the literal
  string are unaffected.
- **Drift between temp and full regimes.** The temp QA001/QA002
  rules are AST-based; ruff D100/D101 will replace them with slightly
  different semantics (e.g., ruff is more permissive about __init__
  patterns). Migration may surface findings the temp regime did not.
  Mitigation: explicit in §6.3 mapping; manager runs a one-shot
  ruff D audit on src/scieasy/qa/** immediately after 1A merges so
  the gap is known.
- **Hook ordering with existing mypy.** The existing mirrors-mypy
  pre-commit hook runs first on edited files; the temp system strict
  mypy invocation runs against src/scieasy/qa/ only. There is no
  conflict, but a contributor may see two mypy stanzas in pre-commit
  output. This is acceptable during the temp window.
- **Verify Workflow Compliance already requires source changes to
  ship with tests/** — the temp system tests under tests/audit/
  satisfy this for the P-0.5.B PR.

### 7.2 Open questions for the project owner

1. **QA003 enforcement scope.** Should QA003 also apply to
   non-track branches (e.g., feat/*, fix/*) during the temp window,
   or stay narrowly scoped to track/adr-042/**? Recommended: stay
   narrow (the temp regime explicitly targets Phase 1
   tracking-branch PRs; broadening risks blocking unrelated
   cleanup-track PRs that do not need agent attribution yet).
2. **temp-review branch-protection requirement.** Should the
   temp-review job be a required check on tracking-branch merges,
   or advisory? Recommended: required on track/adr-042/** PRs only;
   advisory on main PRs (cleanup-track work continues under
   pre-existing rules).
3. **Coverage exemption for scripts/audit/.** The 70% baseline
   applies repo-wide. Confirm scripts/audit/temp_review.py may run
   at any coverage level — or do we hold it to 70%? Recommended:
   hold it to 70% (cheap to write tests for a single-file CLI;
   raises confidence in the gate itself).
4. **Migration logging.** Should the decommission PR move the
   temp_review.py source into docs/audit/decommission-log.md
   verbatim as a historical artifact, or just link to the git
   history? Recommended: link only — the git history is the artifact.

---

## Appendix: Cross-references

- Master plan: ~/.claude/plans/polished-zooming-shell.md §Phase -0.5.
- ADR-042 §13 (trailer formats), §21.1 (full tool stack), §21.6
  (coverage targets), §27.4 (self-exemption window).
- ADR-043 §3 (governance hard blocks, deferred), §5.3 (hook
  hierarchy, future).
- ADR-044 §5 (frontmatter schemas, deferred), §11.5 (auto-generated
  lint, deferred).
- Current .pre-commit-config.yaml (33 lines, unchanged before P-0.5.B).
- Current pyproject.toml [tool.*] (covers ruff / mypy / pytest /
  importlinter / coverage / commitizen — all reused).
- Existing CI workflows: .github/workflows/ci.yml, workflow-gate.yml,
  ai-review.yml.
- Existing local hooks under scripts/hooks/ (5 hooks, untouched by
  P-0.5).
