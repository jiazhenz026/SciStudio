---
title: "Alpha Release Test, CI, and Governance Audit"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Alpha Release Test, CI, and Governance Audit

Agent: A4-test-ci-governance
Persona: test_engineer
Audit mode: with-context
Issue: #1733
Umbrella PR: #1734 `[DO NOT MERGE]`
Branch: `track/alpha-release-audit-20260621`
Worktree: `/Users/jiazhenz/SciStudio-alpha-audit-20260621`
Baseline: `origin/main` at `1948ab2c18fafeb54c82c77646a2f00665e16332`
Observed head: `410e12530a1d3420e912fa666c3f756550537ce0`
Observed at: `2026-06-21T07:49:49Z`

## Recommendation

`pass-with-must-fix`.

The test and governance tooling has enough structure to support a small internal
alpha after must-fix release evidence items are cleared or explicitly
risk-accepted. I found no P0. The current evidence is not yet sufficient to call
the release branch alpha-ready because the committed manager ledger is stale for
current `HEAD`, Sentrux baseline evidence is missing, CI still depends on
editable installs, and GitHub reports 18 open Dependabot alerts on the default
branch.

## Findings

### P0

None observed in the A4 scope.

### P1

1. **Current gate evidence is not final for `410e1253`.**

   Evidence:
   - PR #1734 is open, draft, mergeable, and points at
     `410e12530a1d3420e912fa666c3f756550537ce0`.
   - GitHub runs for `410e1253` eventually settled green during this audit:
     `Deferral Discipline Scan` run `27897622911`, `Workflow Gate Check` run
     `27897622912`, and `CI` run `27897622893` all completed with conclusion
     `success`.
   - `.workflow/records/1733-alpha-release-audit.json` records
     `observed_diff.head_sha` as `0a25758c`, while current branch `HEAD` is
     `410e1253`.
   - `git diff --name-only 0a25758c..HEAD` shows later changes to:
     `.workflow/records/1733-alpha-release-audit.json`,
     `docs/planning/alpha-release-audit-20260621-checklist.md`, and
     `docs/planning/alpha-release-audit-20260621-dispatch-prompts.md`.
   - Read-only pre-PR probe failed for current `HEAD`:

     ```text
     PYTHONPATH=src python -m scistudio.qa.governance.gate_record check --record .workflow/records/1733-alpha-release-audit.json --mode pre-pr --base origin/main --head HEAD --pr-body-file .workflow/local/pr-body.md --skip-execution --no-record
     exit 1
     Unsatisfied obligations:
     - checks.full_audit
       Required check evidence is missing or stale for the current diff.
     ```

   Required action:
   After all audit reports land, rerun the mutating manager-owned gate command
   for the final candidate and finalize the ledger at the final audited SHA. I
   did not run the mutating `gate_record check` because this A4 write set is
   limited to this report.

2. **CI still relies on editable installs, which conflicts with the alpha entry bar and agent rule against `pip install -e .`.**

   Evidence:
   - `.github/workflows/ci.yml` uses `uv pip install --system -e ".[dev]"` in
     Type Check, Architecture Tests, Full Audit, Python Tests, and Import
     Contracts (`ci.yml` lines 53, 74, 90, 121, 159).
   - `.github/workflows/workflow-gate.yml` also installs gate dependencies with
     `uv pip install --system -e ".[dev]"` (line 25).
   - Local command evidence shows why this matters for audit reproducibility:

     ```text
     python -c 'import scistudio, pathlib; print(pathlib.Path(scistudio.__file__).resolve())'
     /opt/anaconda3/lib/python3.12/site-packages/scistudio/__init__.py

     PYTHONPATH=src python -c 'import scistudio, pathlib; print(pathlib.Path(scistudio.__file__).resolve())'
     /Users/jiazhenz/SciStudio-alpha-audit-20260621/src/scistudio/__init__.py
     ```

   Required action:
   For alpha readiness, either switch the CI-equivalent path to a non-editable
   install or documented `PYTHONPATH=src`/wheel-based workflow, or record owner
   risk acceptance that current CI uses editable installs despite the alpha
   criteria.

3. **Sentrux posture is not release-ready evidence yet.**

   Evidence:
   - The manager checklist still has `Sentrux baseline recorded, or N/A reason recorded` unchecked.
   - `sentrux --help` failed locally with exit 127: `zsh:1: command not found: sentrux`.
   - `.sentrux/rules.toml` keeps `max_cycles = 5` and `no_god_files = false`
     (lines 22 and 27). The comments identify remaining cycle debt tied to
     #1336 and call it P0 in that historical context (lines 7-11).
   - The current manager diff is docs/planning/ledger only; the gate ledger
     classified `sentrux` surface count as `0`, so `sentrux_gate` pass here does
     not prove core-runtime Sentrux health.

   Required action:
   Before alpha, run Sentrux from an environment where it is available, commit or
   record the baseline in the manager evidence, or explicitly record a release
   N/A/risk-acceptance rationale.

