# ADR-042 Addendum 6 — Current-State Investigation Digest

Generated from a 5-agent read-only inventory of the current governance subsystem.

Purpose: ground the implementation spec and the implementation agents. Decisions = keep / modify / rewrite / deprecate, judged against the new ledger+evaluator model (gate record = single source of truth; nearly all checking consolidated into `gate_record check`; no duplicate checks).


## Area: gate_record

| Component | Decision | Dup-check? | In ADR/add6 |
|---|---|---|---|
| `gate_record/__init__.py` | **modify** | False | True |
| `gate_record/models.py` | **rewrite** | False | True |
| `gate_record/paths.py` | **modify** | True | True |
| `gate_record/io.py` | **modify** | False | True |
| `gate_record/stages.py` | **rewrite** | False | True |
| `gate_record/validation.py` | **rewrite** | True | True |
| `gate_record/workflow.py` | **rewrite** | True | True |
| `gate_record/cli.py` | **rewrite** | False | True |
| `gate_record/__main__.py` | **keep** | False | False |
| `gate_receipt.py` | **deprecate** | True | True |
| `workflow_gate.py` | **deprecate** | True | True |
| `check-gate-before-push.sh hook` | **modify** | True | True |
| `check-gate-before-pr.sh hook` | **modify** | True | True |
| `scistudio_pr_create.py (PR wrapper)` | **rewrite** | True | True |


### `gate_record/__init__.py` — MODIFY
- **Location:** `src/scistudio/qa/governance/gate_record/__init__.py`
- **Purpose:** Re-export package — provides a flat public surface identical to the original single-file gate_record.py. Exposes every public and private symbol as named imports with noqa:F401 back-compat markers for tests.
- **Current behavior:** Pure re-export module. Imports from cli, io, models, paths, stages, validation and re-publishes everything. Has no logic of its own. Enables `from scistudio.qa.governance.gate_record import ...` without callers knowing the sub-module layout.
- **Decision rationale:** The back-compat surface is fine but the __all__ and re-export list must be updated to drop old CLI subcommand names (start, docs, check, sentrux, plan) that become aliases or are absorbed into new init/check/finalize/amend/plan, and to add the new ledger/evaluator public symbols once the rewrite lands. Until then, keep as-is but flag that every private re-export (_xxx) will need replacement once old test coverage is replaced.


### `gate_record/models.py` — REWRITE
- **Location:** `src/scistudio/qa/governance/gate_record/models.py`
- **Purpose:** Pydantic schema for the on-disk gate record (GateRecord and evidence sub-models). Defines GateStage enum, IssueRef, Scope, ScopeAmendment, StageEvidence, CheckEvidence, SentruxEvidence, FullAuditEvidence, AdminLabelEvidence, CommitEvidence, PullRequestEvidence.
- **Current behavior:** Flat document-style record: a single JSON object with one fixed-sequence stages array. Schema version 1. task_kind is a closed Literal with 7 values; does not include 'guided'. Persona literal does not include 'live_implementer'. No observed_diff, no directive_events, no reconcile_events, no check_events as ledger append-only rows, no strictness_tier, no session_id, no runtime field. CheckEvidence is a flat evidence object, not a ledger event. admin_labels carry applied_by/applied_at but no actor provenance. docs_landing is an untyped Mapping. planned_files / required_checks / changed_test_paths are flat lists overwritten by plan_record, not appended events.
- **Decision rationale:** The model represents a mutable flat record, not an append-only ledger. The ADR-042 Addendum 6 ledger schema requires: directive_events, observed_diff (base/head/fingerprint/surface classification), check_events as append-only list with covered surface and input fingerprint, docs_events, test_events, guard_events, reconcile_events, session_id, runtime, strictness_tier, and the new task kinds (guided) and persona (live_implementer). The model must be restructured from flat document to event-log record. The schema_version must be bumped. Reuse: IssueRef, Scope, CommitEvidence, PullRequestEvidence core shape can be carried forward; AdminLabelEvidence needs actor provenance fields; SentruxEvidence can be ported as a guard_event variant; FullAuditEvidence becomes a check_event variant.


