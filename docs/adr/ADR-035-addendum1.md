---
adr: 35
addendum: 1
title: "AI Block Reuse-Last-Output Toggle — Skip The Run, Re-Emit Prior Output"
status: Proposed
date_created: 2026-06-30
date_accepted: null
date_superseded: null

supersedes: []
superseded_by: null
related: [35, 51]
closes_issues: []
tracking_issue: 1898

is_code_implementation: true
governs:
  modules:
    - scistudio.blocks.ai.ai_block
  contracts:
    - scistudio.blocks.ai.ai_block.AIBlock
    - scistudio.blocks.ai.ai_block.REUSE_LAST_OUTPUT_KEY
  entry_points: []
  files:
    - docs/adr/ADR-035-addendum1.md
    - src/scistudio/blocks/ai/ai_block.py
    - tests/blocks/ai/test_ai_block_skeleton.py
  excludes: []

tests:
  - tests/blocks/ai/test_ai_block_skeleton.py
agent_editable: true
assisted_by:
  - "Claude:claude-opus-4-8"

phase: planning
tags: [adr-035, ai-block, ux, caching, iteration]
owner: "@jiazhenz026"
co_authors: ["@claude"]
language_source: en
translations: []
---

# ADR-035 Addendum 1: AI Block Reuse-Last-Output Toggle — Skip The Run, Re-Emit Prior Output

## 1. Decision Summary

ADR-035 defines the AI Block: each run spawns a claude/codex agent in a PTY
tab, hands it a manifest, waits for completion, then loads the files the agent
wrote at each declared `expected_path` back into the workflow as typed outputs.

This addendum adds an opt-in `reuse_last_output` config toggle. When it is on,
the block **does not run the agent at all**: it re-emits the output files left
at each declared `expected_path` by the previous run and returns immediately.
When there is nothing to reuse, it falls back to a normal agent run instead of
erroring.

The motivating workflow is iterating on the *downstream* half of a graph: an AI
Block that already produced a good result should not re-run (slow, token-costly,
and non-deterministic) every time the user re-runs the workflow to debug a later
block.

### 1.1 Problems Addressed

| Problem | Risk | Response | Detailed section |
|---|---|---|---|
| An AI Block re-runs the agent every workflow run while a user debugs downstream blocks | Wasted time and tokens; a "fixed" result silently changes run-to-run | Opt-in toggle re-emits the previous run's output files and skips the agent entirely | Section 4 |
| Reusing a computed output under changed inputs would be wrong | Silent wrong results if reuse were auto-gated by a heuristic | Reuse is unconditional and user-owned (enable only while inputs are unchanged); no input fingerprinting | Section 3 |
| A node that never produced output has nothing to reuse | A hard error would block the very iteration the toggle is meant to help | Fall back to a normal agent run on any missing/empty declared output | Section 4.2 |
| An audit could mistake a reused result for a genuine agent run | Misattributed lineage | Write a `reuse.json` marker (not a manifest) in the block execution's run dir | Section 4.3 |

## 2. Context And Problem

- An AI Block run is expensive and non-deterministic. Re-running it while
  debugging unrelated downstream blocks wastes time and tokens and can silently
  change a result the user was treating as fixed.
