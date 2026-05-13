# Microplastics e2e test prompt — draft (T-ECA-504 v0)

> **Status**: Draft. This file is the dispatcher-authored v0 of the e2e test
> prompt for ADR-033 Phase 5. It currently lives under `docs/specs/`
> because the canonical landing path `tests/e2e/microplastics/test_prompt.md`
> belongs to T-ECA-501 (Phase 5 scaffold). When T-ECA-501 lands, this
> file will be moved verbatim into `tests/e2e/microplastics/test_prompt.md`
> by a T-ECA-504 migration commit.
>
> **Editing rules (per ADR-033 spec §8.5 T-ECA-504)**: only the dispatcher
> author edits this file. Implementation agents must not modify it during
> the test run. The prompt is the load-bearing test contract; iterate on
> prompt wording rather than on workflow YAML or custom block code.

---

## The prompt (delivered verbatim to the agent)

Below is the literal message body the e2e harness will paste into the
agent's chat input. Everything between the BEGIN and END markers is the
prompt; nothing else.

```text
BEGIN PROMPT --------------------------------------------------------------

You are a scientific workflow agent operating inside the SciEasy GUI. Your
goal is to reproduce the analysis in the microplastics SRS notebook by
building and running a SciEasy workflow.

# Inputs

- Source notebook (read-only reference for the analysis logic and expected
  outputs): `{microplastics_ipynb_path}`.
- Raw data directory: `{microplastics_raw_data_dir}`.
- Project workspace (your scratch space — workflow YAML, custom blocks,
  intermediate outputs all live here): `{project_dir}`.
- Reference outputs directory (DO NOT read until you are ready to compare):
  `{golden_dir}`.

The harness has already created the workspace at `{project_dir}` and
launched the SciEasy backend. **The workspace is empty: no workflow,
no custom blocks, no intermediate outputs.** You start from a blank
canvas. Build everything you need yourself using the available
built-in blocks (discoverable via `list_blocks`); if a step has no
built-in equivalent, write your own Tier-1 custom block under
`{project_dir}/blocks/` and call `reload_blocks`. You have full
read/write access to the workspace via your MCP tools.

# Goal

Produce a workflow that, when run, generates the same per-sample numerical
outputs as the source notebook (peak tables, classification labels, summary
statistics, plot data — whatever the notebook produces). "Same" means the
numerical comparator at `tests/e2e/microplastics/_compare.py` accepts the
comparison (rtol=1e-3, atol=1e-6 for floats; exact equality for labels).

# Method (you decide the details)

- Read the source notebook using Claude Code's built-in `NotebookRead`
  tool (the canonical reader for `.ipynb` files; lives outside the docs/
  scope that the MCP `get_doc` tool covers). The notebook is the
  reference for the analysis logic — read every cell.
- Inspect the raw data with `inspect_data` and `preview_data` BEFORE
  designing any block. Confirm shapes, dtypes, axis conventions, and units
  match what the notebook assumes.
- Build the workflow using `list_blocks`, `get_block_schema`, and
  `write_workflow`. Prefer built-in blocks whenever they cover the step.
- If a step in the notebook has no clean built-in equivalent (custom peak
  picker, custom classifier, custom preprocessing), write a Tier-1 custom
  block under `{project_dir}/blocks/`, then call `reload_blocks` to make
  it available in the registry. Document each custom block's purpose in
  its docstring; the audit will read these.
- Submit the workflow with `run_workflow` — this returns a run id
  *immediately*; it does NOT block until completion. Then poll
  `get_run_status(run_id)` on a backoff (e.g. 2s → 8s → 30s) until the
  status is a terminal value (`completed`, `failed`, or `cancelled`).
  Treat any non-terminal status as "not done yet". Do not assume the
  initial `run_workflow` response means the run is over.
- For each output the notebook produces, read your run's equivalent with
  `inspect_data` + `preview_data` (or `get_block_output`) and verify
  shape/dtype/range look right BEFORE concluding the task is done.

# Discipline reminders

- Self-verify each step. After every `write_workflow` call, run
  `validate_workflow` and read the result. After every `run_workflow`
  invocation, wait for `get_run_status` to report a terminal state.
- If a block errors, read `get_block_logs` for that block before patching.
  Most failures are config drift (wrong column name, wrong axis order),
  not block bugs.
- Do not ask the user to intervene. If a block is missing, write one.
  If a config is wrong, fix it. If the data shape doesn't match what the
  notebook assumes, slice/transpose in a preprocessing block — do not
  silently change tolerances.
- Do not edit the source notebook. Treat it as a read-only spec.
- Do not read files under `{golden_dir}` until the workflow run finished
  and you are ready to compare. The harness uses the same comparator the
  test will use; do not optimise your blocks against the golden directly.

# Completion criterion

You are done when:

1. `get_run_status(run_id)` reports a terminal `completed` status (NOT
   merely that `run_workflow` returned without error — the submit call
   returns immediately with a run id),
2. you have explicitly inspected (via `inspect_data` / `preview_data`)
   each output the notebook produces and confirmed it has the right
   shape, dtype, and order-of-magnitude,
3. you have written a short summary in the chat naming each output and
   where it lives in the workspace.

The harness will then run the numerical comparison against
`{golden_dir}`. If the comparison fails, the harness will append a diff
report to this conversation and you will get one more iteration to
adjust. If the comparison passes, the test passes.

END PROMPT ----------------------------------------------------------------
```

## Placeholder bindings (filled by the harness)

The braces in the prompt are runtime-bound by `tests/e2e/harness.py`:

| Placeholder | Source |
|-------------|--------|
| `{microplastics_ipynb_path}` | constant in the test, points at the user's Box ipynb location |
| `{microplastics_raw_data_dir}` | constant — the ipynb's input directory |
| `{project_dir}` | tmp directory created per test run |
| `{golden_dir}` | `tests/e2e/microplastics/golden/` |

## Versioning

- **v0** (this file): initial draft, written before any e2e run has been
  attempted. Wording is principled but unverified.
- **v1+**: tuned based on diff reports from T-ECA-505 runs. Each version
  bump must record: which run revealed the gap, what prompt change
  addressed it, and whether the next run passed.

Version history (append-only):

| Version | Date | Trigger | Change |
|---------|------|---------|--------|
| v0 | 2026-05-12 | initial draft | n/a |
| v1 | 2026-05-12 | Codex P1+P2 review on PR #760 (issue #759) | (P1) Replaced `get_doc`/`read_block_source` notebook-read instruction with Claude Code's built-in `NotebookRead` tool — `get_doc` is scoped to `docs/` and `read_block_source` reads block class source by name, neither can reach the microplastics ipynb. (P2) Tightened `run_workflow` completion criterion: explicit polling on `get_run_status(run_id)` until terminal `completed`, not initial submit return. |
| v2 | 2026-05-12 | User clarification during Phase 5 cascade | Explicitly stated that the workspace is blank: no pre-existing workflow, no custom blocks, no intermediate outputs. The agent starts from scratch. This was previously implicit (the harness creates a fresh tmp project per run); making it explicit removes any risk the agent assumes a pre-built workflow exists. |

## Why this prompt is the *only* mutable input

Per ADR-033 §8.5 the hard operating constraint is: the dispatcher author
is FORBIDDEN from touching the workflow canvas, editing the workflow
YAML, writing or repairing custom blocks, or otherwise intervening in the
agent's work product during the test. If the agent fails despite prompt
iteration, that is the test's signal that ADR-033's agent design has gaps
— record them in the T-ECA-510 audit report rather than fixing them by
hand.
