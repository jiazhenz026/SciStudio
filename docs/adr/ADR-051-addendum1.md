---
adr: 51
addendum: 1
title: "Interaction Memory — Remember A Decision And Skip The Dialog"
status: Proposed
date_created: 2026-06-26
date_accepted: null
date_superseded: null

supersedes: []
superseded_by: null
related: [51, 29]
closes_issues: []
tracking_issue: 1781

is_code_implementation: true
governs:
  modules:
    - scistudio.engine.scheduler
    - scistudio.engine.runners
    - scistudio.blocks.base.interactive
  contracts:
    - scistudio.blocks.base.interactive.InteractiveMixin.remap_saved_decision
    - scistudio.blocks.base.interactive.interactive_input_signature
    - scistudio.blocks.base.interactive.load_interactive_memory
    - scistudio.blocks.base.interactive.INTERACTIVE_MEMORY_KEY
  entry_points: []
  files:
    - docs/adr/ADR-051-addendum1.md
    - src/scistudio/blocks/base/interactive.py
    - src/scistudio/engine/scheduler/_dispatch.py
    - src/scistudio/engine/runners/worker.py
    - src/scistudio/engine/runners/local.py
    - frontend/src/lib/interactiveMemory.ts
    - frontend/src/App.parts/InteractiveModals.tsx
    - frontend/src/components/BottomPanel.parts/ConfigPanel.tsx
  excludes: []

tests:
  - tests/blocks/test_interactive_mixin.py
agent_editable: true
assisted_by:
  - "Claude:claude-opus-4-8"

phase: planning
tags: [adr-051, interactive-blocks, ux, engine, inheritable-contract]
owner: "@jiazhenz026"
co_authors: ["@claude"]
language_source: en
translations: []
---

# ADR-051 Addendum 1: Interaction Memory — Remember A Decision And Skip The Dialog

## 1. Decision Summary

ADR-051 makes a block pause mid-run, open a window onto its real inputs, and
take a decision from the user. When a user iterates on the *back* half of a
workflow, the earlier interactive steps do not change, yet ADR-051 re-opens the
dialog on every run and forces the same manual decision again.

This addendum adds **interaction memory**: a user can choose to remember an
interactive block's decision so future runs replay it and skip the dialog
entirely — running straight through with the saved decision.

Interaction memory is a **single inheritable contract on `InteractiveMixin`**,
not per-block code. Every interactive block — core or package-provided —
inherits it. The frontend control is rendered generically from
`execution_mode = interactive` (the same way the variadic-port editor renders
from `variadic_inputs`), so a package block gets the capability without writing
any frontend code.

### 1.1 Problems Addressed

| Problem | Risk | Response | Detailed section |
|---|---|---|---|
| Iterating on the back of a workflow re-opens the same interactive dialog every run | Users abandon interactive blocks or stop iterating | Remember the decision and skip the dialog when the inputs are unchanged | Section 2 |
| Per-block memory code would not generalize to package blocks | Each new interactive block re-implements (and re-bugs) memory | One inheritable `InteractiveMixin` contract + schema-driven generic UI | Section 2 |
| A stale decision could be replayed after inputs change | Silent wrong results | Default invalidation on input-signature change; overridable per block | Section 3 |

## 2. The Contract

### 2.1 Where The Decision Lives

The remembered decision is stored in the block's **node config** (the frontend
owns the workflow definition; the engine only reads it — ADR-051 keeps runtime
truth in the backend, workflow-definition truth in the frontend). The config key
is `interactive_memory` (`INTERACTIVE_MEMORY_KEY`), a record:

```json
{
  "enabled": true,
  "decision": { "...": "the verbatim interactive_response" },
  "signature": { "input_1": ["spectrum_01.txt", "spectrum_02.txt"] }
}
```

- `decision` is the user's `interactive_response` stored **verbatim**. The
  framework never interprets it, so any interactive block's decision — routing,
  reordering, or anything a package block invents — is captured completely.
- `signature` is the input fingerprint captured when the decision was saved.

### 2.2 The Input Signature

`interactive_input_signature(inputs) -> {port: [item_label, ...]}` is a generic,
JSON-safe identity fingerprint of an interactive block's inputs. Each item's
label is its source filename (`interactive_item_label`, which prefers
`meta.source_file`). It is computed generically for every interactive block in
the prompt-phase worker and returned in the prompt envelope.

The signature deliberately keys on **filename and order**, because the source
filename is the only identity that is stable across runs (object ids and storage
paths are regenerated every run; derived items without a filename fall back to
position). Adding, removing, reordering, or renaming inputs changes the
signature; editing a same-named file's content does not.

### 2.3 Replay Decision (Overridable)

`InteractiveMixin.remap_saved_decision(saved_decision, saved_signature,
current_signature) -> dict | None` decides whether a remembered decision may be
replayed for the current inputs. It returns the `interactive_response` to apply
automatically (skipping the dialog), or `None` to fall back to opening the
panel.

The **default** (inherited by all interactive blocks): replay the decision
verbatim only when `saved_signature == current_signature`; otherwise fall back
to the dialog. This is safe — it never replays a stale decision — and covers the
"re-run with the front of the workflow unchanged" case. A block MAY override to
remap a decision by item identity so it survives reordering or partial input
changes.

### 2.4 Engine Skip

On dispatch of an interactive block, after the prompt phase builds the panel
view and the input signature, the engine reads `load_interactive_memory(config)`.
When memory is enabled and `remap_saved_decision` returns a response, the engine
resolves the interaction immediately with that response — no `BLOCK_PAUSED`, no
`INTERACTIVE_PROMPT`, no UI — and the compute phase runs with the saved decision.
Otherwise the dialog is emitted as usual, carrying the current `input_signature`
so the frontend can persist it alongside the decision.

The prompt phase still runs (it is a cheap subprocess) so the signature is
always computed against fresh inputs; the user never waits on a dialog.

### 2.5 Generic Frontend

- The remembered decision is persisted by the generic interactive modal wrapper
  on confirm, only when the node has memory enabled. It stores the verbatim
  response and the run's `input_signature` — no block-specific code, so package
  panels inherit it.
- The enable toggle and a "choose again" (clear saved decision) control are
  rendered by the config panel for any block whose `execution_mode` is
  `interactive`, mirroring the variadic-port editor's schema-driven rendering.

## 3. Invalidation And Completeness

Completeness of capture and correctness of invalidation rest on three points:

1. The whole `interactive_response` is persisted verbatim — no interpretation,
   no truncation — so any interaction is fully recorded.
2. The default invalidation is sensitive to structural input changes (add /
   remove / reorder / rename), and never replays a stale decision.
3. A block whose decision depends on input *content* (or that wants stricter or
   looser matching) overrides `remap_saved_decision`; a block that should never
   memoize simply never enables the config toggle.

## 4. Verification

- `tests/blocks/test_interactive_mixin.py` covers `interactive_input_signature`,
  `load_interactive_memory`, and the default `remap_saved_decision` (replay on
  identical signature, fall back on change).
- Frontend tests cover the signature capture in the prompt handler and the
  config-panel toggle render for interactive blocks.

## 5. Consequences

- Interactive blocks become usable in iterative debugging: configure the
  decision once, then re-run the workflow without re-doing it.
- The capability is uniform across core and package blocks with no per-block
  work, and degrades safely (any input change re-opens the dialog).
- The prompt phase still runs on a memory hit (to compute the signature); this
  is a cheap subprocess and imposes no user-facing wait.
