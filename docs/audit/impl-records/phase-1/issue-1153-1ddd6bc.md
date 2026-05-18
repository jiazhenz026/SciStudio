# Implementation record: #1153

Phase 1B sub-PR 2 of the ADR-042/043/044 cascade — trailer + committer
+ orchestrators + amendment_lint (TCs 1B.5, 1B.6, 1B.7, 1B.8). Branches
off `track/adr-042/1b-audit-tools` which already carries 1A schemas
(merged via #1128/#1131/#1133) and 1B sub-PR 1 audit core (#1151).

Implementation SHA: 1ddd6bc.

## Files modified

- `src/scieasy/qa/audit/trailer_lint.py` — NEW. `run()` + helpers
  per ADR-042 §13 / §9.6. `TRAILER_PATTERNS` maps every recognised
  trailer key (`Signed-off-by`, `Assisted-by`, `Fixes`, `ADR`,
  `Reviewed-by`, `Co-authored-by`, `Reviewed-locally`,
  `Maintainer-Override`, `Human-Override`, plus ADR-043 §3.4.2's
  `Loosening-Approved` / `Loosening-Reason` and ADR-043 §3.3's
  `Governance-Modification-Approved-By`) to a compiled regex.
  `extract_trailers()` parses the trailer block by walking from EOF
  back to the first blank line — aborts when any line in that block
  fails `Key: Value` shape. `parse_commits()` uses `git log` with a
  `\x1f` sentinel field separator so commit subjects and bodies pass
  through without quoting hazards. `validate_commit()` runs five
  checks per commit: regex match, missing-`Assisted-by` on agent
  commits (heuristic: author-email token or `Assisted-by:` already in
  body), missing-`Fixes` warning on `fix(...)` subjects, glob-based
  `ADR:` requirement (Q1B.5.2 default: closure-derived glob-to-ADRs
  map via `_load_accepted_adr_refs` / `_build_glob_to_adrs`), and
  `ADR:` reference resolves to a real Accepted ADR. Phase-3 cutoff
  defers to caller per Q1B.5.1 ("no cutoff" pre-TC-1H.8). Layer-3
  GitHub review API check is TODO-tagged with `#1153-ext` follow-up.
- `src/scieasy/qa/audit/committer_enforce.py` — NEW. `check()` per
  ADR-042 §16. `LOG_PATH_REL = "docs/audit/commit-log.jsonl"`.
  Degrades gracefully when the log file does not exist
  (`committer-enforce.no-log-file` INFO finding) or is empty
  (`committer-enforce.empty-log` INFO) — per Q1B.6.1 default,
  because `scripts/committer.py` (TC-1H.8) has not yet shipped.
  `load_commit_log()` validates each line via `CommitLogEntry.model_validate`
  and raises `ValueError` carrying the line number on malformed input
  (caught upstream and emitted as `committer-enforce.malformed-log`
  ERROR). `_enumerate_agent_commits()` walks every commit reachable
  from HEAD with the same agent-detection heuristic as `trailer_lint`
  (email-token OR `Assisted-by:` in body).
- `src/scieasy/qa/audit/full_audit.py` — NEW. `run()` per ADR-042
  §9.6 orchestrator. Always runs the pre-push subset (trailer_lint,
  committer_enforce, frontmatter_lint over all ADR + spec targets,
  closure) per Q1B.7.1. When `pre_push=False` adds `doc_drift` +
  `fact_drift`. When `self_check=True` adds `contradiction_audit` and
  defaults `targets` to `[docs/adr/ADR-042.md]` per §28.2. Each tool
  is wrapped in a uniform `_run_*` helper that produces a `ToolRun`
  with synthesised `started_at` / `completed_at` / `config_hash` /
  `exit_status` (`_exit_status` maps findings to `ok`/`warnings`/
  `errors`). `_closure_ok` reads the closure ToolRun and sets the
  envelope's `bidirectional_closure_ok` accordingly.
- `src/scieasy/qa/audit/contradiction_audit.py` — NEW. `run()` per
  ADR-042 §28.1. Each scan target gets: `_check_supersede_self`
  (defence-in-depth against frontmatter validator),
  `_check_governs_excludes` (excludes anchor under any include?),
  `_check_agent_editable_pairing` (`agent_editable=false` MUST NOT
  have a non-empty allowlist), `_check_undefined_section_refs`
  (bare `§X.Y` refs against actual Markdown headings; `ADR-NNN §X`
  cross-refs are exempt), `_check_internal_clause_heuristic`
  (warning per Q1B.7.3 when both required/must and exempt/may-skip
  surface within 600 chars of a topic key). Cross-ADR
  `_check_cross_adr_supersedes_cycles` does a DFS for back-edges;
  `_check_workflow_stage_cycles` parses Markdown stage-tables
  (`| Stage |…`) for `depends on \`X\``-style entries and DFS-checks.
- `src/scieasy/qa/audit/complete_artifacts.py` — NEW. `check()` per
  ADR-042 §19.2 stage 6. Composes: doc_drift's `missing-docstring`,
  `orphan-class`, closure's `asymmetric` findings; the CHANGELOG
  cross-check (requires `pr_number` argument; an issue-number
  reference is accepted as a proxy); plus four placeholder findings
  for translation / codemod / RBP / cross-runtime skills, each
  TODO-tagged with `#1153-ext` and a follow-up reference. When
  `pr_number` is supplied, the result is filtered to the PR's diff
  files (`git diff --name-only origin/main...HEAD`); placeholder
  files and directories pass through unconditionally.
- `src/scieasy/qa/audit/__init__.py` — UPDATED. `__all__` now
  re-exports the new modules.
- `src/scieasy/qa/schemas/report.py` — UPDATED. Adds
  `CommitLogEntry` per Q1B.6.1 (co-located with the audit envelope
  so `committer-enforce` has a single import path). Pydantic model
  enforces `extra="forbid"`, validates `sha` against
  `^[0-9a-f]+$`, requires every §16.5 field.
- `scripts/audit/amendment_lint.py` — NEW flat script (Q1B.8.1).
  `lint()` returns dict findings to keep the script runnable
  standalone. Three-level target resolution per §27.5: whole-ADR
  (`ADR-NNN`), section (`ADR-NNN §X[.Y]` + optional descriptive
  suffix), section + sub-component (`ADR-NNN §X[.Y] (component: …)`).
  Required for any ADR detected as an addendum (heuristic: title
  contains "Addendum" or filename matches `ADR-NNN-X.md`).
  Conflicting `replace` declarations on the same `(adr, section)`
  key are an error. Circular cross-ADR chains warn per Q1B.8.3.
  `main()` returns 1 on any error-severity finding.
- `scripts/audit/consolidate_cascade.py` — NEW flat script. AUTO
  generates `docs/adr/_consolidated/cascade-current.md`. Walks every
  addendum's `amends:` and applies kind-specific section rewrites:
  `replace` → inline-summary substitution, `extend` → "See also"
  note, `constrain` → "Additional restriction" subsection, `clarify`
  → footnote. Output carries a `<!-- AUTO-GENERATED -->` banner so
  hand-edits stand out (§27.5 generation: AUTO; hand-edits rejected
  is enforced by CI separately).
- `tests/qa/test_audit_trailer_lint.py` — NEW. 21 tests covering
  trailer extraction, every regex's accept/reject corpus, missing
  Assisted-by / Fixes / ADR enforcement, ADR-not-Accepted detection,
  end-to-end git-repo smoke, and bogus commit-range graceful failure.
- `tests/qa/test_audit_committer_enforce.py` — NEW. 8 tests.
- `tests/qa/test_audit_contradiction_audit.py` — NEW. 6 tests.
- `tests/qa/test_audit_complete_artifacts.py` — NEW. 7 tests.
- `tests/qa/test_audit_full_audit.py` — NEW. 4 tests.
- `tests/qa/test_amendment_lint.py` — NEW. 8 tests (loads the flat
  script via `importlib.util.spec_from_file_location`).
- `tests/qa/test_consolidate_cascade.py` — NEW. 6 tests.

Coverage on the five new audit modules (committer_enforce 93%,
trailer_lint 90%, full_audit 94%, contradiction_audit 83%,
complete_artifacts 75%) averages 87%. ≥75% per module; project floor
is 70%. mypy clean (`mypy src/scieasy/qa/audit/
src/scieasy/qa/schemas/report.py --ignore-missing-imports`). ruff
clean (check + format).

## Applied manager defaults (from SUMMARY)

- Q1B.5.1: Phase-3 cutoff defers to caller; "no cutoff" pre-TC-1H.8.
- Q1B.5.2: `ADR:` applicability glob-based via closure 1B.4 outputs.
- Q1B.6.1: `CommitLogEntry` co-located in `scieasy.qa.schemas.report`
  (flagged as ADR-042 errata candidate; current §16.5 spec describes
  the JSONL shape but does not name a canonical pydantic schema
  module — co-locating with the audit envelope is the lowest-cost
  choice).
- Q1B.7.1: pre_push subset = trailer_lint + committer_enforce +
  frontmatter_lint + closure.
- Q1B.7.2: `docs/audit/adr-self-audit/` canonical path (used by the
  contradiction_audit CLI; not yet wired to the script — the audit
  module returns the report directly).
- Q1B.7.3: §28.1 internal-clause heuristic = warning severity.
- Q1B.8.1: `scripts/audit/amendment_lint.py` canonical script path.
- Q1B.8.3: cross-ADR amendment chains allowed; warn on circular.

## Out-of-scope items (TODO-tagged)

- `trailer_lint`: Layer-3 GitHub review API cross-check — TODO
  `#1153-ext`. Requires `GITHUB_TOKEN` + PR context only available
  inside the CI workflow.
- `complete_artifacts`: translation / codemod / RBP / skills checks
  are placeholders — TODO `#1153-ext`. Each depends on a downstream
  sub-phase deliverable (1D translator, §20 codemods, §14 RBP CI,
  §17.4 skill-install verifier).

## Tests + lint

- 70 new tests pass.
- `python -m pytest tests/qa/` total: 509 passed.
- `ruff check` / `ruff format --check` clean on all touched paths.
- `mypy --ignore-missing-imports` clean on new modules.

## Tracking

- Cascade umbrella: #1113.
- IMPL-1B lead issue: #1134.
- Sub-issue: #1153.
- Plan: `~/.claude/plans/polished-zooming-shell.md`.
