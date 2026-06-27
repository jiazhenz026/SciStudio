[DISPATCH-TEMPLATE-V1: audit-no-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: no-context
- Audit branch: audit/adr-044-no-context-20260621
- Audit worktree: /Users/jiazhenz/SciStudio-adr044-audit-20260621
- Allowed audit surfaces (OWNER-RESTRICTED — only these three):
  - `docs/adr/ADR-044.md`
  - `docs/specs/adr-044-subworkflow-block.md`
  - The diff of this branch vs `origin/main` (`git diff origin/main...HEAD`), including the changed files themselves.
- Audit report path: `docs/audit/2026-06-21-adr-044-subworkflow-no-context.md`

## Context Limits

You must NOT read or use:
- The current owner request / chat.
- The GitHub issue (#890 or any other).
- The manager checklist (`docs/planning/adr-044-*`), dispatch prompts, or `docs/planning/**`.
- PR descriptions, PR comments, or commit messages for this work.
- Any manager summary of what changed.
- Other audit reports under `docs/audit/`.

You MAY read ONLY:
- `docs/adr/ADR-044.md`
- `docs/specs/adr-044-subworkflow-block.md`
- The branch diff vs `origin/main` and the full content of files that the diff touches (so you can judge whether the change, in context, satisfies the ADR/spec).
- Tool output from commands you run yourself (pytest, ruff, mypy, grep, the gate check).

Do NOT base findings on the issue, checklist, or any hidden manager intent. Judge ONLY whether the diff faithfully and completely implements ADR-044 and its spec.

## Required Reading

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/personas/audit-reviewer.md
- docs/adr/ADR-044.md
- docs/specs/adr-044-subworkflow-block.md

## Audit Goal

Independently verify that the branch diff implements ADR-044 + the spec COMPLETELY and CORRECTLY.
Be adversarial. The implementation claims to:
- Make `SubWorkflowBlock` authoring-only and inline-flatten subworkflow references at run start
  (`start_workflow`), with `load_workflow` returning the authored graph unchanged.
- Provide `flatten_subworkflows` (pure; id prefixing `<sw_id>__`; edge rewrite; cycle detection via
  canonical-path DFS raising `CyclicSubworkflowError`).
- Add an `exposed_ports` schema section and derive `SubWorkflowBlock` effective ports from it.
- Write the FLATTENED YAML to `RunRecord.workflow_yaml_snapshot`.
- Add a `SubWorkflowBroken` placeholder + validator rejection at run start.
- Delete the stub (`_scheduler_factory`, `_cleanup_callback`, `_run_with_scheduler`, `_sequential_execute`,
  `input_mapping`, `output_mapping`).

NOTE on representation drift (verify against this — the ADR/spec prose predates a refactor):
- The code uses `WorkflowDefinition.nodes` (not `blocks`) and edges as `"node_id:port_name"` (COLON, not dot).
  `exposed_ports.internal` uses DOT (`block_id.port`) on disk. The flattener converts DOT→COLON.
- `api/runtime` is a package (`_runs.py`/`_workflows.py`), not a single `runtime.py`.
- `config.ref.path` is the ref key.
Treat faithful implementation in the REAL representation as correct; do not flag the drift itself as a bug,
but DO flag any place the implementation diverges from ADR/spec INTENT or misses a required behavior.

Check specifically (map each to FR-001..FR-013 / SC-001..SC-007):
- SC-001: zero SubWorkflowBlock nodes reach the scheduler.
- SC-002: `workflow_yaml_snapshot` equals the FLATTENED YAML (watch for a disk-read fast path that would
  serialize the un-flattened on-disk file instead).
- SC-003: direct/2-/3-cycles all raise `CyclicSubworkflowError` with the correct chain.
- SC-005: the deleted stub symbols are truly absent from `blocks/subworkflow/**` and no injection sites remain.
- FR-002 vs FR-003: `load_workflow` does NOT flatten; `start_workflow` does, before validation + dispatch.
- FR-004: effective ports derive from `exposed_ports` and inherit `accepted_types` from the inner port.
- FR-010: broken ref → placeholder at editor load; validator rejects at run start.
- Test coverage adequacy for the above (missing tests for a documented contract = a finding).

## Coordination
- MUST work only on branch `audit/adr-044-no-context-20260621` in worktree `/Users/jiazhenz/SciStudio-adr044-audit-20260621`.
- MUST NOT use `pip install -e .` (use `PYTHONPATH=$PWD/src`).
- MUST NOT merge any PR. MUST NOT edit implementation files. MUST NOT edit the manager checklist.
- MUST write the audit report to `docs/audit/2026-06-21-adr-044-subworkflow-no-context.md` and commit it on the audit branch.

## Checks (run yourself; report results)
- `PYTHONPATH=$PWD/src python -m pytest --no-cov -q <the new/changed test files>`
- `PYTHONPATH=$PWD/src python -m ruff check <changed py>` and `ruff format --check`
- `grep -rn` for the deleted stub symbols across `src/scistudio/` to verify SC-005.
- Targeted reasoning probes (e.g. a small flatten/snapshot probe) where useful.

## Output Required (in the committed report)
- Report path + the commit that contains it.
- Findings ordered by severity: **P0** (release blocker / contract broken), **P1** (must-fix),
  **P2** (should-fix), **P3** (minor/nit). For each: the FR/SC it relates to, file:line evidence from the diff,
  and a concrete fix recommendation.
- Explicit verdict: pass / pass-with-must-fix / block.
- No statement about manager intent.

## Stop Conditions
Stop and report if:
- You are pushed to read issue/checklist/PR context.
- The audit requires hidden manager context.
- You would need to edit implementation code.