### `gate_record/paths.py` — MODIFY
- **Location:** `src/scistudio/qa/governance/gate_record/paths.py`
- **Purpose:** Path-matching primitives and surface classifiers: VALID_OVERRIDE_LABELS, IMPLEMENTATION_TASK_KINDS, IMPLEMENTATION_PATTERNS, NON_IMPLEMENTATION_PATTERNS, CLOSING_KEYWORD_RE, TRAILER_RE, SLUG_RE, _match_path, _matches_any, _is_test_path, _is_implementation_path, _is_governance_path, _sentrux_applies, _normalize_path.
- **Current behavior:** Standalone module with no circular imports. Contains two independent rule sets: (1) _sentrux_applies (used by validation.py for local gate decisions) and (2) sentrux_gate.sentrux_applies_to_changes (a different rule in the separate sentrux_gate.py module). Addendum 6 section 7.5 and the memory note (reference_sentrux_applies_asymmetry.md) explicitly flag this as a known divergence. _GOVERNANCE_PATTERNS controls governance-touch classification but is a separate, independently maintained list from the docs/ai-developer governance surface expansion in Addendum 6 section 7.8.
- **Duplication:** _sentrux_applies here (excludes tests/**) duplicates sentrux_gate.sentrux_applies_to_changes (includes tests/**). Two independent rule sets for the same question create divergent local vs CI behavior — the exact problem Addendum 6 is fixing.
- **Decision rationale:** The surface classification helpers (_is_test_path, _is_implementation_path, _is_governance_path, _sentrux_applies, _match_path) are exactly the 'file-surface classification derived from git' that the evaluator needs. They should be kept as evaluator-owned surface classifiers but must be migrated into the evaluator and deduplicated with sentrux_gate's copy. VALID_OVERRIDE_LABELS must also add 'admin-approved:bypass' (the new label name per Addendum 6 section 7.5 label table). _GOVERNANCE_PATTERNS must be extended to include docs/ai-developer/** per Addendum 6 section 7.8. IMPLEMENTATION_TASK_KINDS must add 'guided'. CLOSING_KEYWORD_RE and TRAILER_RE can be preserved as-is. The module itself can stay as a primitives layer below the evaluator, but _sentrux_applies must be reconciled with sentrux_gate's version.


### `gate_record/io.py` — MODIFY
- **Location:** `src/scistudio/qa/governance/gate_record/io.py`
- **Purpose:** Disk I/O, git helpers, record discovery. _load_record, _write_record, _mark_stage, _upsert_check, _git_lines, _slugify, _record_path, _discover_gate_record, _parse_key_values, _parse_issue_numbers.
- **Current behavior:** _write_record overwrites the entire record (not append-only). _mark_stage mutates the in-memory record in place. _upsert_check replaces a check by name (not appended as a new event). _discover_gate_record has two paths: single record vs umbrella-manager heuristic. None of these record or preserve prior state as ledger events.
- **Decision rationale:** The core I/O primitives (git shell-out, path resolution, slug, JSON read/write) are reusable. However _write_record, _mark_stage, and _upsert_check all implement overwrite/mutation semantics, which contradicts the append-only ledger model. These must be replaced with event-append writers that accumulate events rather than replacing top-level fields. _discover_gate_record can be carried forward with the addition of session_id-based discovery for the new local session identity concept. The git diff helpers can be ported forward as the 'observe git diff' infrastructure the evaluator needs.


### `gate_record/stages.py` — REWRITE
- **Location:** `src/scistudio/qa/governance/gate_record/stages.py`
- **Purpose:** Per-subcommand mutators: start_record, plan_record, amend_record, docs_record, check_record, sentrux_record, finalize_record. Each loads, mutates, marks a stage done, and writes back.
- **Current behavior:** start_record creates or fully replaces a record. plan_record overwrites planned_files, required_checks, changed_test_paths. amend_record appends to record.amendments (the only partially append-only operation) but also overwrites governance_touch. docs_record replaces the entire docs_landing dict (destructive, known bug per memory entry feedback_gate_record_docs_is_destructive). check_record either replaces full_audit or upserts a check by name. sentrux_record replaces the whole sentrux evidence field. finalize_record replaces commit and pull_request. None of these are ledger-append operations; they are all overwriting known fields. check_record does not run any actual commands — it only records agent-supplied evidence. There is no obligation inference, no tier derivation, and no git-diff-based check inference in stages.py.
- **Decision rationale:** Under Addendum 6, the current CLI subcommands map to new commands as follows: start -> init (with instruction generation and session_id, NOT present in start_record); plan -> plan (similar but must observe diff and recompute provisional obligations, not just overwrite fields); amend -> amend (stays append-only, must extend to all field classes not just scope); docs -> folded into amend/plan/check (docs_record as a separate subcommand disappears; docs_events are just a field class in amend/plan/check); check -> check (COMPLETELY different: must run actual commands, observe diff, infer tier-selected check set from CI graph, record sanitized events with input fingerprints, run guards via evaluator — none of this exists in check_record today); sentrux -> absorbed as a guard_event inside check (not a separate subcommand); finalize -> finalize (pre-PR and post-PR modes; must re-observe diff and run reconciliation, not just record supplied SHAs). start_record, plan_record, docs_record, check_record, and sentrux_record must be rewritten. amend_record is the closest to the new model and can be extended rather than fully replaced.


### `gate_record/validation.py` — REWRITE
- **Location:** `src/scistudio/qa/governance/gate_record/validation.py`
- **Purpose:** Validation entry points used by hooks and CI: validate_gate_record, check_pre_commit, check_pre_push, check_pr_ready, check_commit_msg, check_pr. Also _local_bypass_report, _env_bypass_labels, _effective_include, _effective_exclude, _trailers.
- **Current behavior:** validate_gate_record is the central validator. It runs scope checks (changed files vs include/exclude patterns), governance-touch checks, test-required checks (for implementation task kinds), sentrux advisory check, stage completeness, full_audit presence, PR body issue closure, override label validation, and guard_reports forwarding. check_pre_commit calls validate_gate_record with require_final_evidence=False. check_pre_push calls validate_gate_record with require_post_pr_stages=False. check_pr_ready calls validate_gate_record with require_pr_body=True, require_post_pr_stages=False. check_commit_msg validates required trailer keys only. check_pr calls validate_gate_record with full requirements. _test_engineer_scope_guard_findings dynamically imports test_engineer_scope_guard.check. Guard orchestration in workflow.py calls check_pr then combines it with separately called mod_guard, issue_link, docs_landing, weakened_ci_check reports.
- **Duplication:** Scope check logic (_effective_include/_effective_exclude pattern matching) duplicates parts of the scope check in workflow.run_ci; governance-touch check is also redone in mod_guard; issue closure check is done here AND in issue_link.check called from workflow.run_ci, which means the same closure requirement is checked twice with different finding rule_ids.
- **Decision rationale:** validate_gate_record is the current proto-evaluator but has major gaps: (1) it receives agent-declared scope and guard_reports as inputs from callers — it does not derive them from git diff itself; (2) guard reports are stitched together by workflow.run_ci, not by a single shared evaluator; (3) there is no tier derivation — all paths go through the same check set; (4) check evidence validation is absent — it accepts whatever check_results are in the record without verifying covered surface or input fingerprint freshness; (5) required checks are not inferred from diff + CI graph; (6) it is called differently in 4 modes (pre-commit/pre-push/pr-ready/CI) which is the exact duplication problem. Under Addendum 6 this must become a single shared evaluator that: takes (ledger, observed_diff, mode, tier) as inputs; derives all obligations itself; calls guards as evaluator-owned calculators; records a reconcile_event; and is called identically by local hooks, PR wrapper, and CI. The four current entry points (check_pre_commit, check_pre_push, check_pr_ready, check_pr) collapse into evaluator.reconcile(mode=...). _local_bypass_report, _trailers, _env_bypass_labels, _effective_include/exclude, and _closed_issue_numbers are utility helpers that can be ported.


### `gate_record/workflow.py` — REWRITE
- **Location:** `src/scistudio/qa/governance/gate_record/workflow.py`
- **Purpose:** run_ci: shared local/CI guard orchestration. Calls check_pr (from validation), issue_link.check, docs_landing.check, mod_guard.check, weakened_ci_check.verify_no_weakening, combines all reports.
- **Current behavior:** run_ci is the closest thing to an evaluator but it is only called from the CI subcommand and the scistudio_pr_create.py wrapper. It does NOT run actual checks (ruff, mypy, pytest, etc.) — it only runs governance guards. The actual CI-equivalent checks (lint, type, test, frontend) are handled separately by gate_receipt (infer_required_checks + append_check). This means there are two separate 'evaluator-like' flows: workflow.run_ci for governance guards, and gate_receipt for actual check execution — they share no code and run on different occasions.
- **Duplication:** run_ci calls check_pr (from validation.py) which runs scope/stage/sentrux/issue closure checks, then ALSO calls issue_link.check which runs issue closure checks again. Issue closure is checked twice: once in validate_gate_record via check_pr, and once in issue_link.check via run_ci.
- **Decision rationale:** Under Addendum 6, gate_record check must handle both governance guard evaluation AND actual CI-equivalent command execution through a single shared evaluator. The current split between workflow.run_ci (guards) and gate_receipt (commands) is the core duplication problem. workflow.run_ci should be dissolved into the new evaluator, with each guard (mod_guard, issue_link, docs_landing, weakened_ci_check) becoming an evaluator-owned calculator called during check reconciliation. The _combined helper can be ported as the evaluator's report accumulator.


### `gate_record/cli.py` — REWRITE
- **Location:** `src/scistudio/qa/governance/gate_record/cli.py`
- **CLI/trigger:** python -m scistudio.qa.governance.gate_record {start,plan,amend,docs,check,sentrux,finalize,pre-commit,commit-msg,pre-push,pr-ready,ci}
- **Purpose:** Argparse CLI for python -m scistudio.qa.governance.gate_record. Dispatches 12 subcommands: start, plan, amend, docs, check, sentrux, finalize (mutators) and pre-commit, commit-msg, pre-push, pr-ready, ci (validators).
- **Current behavior:** 12 subcommands total. The description string still says 'ADR-042 Addendum 1' (stale). Mutator subcommands all require --gate-record (explicit path, not discovered). Validator subcommands use optional --gate-record with auto-discovery. The 'check' subcommand is a passive evidence recorder (the agent supplies status/exit_code); it does NOT run commands. The 'ci' subcommand delegates to workflow.run_ci which runs governance guards only (not actual lint/type/test). The CLI mixes two completely different concepts under 'check': the agent tells it what happened (passive evidence recording) vs the evaluator running checks itself (active execution). There is no 'init' subcommand (the new Addendum 6 name for start). There is no --session-id, --runtime, --task-kind for init. There is no --pr-body-file for finalize. The 'start' subcommand requires --issue (int) making it fail for tasks where the issue is not yet known at init time.
- **Decision rationale:** The CLI must be restructured to match the Addendum 6 command contract: init (replacing start, adding runtime, session-id, print-instructions, issue optional), plan (removing --gate-record required, adding branch-based discovery, adding docs-updated/docs-na/test-path/test-na/check/check-na/admin-label), amend (adding docs-updated, test-path, check, admin-label, remove-issue, remove-include, remove-exclude), check (completely different: actively runs commands and infers obligations, --mode, --only, --skip-execution), finalize (two-mode pre-PR/post-PR, --pr optional, --pr-body-file). The 'docs', 'sentrux' subcommands are deprecated as standalone commands. The 'pre-commit', 'commit-msg', 'pre-push', 'pr-ready', 'ci' validator subcommands become evaluator.reconcile(mode=...) calls under a single 'check' dispatcher. Migration aliases for 'start' and 'docs' and 'sentrux' must delegate to the new implementation per Addendum 6 section 3.


### `gate_record/__main__.py` — KEEP
- **Location:** `src/scistudio/qa/governance/gate_record/__main__.py`
- **CLI/trigger:** python -m scistudio.qa.governance.gate_record
- **Purpose:** Entry point for python -m scistudio.qa.governance.gate_record. Delegates to cli.main().
- **Current behavior:** Two lines: imports main from cli, calls sys.exit(main()). This is the entry point hard-coded into hooks (check-gate-before-pr.sh, check-gate-before-push.sh) and scripts/scistudio_pr_create.py.
- **Decision rationale:** The entry point pattern is correct and must remain as-is. The prog='gate_record' pin in cli.py ensures stable error output. Only cli.py needs to change; __main__.py stays untouched.


### `gate_receipt.py` — DEPRECATE
- **Location:** `src/scistudio/qa/governance/gate_receipt.py`
- **CLI/trigger:** python -m scistudio.qa.governance.gate_receipt {validate,run,exec}
- **Purpose:** Local ADR-042 gate receipts: local CI-parity pre-PR check runner. Provides CandidateFingerprint (HEAD/diff/body fingerprint), build_candidate, receipt_paths, infer_required_checks, append_check (runs a command and appends stdout/stderr/exit_code to a local JSON receipt file), validate_receipt, _command_for. CLI subcommands: validate, run, exec.
- **Current behavior:** Maintains a separate local-only JSON receipt file under .workflow/local/gate-receipts/ keyed by HEAD SHA + PR body SHA. Tracks changed files, diff fingerprint, gate record fingerprint. infer_required_checks derives required checks from changed file prefixes (independent rule set, separate from validation.py's checks, separate from workflow.py's guards). append_check runs actual commands (ruff, mypy, pytest, frontend tools, full_audit, gate_record pre-commit/pre-push) and records exit code + stdout/stderr SHA256 in the local receipt. validate_receipt checks that the receipt exists, fingerprint matches, all required checks are present and exit 0. Both check-gate-before-pr.sh and check-gate-before-push.sh AND scistudio_pr_create.py call gate_receipt validate as a separate blocking step before gate_record ci. The receipt file is local-only (under .workflow/local/ which is .gitignored). _command_for has its own mapping of check names to command tuples, independently of CHECK_COMMANDS dict — this is another small duplication.
- **Duplication:** infer_required_checks in gate_receipt.py is a completely independent check-selection rule set from: (a) validation.py's governance/sentrux/test checks, (b) workflow.run_ci's guard set, and (c) the CI workflow graph. This is the canonical three-way duplication that Addendum 6 was written to fix. gate_receipt also independently fingerprints the candidate (diff, gate record, PR body SHA) which should become the observed_diff and input fingerprint in check_events.
- **Decision rationale:** gate_receipt is the primary target for absorption per Addendum 6 section 1 (Problems Addressed: 'receipt behavior is folded into the gate record as ledger events'), section 7.2 ('Local-only logs may exist as helper artifacts, but the gate record ledger is the canonical state'), and section 7.5 ('gate_record check is the main local parity command — it must not require the agent to manually run ruff, mypy, pytest...'). Under the new model: (1) CandidateFingerprint becomes the 'observed_diff' field in the ledger with diff fingerprint and file-surface classification; (2) infer_required_checks becomes evaluator obligation inference from observed diff + tier + CI graph; (3) append_check becomes the command execution inside gate_record check which records sanitized check_events in the committed ledger (raw stdout/stderr logs stay in .workflow/local/ as convenience artifacts); (4) validate_receipt becomes the check_events reconciliation that the evaluator performs during gate_record check or gate_record finalize. The receipt file format (local JSON keyed by HEAD SHA) becomes .workflow/local/logs only — not the canonical evidence store. The three CLI subcommands (validate, run, exec) are replaced by gate_record check --mode local, gate_record check --only <name>, and gate_record check as a whole. Compatibility: if scripts/hooks still call gate_receipt validate during migration, they must be updated as part of the rewrite branch per Addendum 6 section 3 step 4.


### `workflow_gate.py` — DEPRECATE
- **Location:** `src/scistudio/qa/governance/workflow_gate.py`
- **Purpose:** CLI wrapper module exposing 'python -m scistudio.qa.governance.workflow_gate ci'. Delegates to gate_record.workflow.run_ci.
- **Current behavior:** Single 'ci' subcommand. Accepts --gate-record (required), --base, --head, --pr-body, --pr-label, --format. Calls run_ci and formats the combined guard report. This is a second CLI entry point for the same run_ci function that gate_record ci also calls. The two are identical in functionality.
- **Duplication:** workflow_gate.main() and the 'ci' branch in gate_record cli.py both call workflow.run_ci with identical argument shapes. Two entry points for the same function.
- **Decision rationale:** workflow_gate.py is a thin wrapper over gate_record.workflow.run_ci. gate_record already exposes a 'ci' subcommand that calls the same run_ci. Having two separate python -m entry points for the same function creates the 'no single source' problem. Under Addendum 6, 'gate_record check --mode ci' becomes the canonical CI entry point. workflow_gate.py should be deprecated with a migration alias if it is referenced anywhere outside gate_record/workflow.py.


### `check-gate-before-push.sh hook` — MODIFY
- **Location:** `scripts/hooks/check-gate-before-push.sh`
- **Purpose:** PreToolUse hook that intercepts 'git push' tool calls and runs: gate_record pre-push (structural validation) + gate_receipt validate (local receipt freshness + check execution results).
- **Current behavior:** Two sequential blocking checks: (1) gate_record pre-push -- validates scope, stages (minus post-PR), bypass labels; (2) gate_receipt validate -- verifies the local receipt file exists, fingerprint matches, and all required check commands passed. Both must pass. Also checks gh pr labels for existing PR to detect bypass labels. Has independent Python inline scripts for label extraction.
- **Duplication:** Runs both gate_record pre-push AND gate_receipt validate as separate blocking steps. Under the new model, a single 'gate_record check --mode pre-push' replaces both.
- **Decision rationale:** Under Addendum 6, gate_receipt validate disappears (folded into ledger). The hook must be updated to call 'gate_record check --mode pre-push' which is the evaluator in pre-push mode. The gate_record pre-push call is replaced by the new check command. The label detection and bypass logic can stay but should route through the evaluator's bypass semantics. Also note: the label 'admin-approved:ai-override' in this hook's valid set is marked as a legacy name; Addendum 6 renames it to 'admin-approved:bypass'.


### `check-gate-before-pr.sh hook` — MODIFY
- **Location:** `scripts/hooks/check-gate-before-pr.sh`
- **Purpose:** PreToolUse hook that intercepts 'gh pr create' tool calls and runs: gate_record pr-ready (structural validation with PR body) + gate_receipt validate (with PR body fingerprint included).
- **Current behavior:** Requires --body or --body-file on the gh pr create command. Runs gate_record pr-ready then gate_receipt validate with pr-body. The pr-body hash is included in the receipt fingerprint so a stale receipt from the pre-push run is invalid for the PR check. Has the same independent label extraction inline Python as check-gate-before-push.sh.
- **Duplication:** Contains its own inline Python for label set extraction that duplicates validation.py's _split_labels/_env_bypass_labels/_invalid_override_labels. Runs both gate_record pr-ready AND gate_receipt validate as separate steps.
- **Decision rationale:** Same as check-gate-before-push.sh: gate_receipt validate is absorbed into 'gate_record check --mode pre-pr'. The PR body extraction logic and closing-keyword check are reusable. The inline label extraction Python duplicates logic from validation.py _split_labels / _env_bypass_labels and should use the evaluator's bypass check instead.


### `scistudio_pr_create.py (PR wrapper)` — REWRITE
- **Location:** `scripts/scistudio_pr_create.py`
- **Purpose:** Wrapper around 'gh pr create' that runs gate_receipt validate + gate_record ci locally before creating the PR. Filters PR-state-dependent findings (core_change_guard, pr_merge_guard, human_bypass_guard, commit_and_submit_pr stage) that cannot exist pre-PR.
- **Current behavior:** Runs two checks: (1) run_gate_receipt_validate — calls gate_receipt validate with actual PR body to verify local receipt; (2) run_gate_record_ci — calls gate_record ci (which runs workflow.run_ci guard orchestration) and filters PR-state findings. Has its own find_gate_record (independent of _discover_gate_record in io.py with slightly different multi-record heuristic), extract_body, extract_base, resolve_base_ref helpers. The filtering of PR-state guards (_FILTERED_GUARD_PREFIXES, _FILTERED_STAGE_NOT_DONE_TOKENS) is a separate hard-coded list of guard prefixes that must stay in sync with guard module names.
- **Duplication:** find_gate_record duplicates _discover_gate_record from io.py (same multi-record heuristic, different code path). _FILTERED_GUARD_PREFIXES is a second hard-coded mapping of guard module names that must stay in sync with the actual guard modules — a classic split-authority problem.
- **Decision rationale:** Under Addendum 6, gate_record finalize --pre-pr becomes the pre-PR readiness check and gate_record check --mode pre-pr becomes the unified evaluator call. The wrapper's current two-step flow (receipt validate + ci guards) collapses to one evaluator call. The wrapper can keep its gh pr create invocation logic, body/base extraction, and dry-run mode. find_gate_record should use _discover_gate_record from io.py instead of its own implementation. The _FILTERED_GUARD_PREFIXES list is an architectural debt: the evaluator should know which findings are pre-PR-impossible by mode, not require the caller to maintain an allowlist of guard names. This filtering logic moves into the evaluator's pre-PR reconciliation mode.


### Extra findings — gate_record

```text
CLI subcommand mapping (current -> Addendum 6 target):

  CURRENT SUBCOMMAND      -> ADDENDUM 6 TARGET
  start                   -> init (rename; must add runtime, session-id, optional issue, print-instructions)
  plan                    -> plan (similar but must add diff-observation, docs/test/check fields, branch-based discovery)
  amend                   -> amend (extend to all field classes; currently only does scope + governance_touch)
  docs                    -> DEPRECATED as standalone; docs_updated/docs_na fields fold into plan/amend/check
  check (passive)         -> REWRITE; must become active check runner; current semantics move to internal event recording
  sentrux                 -> DEPRECATED as standalone; becomes guard_event inside check
  finalize                -> finalize (two-mode pre-PR/post-PR, must run reconciliation, not just record SHAs)
  pre-commit              -> gate_record check --mode pre-commit (evaluator mode)
  commit-msg              -> kept (trailer validation is unchanged)
  pre-push                -> gate_record check --mode pre-push (evaluator mode)
  pr-ready                -> gate_record check --mode pre-pr (evaluator mode; combined with receipt validation)
  ci                      -> gate_record check --mode ci (evaluator mode; combined with guard orchestration)

GAPS NOT YET IN CURRENT CODE that the rewrite must add:
1. Strictness tier derivation (task_kind -> baseline tier -> diff-based escalation) - entirely absent today.
2. CI graph parsing / check-set inference from .github/workflows/ path filters - entirely absent; gate_receipt.infer_required_checks is a hand-written approximation.
3. Observed diff recorded as a ledger field (observed_diff with base/head/fingerprint/surface classification) - absent; currently only passed as a transient argument to validate_gate_record.
4. Check event input fingerprints (which files were covered, what sha256 was the diff at check time) - absent; gate_receipt records diff_sha256 + gate_record_sha256 per receipt file but this is not in the committed ledger.
5. session_id / .git/scistudio/gates/ local session state - absent entirely.
6. runtime field on GateRecord - absent; not in the current schema.
7. guided task kind - absent from GateRecord.task_kind Literal.
8. live_implementer persona - absent from Persona Literal.
9. directive_events as an append-only list - absent; only owner_directive (single string) exists.
10. reconcile_events - absent; reconciliation results are not recorded back into the ledger.
11. Task-kind instruction generation at init time - absent; init (start_record) produces no instructions.
12. Admin label actor provenance (who applied the label, when, from what PR labels API call) - partially present (AdminLabelEvidence has applied_by/applied_at) but CI never populates it; the observed_admin_labels vs requested_admin_labels distinction is absent.
13. Sanitization checks for committed ledger content (no absolute paths, no env dumps, no raw stdout) - absent from write path.
14. Per-worktree isolated CI-equivalent environment for check execution - absent; gate_receipt.append_check uses ambient PYTHONPATH without version isolation.

VALID_OVERRIDE_LABELS divergence: Current set is {human-authored, admin-approved:ai-override, admin-approved:core-change, admin-approved:merge}. Addendum 6 table in section 7.5 lists {admin-approved:bypass, admin-approved:core-change, admin-approved:merge} plus human-authored as a CI-only signal. 'admin-approved:ai-override' -> 'admin-approved:bypass' rename must be tracked as a migration item. Both hook scripts and scistudio_pr_create.py hard-code 'admin-approved:ai-override' in their valid label sets and must be updated.

Calling surface (what currently invokes gate_record and gate_receipt):
- scripts/hooks/check-gate-before-push.sh: gate_record pre-push + gate_receipt validate
- scripts/hooks/check-gate-before-pr.sh: gate_record pr-ready + gate_receipt validate
- scripts/scistudio_pr_create.py: gate_receipt validate + gate_record ci
- .github/workflows/ (Verify Workflow Compliance job): gate_record ci via workflow_gate or gate_record ci subcommand (not read in this session but referenced in gate_record/workflow.py and scistudio_pr_create.py)
- tests/qa/test_gate_record.py: imports private symbols from the package __init__.py re-export surface

Under Addendum 6, all four calling surfaces must converge on a single evaluator entry point (gate_record check --mode ...) rather than maintaining separate calling conventions for each surface type.
```

## Area: guards — src/scistudio/qa/governance/ (all modules except gate_record subpackage)

| Component | Decision | Dup-check? | In ADR/add6 |
|---|---|---|---|
| `workflow_gate` | **rewrite** | True | True |
| `docs_landing` | **modify** | False | True |
| `issue_link` | **modify** | False | True |
| `persona_policy` | **modify** | False | True |
| `core_change_guard` | **rewrite** | True | True |
| `human_bypass_guard` | **rewrite** | False | True |
| `pr_merge_guard` | **modify** | False | True |
| `mod_guard` | **rewrite** | True | True |
| `weakened_ci_check` | **rewrite** | True | True |
| `sentrux_gate` | **modify** | False | True |
| `test_engineer_scope_guard` | **modify** | False | True |
| `gate_receipt` | **deprecate** | True | True |
| `worktree_write_guard` | **modify** | False | True |
| `paths` | **keep** | False | False |


### `workflow_gate` — REWRITE
- **Location:** `src/scistudio/qa/governance/workflow_gate.py`
- **CLI/trigger:** python -m scistudio.qa.governance.workflow_gate ci --gate-record <path> --base ... --head ...
- **Purpose:** Thin CLI entry point and `run_ci()` orchestrator. Calls each guard independently, assembles a combined AuditReport, and exposes the `workflow_gate ci` command used by the CI workflow-gate.yml step.
- **Current behavior:** Reads the gate record via `_load_record`, derives changed files from git, then calls `issue_link.check`, `docs_landing.check`, `mod_guard.check`, `weakened_ci_check.verify_no_weakening`, and `gate_record.validation.check_pr` as separate independent calls. Each guard receives only the slice of data that `run_ci` chooses to pass. No single evaluator; no ledger-event output; no tier selection.
- **Duplication:** The CI workflow-gate.yml also calls most of the same guards a second time in a separate Python inline script (the 'Run ADR-042 guard orchestration' step). That step calls human_bypass_guard, issue_link, docs_landing, sentrux_gate, core_change_guard, mod_guard, pr_merge_guard, and weakened_ci_check independently. So the guard logic runs twice in CI from two different callers with different inputs, creating the split-authority problem Addendum 6 addresses.
- **Decision rationale:** Addendum 6 §7.5 and §3 require a single shared evaluator that all callers (local hooks, PR wrapper, CI) use. workflow_gate currently IS that CI-mode entry point but it is not an evaluator: it is an ad-hoc orchestrator that bypasses tier selection, does not read ledger events, and duplicates guard calls already present in the CI YAML inline script. Rewrite as the evaluator's CI-mode runner (`gate_record check --mode ci`) so the same evaluator path is used for both local and CI, eliminating the parallel CI-YAML guard invocations.


### `docs_landing` — MODIFY
- **Location:** `src/scistudio/qa/governance/docs_landing.py`
- **CLI/trigger:** python -m scistudio.qa.governance.docs_landing --changed-file ... --docs-landing-json ...
- **Purpose:** Validates that governed changes (implementation, governance, workflow files) have docs/changelog/checklist landing evidence or an explicit N/A rationale in the gate record.
- **Current behavior:** Pure calculator: accepts `changed_files` and `docs_landing` dict from caller. Does NOT read the gate record itself; the caller must extract `record.docs_landing` and pass it. Has its own `IMPLEMENTATION_PREFIXES` and `GOVERNANCE_PREFIXES` surface classifiers that are defined independently from the evaluator's surface model.
- **Duplication:** No duplicate — the check logic itself is not replicated elsewhere. However, the caller (workflow_gate, gate_receipt, CI YAML) must supply inputs, creating a dependency on external wiring rather than reading from the ledger directly.
- **Decision rationale:** Addendum 6 §7.5 says `docs_landing.check` must be called by the evaluator, not independently. The calculation logic is sound and can be preserved. Modify to remove the standalone CLI entry point or keep it only as a thin wrapper; the real invocation must go through the evaluator which supplies inputs from the ledger's `docs_events` / `observed_diff`. Surface prefix constants should migrate to the evaluator's surface classification model.


### `issue_link` — MODIFY
- **Location:** `src/scistudio/qa/governance/issue_link.py`
- **CLI/trigger:** python -m scistudio.qa.governance.issue_link --issue ... --issue-url ... --pr-body ...
- **Purpose:** Validates that at least one linked issue exists in the gate record, that issue records are structurally valid, and that the PR body uses closing keywords for every issue. Also exposes `resolve_or_create` and `IssueClient` protocol for issue resolution.
- **Current behavior:** Pure calculator: accepts issues list and PR body from caller. Does not read the gate record; the caller must extract `record.issues`. The `resolve_or_create` helper adds a second responsibility (GitHub integration) to what should be a pure validation module.
- **Duplication:** No duplicate — the check logic is not replicated elsewhere. But like docs_landing, the external wiring is the problem, not the calculation.
- **Decision rationale:** Addendum 6 §7.5 lists issue-link checks as evaluator responsibilities. The validation calculation (`check` function) should stay as an evaluator-owned calculator receiving inputs from the ledger's `issues` field and `pull_request` field. The `resolve_or_create` / `IssueClient` interface is a separate GitHub integration concern; it should be separated from the validation module or moved to a helper used only during `init`/`amend`. Remove the standalone bypass path that passes issues from outside the ledger.


### `persona_policy` — MODIFY
- **Location:** `src/scistudio/qa/governance/persona_policy.py`
- **CLI/trigger:** python -m scistudio.qa.governance.persona_policy --declaration-json ...
- **Purpose:** Validates that the declared persona is one of the ADR-042 allowed personas, that the skill name matches the persona table, and that the runtime root, skill path, constitution path, root policy path, and workflow docs all exist on disk.
- **Current behavior:** Pure calculator: accepts a `declaration` dict and `repo_root`. Reads no ledger. Has a hardcoded `ALLOWED_PERSONAS` frozenset that does NOT include `live_implementer` (added in Addendum 6). Also maps `implementer` to skill name `implementation-worker`, which conflicts with the actual skill name `implementer` seen in AGENTS.md. The path-existence checks for `skill_path`/`constitution_path`/`root_policy_path`/`workflow_docs` run at check time, not on ledger-declared values.
- **Duplication:** No duplicate — the check logic is not replicated elsewhere.
- **Decision rationale:** Addendum 6 §7.5 lists `persona_policy.check` as an evaluator responsibility. The calculation logic is correct in structure. Required modifications: (1) add `live_implementer` to ALLOWED_PERSONAS and add its skill mapping; (2) fix the `implementer` skill name mapping to match the actual skill name; (3) rename the label in the Addendum 6 vocabulary for `admin-approved:bypass` (not `ai-override`) — this module does not reference that label but the persona table in Addendum 6 §7.3 updates the skill name for `live_implementer`; (4) have the evaluator supply the declaration from the ledger's `persona` and `runtime` fields rather than accepting a free-form dict.


### `core_change_guard` — REWRITE
- **Location:** `src/scistudio/qa/governance/core_change_guard.py`
- **CLI/trigger:** python -m scistudio.qa.governance.core_change_guard --changed-file ... --pr-json ...
- **Purpose:** Hard-fails AI-authored changes to protected core and governance paths that lack `admin-approved:core-change` label provenance or an admin approval review.
- **Current behavior:** Pure calculator: accepts `changed_files`, `pr`, and `session` from caller. Does NOT read the ledger for the `requested_admin_labels` field that the ledger is supposed to record. Has its own `PROTECTED_GLOBS` tuple that includes `src/scistudio/qa/governance/**` and other governance paths in addition to the core runtime paths; this overlaps with `mod_guard.PROTECTED_PATTERNS` without a single canonical source. Imports `ADMIN_PERMISSIONS` and `CORE_CHANGE_LABEL` from `human_bypass_guard`, creating a shared-constants coupling.
- **Duplication:** In the CI workflow-gate.yml 'Run ADR-042 guard orchestration' step, `core_change_guard.check` is called twice: once with its own PROTECTED_GLOBS and once again with `mod_guard.PROTECTED_PATTERNS` as the protected_globs parameter. This double-call pattern is the CI YAML's workaround for two guards having overlapping but non-identical protected glob sets.
- **Decision rationale:** Addendum 6 §7.5 and §7.8 require the evaluator to consolidate protected-path authorization into a single canonical glob set and to read `requested_admin_labels` from the ledger rather than from caller-supplied PR data alone. The current guard has a protected-glob set that partially duplicates mod_guard, creating the double-call workaround in CI. Rewrite as an evaluator-owned calculator: (1) consolidate protected-path classification into the evaluator's single path-surface model; (2) read `requested_admin_labels` from the ledger; (3) verify observed admin labels from PR metadata supplied by the evaluator.


### `human_bypass_guard` — REWRITE
- **Location:** `src/scistudio/qa/governance/human_bypass_guard.py`
- **CLI/trigger:** python -m scistudio.qa.governance.human_bypass_guard --pr-json ...
- **Purpose:** Validates human-authored and administrator override label provenance. Also exports shared constants (`ADMIN_PERMISSIONS`, `CORE_CHANGE_LABEL`, `MERGE_LABEL`, `VALID_OVERRIDE_LABELS`) used by core_change_guard, pr_merge_guard, mod_guard, weakened_ci_check, and worktree_write_guard.
- **Current behavior:** Pure calculator for PR label validation. Defines `AI_OVERRIDE_LABEL = 'admin-approved:ai-override'` — the OLD label name. Addendum 6 §7.5 renames this to `admin-approved:bypass`. The dual role (validation + constants exporter) means the old label name is imported by and used in several other guards and the gate_record validation module, creating a migration surface. The `_has_ai_evidence` heuristic (checking commit messages for 'Assisted-by:' or 'Gate-Record:') is an independent heuristic not driven by the ledger's own `runtime` or `check_events` fields.
- **Duplication:** The label provenance check logic itself is not duplicated. However, the constants it exports (VALID_OVERRIDE_LABELS) are duplicated into the CI YAML inline script at line 56-61 of workflow-gate.yml.
- **Decision rationale:** Addendum 6 §7.5 requires the evaluator to handle `human_bypass_guard` in CI mode. Additionally, the `admin-approved:ai-override` label must be migrated to `admin-approved:bypass` per the Addendum 6 label vocabulary in §7.5. All downstream constants importers (core_change_guard, pr_merge_guard, mod_guard, weakened_ci_check, worktree_write_guard, gate_record/paths.py, gate_record/validation.py, gate_record/stages.py) must also be updated. As part of the rewrite: move the shared label constants into the evaluator's label vocabulary module; have the guard read PR label provenance from the evaluator's `observed_admin_labels` ledger field rather than re-parsing raw PR events; remove the AI-evidence heuristic and use the ledger's `runtime` field instead.


### `pr_merge_guard` — MODIFY
- **Location:** `src/scistudio/qa/governance/pr_merge_guard.py`
- **CLI/trigger:** python -m scistudio.qa.governance.pr_merge_guard --pr-json ... --intent merge
- **Purpose:** Blocks AI merge automation unless the `admin-approved:merge` label with authorized provenance is present on the PR.
- **Current behavior:** Pure calculator: accepts `pr`, `intent`, and `actor` from caller. Does NOT read the ledger. The `is_ai_actor` flag is derived from `actor.get('is_ai', True)` — defaulting to True, meaning anything not explicitly flagged as non-AI is treated as AI. In the CI YAML 'Run ADR-042 guard orchestration' step it is called with `intent='comment'` which is not in `MERGE_INTENTS`, so `needs_approval` is always False in that CI invocation and the guard effectively does nothing there.
- **Duplication:** The check logic is not duplicated. However, the current CI invocation uses intent='comment' which puts the guard into a pass-always state, effectively neutering the check in CI.
- **Decision rationale:** Addendum 6 §7.5 requires `pr_merge_guard` to be called by the evaluator. The merge-blocking logic is correct. Required fixes: (1) have the evaluator determine merge intent from the actual GitHub event type (not hardcoded 'comment'), so the guard actually fires when a merge automation attempt occurs; (2) read `observed_admin_labels` from the evaluator's ledger data rather than raw PR input; (3) remove the standalone CLI if merge detection is fully evaluator-driven.


### `mod_guard` — REWRITE
- **Location:** `src/scistudio/qa/governance/mod_guard.py`
- **CLI/trigger:** python -m scistudio.qa.governance.mod_guard --repo-root ... --base ... --head ...
- **Purpose:** Blocks unauthorized changes to governance-critical files (`AGENTS.md`, `.workflow/**`, `.github/workflows/**`, `pyproject.toml` excluded, `src/scistudio/qa/**`, `tests/qa/**`, etc.) using its own `PROTECTED_PATTERNS` and an environment-variable bypass mechanism.
- **Current behavior:** Runs its own git diff to get changed files. Uses two env-var bypass channels (`SCISTUDIO_GOVERNANCE_CHANGE_APPROVED=1` and `SCISTUDIO_GATE_BYPASS_LABELS`) that are independent authorities separate from the ledger. The `PROTECTED_PATTERNS` overlaps with `core_change_guard.PROTECTED_GLOBS` — both cover `src/scistudio/qa/**` and `.github/workflows/**` — but are not identical. In CI the guard is called twice: once by `workflow_gate.run_ci` and once directly in the inline Python script, with different `allow_governance_change` arguments.
- **Duplication:** Overlapping PROTECTED_PATTERNS with core_change_guard (both guard `.github/workflows/**`, `.workflow/**`, `src/scistudio/qa/**`). Called twice in CI: once from workflow_gate.run_ci and once in the inline YAML Python script, each with different inputs.
- **Decision rationale:** Addendum 6 §7.5 explicitly lists `governance_mod_guard` as an evaluator responsibility and requires guards to receive inputs from the evaluator, not maintain independent rule sets. The env-var bypass channels (`SCISTUDIO_GOVERNANCE_CHANGE_APPROVED`, `SCISTUDIO_GATE_BYPASS_LABELS`) are independent authorities that the evaluator must replace: approval is signaled via the ledger's `governance_touch` flag and `requested_admin_labels`, and CI verifies via `observed_admin_labels`. The PROTECTED_PATTERNS overlap with core_change_guard must be resolved by merging into a single canonical protected-path surface classification in the evaluator.


### `weakened_ci_check` — REWRITE
- **Location:** `src/scistudio/qa/governance/weakened_ci_check.py`
- **CLI/trigger:** python -m scistudio.qa.governance.weakened_ci_check --repo-root ... --base ... --head ...
- **Purpose:** Scans diffs in governed CI/pre-commit files (`.github/workflows/*.yml`, `.pre-commit-config.yaml`, `pyproject.toml`) for patterns that remove required check tokens or add CI-weakening constructs (`continue-on-error: true`, `|| true`, `--no-verify`, etc.).
- **Current behavior:** Runs its own git diff against `GOVERNED_PATTERNS`. Uses the same env-var bypass channel (`SCISTUDIO_GATE_BYPASS_LABELS`) as mod_guard, duplicating the bypass-label parsing logic. The `GOVERNED_PATTERNS` covers only CI/pre-commit files, not the broader governance surface. The `REQUIRED_REMOVAL_TOKENS` hard-code the CI command tokens that must not be removed — this is a static list independent of CI's actual current check inventory.
- **Duplication:** Duplicates the env-var bypass-label parsing logic already present in mod_guard (both modules define `_local_bypass_findings()` that reads `SCISTUDIO_GATE_BYPASS_LABELS`). The REQUIRED_REMOVAL_TOKENS list is a hand-maintained copy of CI command tokens that is not generated from the CI workflow graph.
- **Decision rationale:** Addendum 6 §7.5 requires `weakened_ci_check` to be called by the evaluator. The env-var bypass duplication must be eliminated; bypass authority must come from the ledger's `governance_touch` and `requested_admin_labels` fields, not from environment variables. The `REQUIRED_REMOVAL_TOKENS` list should be derived from (or validated against) the CI workflow graph that the evaluator already parses for tier-selected check selection (Addendum 6 §7.5), rather than being a separate static list.


### `sentrux_gate` — MODIFY
- **Location:** `src/scistudio/qa/governance/sentrux_gate.py`
- **CLI/trigger:** python -m scistudio.qa.governance.sentrux_gate <evidence-json-path> --changed-file ...
- **Purpose:** Parses and validates Sentrux free-tier evidence from the gate record. Normalizes evidence from MCP or CLI JSON output. Has a `sentrux_applies_to_changes()` predicate for deciding applicability.
- **Current behavior:** Has two modes of operation: the `verify_free_tier_claims` function accepts evidence directly from the caller, and `sentrux_applies_to_changes` has its own surface-prefix lists (`_SOURCE_PREFIXES`, `_WORKFLOW_PREFIXES`, `_ARCHITECTURE_DOC_PREFIXES`). In CI the module is called advisory-only (non-blocking). There is a documented asymmetry: `sentrux_gate.sentrux_applies_to_changes` includes `tests/**` surfaces but `gate_record._sentrux_applies` excludes them — this means CI and local disagree on applicability for test-only diffs.
- **Duplication:** No duplicate check logic. But the applicability predicate is duplicated in an inconsistent form in gate_record's internal `_sentrux_applies` function, creating the CI/local asymmetry that Addendum 6 is designed to eliminate.
- **Decision rationale:** Addendum 6 §7.5 requires `sentrux_gate` to be called by the evaluator as 'advisory or blocking according to the active ADR-042 addendum semantics'. The evidence parsing and validation logic is reusable. Required changes: (1) consolidate `sentrux_applies_to_changes` and `gate_record._sentrux_applies` into a single applicability predicate in the evaluator's surface classification model, eliminating the CI/local asymmetry; (2) have the evaluator supply evidence from the ledger's `check_events` where a `sentrux.free_tier` event is recorded; (3) keep the `SentruxEvidence` model and `parse_sentrux_result` as the canonical evidence normalizer.


### `test_engineer_scope_guard` — MODIFY
- **Location:** `src/scistudio/qa/governance/test_engineer_scope_guard.py`
- **CLI/trigger:** python -m scistudio.qa.governance.test_engineer_scope_guard --persona test_engineer --changed-file ...
- **Purpose:** Blocks `test_engineer` persona work from modifying production code, build config, or governance files. Classifies paths into allowed test artifacts, blocked production surfaces, blocked build surfaces, and blocked governance surfaces.
- **Current behavior:** Optionally reads the gate record via a `record` parameter (imports `_source_sha` from `pr_merge_guard`, an unrelated module). When `record` is supplied, it extracts `scope.include` and `amendments[*].include` to allow QA-tooling path exceptions. Can also be called without a record by passing `persona` and `changed_files` directly. When called from the current CI inline script, it is NOT called at all — the CI YAML does not invoke this guard despite it being in the inventory.
- **Duplication:** No duplicate check logic. Not currently called in CI.
- **Decision rationale:** Addendum 6 §7.5 requires `test_engineer_scope_guard` to be called by the evaluator. The path classification logic is correct and reusable. Required changes: (1) remove the optional record parameter and have the evaluator supply persona and scope directly from the ledger; (2) move the `_source_sha` import to a shared utility instead of borrowing from `pr_merge_guard`; (3) ensure the evaluator actually invokes this guard for test_engineer persona tasks in CI (currently absent from the CI YAML).


### `gate_receipt` — DEPRECATE
- **Location:** `src/scistudio/qa/governance/gate_receipt.py`
- **CLI/trigger:** python -m scistudio.qa.governance.gate_receipt run|validate|exec --gate-record ...
- **Purpose:** Local-only receipt file system that runs check commands, fingerprints the current candidate (base/head/diff/gate-record/PR-body SHA256), and validates that all required checks ran and passed for that exact candidate. Maintains its own check inference logic (`infer_required_checks`) and a hardcoded `CHECK_COMMANDS` dict.
- **Current behavior:** Operates as a fully independent subsystem alongside the gate record. Has its own `infer_required_checks()` that maps changed-file surfaces to required check names — this is a parallel version of the same obligation inference that the evaluator is supposed to own. The `CHECK_COMMANDS` dict hard-codes check commands locally instead of deriving them from the CI workflow graph. Receipts are local-only files under `.workflow/local/gate-receipts/` — they are NOT ledger events and are NOT committed. This creates the 'gate record and receipt record overlapping evidence' problem identified in Addendum 6 §1.1.
- **Duplication:** The `infer_required_checks()` function duplicates the check-inference logic that should exist only in the evaluator. The `CHECK_COMMANDS` dict is a hand-written subset of CI commands, partially overlapping with the CI workflow graph parsing that Addendum 6 requires the evaluator to perform. The receipt fingerprinting and freshness validation duplicates what the evaluator's `check_events` covered-surface/input-fingerprint model is designed to replace.
- **Decision rationale:** Addendum 6 §1.1 explicitly identifies gate_receipt as the source of the 'overlapping evidence' and 'check evidence freshness all-or-nothing' problems. Addendum 6 §3 step 8 states: 'Replace receipt files with ledger check and reconcile events.' The receipt module must be deleted in the rewrite, with its candidate fingerprinting (diff SHA256, gate-record SHA256, PR-body SHA256) ported into the evaluator's `check_events` input-fingerprint model, and its command execution ported into `gate_record check` which runs the evaluator-inferred tier-selected command set.


### `worktree_write_guard` — MODIFY
- **Location:** `src/scistudio/qa/governance/worktree_write_guard.py`
- **CLI/trigger:** python -m scistudio.qa.governance.worktree_write_guard --hook-json (reads stdin) | --repo-root ... --target ...
- **Purpose:** Pre-tool hook guard that blocks AI writes to paths outside the gate record's declared scope include/exclude patterns, to non-main branches, or when no gate record exists. Validates Claude/Codex hook payloads from stdin.
- **Current behavior:** Reads the gate record directly (via `_load_record`) and derives effective include/exclude lists by accumulating `scope.include`, `scope.exclude`, and all `amendments[*].include/exclude`. Has its own `_discover_record()` logic to find the gate record by branch name. Uses `BROAD_OVERRIDE_LABELS` (containing the OLD `admin-approved:ai-override` label name). Does NOT use a shared evaluator; it is called as a pre-tool hook before the full gate cycle runs, so it operates on whatever ledger state is present at write time.
- **Duplication:** The record-discovery logic (`_discover_record`) duplicates logic also present in gate_record's auto-discovery. The scope-matching logic is a simplified local version of the evaluator's planned scope reconciliation.
- **Decision rationale:** Addendum 6 §7.5 lists `worktree_write_guard` as 'before tool mutation and evaluator reconciliation afterward'. The pre-tool hook role is correct and must be preserved. Required changes: (1) update `BROAD_OVERRIDE_LABELS` to use `admin-approved:bypass` instead of `admin-approved:ai-override`; (2) delegate record discovery to the evaluator's canonical discovery logic rather than reimplementing it; (3) have the scope check read the ledger's effective include/exclude from the evaluator's scope model (which also tracks directive events in `guided` tasks); (4) record the write attempt as a `guard_event` in the ledger when it blocks.


### `paths` — KEEP
- **Location:** `src/scistudio/qa/governance/paths.py`
- **CLI/trigger:** No CLI. Import only.
- **Purpose:** Shared utility module providing `is_gate_record_path()` — a single-source-of-truth predicate for identifying `.workflow/records/**` files so that governance guards do not accidentally treat committed gate records as protected governance changes.
- **Current behavior:** Pure utility: no side effects, no independent authority, no bypass logic. Imported by `docs_landing`, `core_change_guard`, `mod_guard` (implicitly through its UNPROTECTED_PATTERNS), `sentrux_gate`, and `gate_record.paths`. The module was introduced specifically to fix the repeated inconsistent exclusion bug (#1316, #1340, #1362).
- **Duplication:** No duplication. This module IS the consolidation of previously duplicated exclusion logic.
- **Decision rationale:** This module is not listed in Addendum 6 because it is a utility, not a guard. The no-duplication principle supports keeping it: it solves a real recurring inconsistency problem with a single shared predicate. In the rewrite it should be migrated into the evaluator's shared path-classification utilities (or kept as a sub-module of the evaluator package) so all guard calculators and the CI mode share the same exclusion predicate. No changes needed to the predicate logic itself.


### Extra findings — guards — src/scistudio/qa/governance/ (all modules except gate_record subpackage)

```text
1. LABEL NAME MIGRATION SCOPE: Addendum 6 §7.5 replaces `admin-approved:ai-override` with `admin-approved:bypass`. This affects: human_bypass_guard.py (defines AI_OVERRIDE_LABEL), worktree_write_guard.py (BROAD_OVERRIDE_LABELS), gate_record/paths.py (hardcoded label string), gate_record/validation.py (broad_bypass_labels set, line 174), gate_record/stages.py (docstring, line 134), and the CI workflow-gate.yml inline Python script (valid_override set, line 56-61). All must be updated atomically in the rewrite.

2. MISSING GUARD IN CI: test_engineer_scope_guard is listed in Addendum 6 §7.5 and §3 but is NOT invoked anywhere in the current workflow-gate.yml. It exists as a standalone module with tests but has no CI enforcement path. The rewrite must wire it through the evaluator so it runs for all test_engineer persona gate records.

3. MISSING PERSONA: persona_policy.py's ALLOWED_PERSONAS frozenset does not include `live_implementer`, which Addendum 6 §7.2 and §7.3 add as a required persona. The REQUIRED_PERSONA_SKILLS map also does not have an entry for it. Additionally, the `implementer` skill is mapped to `implementation-worker` but the actual repository skill is named `implementer` (per AGENTS.md routing entries). Both must be corrected in the rewrite.

4. DOUBLE GUARD INVOCATION IN CI: The workflow-gate.yml has two separate Python steps that call overlapping guard sets. Step 1 ('Validate committed gate records') calls `gate_record ci` which internally calls `workflow_gate.run_ci` (which calls issue_link, docs_landing, mod_guard, weakened_ci_check, gate_record.validation.check_pr). Step 2 ('Run ADR-042 guard orchestration') then calls human_bypass_guard, issue_link, docs_landing, sentrux_gate, core_change_guard, mod_guard, pr_merge_guard, weakened_ci_check independently again. This means issue_link, docs_landing, mod_guard, and weakened_ci_check each run twice in every CI pass, with different inputs and potentially different results. The rewrite must collapse this into a single evaluator call.

5. SKILL_POINTER_SYNC NOT IMPLEMENTED: Addendum 6 §7.4 mentions `skill_pointer_sync` as a verifier that pointers remain valid across runtime config roots. No such module exists anywhere in `src/scistudio/qa/governance/`. This is a gap that the rewrite must fill as a new evaluator-owned calculator.

6. ENV-VAR BYPASS CHANNELS ARE PARALLEL AUTHORITIES: mod_guard uses `SCISTUDIO_GOVERNANCE_CHANGE_APPROVED=1` and `SCISTUDIO_GATE_BYPASS_LABELS`, and weakened_ci_check uses `SCISTUDIO_GATE_BYPASS_LABELS`. These environment-variable bypass channels are independent authorities that exist outside the ledger. Addendum 6 §7.5 requires bypass and authorization to flow through the ledger's `requested_admin_labels` and CI's `observed_admin_labels`, not env vars. The rewrite must remove these channels.

7. GATE_RECEIPT INFER_REQUIRED_CHECKS vs EVALUATOR: gate_receipt.infer_required_checks() is a hand-written surface-to-check mapping that predates the evaluator design. It maps surface prefixes to check names using its own logic independent of the CI workflow graph. Addendum 6 §7.5 requires the evaluator to derive the required check set from the CI workflow graph, task kind, and tier. The gate_receipt's infer_required_checks must not be migrated into the evaluator as-is; the evaluator must derive checks from the actual CI workflow definitions.
```

## Area: hooks

| Component | Decision | Dup-check? | In ADR/add6 |
|---|---|---|---|
| `check-worktree-write-guard.sh` | **rewrite** | True | True |
| `check-gate-before-push.sh` | **rewrite** | True | True |
| `check-gate-before-pr.sh` | **rewrite** | True | True |
| `check-ci-after-pr.sh` | **keep** | False | False |
| `check-agent-template.sh` | **modify** | False | False |
| `remind-checklist-discipline.sh` | **modify** | False | False |
| `run_python_module.py` | **keep** | False | False |
| `scistudio-governance-mod-guard (pre-commit)` | **rewrite** | True | True |
| `scistudio-weakened-ci-check (pre-commit)` | **rewrite** | True | True |
| `scistudio-gate-record-pre-commit (pre-commit)` | **rewrite** | True | True |
| `scistudio-gate-record-commit-msg (pre-commit)` | **rewrite** | False | True |
| `pre-commit standard hooks (trailing-whitespace, end-of-file-fixer, check-yaml, check-json, check-added-large-files, check-merge-conflict, detect-private-key)` | **keep** | False | False |
| `ruff + ruff-format (pre-commit)` | **modify** | True | False |
| `mypy (pre-commit)` | **modify** | True | False |
| `commitizen (pre-commit, commit-msg stage)` | **keep** | False | False |
| `scistudio_pr_create.py (PR wrapper)` | **rewrite** | True | True |
| `workflow-gate.yml / Verify Workflow Compliance (CI)` | **rewrite** | True | True |


### `check-worktree-write-guard.sh` — REWRITE
- **Location:** `scripts/hooks/check-worktree-write-guard.sh`
- **CLI/trigger:** PreToolUse on Edit|Write|MultiEdit|NotebookEdit|apply_patch (wired in .codex/hooks.json only; NOT in .claude/settings.json due to owner disabling it)
- **Purpose:** PreToolUse harness hook (Claude/Codex) that blocks AI write-tool calls (Edit/Write/MultiEdit/NotebookEdit/apply_patch) when the target path violates worktree scope. Delegates to scistudio.qa.governance.worktree_write_guard --hook-json.
- **Current behavior:** Reads hook stdin JSON, calls check_hook_payload() which: (1) resolves the repo root by calling git rev-parse --show-toplevel from the cwd field in the payload, (2) checks if current branch is main/master — blocks unconditionally, (3) requires exactly one gate record matching the current branch in .workflow/records/, (4) loads that gate record's scope.include and amendments[].include patterns, (5) for every target path: resolves it relative to the repo root, then blocks the write if it is OUTSIDE the include patterns OR INSIDE the exclude patterns. OVER-BLOCKING root cause: step (1) uses git rev-parse from payload.cwd, which succeeds for any path under the repo — but when the AI writes to a path that is outside the repo entirely (e.g. the Claude memory directory at ~/.claude/...), _repo_root() still resolves to the current git repo root because it is called from the repo's cwd, then resolved.relative_to(root) raises ValueError which the code catches and emits 'write target is outside the assigned worktree'. This means ANY write to a file outside the repo (memory files, temp files, external logs) is incorrectly blocked. Additionally, the guard blocks writes where the target path does not match the declared gate-scope include patterns, which means even writes inside the repo but outside the declared scope are blocked — this is the 'intended' scope-guard feature but has been reported as over-blocking in practice because the memory path error is the most visible symptom.
- **Duplication:** ADR-042 Addendum 6 section 7.5 states worktree_write_guard should be an evaluator-owned calculator. The scope-reconciliation logic (include/exclude pattern matching) is a duplicate of what the shared evaluator will do during reconciliation. The guard currently has its own independent scope-evaluation rule set that is separate from gate_record check reconciliation. This is exactly the 'individual tools keep independent rule sets' problem the new design eliminates.
- **Decision rationale:** Listed in Addendum 6 section 7.5 and section 3 inventory. Must become an evaluator-owned calculator. The current over-blocking bug must be fixed: the ONLY purpose of the hook in the new model is to block an AI agent from writing to the MAIN repo working tree when that agent is supposed to be in an assigned worktree. MINIMAL revised logic: (1) Check whether the target path resolves to inside any git repository root reachable from the cwd. (2) If the target path is OUTSIDE any git repo (e.g. ~/.claude/memory/), ALLOW it unconditionally — the guard has no jurisdiction outside repo boundaries. (3) If the target path is inside a repo, identify which worktree/repo it belongs to. (4) Block ONLY if: the resolved repo root is the MAIN repo working tree (the one at the canonical non-worktree checkout path, typically checked via git worktree list) AND the current agent session is supposed to be operating in a different assigned worktree (i.e. the agent's cwd is itself inside a git worktree that is NOT the main working tree). (5) Allow all writes inside the agent's own assigned worktree, any other non-main worktree, and any path outside all repos. The scope-enforcement (include/exclude pattern matching) should be REMOVED from this hook — that responsibility belongs entirely to the evaluator's reconciliation during gate_record check/finalize, not at write-time.


### `check-gate-before-push.sh` — REWRITE
- **Location:** `scripts/hooks/check-gate-before-push.sh`
- **CLI/trigger:** PreToolUse on Bash matching 'git push*' (wired in .claude/settings.json)
- **Purpose:** PreToolUse harness hook (Claude) that intercepts 'git push' Bash commands and validates the ADR-042 gate record before allowing the push.
- **Current behavior:** Parses the Bash command JSON from stdin; if it is not a git push, passes through. Reads bypass labels from SCISTUDIO_GATE_BYPASS_LABELS env and from gh pr view on the current branch. Calls 'gate_record pre-push' with --base and --bypass-label args; on nonzero exit denies the push. If a broad bypass label (human-authored or admin-approved:ai-override) is present and gate_record pre-push passes, allows unconditionally. Otherwise, discovers the branch's gate record in .workflow/records/, runs 'gate_receipt validate --repo-root --gate-record --base --head', and denies if that also fails. Contains independent bypass-label parsing and validation logic in embedded Python.
- **Duplication:** Runs gate_record pre-push AND gate_receipt validate as separate independent checks with their own label/bypass logic. Under Addendum 6, 'gate_record check --mode pre-push' consolidates both into one evaluator call. The bypass label parsing embedded in the shell script is a second independent rule set for bypass semantics that must not exist separately.
- **Decision rationale:** Listed in Addendum 6 section 3 inventory as 'hook scripts under scripts/hooks/**'. Under the new model this hook must become a thin shell: call 'gate_record check --mode pre-push --base origin/main --head HEAD' and forward the exit code as allow/deny. All label-parsing, bypass logic, and receipt validation belong in the evaluator. The script must not keep its own label vocabulary or bypass conditions.


### `check-gate-before-pr.sh` — REWRITE
- **Location:** `scripts/hooks/check-gate-before-pr.sh`
- **CLI/trigger:** PreToolUse on Bash matching 'gh pr create*' (wired in .claude/settings.json)
- **Purpose:** PreToolUse harness hook (Claude) that intercepts 'gh pr create' Bash commands and validates ADR-042 gate readiness before allowing PR creation.
- **Current behavior:** Parses the Bash command, extracts --body/--body-file, and extracts --label flags from the gh pr create command itself. Reads bypass labels. Requires the PR body to be present (denies without it). With broad bypass present, runs 'gate_record pr-ready' as a soft check but still allows. Without bypass, checks that the PR body contains Closes/Fixes/Resolves #N (independent regex check), runs 'gate_record pr-ready', discovers the branch gate record, then runs 'gate_receipt validate --pr-body'. Has its own embedded Python for label extraction from the gh CLI args, which is an independent copy of PR body and label parsing logic.
- **Duplication:** Contains independent issue-closure keyword checking (its own regex) that duplicates issue_link.check logic in the evaluator. Contains independent PR body and label extraction that duplicates scistudio_pr_create.py and gate_receipt logic. Calls gate_record pr-ready AND gate_receipt validate separately. Under Addendum 6 all of this collapses into a single evaluator call.
- **Decision rationale:** Listed in Addendum 6 section 3 inventory. Must become a thin wrapper: extract the PR body file path from the gh command, then call 'gate_record check --mode pre-pr --pr-body-file <path> --base origin/main --head HEAD'. The evaluator handles all label, bypass, issue-closure, receipt, and scope validation. The embedded Python issue-closure regex and label extraction in the shell script must be removed.


### `check-ci-after-pr.sh` — KEEP
- **Location:** `scripts/hooks/check-ci-after-pr.sh`
- **CLI/trigger:** PostToolUse on Bash matching 'gh pr create*' (wired in .claude/settings.json)
- **Purpose:** PostToolUse harness hook (Claude) that fires after 'gh pr create' to remind the agent to watch CI.
- **Current behavior:** Extracts the PR URL from stdout of gh pr create. Prints a mandatory multi-step reminder message telling the agent to wait for CI, run 'gh pr checks N --watch', and not report the PR as done until CI passes. Does not block; is advisory output only.
- **Duplication:** Not a check — it is a post-creation reminder. The evaluator's finalize command handles PR provenance, but reminding the agent to watch CI is a separate runtime-harness concern.
- **Decision rationale:** Not listed in ADR/addendum as something to rewrite or deprecate. It does not duplicate evaluator work — it is a runtime reminder behavior that fills the gap between PR creation and CI completion. Under the new model the agent should call 'gate_record finalize --pr <url>' after PR creation; this hook can be updated to remind of that specific step instead of generic CI-watching instructions, but the hook itself is a useful harness layer that prevents the agent from reporting done before CI runs.


### `check-agent-template.sh` — MODIFY
- **Location:** `scripts/hooks/check-agent-template.sh`
- **CLI/trigger:** PreToolUse on Agent (wired in both .claude/settings.json and .codex/hooks.json)
- **Purpose:** PreToolUse harness hook (Claude and Codex) on Agent dispatch that warns (does NOT block) when a non-Explore agent dispatch is missing the [DISPATCH-TEMPLATE-V1: <role>] marker.
- **Current behavior:** Reads the Agent dispatch payload, checks the subagent_type and prompt fields. Skips Explore/plan/empty types. For any other subagent type, checks if the prompt contains '[DISPATCH-TEMPLATE-V1:'. Emits a warning to stderr if missing, but exits 0 (non-blocking). Hard-codes ADR-035/036 cascade template role names in the warning message.
- **Duplication:** Not a quality-gate check — it is a dispatch-hygiene reminder for cascade agent prompts. This kind of dispatch protocol enforcement is not part of the evaluator's responsibility in Addendum 6.
- **Decision rationale:** Not in Addendum 6 inventory. The ADR-035/036 cascade is long past; the warning message still cites that specific cascade, making the hook feel stale. However the underlying concept — ensuring agent dispatch prompts follow the project template convention — remains valid. Should be updated to remove the ADR-035/036 specific mention and generalize the warning to the current agent-dispatch templates in docs/ai-developer/templates/. The non-blocking warn-only behavior is appropriate. Does not need to be wired into the evaluator.


### `remind-checklist-discipline.sh` — MODIFY
- **Location:** `scripts/hooks/remind-checklist-discipline.sh`
- **CLI/trigger:** PostToolUse on Edit|Write|MultiEdit|NotebookEdit (for adr-*-checklist.md paths) and TaskCreate|TaskUpdate|TaskStop|TodoWrite (wired in both .claude/settings.json and .codex/hooks.json)
- **Purpose:** PostToolUse harness hook (Claude and Codex) that fires after checklist-file edits or task-management tool calls and prints a multi-step checklist discipline reminder to the agent.
- **Current behavior:** Parses tool name and file_path from hook stdin. Fires for Edit/Write/MultiEdit/NotebookEdit when the path matches *adr-*-checklist.md*. Also fires for any TaskCreate/TaskUpdate/TaskStop/TodoWrite call. When triggered, prints a 6-step discipline reminder covering: memory re-reading, artifact link verification, scope discipline, stale marker sweeps, inline-list consistency, and agent-manager skill compliance. The checklist reminder hard-codes specific memory file names from the user's Claude memory.
- **Duplication:** Not a quality-gate check. This is a workflow-discipline reminder specific to the multi-agent dispatch protocol. It references specific user memory files that are external to the repo governance model.
- **Decision rationale:** Not in Addendum 6 inventory. The hook is valid as a runtime reminder for dispatch-coordination discipline but the memory file references (feedback_skill_rules_are_protocol_not_guidance.md, etc.) are user-specific memory paths that do not belong in the committed codebase hook. Should be updated to reference canonical repo docs (docs/ai-developer/) instead of user memory paths. The broad TaskCreate/TaskUpdate/TaskStop/TodoWrite trigger is also very wide — consider scoping it to prevent reminder noise on every task update.


### `run_python_module.py` — KEEP
- **Location:** `scripts/hooks/run_python_module.py`
- **CLI/trigger:** Called as the 'entry' by pre-commit for scistudio-governance-mod-guard, scistudio-weakened-ci-check, scistudio-gate-record-pre-commit, and scistudio-gate-record-commit-msg hooks
- **Purpose:** Helper utility used by .pre-commit-config.yaml hooks to invoke Python governance modules from the repo's src layout without pip install.
- **Current behavior:** Inserts repo_root/src into sys.path, then uses runpy.run_module to execute the given Python module as __main__. Allows pre-commit to run governance modules without requiring the package to be installed.
- **Duplication:** Pure infrastructure plumbing, not a check itself.
- **Decision rationale:** Not in Addendum 6 inventory as something to replace. It is a necessary bridge between pre-commit's 'language: system' hooks and the src-layout Python package. Under the new model, pre-commit hooks will still need a way to invoke the evaluator; this utility remains useful or can be replaced with 'uv run python -m ...' if the project adopts uv for pre-commit too.


### `scistudio-governance-mod-guard (pre-commit)` — REWRITE
- **Location:** `.pre-commit-config.yaml, entry: scistudio.qa.governance.mod_guard`
- **CLI/trigger:** pre-commit stage (git commit), triggered when staged files match ^(AGENTS.md|.workflow/|.github/workflows/|.pre-commit-config.yaml|docs/adr/ADR-042.md|docs/specs/adr-042-*.md|src/scistudio/qa/|tests/qa/)
- **Purpose:** Git pre-commit hook that blocks commits to governance-critical files (AGENTS.md, .workflow/**, .github/workflows/**, .pre-commit-config.yaml, ADR-042 docs, src/scistudio/qa/**) without explicit approval.
- **Current behavior:** Calls mod_guard.check() with --staged flag. Reads SCISTUDIO_GOVERNANCE_CHANGE_APPROVED env and SCISTUDIO_GATE_BYPASS_LABELS env. Blocks the commit with ERROR findings for any staged governance file change that lacks explicit approval. Has its own protected-pattern list (PROTECTED_PATTERNS tuple) and its own bypass-label validation that is independent of the evaluator.
- **Duplication:** Under Addendum 6, governance_mod_guard becomes an evaluator-owned calculator (section 7.5: 'governance_mod_guard called by the evaluator'). The independent bypass-label vocabulary in mod_guard.py duplicates human_bypass_guard.VALID_OVERRIDE_LABELS and the evaluator's bypass semantics. The protected-path list is a separate authority from the evaluator's path-allowlist logic.
- **Decision rationale:** Listed in Addendum 6 section 3 inventory and section 7.5. Must become an evaluator-owned calculator with no independent rule set. The pre-commit hook entry point should call 'gate_record check --mode pre-commit' (or a thin evaluator call) rather than invoking mod_guard directly. The protected-pattern list and bypass-label set must be owned by the evaluator, not duplicated in this module.


### `scistudio-weakened-ci-check (pre-commit)` — REWRITE
- **Location:** `.pre-commit-config.yaml, entry: scistudio.qa.governance.weakened_ci_check`
- **CLI/trigger:** pre-commit stage (git commit), triggered when staged files match ^(.github/workflows/|.pre-commit-config.yaml|pyproject.toml)
- **Purpose:** Git pre-commit hook that detects diffs that weaken CI or pre-commit by removing required check tokens or adding failure-suppression patterns to .github/workflows/*.yml, .pre-commit-config.yaml, and pyproject.toml.
- **Current behavior:** Calls weakened_ci_check.verify_no_weakening() with --staged flag. Parses the staged diff, checks for removed tokens (ruff, mypy, pytest, etc.) and added weakening patterns (continue-on-error, always-false conditionals, --no-verify, exit 0 suppressors). Has its own REQUIRED_REMOVAL_TOKENS and ADDED_WEAKENING_PATTERNS lists and its own bypass-label handling via human_bypass_guard.VALID_OVERRIDE_LABELS.
- **Duplication:** Under Addendum 6, weakened_ci_check becomes an evaluator-owned calculator (section 7.5). The bypass-label validation and the token/pattern lists are maintained independently of the evaluator. The CI workflow runs this check again in guard orchestration, creating two separate running points of the same logic.
- **Decision rationale:** Listed in Addendum 6 section 3 inventory and section 7.5. Must become an evaluator-owned calculator. The pre-commit hook should delegate to the evaluator rather than calling weakened_ci_check directly. The REQUIRED_REMOVAL_TOKENS list and ADDED_WEAKENING_PATTERNS are the evaluator's responsibility; the module may remain as the implementation but must receive its inputs from the evaluator rather than maintaining its own rule vocabulary.


### `scistudio-gate-record-pre-commit (pre-commit)` — REWRITE
- **Location:** `.pre-commit-config.yaml, entry: scistudio.qa.governance.gate_record pre-commit`
- **CLI/trigger:** pre-commit stage (git commit), triggered when staged files match ^(src/|packages/|frontend/|web/|tests/|.workflow/records/|.github/workflows/|.pre-commit-config.yaml|scripts/hooks/)
- **Purpose:** Git pre-commit hook that validates staged files against the committed gate record — checks that staged paths are within the record's declared scope (include/exclude patterns) and that the record is in a valid state for committing.
- **Current behavior:** Calls gate_record validation.check_pre_commit(). Reads bypass labels from env. Discovers the gate record for the current branch. Validates that the staged file set does not exceed declared scope. Has its own bypass handling.
- **Duplication:** The scope-checking logic at commit time duplicates what the evaluator will do during 'gate_record check' reconciliation. The bypass handling is another independent copy of the bypass-label vocabulary. The pre-commit scope check and the evaluator reconciliation check are checking the same invariant (staged files within allowed scope) at different stages independently.
- **Decision rationale:** Listed in Addendum 6 section 3 inventory. Under the new model, 'gate_record check --mode pre-commit' is the evaluator's pre-commit entry point. This hook's scope-check logic must be delegated to the evaluator. The hook entry point in .pre-commit-config.yaml can remain as an invocation stub, but the validation logic must live inside the evaluator, not as independent check_pre_commit() code.


### `scistudio-gate-record-commit-msg (pre-commit)` — REWRITE
- **Location:** `.pre-commit-config.yaml, entry: scistudio.qa.governance.gate_record commit-msg, stages: [commit-msg]`
- **CLI/trigger:** commit-msg stage (git commit), no path filter — runs on every commit
- **Purpose:** Git commit-msg stage hook that validates commit message trailers — checks for required Gate-Record: and Assisted-by: trailer presence on AI-authored commits.
- **Current behavior:** Calls gate_record validation.check_commit_msg() with the message file path. Reads bypass labels. Validates that the commit message contains required trailers (Gate-Record: path, Assisted-by: runtime) for AI-authored commits. Allows bypass via label env.
- **Duplication:** This is the only hook that checks commit message trailers at commit time. The CI workflow-gate checks AI evidence markers (Gate-Record: and Assisted-by: in commit messages) but does so after the fact. The pre-commit hook catches missing trailers before the commit lands. There is some downstream CI duplication (CI re-checks for these markers), but the pre-commit check has a different purpose (prevent the commit from being created) vs CI (validate after the fact).
- **Decision rationale:** Listed in Addendum 6 section 3 inventory. The hook entry point should remain in .pre-commit-config.yaml as the commit-msg gate. However the commit-trailer validation logic (what trailers are required, what format, what bypass is allowed) must be owned by the evaluator and called as 'gate_record check --mode commit-msg <message-file>' rather than as a separate check_commit_msg() function with its own bypass-label logic.


### `pre-commit standard hooks (trailing-whitespace, end-of-file-fixer, check-yaml, check-json, check-added-large-files, check-merge-conflict, detect-private-key)` — KEEP
- **Location:** `.pre-commit-config.yaml, repo: https://github.com/pre-commit/pre-commit-hooks`
- **CLI/trigger:** pre-commit stage (git commit)
- **Purpose:** Standard file-hygiene pre-commit hooks: whitespace normalization, YAML/JSON syntax, large file detection, merge conflict marker detection, private key scanning.
- **Current behavior:** Industry-standard hooks from pre-commit/pre-commit-hooks. Run unconditionally (no path filter). Non-governance hygiene checks.
- **Duplication:** detect-private-key and check-merge-conflict tokens appear in weakened_ci_check.REQUIRED_REMOVAL_TOKENS, meaning weakened_ci_check tracks whether these hooks are removed from the config. That is a meta-duplication (checking that the check exists) not a duplication of the check itself.
- **Decision rationale:** Standard repository hygiene. Not in Addendum 6 rewrite scope. The evaluator's CI-parity check (section 7.5) acknowledges that 'detect-private-key' and 'check-merge-conflict' are in weakened_ci_check's removal token list — these hooks should remain exactly as they are.


### `ruff + ruff-format (pre-commit)` — MODIFY
- **Location:** `.pre-commit-config.yaml, repo: https://github.com/astral-sh/ruff-pre-commit, rev: v0.11.4`
- **CLI/trigger:** pre-commit stage (git commit)
- **Purpose:** Python lint and format enforcement at commit time.
- **Current behavior:** Runs 'ruff --fix' and 'ruff-format' on all staged Python files. Uses a pinned version v0.11.4.
- **Duplication:** CI also runs 'ruff check .' and 'ruff format --check .'. Addendum 6 section 7.10 explicitly addresses this: pre-commit pinned versions must match CI-resolved versions. There is currently a version-drift risk between the pinned v0.11.4 in pre-commit and whatever CI resolves. Under the new model the evaluator enforces version parity — this is the core 'green locally, red CI' problem.
- **Decision rationale:** Keep as pre-commit hook but address the version-parity requirement from Addendum 6 section 7.10. The evaluator's 'gate_record check' must run ruff at the same resolved version CI uses. The pre-commit pin should be derived from the same source CI uses (e.g. uv.lock or the CI workflow's setup-uv pinning) rather than a hand-maintained revision in .pre-commit-config.yaml.


### `mypy (pre-commit)` — MODIFY
- **Location:** `.pre-commit-config.yaml, repo: https://github.com/pre-commit/mirrors-mypy, rev: v1.15.0`
- **CLI/trigger:** pre-commit stage (git commit)
- **Purpose:** Python type checking at commit time.
- **Current behavior:** Runs mypy with --ignore-missing-imports on changed Python files. additional_dependencies is empty, meaning mypy may miss stub packages.
- **Duplication:** CI runs 'mypy src/scistudio/ --ignore-missing-imports' on Python 3.13. Pre-commit uses mirrors-mypy v1.15.0 which may not be the same version. Same version-drift risk as ruff. The empty additional_dependencies also means pre-commit mypy runs with fewer stubs than CI.
- **Decision rationale:** Keep as pre-commit hook but address version-parity per Addendum 6 section 7.10. The evaluator should validate that the pre-commit mypy version matches the CI mypy version and that additional_dependencies includes whatever stubs CI uses.


### `commitizen (pre-commit, commit-msg stage)` — KEEP
- **Location:** `.pre-commit-config.yaml, repo: https://github.com/commitizen-tools/commitizen, rev: v4.4.1`
- **CLI/trigger:** commit-msg stage (git commit)
- **Purpose:** Commit message format enforcement (conventional commits) at commit-msg stage.
- **Current behavior:** Validates commit message format against commitizen rules (conventional commits: feat/fix/chore/etc.). Runs in commit-msg stage.
- **Duplication:** The scistudio-gate-record-commit-msg hook (same stage) checks AI-specific trailers. These are complementary, not duplicating each other: commitizen checks format/type, gate-record-commit-msg checks AI provenance trailers.
- **Decision rationale:** Not in Addendum 6 scope. Conventional commit format enforcement is a repository quality standard independent of the AI governance model. Keep as-is.


### `scistudio_pr_create.py (PR wrapper)` — REWRITE
- **Location:** `scripts/scistudio_pr_create.py`
- **CLI/trigger:** Manual invocation: 'python scripts/scistudio_pr_create.py --title ... --body ...'. Also referenced in AGENTS.md/rules as the required path for AI-authored PRs per ADR-042 Addendum 5.
- **Purpose:** Wrapper around 'gh pr create' that runs gate_record ci and gate_receipt validate locally before opening the PR, to surface CI-equivalent findings before the PR exists.
- **Current behavior:** Extracts --body/--body-file and --base from argv. Discovers the branch's gate record. Calls gate_receipt validate (separate module) and gate_record ci (separate command) sequentially with the PR body. Filters out three PR-state guards (core_change_guard, pr_merge_guard, human_bypass_guard) as 'CI-authoritative' since labels cannot exist before the PR. Prints filtered findings and blocks if any non-PR-state findings remain. Then calls gh pr create. Has its own find_gate_record() and extract_body()/extract_base() logic that partially duplicates logic in check-gate-before-pr.sh.
- **Duplication:** Under Addendum 6, both gate_receipt validate and gate_record ci are replaced by 'gate_record check --mode pre-pr' via the single evaluator. The wrapper's find_gate_record(), _is_pr_state_finding(), and filter_findings() logic, plus the sequential receipt+ci call pattern, are exactly the duplication the new model eliminates. The 'filtered guard' filtering logic (PR-state guards cannot be validated pre-PR) must become an evaluator-internal distinction, not caller-side filtering.
- **Decision rationale:** Listed in Addendum 6 section 3 inventory ('PR wrapper behavior in scripts/scistudio_pr_create.py'). Under the new model this wrapper becomes a thin shell: call 'gate_record check --mode pre-pr --pr-body-file <path>' and if exit 0, call 'gh pr create'. The wrapper's gate-discovery, receipt-validation, ci-validation, and finding-filtering logic all move into the evaluator. The SCISTUDIO_SKIP_PREFLIGHT escape hatch and the --dry-run mode should be preserved in the rewrite.


### `workflow-gate.yml / Verify Workflow Compliance (CI)` — REWRITE
- **Location:** `.github/workflows/workflow-gate.yml`
- **CLI/trigger:** GitHub Actions: pull_request events (opened, synchronize, reopened, edited, ready_for_review, labeled, unlabeled) and workflow_dispatch
- **Purpose:** GitHub Actions CI workflow that validates committed gate records, runs human-bypass guard, and runs full guard orchestration (docs_landing, issue_link, mod_guard, weakened_ci_check, core_change_guard, pr_merge_guard, human_bypass_guard, sentrux_gate) for every PR.
- **Current behavior:** Step 1 ('Validate committed gate records'): discovers changed gate records in the diff, collects PR metadata (labels, label events, review events, actor permissions) via gh api calls, runs human_bypass_guard.check(), then calls 'gate_record ci --gate-record ... --base ... --head HEAD --pr-body ... --pr-label ...' for each record. Has umbrella-PR logic to prefer manager-task-kind records. Step 2 ('Run ADR-042 guard orchestration'): separately imports and calls individual guard modules (core_change_guard, docs_landing, human_bypass_guard, issue_link, mod_guard, pr_merge_guard, sentrux_gate, weakened_ci_check) directly. Sentrux is advisory (::warning:: only). The CI workflow therefore calls both gate_record ci (step 1) AND individual guard modules (step 2) — meaning many guards run twice.
- **Duplication:** Step 1 calls gate_record ci which internally calls guards. Step 2 then calls the same guards directly again. This is a two-step redundancy: human_bypass_guard runs in step 1 (inside gate_record ci), and then again in step 2. mod_guard and weakened_ci_check also run in both places. Under Addendum 6, CI should call 'gate_record check --mode ci' ONCE and that single evaluator call runs all guards as owned calculators.
- **Decision rationale:** Listed in Addendum 6 section 3 inventory and section 7.5 (the evaluator's CI mode). The workflow must be rewritten to a single evaluator invocation: 'gate_record check --mode ci --gate-record <record> --base origin/$BASE_REF --head HEAD --pr-body <body> [--pr-label ...]'. The PR metadata collection (label events, actor permissions) that is currently done in inline shell Python should be consumed by the evaluator's CI mode. The two-step guard duplication must be eliminated. The umbrella-PR manager-record selection logic should move into the evaluator.


### Extra findings — hooks

```text
WORKTREE WRITE GUARD OVER-BLOCKING ANALYSIS

Current blocking logic (in worktree_write_guard.py check_paths()):
1. Resolves repo root via git rev-parse --show-toplevel from the payload cwd.
2. Blocks if current branch is main/master/HEAD.
3. Blocks if no gate record matches current branch.
4. For each target path: resolves to absolute, calls .relative_to(root). If ValueError (path is outside the repo), emits "write target is outside the assigned worktree".
5. If the gate record has include patterns: blocks if the path does not match them.
6. Blocks if the path matches exclude patterns.

Why it over-blocks:
- Step 4 catches ALL writes outside the repo — memory directories (~/.claude/memory/), temp directories (/tmp/), log files outside the workspace, IDE temp files. The code correctly identifies these as "outside the assigned worktree" but the INTENT was only to block writes to the WRONG repo worktree, not to block writes to non-repo paths entirely.
- Step 3 blocks before even reaching path checks if there is no gate record, meaning a new task with no gate record yet cannot write ANYTHING — including writing the gate record file itself. The gate record lives at .workflow/records/*.json which should always be allowed.
- Step 5 blocks writes inside the repo that are outside declared scope at write time, which is a pre-emptive scope guard. This is distinct from the over-blocking bug but is also undesirable under Addendum 6 (scope enforcement belongs in reconciliation, not at write time).
- The guard is currently DISABLED in .claude/settings.json (owner removed it, per memory note: "owner 指示禁用，已从本地 .claude/settings.json PreToolUse 移除"). It remains active in .codex/hooks.json.

MINIMAL REVISED LOGIC (proposed):

The ONLY purpose of the hook in the new model: block an AI agent from writing to the MAIN REPO WORKING TREE when that agent's session is supposed to be in an assigned worktree.

Proposed algorithm (replaces check_paths() entirely):

1. If target path is outside any git repository (resolved path is not under any git root reachable from cwd): ALLOW unconditionally. The guard has no jurisdiction over non-repo paths.
2. Identify the git root of the target path (git rev-parse --show-toplevel from target path's parent, not from cwd).
3. Get the list of worktrees: git worktree list --porcelain from the main repo root.
4. Identify whether the AGENT'S OWN WORKING DIRECTORY is in a non-main worktree (i.e., the agent's cwd belongs to a worktree whose path is NOT the main worktree path from the worktree list).
5. If the agent is in a non-main worktree AND the target path resolves to the MAIN worktree's root: BLOCK with message "agent in worktree <X> must not write to main working tree <main-path>".
6. In all other cases: ALLOW.

What this removes:
- The gate record requirement (step 3 above): removed entirely.
- The include/exclude scope enforcement (steps 5-6 above): removed entirely; belongs in evaluator reconciliation.
- The outside-repo blocking (step 4 above): inverted to ALLOW instead of BLOCK.
- The main-branch check: removed as a standalone block; it becomes a consequence of the worktree identity check (the main branch is in the main worktree, and if the agent is in an assigned worktree, writing to the main worktree is blocked regardless of what branch is checked out there).

This makes the hook minimal: it only blocks the specific cross-worktree write scenario the owner intended to prevent.

---

RECOMMENDED COMPLETE HOOK LIST FOR THE NEW SYSTEM

The following is the complete recommended list of hooks the system needs after the Addendum 6 rewrite:

PRE-COMMIT HOOKS (.pre-commit-config.yaml):

- scistudio-gate-record-pre-commit (pre-commit stage): REWRITE. Thin entry point calling 'gate_record check --mode pre-commit --staged'. All scope and bypass logic delegated to evaluator.

- scistudio-gate-record-commit-msg (commit-msg stage): REWRITE. Thin entry point calling 'gate_record check --mode commit-msg <message-file>'. All trailer and bypass logic delegated to evaluator.

- scistudio-governance-mod-guard (pre-commit stage): REWRITE. Thin entry point calling 'gate_record check --mode pre-commit --check governance_mod_guard' or collapsed into the single pre-commit evaluator call. Protected-path list and bypass logic must be evaluator-owned. NOTE: Addendum 6 section 3 says to delete the old module and replace; the pre-commit hook entry point can stay as an evaluator invocation alias.

- scistudio-weakened-ci-check (pre-commit stage): REWRITE. Same pattern — thin entry point calling the evaluator's weakened-CI check, not the standalone module.

- trailing-whitespace, end-of-file-fixer, check-yaml, check-json, check-added-large-files, check-merge-conflict, detect-private-key (standard hooks): KEEP unchanged.

- ruff + ruff-format (pre-commit stage): KEEP but pin version to match CI per Addendum 6 section 7.10 version-parity requirement. Evaluator must validate version agreement.

- mypy (pre-commit stage): KEEP but address version-parity and additional_dependencies alignment with CI per section 7.10.

- commitizen (commit-msg stage): KEEP unchanged.

HARNESS HOOKS (.claude/settings.json and .codex/hooks.json):

- PreToolUse / Bash (git push*) — check-gate-before-push.sh: REWRITE as thin shell calling 'gate_record check --mode pre-push --base origin/main --head HEAD'. Wire in both .claude/settings.json and .codex/hooks.json.

- PreToolUse / Bash (gh pr create*) — check-gate-before-pr.sh: REWRITE as thin shell extracting PR body file and calling 'gate_record check --mode pre-pr --pr-body-file <path>'. Wire in both settings files.

- PostToolUse / Bash (gh pr create*) — check-ci-after-pr.sh: KEEP but update the reminder to mention 'gate_record finalize --pr <url>' as the required post-creation step, in addition to CI-watch guidance.

- PreToolUse / Edit|Write|MultiEdit|NotebookEdit|apply_patch — check-worktree-write-guard.sh: REWRITE with minimal revised logic above (only block cross-worktree main-repo writes). Re-enable in .claude/settings.json (it was disabled due to over-blocking which this rewrite fixes).

- PreToolUse / Agent — check-agent-template.sh: MODIFY to remove ADR-035/036 specific references and generalize to current dispatch template paths. Keep non-blocking warn-only behavior.

- PostToolUse / Edit|Write|MultiEdit|NotebookEdit + TaskCreate|TaskUpdate|TaskStop|TodoWrite — remind-checklist-discipline.sh: MODIFY to remove user-specific memory file path references. Replace with canonical docs/ai-developer/ references. Consider narrowing the TaskCreate/etc. trigger to reduce noise.

CI HOOKS (.github/workflows/):

- workflow-gate.yml: REWRITE to call a single evaluator invocation 'gate_record check --mode ci' instead of the current two-step (gate_record ci + direct guard orchestration) pattern. PR metadata collection should be passed to the evaluator, not pre-processed in inline shell Python.

HOOKS NOT NEEDED IN NEW SYSTEM (to DELETE or NOT ADD):

- No hook should keep independent bypass-label vocabularies. The evaluator owns label semantics.
- No hook should keep independent protected-path lists. The evaluator owns path rules.
- No hook should call gate_receipt validate separately — receipts are folded into ledger events.
- No hook should call gate_record ci separate from the unified check command (ci mode is one evaluator mode, not a separately invoked tool).

---

COMPONENTS LISTED IN ADR-042 ADDENDUM 6 SECTION 3 INVENTORY (all must be rewritten or confirmed replaced):

- gate_record schema, CLI, validation, stage handling, I/O, and workflow orchestration: EXISTS, needs rewrite per new ledger/evaluator design.
- gate_receipt behavior: EXISTS (src/scistudio/qa/governance/gate_receipt.py), must be folded into ledger check/reconcile events and DELETED as independent module.
- workflow_gate: EXISTS (src/scistudio/qa/governance/workflow_gate.py), must become evaluator-internal, not a standalone module.
- docs_landing: EXISTS (src/scistudio/qa/governance/docs_landing.py), must become evaluator-owned calculator.
- issue_link: EXISTS (src/scistudio/qa/governance/issue_link.py), must become evaluator-owned calculator.
- persona_policy: EXISTS (src/scistudio/qa/governance/persona_policy.py), must become evaluator-owned calculator.
- core_change_guard: EXISTS (src/scistudio/qa/governance/core_change_guard.py), must become evaluator-owned calculator.
- human_bypass_guard: EXISTS (src/scistudio/qa/governance/human_bypass_guard.py), must become evaluator-owned calculator.
- pr_merge_guard: EXISTS (src/scistudio/qa/governance/pr_merge_guard.py), must become evaluator-owned calculator.
- mod_guard: EXISTS at src/scistudio/qa/governance/mod_guard.py, must become evaluator-owned calculator.
- weakened_ci_check: EXISTS at src/scistudio/qa/governance/weakened_ci_check.py, must become evaluator-owned calculator.
- sentrux_gate: EXISTS (src/scistudio/qa/governance/sentrux_gate.py), must become evaluator-owned calculator (currently advisory).
- test_engineer_scope_guard: EXISTS (src/scistudio/qa/governance/test_engineer_scope_guard.py), must become evaluator-owned calculator.
- worktree_write_guard: EXISTS, must become evaluator-owned calculator with minimal revised logic.
- hook scripts under scripts/hooks/**: ALL EXIST, all must be rewritten as described above.
- PR wrapper (scripts/scistudio_pr_create.py): EXISTS, must be rewritten as thin evaluator caller.

LABEL VOCABULARY MIGRATION NOTE:
The Addendum 6 section 3 inventory explicitly requires migrating from 'admin-approved:ai-override' to 'admin-approved:bypass'. Multiple files currently use 'admin-approved:ai-override': check-gate-before-push.sh (line 56), check-gate-before-pr.sh (line 63), workflow-gate.yml (lines 59, 163, 311), and mod_guard.py / weakened_ci_check.py (via human_bypass_guard.VALID_OVERRIDE_LABELS). The evaluator rewrite must update all of these references simultaneously to avoid a split vocabulary state."
```

## Area: ci

| Component | Decision | Dup-check? | In ADR/add6 |
|---|---|---|---|
| `ci.yml / Lint & Format (lint job)` | **keep** | False | True |
| `ci.yml / Type Check (typecheck job)` | **modify** | False | True |
| `ci.yml / Architecture Tests (architecture job)` | **keep** | False | True |
| `ci.yml / Full Audit (full-audit job)` | **keep** | False | True |
| `ci.yml / Test matrix (test job)` | **keep** | False | True |
| `ci.yml / Import Contracts (import-lint job)` | **keep** | False | True |
| `ci.yml / Frontend (frontend job)` | **keep** | False | True |
| `ci.yml / Wheel Release Smoke (wheel-release-smoke job)` | **keep** | False | True |
| `workflow-gate.yml / Verify Workflow Compliance (workflow-gate job) — step: Validate committed gate records` | **rewrite** | True | True |
| `workflow-gate.yml / Verify Workflow Compliance (workflow-gate job) — step: Run ADR-042 guard orchestration` | **rewrite** | True | True |
| `workflow-gate.yml job-level trigger and skip logic` | **keep** | False | True |
| `semantic-dup-scan.yml / Semantic duplication ratchet (semantic-dup-check job)` | **keep** | False | True |
| `ai-review.yml / Codex PR Review (ai-review job)` | **keep** | False | True |
| `workflow-gate.yml — label vocabulary: admin-approved:ai-override` | **modify** | False | True |
| `workflow-gate.yml — temp file coupling (.workflow-pr-metadata.json)` | **deprecate** | True | False |
| `workflow-gate.yml — run_ci() / check_pr() call inside gate_record ci (workflow.py + validation.py)` | **rewrite** | True | True |


### `ci.yml / Lint & Format (lint job)` — KEEP
- **Location:** `.github/workflows/ci.yml (lines 25-39)`
- **CLI/trigger:** ruff check . && ruff format --check .
- **Purpose:** Run ruff check and ruff format --check on the full repository on push/PR to main or track/** branches.
- **Current behavior:** Installs ruff via `uv pip install --system ruff`, then runs `ruff check .` and `ruff format --check .`. Python 3.13 only. No governance involvement; purely a quality check. Runs unconditionally on any diff.
- **Decision rationale:** This job is a pure repository quality check — it is the CI source of truth that `gate_record check` must mirror locally per Section 7.10. It does not duplicate evaluator logic; the evaluator reads this job's command to derive the local Tier 1/Tier 2 obligation. No change to the CI job itself is needed. The only migration touch is that Addendum 6 requires the evaluator to read the pinned ruff version from this job (uv resolves from pyproject.toml) and reproduce that version locally — no YAML change required for that. The job is listed explicitly in ADR-042 Addendum 6, Section 7.5 CI snapshot table.


### `ci.yml / Type Check (typecheck job)` — MODIFY
- **Location:** `.github/workflows/ci.yml (lines 41-61)`
- **CLI/trigger:** mypy src/scistudio/ --ignore-missing-imports
- **Purpose:** Run mypy on src/scistudio/ to enforce static types, skipping when the directory does not yet exist.
- **Current behavior:** Installs `.[dev]` via `uv pip install --system -e .`, then runs `mypy src/scistudio/ --ignore-missing-imports` on Python 3.13. Guard: directory-existence check before running. No governance involvement.
- **Decision rationale:** The job is listed in Addendum 6 Section 7.5 and is the CI source-of-truth for the type-check command. No structural change needed. One environment-parity concern raised by Addendum 6 Section 7.10: this job uses `pip install -e .` (editable install), but AGENTS.md and Section 7.10 prohibit editable installs that pollute the shared environment. For CI the shared environment is the runner's system interpreter, which is discarded after the job, so the intent of the ban (protecting worktrees) does not apply here. However, the evaluator's local `gate_record check` must NOT reproduce this as `pip install -e .`; it must use `PYTHONPATH=src` or an isolated venv per Section 7.10. Document this asymmetry in the evaluator; no CI YAML change required.


### `ci.yml / Architecture Tests (architecture job)` — KEEP
- **Location:** `.github/workflows/ci.yml (lines 62-77)`
- **CLI/trigger:** pytest tests/architecture/ -v --no-cov
- **Purpose:** Run import-boundary and architecture contract tests under tests/architecture/ to catch cross-module violations.
- **Current behavior:** Installs `.[dev]`, then runs `pytest tests/architecture/ -v --no-cov`. No governance involvement. No path filters — runs on every PR diff.
- **Decision rationale:** Listed explicitly in Addendum 6 Section 7.5 CI snapshot table. Pure quality job; the evaluator reads this job to derive the local Tier 1 architecture-test obligation. No duplication of governance logic. No CI YAML change needed; the evaluator must mirror `pytest tests/architecture/ -v --no-cov` for Tier 1/Tier 2 when architecture-governed or import-boundary surfaces are affected.


### `ci.yml / Full Audit (full-audit job)` — KEEP
- **Location:** `.github/workflows/ci.yml (lines 78-103)`
- **CLI/trigger:** PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output .audit/full-audit.json
- **Purpose:** Run the full ADR-042 audit sweep (full_audit) against the repository and upload the JSON report as an artifact.
- **Current behavior:** Installs `.[dev]`, runs `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output .audit/full-audit.json`, uploads `.audit/full-audit.json`. Uses `PYTHONPATH=src` — not an editable install. Upload is unconditional (`if: always()`). No governance involvement; the job is the CI reference for audit evidence.
- **Decision rationale:** Listed in Addendum 6 Section 7.5 CI snapshot table. The evaluator must mirror `PYTHONPATH=src python -m scistudio.qa.audit.full_audit ...` for all tiers of AI-authored work. The `PYTHONPATH=src` pattern is exactly what Addendum 6 Section 7.10 designates as the CI-equivalent importable environment that local `gate_record check` should reproduce. No CI YAML change needed.


### `ci.yml / Test matrix (test job)` — KEEP
- **Location:** `.github/workflows/ci.yml (lines 105-146)`
- **CLI/trigger:** timeout 600 pytest -n auto --timeout=60 --timeout-method=thread (3.13); same with --no-cov (3.11)
- **Purpose:** Run the full pytest suite on Python 3.11 and 3.13 with parallel execution, per-test timeouts, and a shell-level timeout guard.
- **Current behavior:** Installs `.[dev]` + `pytest-timeout`. Python 3.13: `timeout 600 pytest -n auto --timeout=60 --timeout-method=thread`. Python 3.11: same but `--no-cov`. Handles exit code 5 (no tests collected) as non-fatal. No governance involvement.
- **Decision rationale:** Listed in Addendum 6 Section 7.5 CI snapshot table. The evaluator must use the same `pytest -n auto --timeout=60 --timeout-method=thread` command when Python implementation or test surfaces are affected. The 3.11/3.13 matrix is the CI authority; local `gate_record check` may run only 3.13 for speed but must document it satisfies the matrix obligation (or must run both). No CI YAML change needed.


### `ci.yml / Import Contracts (import-lint job)` — KEEP
- **Location:** `.github/workflows/ci.yml (lines 147-167)`
- **CLI/trigger:** lint-imports (conditional on src/scistudio/ existing)
- **Purpose:** Run lint-imports to enforce import boundary contracts defined in pyproject.toml, skipping when src/scistudio does not exist.
- **Current behavior:** Installs `.[dev]`, runs `lint-imports` if `src/scistudio` exists. No path filters — runs unconditionally.
- **Decision rationale:** Listed in Addendum 6 Section 7.5 CI snapshot table. The evaluator must mirror `lint-imports` when Python source, architecture, package-boundary, or import-contract surfaces are in the observed diff (Tier 1 always; Tier 2/3 surface-gated). No CI YAML change needed.


### `ci.yml / Frontend (frontend job)` — KEEP
- **Location:** `.github/workflows/ci.yml (lines 180-223)`
- **CLI/trigger:** npm ci && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build + dist freshness find
- **Purpose:** Run ESLint, Prettier format check, TypeScript compilation, Vitest unit tests, production build, and a dist freshness check for the frontend.
- **Current behavior:** Uses Node 20 + npm cache on frontend/package-lock.json. Runs: `npm ci`, `npm run lint`, `npm run format:check`, `npm run typecheck`, `npm test`, `npm run build`. Dist freshness check uses `find frontend/src -newer frontend/dist/index.html`. No path filters — runs on every PR. No governance involvement.
- **Decision rationale:** Listed in Addendum 6 Section 7.5 CI snapshot table as the canonical frontend CI command surface. The evaluator must mirror all six npm commands plus the dist freshness check when frontend source/config/test/dist surfaces appear in the observed diff. No CI YAML change needed.


### `ci.yml / Wheel Release Smoke (wheel-release-smoke job)` — KEEP
- **Location:** `.github/workflows/ci.yml (lines 225-303)`
- **CLI/trigger:** python -m build --wheel + zipfile inspection + venv install + FastAPI TestClient GET /
- **Purpose:** Build the full wheel (frontend + Python), verify the SPA bundle is present inside the wheel, install it into a fresh venv, and smoke-test the GUI root endpoint.
- **Current behavior:** Builds frontend, copies dist into the Python static-assets directory, builds the wheel with SCISTUDIO_REQUIRE_FRONTEND_BUILD=1, inspects the wheel contents via zipfile, installs the wheel in a fresh venv, and makes a FastAPI TestClient GET / request. Uploads wheel only on tag pushes. No governance involvement.
- **Decision rationale:** Listed in Addendum 6 Section 7.5 CI snapshot table. The evaluator must include the wheel release smoke job in Tier 1 and when packaging/release/static-bundle surfaces are affected. The local equivalent must reproduce the build + install + smoke-test sequence. No CI YAML change needed.


### `workflow-gate.yml / Verify Workflow Compliance (workflow-gate job) — step: Validate committed gate records` — REWRITE
- **Location:** `.github/workflows/workflow-gate.yml (lines 1-231, step beginning at line 27)`
- **CLI/trigger:** PYTHONPATH=src python -m scistudio.qa.governance.gate_record ci --gate-record <record> --base ... --pr-body ... --pr-label ...
- **Purpose:** On every PR event: discover changed gate records, assemble PR metadata (labels, label-actor provenance, review events via gh API), run human_bypass_guard, determine bypass status, then call `gate_record ci` for every non-bypassed gate record to validate the committed ledger against PR state.
- **Current behavior:** Runs an inline Python script that: (1) lists changed .workflow/records/*.json files from the git diff; (2) fetches PR label events and reviews via `gh api` to build provenance; (3) calls `scistudio.qa.governance.human_bypass_guard.check()` directly; (4) decides whether to skip gate-record validation (human-authored or ai-override labels); (5) if not skipped, filters to a single manager-record for umbrella PRs; (6) calls `PYTHONPATH=src python -m scistudio.qa.governance.gate_record ci --gate-record <record> --base ... --head ... --pr-body ... --pr-label ...` for each record. The `gate_record ci` command routes to `run_ci()` in workflow.py, which calls `check_pr()` (validation.py) plus `issue_link`, `docs_landing`, `mod_guard`, `weakened_ci_check` guards. The label vocabulary includes the old `admin-approved:ai-override` alongside the newer labels.
- **Duplication:** Inline PR-metadata assembly, human_bypass_guard call, bypass routing, and umbrella manager-record selection logic are duplicated in both CI steps and should move into the evaluator.
- **Decision rationale:** Three duplication problems exist under Addendum 6. First, the inline Python in the step independently implements PR-metadata assembly, label-provenance fetching, human_bypass_guard invocation, and bypass routing — all logic that the new shared evaluator is supposed to own (Section 7.5: 'tools must receive their inputs from the evaluator and must not keep independent rule sets'). After the rewrite, CI should call a single entry point — `gate_record check --mode ci` — and the evaluator internally handles PR-metadata assembly, bypass semantics, and guard orchestration. Second, the umbrella-PR manager-record selection logic is duplicated verbatim in the next step (guard orchestration step). Third, the step references `admin-approved:ai-override` (the old label vocabulary); Addendum 6 Section 7.5 and Section 3 migration notes specify migrating to `admin-approved:bypass`. This step also inherently requires PR-state (PR body, PR labels, label provenance via gh API) so it is correctly PR-only; that characteristic should be preserved as the evaluator's `--mode ci` mode. Post-rewrite target: one shell call to `gate_record check --mode ci --base ... --head ...` with the evaluator reading PR context from the GITHUB_* environment variables directly.


### `workflow-gate.yml / Verify Workflow Compliance (workflow-gate job) — step: Run ADR-042 guard orchestration` — REWRITE
- **Location:** `.github/workflows/workflow-gate.yml (lines 234-385)`
- **CLI/trigger:** Inline Python calling governance module functions directly (no single CLI entry point)
- **Purpose:** After gate-record validation: run the full set of blocking guards (human_bypass_guard, core_change_guard, mod_guard/governance-mod, pr_merge_guard, weakened_ci_check) and surface Sentrux findings as advisory warnings.
- **Current behavior:** Another large inline Python block that: (1) calls `human_bypass_guard.check()` again (second call in same job); (2) decides bypass/skip independently again; (3) assembles the `pr` dict from an on-disk `.workflow-pr-metadata.json` file written by the previous step; (4) calls `issue_link.check()`, `docs_landing.check()`, `sentrux_gate.verify_free_tier_claims()` (advisory), `core_change_guard.check()` (twice — once for core paths, once reusing core_change_guard for mod patterns), `pr_merge_guard.check()`, `mod_guard.check()`, `weakened_ci_check.verify_no_weakening()` all as independent module calls; (5) collects and prints all reports; (6) exits 1 if any blocks_merge. Each guard module is called directly with its own inputs derived from the step's environment rather than through any unified evaluator.
- **Duplication:** human_bypass_guard called twice (once per step), core_change_guard called twice in one step, issue_link and docs_landing checks run here AND inside run_ci() called by the previous step — four distinct duplication instances in a single job.
- **Decision rationale:** This step is the primary source of the duplication problem that Addendum 6 is designed to eliminate. Each guard is called as an independent authority with its own input derivation and bypass logic, exactly the anti-pattern Section 7.5 prohibits: 'Individual tools may calculate findings, but they must receive their inputs from the evaluator and must not keep independent rule sets.' Specific duplications: (a) `human_bypass_guard` is called twice in the same job (once per step); (b) `core_change_guard` is called twice in this single step — once for core paths and once reusing the same function with `mod_guard.PROTECTED_PATTERNS` for the governance-mod check, which conflates two separate guard responsibilities; (c) the PR-metadata assembly and bypass routing repeat the same logic as the previous step; (d) `issue_link.check()` and `docs_landing.check()` are both run here AND inside `run_ci()` (which is called from the previous step via `gate_record ci`), meaning these checks run twice per PR. After the rewrite, this entire step should disappear. The evaluator's CI mode (`gate_record check --mode ci`) must run all guards internally, deduplicate calls, and report a single consolidated result. Sentrux advisory status must also be owned by the evaluator (it already has the semantics right — advisory only). The `.workflow-pr-metadata.json` temp file coupling between steps is fragile and should also be eliminated by giving the evaluator direct access to the GitHub API context.


### `workflow-gate.yml job-level trigger and skip logic` — KEEP
- **Location:** `.github/workflows/workflow-gate.yml (lines 1-13)`
- **CLI/trigger:** on: pull_request + workflow_dispatch; if: not dependabot
- **Purpose:** Trigger the workflow on all PR events (opened, synchronize, reopened, edited, ready_for_review, labeled, unlabeled) and skip for dependabot PRs.
- **Current behavior:** Triggers on `pull_request` event types listed above plus `workflow_dispatch`. Skips the entire job when the PR author is dependabot[bot] via `if: github.event.pull_request.user.login != 'dependabot[bot]'`. Does NOT trigger on push to main — this workflow is PR-only.
- **Decision rationale:** The trigger set is correct: the evaluator's CI mode inherently requires a PR to exist (it reads PR body, labels, and label provenance). The `labeled`/`unlabeled` events are essential because admin labels can change after the PR is opened, and re-running on those events ensures label-provenance checks are current. Keeping the dependabot skip is appropriate since dependabot PRs have no gate record. This job-level configuration is orthogonal to the evaluator rewrite and should be preserved. Not explicitly listed as a named component in Addendum 6, but it governs the `workflow-gate.yml / Verify Workflow Compliance` job that IS listed.


### `semantic-dup-scan.yml / Semantic duplication ratchet (semantic-dup-check job)` — KEEP
- **Location:** `.github/workflows/semantic-dup-scan.yml (lines 1-75)`
- **CLI/trigger:** python scripts/semantic_dup_scan.py --check docs/audit/baselines/semantic-dup-baseline.json --out semantic-dup-report.md --json-out semantic-dup-current.json
- **Purpose:** Run the semantic-duplication ratchet check to detect new semantic-duplicate clusters in Python source files, gated by path filters. Weekly scheduled run catches regressions that slipped through PR path filters.
- **Current behavior:** Triggers on PR to main/track/** when paths match `src/scistudio/**/*.py`, `scripts/semantic_dup_scan.py`, baseline JSON, the addendum file, or the workflow itself. Also runs on a weekly Monday cron schedule. Installs fastembed + numpy only (no scistudio install). Runs `python scripts/semantic_dup_scan.py --check docs/audit/baselines/semantic-dup-baseline.json --out semantic-dup-report.md --json-out semantic-dup-current.json`. Uploads report artifacts. No governance involvement.
- **Decision rationale:** Listed explicitly in Addendum 6 Section 7.5 CI snapshot table. The evaluator must run this command when the workflow path filters match the observed diff. The path-filter logic is the evaluator's responsibility to mirror locally. The weekly cron schedule and artifact upload are CI-only concerns (no local equivalent needed). The fastembed model cache step is a CI performance optimization with no local analog needed. No CI YAML change needed.


### `ai-review.yml / Codex PR Review (ai-review job)` — KEEP
- **Location:** `.github/workflows/ai-review.yml (lines 1-51)`
- **CLI/trigger:** python scripts/ai_review.py (via Codex CLI); continue-on-error: true
- **Purpose:** Run an AI review of each PR by invoking the Codex CLI (via scripts/ai_review.py) and posting review comments. Runs on PR opened and synchronize events only.
- **Current behavior:** Installs Codex CLI via npm (`@openai/codex`), configures Codex auth from a secret, then runs `python scripts/ai_review.py` with GITHUB_TOKEN, PR_NUMBER, and REPO_NAME env vars. Has `continue-on-error: true` — does NOT block CI. Requires a CODEX_AUTH_JSON secret. Explicitly listed in Addendum 6 Section 7.5 as 'Not a local readiness command; it is PR-only review automation and does not become a local gate_record check obligation.'
- **Decision rationale:** Addendum 6 Section 7.5 explicitly classifies this as PR-only review automation that is not a local `gate_record check` obligation. The `continue-on-error: true` flag correctly prevents it from blocking merges on AI review failures. The evaluator must not attempt to mirror this locally. The job is correctly isolated from the governance evaluation path. No change needed.


### `workflow-gate.yml — label vocabulary: admin-approved:ai-override` — MODIFY
- **Location:** `.github/workflows/workflow-gate.yml (lines 55-58, 162-163)`
- **CLI/trigger:** label string 'admin-approved:ai-override' in valid_override set and bypass routing
- **Purpose:** The string 'admin-approved:ai-override' appears in the valid_override set and is tested for in bypass routing inside the workflow-gate job.
- **Current behavior:** The set `valid_override` in the PR-metadata assembly block includes `admin-approved:ai-override` alongside `human-authored`, `admin-approved:core-change`, and `admin-approved:merge`. The bypass routing then explicitly checks `HUMAN_BYPASS_STATUS == 'admin-ai-override'` to skip gate-record validation. This is the OLD label vocabulary from before Addendum 5/6.
- **Decision rationale:** Addendum 6 Section 7.5 defines the current label vocabulary as: `admin-approved:bypass` (AI gate workflow bypass), `admin-approved:core-change`, `admin-approved:merge`. Section 3 migration notes explicitly list 'existing workflow label vocabulary, including migration from any older admin-approved:ai-override references to admin-approved:bypass' as a required rewrite item. This label reference must be updated to `admin-approved:bypass` as part of the workflow-gate rewrite. Not a standalone component but a field within the workflow-gate job; flagged separately because it is a concrete migration action item.


### `workflow-gate.yml — temp file coupling (.workflow-pr-metadata.json)` — DEPRECATE
- **Location:** `.github/workflows/workflow-gate.yml (lines 155-158, 303-307)`
- **CLI/trigger:** Path('.workflow-pr-metadata.json').write_text / .read_text in two separate run: steps
- **Purpose:** The gate-record validation step writes PR metadata to `.workflow-pr-metadata.json` on the runner filesystem; the guard orchestration step reads it back to avoid re-fetching label provenance.
- **Current behavior:** `Path('.workflow-pr-metadata.json').write_text(os.environ['PR_METADATA'], ...)` in the first step; `pr_metadata_path.read_text(...)` in the second step as a fallback when the file exists. This is an implicit coupling between two separate `run:` steps in the same job through an untracked runner filesystem file.
- **Duplication:** Exists only to bridge two steps that both independently duplicate PR-metadata assembly; goes away when the evaluator owns that assembly.
- **Decision rationale:** This pattern exists only because the two steps independently duplicate PR-metadata assembly and bypass logic. Once the evaluator owns both (as a single `gate_record check --mode ci` call), neither step needs to pass data to the other through a temp file. The temp file should be eliminated as a byproduct of collapsing the two steps into one evaluator call. Not a component in Addendum 6's inventory; flagged as a coupling artifact that disappears naturally during the rewrite.


### `workflow-gate.yml — run_ci() / check_pr() call inside gate_record ci (workflow.py + validation.py)` — REWRITE
- **Location:** `src/scistudio/qa/governance/gate_record/workflow.py (run_ci); src/scistudio/qa/governance/gate_record/validation.py (check_pr, validate_gate_record)`
- **CLI/trigger:** python -m scistudio.qa.governance.gate_record ci --gate-record <record> ...
- **Purpose:** The current `gate_record ci` subcommand entry point: runs blocking guards (issue_link, docs_landing, mod_guard, weakened_ci_check) and gate-record schema/scope validation against the PR diff.
- **Current behavior:** workflow.py::run_ci() calls check_pr() (which calls validate_gate_record()), plus issue_link.check(), docs_landing.check(), mod_guard.check(), weakened_ci_check.verify_no_weakening(). validate_gate_record() also internally calls test_engineer_scope_guard via dynamic import. The result is aggregated into a single AuditReport. This is the closest thing to a shared evaluator that currently exists — but it is incomplete: it does not run core_change_guard, human_bypass_guard, pr_merge_guard, or sentrux_gate; those are still in the workflow-gate.yml inline script. check_pr() does not run checks (ruff/mypy/pytest/etc.); it only validates the committed record claims against the diff.
- **Duplication:** Runs issue_link and docs_landing checks that are also called independently in the workflow-gate.yml guard orchestration step, causing these checks to execute twice per PR.
- **Decision rationale:** This is the seed of the new evaluator. Under Addendum 6, `gate_record check --mode ci` becomes the single entry point that subsumes ALL of: (a) the current run_ci()/check_pr() logic; (b) the inline guard calls in the workflow-gate.yml guard orchestration step; (c) the PR-metadata assembly and bypass logic. The rewrite should evolve run_ci() into the full evaluator CI mode, adding core_change_guard, human_bypass_guard, pr_merge_guard, sentrux_gate (advisory), task-kind/tier-selected check inference, observed-diff fingerprinting, ledger event recording, and the new --mode local/pre-push/pre-pr/ci dispatch. The current 'ci' subcommand in cli.py (which routes to run_ci()) should become the new `check --mode ci` as specified in Addendum 6 Section 7.5.


### Extra findings — ci

```text
1. PYTHON VERSION MISMATCH: workflow-gate.yml uses Python 3.11 (line 20) while ci.yml uses Python 3.13 for all jobs. Since the evaluator (workflow_gate) must call the same governance modules as the local `gate_record check`, there is a version inconsistency risk. Addendum 6 Section 7.10 makes CI the source-of-truth for tool versions. The rewrite should align workflow-gate.yml to Python 3.13 unless a specific compatibility reason for 3.11 is documented.

2. MISSING GUARD IN run_ci(): The current `workflow.py::run_ci()` (called by `gate_record ci`) does NOT call `core_change_guard`, `human_bypass_guard`, `pr_merge_guard`, or `sentrux_gate` — those are only in the workflow-gate.yml inline script. This means if an agent calls `gate_record ci` directly (e.g., locally or from a wrapper), it gets a different, weaker check set than what workflow-gate.yml enforces in CI. This is precisely the 'local/CI discrepancy' Addendum 6 is designed to eliminate. The new evaluator's `--mode ci` must be identical to what the CI job enforces.

3. WORKTREE_WRITE_GUARD NOT IN CI: `scistudio.qa.governance.worktree_write_guard` is listed in Addendum 6 Section 3's required inventory and Section 7.5's guard table, but it does not appear in any CI workflow. It is a pre-tool hook only (enforced locally). This is correct per its design, but the inventory should note it is local-only and does not need a CI job; the evaluator should document this boundary explicitly.

4. PERSONA_POLICY NOT IN CI: `scistudio.qa.governance.persona_policy` is listed in Addendum 6 Section 7.5 ('persona_policy.check called by the evaluator') but does not appear in any CI workflow job or in the current run_ci() / validate_gate_record() path (cli.py imports it but it is not wired into the CI flow). The evaluator rewrite must wire persona_policy into the CI mode.

5. TEST_ENGINEER_SCOPE_GUARD IS DYNAMICALLY IMPORTED: In validation.py lines 104-157, test_engineer_scope_guard is invoked via dynamic import from within validate_gate_record(). This already treats it as an evaluator-called calculator, which is the Addendum 6 pattern. The rewrite should make this pattern explicit for ALL guards (not just this one) and move the dynamic import to a static evaluator guard registry.

6. GATE_RECEIPT.PY NOT IN CI: `scistudio.qa.governance.gate_receipt` is listed in Addendum 6 Section 3's required inventory. It does not appear in any CI workflow. It exists as a local-only artifact (generating local receipt files). Under Addendum 6 its behavior is to be folded into ledger check/reconcile events; CI does not need to call it separately, but the migration must explicitly delete or redirect it.

7. PATH FILTER ABSENT ON workflow-gate.yml: ci.yml has commented-out path filters on the frontend job. workflow-gate.yml has NO path filters at all — it runs on every PR event regardless of which files changed. Under Addendum 6 the evaluator should use the observed git diff to determine which checks are mandatory (tier selection). The absence of CI path filters on the gate job is not a bug (the gate must run on every AI-authored PR) but the evaluator's tier logic must handle the case where the diff is docs-only differently from a core-code change.

8. GH API PERMISSION CHECK IN CI: The workflow-gate.yml guard orchestration step calls `gh api repos/{repo}/collaborators/{actor}/permission` for each label event and review. This provenance check is inherently PR-only and CI-only (requires GitHub API access and GH_TOKEN). The evaluator's CI mode must encapsulate this call internally. The local mode of `gate_record check` cannot verify label provenance (no PR exists) and must record it as a pre-PR gap, as specified in Addendum 6 Section 7.5.
```

## Area: tests

| Component | Decision | Dup-check? | In ADR/add6 |
|---|---|---|---|
| `test_gate_record.py` | **rewrite** | True | True |
| `test_gate_receipt.py` | **deprecate** | True | True |
| `test_gate_record_ci.py` | **rewrite** | False | True |
| `test_gate_record_hooks.py` | **rewrite** | False | True |
| `governance/test_gate_record_package.py` | **rewrite** | False | False |
| `test_core_change_guard.py` | **keep** | False | True |
| `test_governance_mod_guard.py` | **modify** | False | True |
| `test_human_bypass_guard.py` | **modify** | False | True |
| `test_pr_merge_guard.py` | **keep** | False | True |
| `test_worktree_write_guard.py` | **modify** | False | True |
| `test_test_engineer_scope_guard.py` | **keep** | False | True |
| `test_sentrux_gate.py` | **keep** | False | True |
| `test_governance_weakened_ci_check.py` | **modify** | False | True |
| `test_docs_landing.py` | **keep** | False | True |
| `test_issue_link.py` | **keep** | False | True |
| `test_persona_policy.py` | **modify** | False | True |
| `test_governance_paths.py` | **modify** | False | False |
| `test_architecture_drift.py` | **keep** | False | False |
| `test_audit_closure.py` | **keep** | False | False |
| `test_audit_doc_drift.py` | **keep** | False | False |
| `test_audit_fact_drift.py` | **keep** | False | False |
| `test_audit_frontmatter_lint.py` | **modify** | False | False |
| `test_audit_full_audit.py` | **keep** | False | False |
| `test_audit_semantic_dup.py` | **keep** | False | False |
| `test_audit_signature_contracts.py` | **keep** | False | False |
| `test_audit_signature_drift.py` | **keep** | False | False |
| `test_audit_vulture.py` | **keep** | False | False |
| `test_schemas_report.py` | **keep** | False | False |
| `test_schemas_maintainers.py` | **keep** | False | False |
| `test_schemas_signatures.py` | **keep** | False | False |
| `test_generate_facts_cli.py` | **keep** | False | False |
| `test_griffe_facts.py` | **keep** | False | False |
| `test_scistudio_pr_create.py` | **rewrite** | True | True |
| `test_semantic_dup_scan.py` | **keep** | False | False |


### `test_gate_record.py` — REWRITE
- **Location:** `tests/qa/test_gate_record.py`
- **Purpose:** Tests for the current gate_record module: GateRecord Pydantic schema validation, old CLI command surface (start/plan/amend/docs/check/sentrux/finalize), pre-commit/commit-msg/pre-push/pr-ready check functions, bypass label semantics, scope/governance-touch rules, and _is_test_path/_is_governance_path helpers.
- **Current behavior:** Asserts the OLD six-stage linear schema (CANONICAL_STAGE_ORDER), the old command names ('start', 'plan', 'amend', 'docs', 'check', 'sentrux', 'finalize', 'pre-commit', 'commit-msg', 'pre-push', 'pr-ready', 'ci'), the split-receipt model (sentrux, full_audit, check_results fields as top-level GateRecord fields), and bypass labels including 'admin-approved:ai-override' (renamed to 'admin-approved:bypass' in Addendum 6). Scope rules (_is_governance_path, governance_touch), vitest test-path recognition, and the pr-ready stage carve-out also live here. The end-to-end workflow test drives the old CLI command sequence rather than the new init/plan/amend/check/finalize commands from Addendum 6.
- **Duplication:** The old top-level sentrux/full_audit fields duplicate ledger check_events; the old stage sequence duplicates the new ledger lifecycle concerns; the 'ai-override' label vocabulary is being renamed to 'bypass'.
- **Decision rationale:** This file encodes the old receipt-and-stage model. The schema fields (stages, sentrux, full_audit, check_results as top-level GateRecord attributes), CLI command names (start vs init, docs vs amend, sentrux as a standalone subcommand), and bypass label vocabulary all change under Addendum 6. The governance-path classification, vitest test-path logic, and governance_touch rules encode still-valid protection behavior and must be ported. The stage carve-out logic (pre-PR does not require commit_and_submit_pr done) reflects the correct pre-PR/post-PR distinction from Addendum 6 finalize and must be ported as ledger reconciliation tests. About 40% of the file encodes old duplication semantics; about 60% encodes valid guard behavior that must survive as ledger-reconciliation and path-classification tests.


### `test_gate_receipt.py` — DEPRECATE
- **Location:** `tests/qa/test_gate_receipt.py`
- **Purpose:** Tests for the separate gate_receipt module: CandidateFingerprint, receipt_paths, infer_required_checks, and validate_receipt. Covers stale-fingerprint detection and missing-check detection using a local .workflow/local/gate-receipts/ directory.
- **Current behavior:** Asserts the OLD split-receipt architecture where a separate local receipt file (not the committed gate record) carries the candidate fingerprint and check evidence. Tests that validate_receipt reads the receipt and compares diff_sha256 against the live candidate. infer_required_checks tests combine gate_record.required_checks with diff-surface detection. This is precisely the per-candidate local receipt design that Addendum 6 Section 1.1 identifies as creating duplicate/conflicting candidate state.
- **Duplication:** The entire file tests the local receipt mechanism that is being replaced by ledger check_events and reconcile_events. The diff fingerprinting logic belongs in the evaluator, not in a separate receipt module.
- **Decision rationale:** Addendum 6 Section 3 step 8 explicitly says 'Replace receipt files with ledger check and reconcile events.' The entire gate_receipt module and its test file encode the split-receipt duplication anti-pattern that Addendum 6 eliminates. No part of this test file tests behavior that survives the rewrite; the stale-fingerprint and missing-check concepts survive but are re-expressed as ledger reconcile_events in gate_record check/finalize. This file should be deleted alongside the gate_receipt source module.


### `test_gate_record_ci.py` — REWRITE
- **Location:** `tests/qa/test_gate_record_ci.py`
- **Purpose:** CI-mode gate_record validation: PR body must close every gate issue, all stages must be done in CI mode, scope validation, amendment-based scope expansion, implementation-change requires test file, changed_test_paths must appear in diff, docs-task without impl does not require tests, sentrux optional/skip/fail semantics, override label vocabulary, guard reports as hard-fail inputs, test_engineer_scope_guard invocation.
- **Current behavior:** Tests validate_gate_record and check_pr using the old GateRecord schema. The 'sentrux is opt-in and missing/skipped does not block' rule (Addendum 3) is captured here. The guard-report aggregation test (guard_reports=[...] parameter on validate_gate_record) tests the exact integration point Addendum 6 Section 7.5 requires: guards feed the evaluator. The test_engineer scope guard invocation test validates that the evaluator calls the guard module. These are the most important behavioral contracts to preserve.
- **Duplication:** No receipt duplication here. The sentrux advisory semantics and guard aggregation tests encode still-valid evaluator contracts.
- **Decision rationale:** Most of the behavioral rules here survive into the Addendum 6 model: issue closure, stage completion in CI mode, scope enforcement, test evidence requirements, sentrux advisory semantics, guard aggregation, and test_engineer_scope_guard invocation. These must all be ported as ledger-reconciliation tests against the new evaluator. However the fixture format (old GateRecord schema fields), the old stage enum values, and the old validate_gate_record function signature are all replaced. The rewrite replaces old-schema assertions with ledger-reconcile assertions while preserving the same behavioral rules.


### `test_gate_record_hooks.py` — REWRITE
- **Location:** `tests/qa/test_gate_record_hooks.py`
- **Purpose:** Structural checks that hook wrappers, pre-commit config, and CI workflow all call gate_record CLI and not legacy gate.py/active. Verifies hook content: bypass label strings, receipt body extraction, workflow guard orchestration.
- **Current behavior:** File-content assertion tests: verifies hook scripts contain 'scistudio.qa.governance.gate_record', do not contain '.workflow/gate.py', include correct bypass label strings, and that the CI workflow invokes human_bypass_guard, core_change_guard, pr_merge_guard. Also asserts legacy files (.workflow/gate.py, .workflow/active) are absent. The hook bypass-label list includes 'admin-approved:ai-override' which Addendum 6 renames to 'admin-approved:bypass'.
- **Duplication:** No receipt duplication. Tests are structural wiring verification, not check logic duplication.
- **Decision rationale:** The structural assertions about hook wiring are still-valid behavior to preserve: hooks must call the evaluator entry point, must not call old entry points, must support the correct bypass-label vocabulary, and the CI workflow must invoke the evaluator guards. These tests must be updated to reflect: (1) new CLI command names (init/plan/amend/check/finalize instead of start/plan/amend/docs/check/sentrux/finalize), (2) renamed bypass label 'admin-approved:ai-override' to 'admin-approved:bypass', (3) guards now called via evaluator rather than directly in the workflow YAML. The legacy-file-removed tests remain valid. The receipt-body extraction test (test_pr_hook_validates_receipt_against_real_pr_body) tests pr-body plumbing that is preserved in the finalize command.


### `governance/test_gate_record_package.py` — REWRITE
- **Location:** `tests/qa/governance/test_gate_record_package.py`
- **Purpose:** Refactor-guard tests for the gate_record sub-package: every public and private name from the pre-refactor single-file module is still importable; CLI subcommands are byte-identical; self-hosting end-to-end smoke (start->plan->docs->check->sentrux->finalize); package layout files are present.
- **Current behavior:** Exhaustively asserts the current module surface: specific subcommand list (start, plan, amend, docs, check, sentrux, finalize, pre-commit, commit-msg, ci, pre-push, pr-ready), public and private function/class names. The end-to-end smoke test uses the OLD CLI command sequence. The package-layout assertion names specific sub-modules (paths, models, io, validation, stages, cli).
- **Duplication:** No receipt duplication. This is a surface-contract test.
- **Decision rationale:** The package surface will change substantially: old subcommands (start, docs, sentrux) are replaced by (init, amend, check); internal modules may be restructured for the ledger/evaluator design. The public-name lists will change because GateRecord, GateStage, CANONICAL_STAGE_ORDER, SentruxEvidence, CheckEvidence, and related types are all being redesigned. The self-hosting smoke must be rewritten against the new init/plan/amend/check/finalize command sequence. The principle being tested (all public names importable, CLI surface stable, end-to-end flow works) is valid and should be preserved as a rewritten package-surface-stability test.


### `test_core_change_guard.py` — KEEP
- **Location:** `tests/qa/test_core_change_guard.py`
- **Purpose:** Tests for core_change_guard.check: passes for unprotected files, blocks protected core paths without admin-approved:core-change label, accepts the label with authorized provenance, rejects misspelled labels, accepts APPROVED review from maintainer.
- **Current behavior:** Tests the standalone check() function. Under Addendum 6, core_change_guard becomes an 'evaluator-owned calculator' (Section 7.5) rather than an independent authority. The check() function interface is expected to survive as an internal evaluator call, receiving its inputs from the evaluator. The protected-path concept, label requirement, and provenance verification are all valid behaviors listed in Addendum 6 Section 7.5 and 7.8.
- **Duplication:** No receipt duplication. This tests a distinct protection rule.
- **Decision rationale:** All five test cases encode protected-path authorization behavior that Addendum 6 explicitly preserves (Section 7.8: protected core paths require admin-approved:core-change label, CI verifies actor permission). The guard becomes evaluator-owned but its detection logic is unchanged. These tests can remain as-is if the check() function signature is preserved, or need minor updates if the guard's interface changes to receive evaluator-supplied inputs.


### `test_governance_mod_guard.py` — MODIFY
- **Location:** `tests/qa/test_governance_mod_guard.py`
- **Purpose:** Tests for mod_guard.check on real git repos: blocks protected staged changes (CI config, pre-commit config, gate-record schema) without approval, allows gate record JSON files, allows explicit flag/env override, accepts/rejects bypass labels.
- **Current behavior:** Uses subprocess git init + staged file patterns to test the mod_guard. The bypass label tested includes 'admin-approved:ai-override'. Under Addendum 6 this label is renamed to 'admin-approved:bypass'. The APPROVAL_ENV environment variable bypass is a local-only mechanism; the new model centralizes bypass to evaluator-verified labels. The gate-record JSON carve-out (.workflow/records/**) is valid behavior that must be preserved.
- **Duplication:** No receipt duplication. This tests a distinct governance protection rule.
- **Decision rationale:** The core protection behavior (blocking non-record .workflow/** changes, CI config changes, etc.) is valid and must survive. The bypass label in test_mod_guard_accepts_adr042_local_bypass_labels needs updating from 'admin-approved:ai-override' to 'admin-approved:bypass'. The APPROVAL_ENV-based bypass is a local mechanism that may not survive if the rewrite centralizes bypass handling to the evaluator; that test should be reviewed when the new evaluator is designed. The gate-record-only carve-out test must definitely survive.


### `test_human_bypass_guard.py` — MODIFY
- **Location:** `tests/qa/test_human_bypass_guard.py`
- **Purpose:** Tests for human_bypass_guard.check: valid override label vocabulary, human-authored label skips AI gates, requires authorized provenance, human-authored with AI evidence requires admin-approved:ai-override, invalid labels rejected.
- **Current behavior:** VALID_OVERRIDE_LABELS is tested to include 'admin-approved:ai-override'. Under Addendum 6 Section 7.5, this label is renamed to 'admin-approved:bypass'. The test test_valid_override_label_vocabulary_is_exact will need updating. The fundamental behavior (human-authored label skips AI gates, label provenance must be authorized, AI evidence with human-authored requires an additional admin override) is all valid and preserved in Addendum 6.
- **Duplication:** No receipt duplication. Tests a distinct bypass provenance rule.
- **Decision rationale:** The label name change from 'admin-approved:ai-override' to 'admin-approved:bypass' (Addendum 6 Section 7.5 and Section 3 migration note about 'migration from any older admin-approved:ai-override references') requires updating test_valid_override_label_vocabulary_is_exact and test_ai_override_allows_ai_evidence_when_authorized. All other behavioral tests are valid and should be preserved. The guard becomes evaluator-owned but the check() interface likely survives.


### `test_pr_merge_guard.py` — KEEP
- **Location:** `tests/qa/test_pr_merge_guard.py`
- **Purpose:** Tests for pr_merge_guard.check: blocks AI merge without admin-approved:merge, accepts authorized merge label, rejects unauthorized provenance, ignores non-merge intent.
- **Current behavior:** All four test cases encode the 'AI agents may not merge PRs' rule from Addendum 6 Section 7.8. The label vocabulary and provenance requirement are unchanged between the current implementation and Addendum 6.
- **Duplication:** No receipt duplication. Tests a distinct merge-authorization rule.
- **Decision rationale:** All test cases encode behavior explicitly listed in Addendum 6 Section 7.8 and Section 7.5. The guard becomes evaluator-owned but the detection logic is unchanged. No label renaming affects this guard. These tests can remain as-is.


### `test_worktree_write_guard.py` — MODIFY
- **Location:** `tests/qa/test_worktree_write_guard.py`
- **Purpose:** Tests for worktree_write_guard: blocks writing to main branch, blocks paths outside worktree and outside gate scope, blocks exclude-pattern paths via hook payload.
- **Current behavior:** Tests check_paths and check_hook_payload using the old GateRecord JSON schema (six-stage list, scope.include/exclude). The scope.include/exclude model survives in Addendum 6 (declared_scope.include/declared_scope.exclude in the ledger). The worktree/main-branch protection rules are explicitly preserved in Addendum 6 Section 7.5.
- **Duplication:** No receipt duplication. Tests a distinct write-guard protection rule.
- **Decision rationale:** The protection behavior (blocking main branch writes, blocking out-of-scope paths, blocking exclude-pattern paths) is valid and must survive. The fixture helper _record() uses old GateRecord schema fields (six named stages, scope as a top-level dict). When the ledger schema changes the fixture must be updated. The behavioral assertions can remain unchanged if the guard's interface is preserved.


### `test_test_engineer_scope_guard.py` — KEEP
- **Location:** `tests/qa/test_test_engineer_scope_guard.py`
- **Purpose:** Tests for test_engineer_scope_guard.check: not applied to other personas, allows backend tests and validation evidence, allows explicit frontend test patterns, blocks frontend product code, blocks production runtime/build surfaces, blocks governance paths, allows explicitly scoped QA tooling, reports attempted amendment for non-QA production paths, normalizes absolute paths.
- **Current behavior:** All test cases encode valid production-code boundary rules for the test_engineer persona. These rules are explicitly preserved in Addendum 6 Section 7.5 ('test_engineer_scope_guard called by the evaluator') and Section 7.7.2 (persona matrix). The guard interface (check with persona, changed_files, scope_includes, repo_root) is stable.
- **Duplication:** No receipt duplication. Tests a distinct persona scope-enforcement rule.
- **Decision rationale:** All test cases encode behavior explicitly listed in Addendum 6. The guard becomes evaluator-owned but the detection logic is unchanged. No schema or label changes affect this guard. These tests can remain as-is.


### `test_sentrux_gate.py` — KEEP
- **Location:** `tests/qa/test_sentrux_gate.py`
- **Purpose:** Tests for sentrux_gate: parse_sentrux_result from MCP and CLI JSON shapes, verify_free_tier_claims for source changes, docs-only N/A, pro-only claims rejection, unchecked-rule completion rejection, architecture/ADR files cannot be N/A'd.
- **Current behavior:** Tests the sentrux evidence parsing and verification logic. Under Addendum 6 Section 7.5, sentrux_gate is called by the evaluator 'as advisory or blocking according to the active ADR-042 addendum semantics'. The current tests capture the Addendum 3 semantics (advisory, not mandatory block for missing evidence). These semantics are referenced in the Addendum 6 Section 7.5 sentrux row. The test for verify_free_tier_claims returning blocks_merge=True for source changes when evidence=None (test_verify_free_tier_rejects_missing_evidence_for_source_change) appears to conflict with the Addendum 3 opt-in semantics captured in test_gate_record_ci.py. This inconsistency exists in the current codebase and should be clarified during the rewrite.
- **Duplication:** No receipt duplication. Tests a distinct sentrux evidence verification rule.
- **Decision rationale:** The sentrux evidence parsing and claim-verification rules encode valid behavior that Addendum 6 preserves. The applicability detection (sentrux_applies_to_changes) and the docs-only N/A rules are all valid. The inconsistency between verify_free_tier blocking and Addendum 3 opt-in semantics should be resolved in the rewrite rather than requiring deletion of these tests. The guards become evaluator-owned but their detection interfaces survive.


### `test_governance_weakened_ci_check.py` — MODIFY
- **Location:** `tests/qa/test_governance_weakened_ci_check.py`
- **Purpose:** Tests for weakened_ci_check.verify_no_weakening: detects removed required checks (ruff), detects added continue-on-error, passes unrelated diffs, detects removed pre-commit hooks, accepts/rejects bypass labels.
- **Current behavior:** Tests the weakened-CI detection guard on real git repos. The bypass label tested includes 'admin-approved:ai-override'. Under Addendum 6 this label is renamed to 'admin-approved:bypass'. The core behavioral rules (detect CI weakening patterns) are explicitly preserved in Addendum 6 Section 7.5 ('weakened_ci_check called by the evaluator').
- **Duplication:** No receipt duplication. Tests a distinct CI-weakening detection rule.
- **Decision rationale:** The weakened-CI detection logic is valid and must survive. Only the bypass label in test_weakened_ci_accepts_adr042_local_bypass_label needs updating from 'admin-approved:ai-override' to 'admin-approved:bypass'. The detection tests themselves (removed ruff, added continue-on-error, removed pre-commit hook) are valid and should remain.


### `test_docs_landing.py` — KEEP
- **Location:** `tests/qa/test_docs_landing.py`
- **Purpose:** Tests for docs_landing.check: blocks governed changes without docs/changelog/checklist evidence, accepts paths and N/A rationales, does not require evidence for unrelated docs-only change.
- **Current behavior:** Tests the standalone docs_landing.check() function with the docs_landing dict structure. Under Addendum 6 this becomes an evaluator-called calculator. The behavioral rules (governed changes require docs landing, unrelated docs do not) are explicitly preserved in Addendum 6 Section 7.5 ('docs_landing.check called by the evaluator').
- **Duplication:** No receipt duplication.
- **Decision rationale:** All three test cases encode valid docs-landing behavior that Addendum 6 preserves. The guard interface (changed_files, docs_landing dict) is stable. These tests can remain as-is.


### `test_issue_link.py` — KEEP
- **Location:** `tests/qa/test_issue_link.py`
- **Purpose:** Tests for issue_link: resolve_or_create prefers existing issue, can create if missing, requires PR body closing keywords, accepts multiple issue closures, rejects mismatched issue URL.
- **Current behavior:** Tests the issue_link module that handles issue discovery and closing-keyword validation. All behaviors are valid under Addendum 6 (issue linkage is always required, PR body must close issues).
- **Duplication:** No receipt duplication.
- **Decision rationale:** All test cases encode behaviors explicitly required in Addendum 6 (Section 7.7.3: 'issue: Always required before PR readiness'; closing keywords required in finalize). No receipt duplication. These tests can remain as-is.


### `test_persona_policy.py` — MODIFY
- **Location:** `tests/qa/test_persona_policy.py`
- **Purpose:** Tests for persona_policy.check: accepts supported persona with required skill/constitution/policy files, rejects test_engineer skill mismatch, rejects unsupported persona, rejects missing skill/policy pointers, rejects runtime-specific root.
- **Current behavior:** Tests the persona_policy module. Addendum 6 Section 7.3 adds 'live_implementer' as a new persona and changes the allowed persona list. The test_persona_policy_rejects_unsupported_persona test uses 'freeform_agent' which is still unsupported, but any test asserting the allowed persona set needs to add 'live_implementer'. The runtime_root check for '.vendor-only' being unsupported is valid behavior (Section 7.4 AI-agnostic runtime roots).
- **Duplication:** No receipt duplication.
- **Decision rationale:** The structural validation rules (skill/constitution/policy pointers must exist, runtime root must be from the supported set) are valid and preserved. The test must be updated to reflect the new persona 'live_implementer' added in Addendum 6 Section 7.3. A new test for live_implementer acceptance should be added. The VALID_OVERRIDE_LABELS dependency (if any) must be updated for the 'bypass' rename.


### `test_governance_paths.py` — MODIFY
- **Location:** `tests/qa/test_governance_paths.py`
- **Purpose:** Tests for shared governance path helper is_gate_record_path and its integration with core_change_guard, sentrux_gate, docs_landing, and gate_record._sentrux_applies. Also tests docs_record CHANGELOG routing and gate_record._sentrux_applies exclusion.
- **Current behavior:** Tests the paths helper that determines which .workflow/records/** paths are gate-record evidence (excluded from governance-protection rules). This is a cross-cutting concern affecting four governance modules. The TestDocsRecordChangelogRouting class tests the docs_record function from the old CLI (start_record, docs_record), which will be replaced by init/amend in Addendum 6. The TestGateRecordSentruxAppliesException tests gate_record._sentrux_applies which is an internal function that may or may not survive refactoring.
- **Duplication:** No receipt duplication.
- **Decision rationale:** The is_gate_record_path helper and the module integration tests (TestCoreChangeGuardRecordsException, TestSentruxApplicabilityRecordsException, TestDocsLandingRecordsException) encode the critical 'records-only diff does not trigger governance protection' rule. This behavior is valid and must survive. The CHANGELOG routing tests (TestDocsRecordChangelogRouting) use the old CLI function names (start_record, docs_record) and the old docs_landing dict structure; these must be rewritten to use the new ledger amend/check flow while preserving the CHANGELOG classification rule. TestGateRecordSentruxAppliesException tests an internal that may be refactored away.


### `test_architecture_drift.py` — KEEP
- **Location:** `tests/qa/test_architecture_drift.py`
- **Purpose:** Tests for architecture_drift.check: accepts valid module/symbol/signature references in ARCHITECTURE.md, reports stale signatures in Python code blocks, reports missing symbols, reports missing module paths, skips non-normative examples.
- **Current behavior:** Tests the architecture_drift audit tool which is part of qa.audit (not qa.governance). This tool is not directly affected by the gate record rewrite.
- **Duplication:** No receipt duplication. qa.audit is independent of qa.governance gate plumbing.
- **Decision rationale:** Architecture drift detection is a qa.audit concern, not a gate_record/receipt concern. Addendum 6 Section 7.5 lists full_audit (which includes architecture_drift as a child report) as a check run by gate_record check. These tests are pure audit-logic tests with no receipt or stage semantics. No changes needed.


### `test_audit_closure.py` — KEEP
- **Location:** `tests/qa/test_audit_closure.py`
- **Purpose:** Tests for audit.closure.check_bidirectional: reports symbols without governance, accepts maintainer-owned symbols, accepts module governance, applies locked document governance amendments, skips draft future governance.
- **Current behavior:** Pure audit-logic tests for bidirectional closure between code symbols and governance documents.
- **Duplication:** No receipt duplication.
- **Decision rationale:** These are qa.audit tests independent of gate record semantics. Full audit is referenced in Addendum 6 as a check run by gate_record check (Section 7.5 CI workflow table), but the audit logic itself is unchanged. No receipt or stage semantics involved.


### `test_audit_doc_drift.py` — KEEP
- **Location:** `tests/qa/test_audit_doc_drift.py`
- **Purpose:** Tests for audit.doc_drift.classify_repo: phantom governed contracts/files, resolved governed contracts/files, draft-status skipping, ADR-to-spec alignment, spec-to-ADR alignment, planning/legacy ADR phase exemptions, unlinked spec detection.
- **Current behavior:** Pure audit-logic tests for doc drift detection between ADR/spec governs fields and actual source/contracts.
- **Duplication:** No receipt duplication.
- **Decision rationale:** Independent qa.audit tests, no gate record semantics. No changes needed.


### `test_audit_fact_drift.py` — KEEP
- **Location:** `tests/qa/test_audit_fact_drift.py`
- **Purpose:** Tests for audit.fact_drift.check_substitutions: reports unknown fact template references, accepts known fact references.
- **Current behavior:** Pure audit-logic tests. No gate record semantics.
- **Duplication:** No receipt duplication.
- **Decision rationale:** Independent qa.audit tests. No changes needed.


### `test_audit_frontmatter_lint.py` — MODIFY
- **Location:** `tests/qa/test_audit_frontmatter_lint.py`
- **Purpose:** Tests for audit.frontmatter_lint: ADR/addendum/spec/architecture frontmatter validation, filename matching, H1 heading, detail section references, structure checks.
- **Current behavior:** Pure audit-logic tests. The test_adr042_governance_documents_pass_frontmatter_lint test asserts the real ADR-042 and ADR-042-addendum1.md files pass; Addendum 6 adds a new addendum6.md file. After the rewrite, a corresponding 'ADR-042-addendum6.md passes frontmatter lint' assertion should exist.
- **Duplication:** No receipt duplication.
- **Decision rationale:** These tests are qa.audit tests independent of gate record semantics. The only needed update is adding ADR-042-addendum6.md to the list in test_adr042_governance_documents_pass_frontmatter_lint (and any new spec file referenced by Addendum 6).


### `test_audit_full_audit.py` — KEEP
- **Location:** `tests/qa/test_audit_full_audit.py`
- **Purpose:** Tests for audit.full_audit.run and render_markdown: renders human-readable summary, reports stale generated facts, generates default in-memory facts when snapshot is missing.
- **Current behavior:** Pure audit-logic tests. Full audit is a check run by gate_record check under Addendum 6 but the audit module itself is unchanged.
- **Duplication:** No receipt duplication.
- **Decision rationale:** Independent qa.audit tests. No gate record semantics. No changes needed.


### `test_audit_semantic_dup.py` — KEEP
- **Location:** `tests/qa/test_audit_semantic_dup.py`
- **Purpose:** Tests for audit.semantic_dup wrapper: script-missing fallback, subprocess-failure fallback, happy path parsing, default model name.
- **Current behavior:** Pure audit-logic tests. The semantic-dup ratchet is referenced in Addendum 6 Section 7.5 as a check run by gate_record check for Tier 1 and when path filters match.
- **Duplication:** No receipt duplication.
- **Decision rationale:** Independent qa.audit tests. No changes needed.


### `test_audit_signature_contracts.py` — KEEP
- **Location:** `tests/qa/test_audit_signature_contracts.py`
- **Purpose:** Tests for audit.signature_contracts.extract_adr_signature_contracts: reads active ADR sections, records file/line numbers, skips inactive ADRs.
- **Current behavior:** Pure audit-logic tests. No gate record semantics.
- **Duplication:** No receipt duplication.
- **Decision rationale:** Independent qa.audit tests. No changes needed.


### `test_audit_signature_drift.py` — KEEP
- **Location:** `tests/qa/test_audit_signature_drift.py`
- **Purpose:** Tests for audit.signature_drift.check_expected_signatures: missing symbol, parameter mismatch, Pydantic model field check, CLI exit code mismatch.
- **Current behavior:** Pure audit-logic tests. No gate record semantics.
- **Duplication:** No receipt duplication.
- **Decision rationale:** Independent qa.audit tests. No changes needed.


### `test_audit_vulture.py` — KEEP
- **Location:** `tests/qa/test_audit_vulture.py`
- **Purpose:** Tests for audit.vulture_audit: skipped when vulture unavailable, zero findings for no targets, warning findings for dead code, allowlist suppression, main returns zero on warning-only, pyproject config honors ignore_decorators and exclude.
- **Current behavior:** Pure audit-logic tests. Vulture is referenced in Addendum 6 as part of full_audit. The never-blocks-merge semantic is valid and preserved.
- **Duplication:** No receipt duplication.
- **Decision rationale:** Independent qa.audit tests. No changes needed.


### `test_schemas_report.py` — KEEP
- **Location:** `tests/qa/test_schemas_report.py`
- **Purpose:** Tests for qa.schemas.report: AuditReport blocks_merge on error finding, collects child error findings, AuditFinding accepts ADR-042 compatibility fields.
- **Current behavior:** Tests the shared report schema used by all guards and audit tools. This schema is the output type for all evaluator calculator calls.
- **Duplication:** No receipt duplication.
- **Decision rationale:** The AuditReport schema is the shared output type for all guard calculators and audit tools. Addendum 6 does not change this schema. These tests are foundational and must not be deleted.


### `test_schemas_maintainers.py` — KEEP
- **Location:** `tests/qa/test_schemas_maintainers.py`
- **Purpose:** Tests for qa.schemas.maintainers: accepts owner rule, rejects empty owners.
- **Current behavior:** Pure schema tests for the Maintainers/MaintainerRule Pydantic models.
- **Duplication:** No receipt duplication.
- **Decision rationale:** Independent schema tests. No changes needed.


### `test_schemas_signatures.py` — KEEP
- **Location:** `tests/qa/test_schemas_signatures.py`
- **Purpose:** Tests for qa.schemas.signatures: ExpectedSignature, ExpectedParameter, ExpectedModelField, ExpectedCliCommand schema validation and ADR-042 aliases.
- **Current behavior:** Pure schema tests. No gate record semantics.
- **Duplication:** No receipt duplication.
- **Decision rationale:** Independent schema tests. No changes needed.


### `test_generate_facts_cli.py` — KEEP
- **Location:** `tests/qa/test_generate_facts_cli.py`
- **Purpose:** Tests for scripts/audit/generate_facts.py CLI: write-and-check round trip, stale file detection.
- **Current behavior:** Tests the facts generation script used by full audit. No gate record semantics.
- **Duplication:** No receipt duplication.
- **Decision rationale:** Independent audit script test. No changes needed.


### `test_griffe_facts.py` — KEEP
- **Location:** `tests/qa/test_griffe_facts.py`
- **Purpose:** Tests for audit.griffe_facts: extract_symbol_facts extracts public classes/functions with correct parameter/return metadata, skips private functions; generate_registry wraps results.
- **Current behavior:** Pure audit-logic tests for griffe-based symbol extraction. No gate record semantics.
- **Duplication:** No receipt duplication.
- **Decision rationale:** Independent qa.audit tests. No changes needed.


### `test_scistudio_pr_create.py` — REWRITE
- **Location:** `tests/scripts/test_scistudio_pr_create.py`
- **Purpose:** Tests for scripts/scistudio_pr_create.py: extract_body, find_gate_record (including umbrella manager-record preference), filter_findings (PR-creation-blocked findings filtered vs kept), main smoke with --dry-run, extract_base and resolve_base_ref, base wiring into gate_record ci.
- **Current behavior:** Tests the PR wrapper script. The filter_findings tests include filtering 'core_change_guard.missing-admin-approval', 'pr_merge_guard.missing-admin-merge-approval', and 'human_bypass_guard.missing-bypass-label' as pre-PR-expected findings. The test_main_base_wiring tests assert that run_gate_record_ci is called with the resolved base. Under Addendum 6, the PR wrapper is expected to call the evaluator via gate_record check --mode pre-pr or gate_record finalize instead of the older gate_record ci subcommand. The find_gate_record umbrella-preference logic encodes valid behavior that Addendum 6 preserves (manager records take precedence in multi-record PRs). The filter_findings set may change if the new evaluator produces different rule_ids for pre-PR-expected failures.
- **Duplication:** The filter_findings tests currently whitelist specific rule_ids that are pre-PR-expected failures; this is a form of duplicating the evaluator's pre-PR mode logic in the wrapper test. Under Addendum 6, pre-PR mode is handled by gate_record finalize --mode pre-pr, removing the need for the wrapper to have its own filter list.
- **Decision rationale:** Addendum 6 Section 3 step 4 says to 'Delete or replace hook and wrapper entry points that call old validation semantics.' The PR wrapper itself will be rewritten to call gate_record finalize (pre-PR mode) rather than gate_record ci. The filter_findings rule_id list will change based on the new evaluator's output. The find_gate_record and extract_body logic are likely to survive. The base-wiring tests will need updating for the new finalize command interface. The test principles (wrapper delegates to evaluator, umbrella manager preference, extract_body parses argv) are valid and must be ported.


### `test_semantic_dup_scan.py` — KEEP
- **Location:** `tests/scripts/test_semantic_dup_scan.py`
- **Purpose:** Tests for scripts/semantic_dup_scan.py: function extraction, docstring stripping, similarity clustering, ratchet violation detection, baseline JSON schema.
- **Current behavior:** Pure unit tests for the semantic duplication scanner script logic. No gate record semantics.
- **Duplication:** No receipt duplication.
- **Decision rationale:** Independent script tests. No changes needed.


### Extra findings — tests

```text
MISSING TESTS IDENTIFIED BY ADDENDUM 6 SECTION 4 (Verification requirements):

The following test behaviors are required by Addendum 6 Section 4 but are NOT present anywhere in tests/qa/:

1. Observed changed files derived from git, not only declared by the agent (no test asserts that gate_record check/finalize reads git diff; current tests use changed_files= as a caller-supplied list).

2. Declared docs and test evidence reconciled against observed diff (Addendum 6 Section 7.2 'declared docs and test evidence is reconciled against the observed git diff, so a claimed docs or test path that is not actually changed does not satisfy its obligation' — test_gate_record_ci.py has test_changed_test_paths_must_be_in_pr_diff which is the closest existing test, but the claim-vs-diff reconciliation for docs_events is not tested).

3. Local and CI modes use the same evaluator (no test asserts that gate_record check --mode ci and --mode local call the same reconciliation path).

4. Local checks run the same resolved tool versions as CI and check fails closed when parity cannot be reproduced (no test for this new Section 7.10 requirement).

5. Hook, wrapper, and CI reports agree for the same fixture (no integration fixture test comparing all three call paths).

6. Prior check evidence remains valid only for unchanged covered surfaces; gate-record edits invalidate reconciliation evidence when obligations change (no test for incremental check validity — this is entirely new Addendum 6 behavior).

7. Committed gate records do not contain absolute local paths, raw command transcripts, environment dumps (no test for ledger sanitization, which is a new Addendum 6 Section 7.5 requirement).

8. Task-kind profiles produce the expected obligations (no test driving init with each of the eight task kinds and asserting the inferred obligation set).

9. guided work can expand through owner directive events without bypassing final tier-selected check obligations (no test for the new guided/live_implementer task kind).

IMPORTANT NOTE on test_gate_record_ci.py test_sentrux_missing_evidence_is_allowed_for_applicable_changes vs test_sentrux_gate.py test_verify_free_tier_rejects_missing_evidence_for_source_change:
These two tests are in direct contradiction. test_gate_record_ci.py says missing sentrux evidence does NOT block (Addendum 3 semantics). test_sentrux_gate.py says missing evidence for a source change DOES block. The rewrite must clarify which behavior the Addendum 6 model requires and consolidate into a single unambiguous test.

LABEL RENAME requires sweep: Multiple test files contain the string 'admin-approved:ai-override'. Addendum 6 Section 3 explicitly lists 'migration from any older admin-approved:ai-override references to admin-approved:bypass' as a required migration item. Files needing this update: test_gate_record.py (line 848), test_gate_record_hooks.py (line 80), test_governance_mod_guard.py (line 109, 118), test_governance_weakened_ci_check.py (line 124, 134), test_human_bypass_guard.py (line 21, 45, 47). test_gate_record.py also has test_broad_override_labels_bypass_local_intermediate_hooks parameterized with 'admin-approved:ai-override' which will need updating to 'admin-approved:bypass'.
```