4. **GitHub reports 18 open Dependabot alerts on the default branch; npm coverage is not configured in Dependabot.**

   Evidence:
   - User-provided push warning: default branch has 18 Dependabot
     vulnerabilities.
   - Verified with GitHub API:

     ```text
     gh api '/repos/zjzcpj/SciStudio/dependabot/alerts?state=open&per_page=100' --jq 'length'
     18
     ```

   - Alert summary from the same API call:
     - 1 high: `vite` in `frontend/package-lock.json`
     - 15 medium: `vite`/`dompurify` in `frontend/package-lock.json`
     - 2 low: `dompurify` in `frontend/package-lock.json`
   - `.github/dependabot.yml` only configures `pip` and `github-actions`
     ecosystems; it does not configure `npm` for `frontend/package-lock.json`
     (lines 2-17).

   Required action:
   Hand off to A6-security-ops and the manager. Resolve the high alert and
   either resolve or explicitly risk-accept the remaining alerts before alpha.
   Add npm Dependabot coverage or another tracked dependency-update mechanism.

### P2

1. **Coverage gate remains intentionally lowered.**

   Evidence:
   `pyproject.toml` lines 215-219 keep a tracked `TODO(#1540)` to restore the
   coverage gate to at least 80%; current pytest addopts enforce
   `--cov-fail-under=70`.

   Alpha impact:
   This is tracked and does not block a small internal alpha by itself, but it is
   a good-to-fix item before broader testing.

2. **Full audit passes but leaves advisory/planned findings outside the alpha core.**

   Evidence:
   Fresh local full audit passed with no blocking findings:

   ```text
   PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json
   exit 0
   status: pass
   implemented children: generate_facts, frontmatter_lint, fact_drift,
   doc_drift, developer_docs, closure, signature_drift, architecture_drift,
   vulture
   deferred child: semantic_dup
   ```

   The report included info-level planned package-validator findings and
   warning-level vulture findings. These do not block core runtime alpha but
   should remain visible in the final report.

### P3

1. **Gate wrapper/discovery ergonomics caused audit friction.**

   Evidence:
   - The manager checklist records that wrapper dry-run was blocked because the
     wrapper uses `--skip-execution` and the gate reported skip-execution as
     non-final readiness.
   - `scripts/scistudio_pr_create.py` intentionally calls `gate_record check
     --mode pre-pr --skip-execution` (lines 99-119).
   - Automatic read-only discovery failed in this worktree:

     ```text
     PYTHONPATH=src python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/main --head HEAD --pr-body-file .workflow/local/pr-body.md --skip-execution --no-record
     exit 2
     no gate ledger found; run init first
     ```

   Alpha impact:
   This is an ergonomics and workflow reliability issue, not a direct core
   runtime blocker once manager reruns the explicit record check.

## Command Results

| Command | Result |
|---|---|
| `git rev-parse HEAD` | `410e12530a1d3420e912fa666c3f756550537ce0` |
| `git rev-parse origin/main` | `1948ab2c18fafeb54c82c77646a2f00665e16332` |
| `git diff --name-only origin/main...HEAD` | Four files before this report: manager gate record, alpha criteria, checklist, dispatch prompts |
| `PYTHONPATH=src python -m pytest tests/qa tests/scripts/test_scistudio_pr_create.py --no-cov` | Pass: `404 passed in 63.56s` |
| `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json` | Pass: status `pass`, no blocking findings; repeated after report creation with same result |
| `PYTHONPATH=src python scripts/deferral_scan.py --diff origin/main` | Pass: `+0 tracked TODO(#NNN), +0 untracked deferral(s)`; repeated after report creation with same result |
| `PYTHONPATH=src python scripts/deferral_scan.py --check docs/audit/baselines/deferral-baseline.json` | Pass: untracked deferrals within baseline ratchet |
| `sentrux --help` | Blocked locally: exit 127, command not found |
| `gh api '/repos/zjzcpj/SciStudio/dependabot/alerts?state=open&per_page=100' --jq 'length'` | `18` open alerts |
| Explicit read-only pre-PR probe with `--skip-execution --no-record` | Fail: stale/missing `checks.full_audit` for current diff |

No `pip install -e .` command was run during this audit.

## CI Observation

GitHub PR #1734 at `410e1253` is a draft `[DO NOT MERGE]` umbrella PR. At the
final poll during this audit:

- `Workflow Gate Check` succeeded.
- `Deferral Discipline Scan` succeeded.
- `CI` succeeded.

CI success at the current SHA is positive release evidence. The manager still
needs to refresh/finalize the gate ledger after all audit reports land.