- ADR-035 already persists each run's outputs at stable, project-relative
  `expected_path`s (`./<block>_outputs/<port>.<ext>` by default). Those files
  survive between runs; they are only removed by `_clear_expected_outputs()` at
  the *start* of the next run (#1789). The "last output" is therefore already
  durably on disk — no new artifact store is needed.

## 3. Relationship To ADR-051 Interaction Memory

ADR-051 Addendum 1 ("Interaction Memory") is superficially similar — both add a
"skip" toggle — but the semantics are deliberately different:

| | ADR-051 interaction memory | ADR-035 reuse-last-output (this addendum) |
|---|---|---|
| What is reused | The user's *decision* (a config value) | The block's *output files* |
| Does it recompute | Yes — compute phase still runs | No — the agent never runs |
| Input-change gating | Yes — replays only when the input fingerprint matches (`remap_saved_decision`) | No — unconditional; the user owns the decision to enable it |
| Failure mode when stale | Re-opens the dialog | Falls back to a normal run |

The reuse toggle is intentionally **unconditional**: it does not fingerprint
inputs. Reusing a *decision* under changed inputs is safe (the compute step still
runs on the new inputs); reusing a computed *output* under changed inputs is not,
so gating it automatically would give false confidence. Instead the contract is
explicit: the user enables the toggle only while inputs are unchanged, exactly
the debug-the-downstream-blocks scenario. This keeps the mechanism simple and its
correctness the user's call, not a heuristic's.

## 4. Design

### 4.1 Config Field

A boolean `reuse_last_output` field is added to `AIBlock.config_schema`
(default `false`, not required). Boolean schema fields already render as a
checkbox in the config panel (`ConfigField`), so no frontend change is required.
The block `version` is bumped `0.2.0 → 0.3.0` (contract change).

`REUSE_LAST_OUTPUT_KEY = "reuse_last_output"` is the exported config key;
`_reuse_last_output_enabled(config)` reads it (`BlockConfig.get` already looks in
`params` first, then extra fields, so one lookup covers both storage locations).

### 4.2 Bypass In `AIBlock.run()`

`run()` resolves the declared output specs (`{port: {expected_path,
expected_type}}`) up front — before any `run_dir`, manifest, or clear side
effect. When the toggle is on, `_try_reuse_last_output()` is attempted first:

- **Hit** — every declared output exists at its `expected_path` and is
  non-empty. The files are loaded through the same `_validate_and_load_outputs()`
  path a normal run uses, `run()` returns them, and no PTY tab is requested. The
  prior files are left untouched (the bypass runs before `_clear_expected_outputs`).
- **Miss** — any declared output is missing or empty (never ran, or a partial
  prior run). `_try_reuse_last_output()` returns `None` and `run()` falls through
  to the normal agent run.

Requiring *every* declared output to be present-and-non-empty makes the miss
boundary exactly the "never successfully ran" case the fallback is meant to
cover. A present-but-corrupt file is loaded through the normal validator and
surfaces its real load error rather than being silently re-run.

### 4.3 Traceability

A reuse hit records itself on the block execution's own run dir
(`.scistudio/ai-block-runs/<execution-id>/`) by writing a `reuse.json` marker
(`{"reused_last_output": true, "block": {...}, "outputs": {...}}`) *instead of* a
`manifest.json` + `signals/`. The presence of `reuse.json` and the absence of a
manifest is the durable, per-execution audit signal that distinguishes a reused
result from a genuine agent run; the reuse and fallback branches also log at INFO.

The PTY completion path (`notify_block_pty_event`) is deliberately not used on a
reuse hit: it is a frontend-only WS broadcast that decorates a tab title and
resolves `tab_id` from the engine's tab→run map. A reuse opens no tab, so a
notify would carry `tab_id = null`, be dropped by the frontend, and record
nothing durable — it is not a lineage channel.

## 5. Consequences

- **Positive** — cheap, deterministic iteration on downstream blocks; no new
  storage; frontend gets the checkbox for free; default-off preserves existing
  behavior exactly.
- **Negative / accepted** — correctness under changed inputs is the user's
  responsibility (by design; see §3). Reuse depends on the prior run's files
  still being present at their `expected_path`; if the user deleted them, the
  block falls back to a normal run.

## 6. Scope And Non-Goals

- No input fingerprinting, no cross-run cache index, no cache invalidation — out
  of scope by decision (§3). If a future need for input-aware reuse appears it is
  a separate ADR, not a silent extension of this toggle.
- No change to the completion-signal race, manifest schema, or PTY contract.
