---
title: "ADR-054 Assembly Dispatch — S5-B2 Panel Reference And Panel Tools"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S5-B2 — The Panel Reference, The Block-Contract Rewrite, And The Panel Tools

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 5's panel-authoring half — the
  panel-contract reference, the rewrite of the panel section of the block
  contract, and the four panel tools including the stub harness a scaffolded
  panel is born with.
- Task kind: feature
- Persona: implementer
- Issue: #2254
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2254
- Umbrella PR: #2255 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-integration
- Track branch (your PR base): track/adr-054-spec5-agent-enablement
- Agent branch: feat/2254-panel-tools
- Agent worktree: .worktrees/s5-b2
- Gate record: .workflow/records/2254-feat-2254-panel-tools.json
- Checklist: docs/planning/adr-054-assembly-checklist.md
- Shared preamble: docs/planning/adr-054-assembly-dispatch-prompts/_common.md
  — read it first.

## Required Rules

Everything in the shared preamble, plus:

- `docs/specs/adr-054-agent-enablement.md` — your spec. You implement
  **T-003 and T-004** of its §4.3, covering FR-010 to FR-018.
- `docs/specs/adr-054-panel-contract.md` — the contract your reference
  document describes. **The landed code is the fact**: read
  `src/scistudio/core/panels.py`, `src/scistudio/panels/**` and
  `src/scistudio/api/routes/panels.py` and describe what they actually do.
  Where the spec and the code disagree, say so in your report rather than
  documenting the spec.
- ADR-054 §8.2 — the layering your documents follow: a skill stays short with
  no inline code, the reference documents carry contracts, and worked patterns
  are fetched through the example-listing tools.

## Scope

You own only:

- `src/scistudio/_agent_reference/panel-contract.md` — new.
- `src/scistudio/_agent_reference/block-contract.md` — the panel section only.
- `src/scistudio/_agent_reference/README.md` — the index entry.
- `src/scistudio/ai/agent/mcp/tools_panels/**` — new.
- `src/scistudio/ai/agent/mcp/server.py` — registering the panel group only.
  **Coordinate**: S5-B3 registers the explore group in the same file. Make
  your edit minimal and additive so the two merge cleanly.
- `tests/ai/test_mcp_tools_panels.py` — new.

You must not touch:

- `src/scistudio/_agent_reference/public-api.md` and `data-types.md` — S5-B4.
- `src/scistudio/ai/agent/mcp/tools_explore/**` — S5-B3.
- The workspace-focus files (`api/routes/ai.py`, `api/runtime/_projects.py`,
  `mcp/runtime.py`, `_context.py`, `tools_workflow/read.py`) — S5-B1.
- `src/scistudio/_skills/**`, `src/scistudio/agent_provisioning/**`,
  `tools_authoring.py`, the count assertions — S5-B4.
- `src/scistudio/panels/**` and `src/scistudio/core/panels.py` — spec 1's
  landed runtime. Your tools *use* the registry; they do not change it.
- Every `frontend/**` path.
- `docs/architecture/**`.

If you need an out-of-scope path, stop and report back. Do not edit it.

## TODO And Deferral Rule

Per the shared preamble. Do not open an issue; append to
`docs/planning/adr-054-assembly-followups.md` under `## S5-B2`.

## Work To Do

1. **T-003 — the reference documents.**
   `panel-contract.md` is the **single** description of: the capability
   declaration, the message contract, the on-disk layout, the tier a panel is
   written into, the registration per tier, and the statement whitelist for
   emitted code (FR-010).
   Rewrite the panel section of `block-contract.md` (FR-011) — **rewrite, not
   append**. It currently teaches the ES-module form the panel contract
   retires, and a document that teaches both is worse than one that teaches
   neither. No mention of the ES-module form or the retired asset route may
   remain. Index the new document in the reference README (FR-013).
2. **T-004 — the panel tools, and the harness that makes the form honest.**
   - `scaffold_panel` writes a panel directory into a named tier for named
     target types and a capability: the declaration, a self-contained document
     with a **working** skeleton, and a harness (FR-014).
   - The harness is the point. ADR-054 §8.5 says the argument for a plain HTML
     panel is sound only if the agent can actually open its work and look at
     it. The harness must be a document that **opens on its own in a browser**:
     it loads the panel document, supplies representative data for the declared
     target types, stands in for the host side of the message contract, and
     shows any emission the panel makes. The tool returns the harness path and
     the URL the existing GUI tool exposes (FR-015).
     Generate the harness **from the same contract module the host uses**, not
     from a hand-copied description of it. A harness that restates the message
     contract in its own words is the drift this design is trying to avoid.
   - `read_panel_source` returns a registered panel's declaration and document
     by id, from whichever tier it resolved from (FR-016).
   - `list_panel_examples` returns the panel examples in the corpus (FR-017).
     The corpus additions themselves are S5-B4's; your tool must return them
     when they exist and must not fail when they do not yet.
   - `reload_panels` rebuilds the panel registry and returns the discovered
     panels with their tiers, capabilities, and any discovery diagnostics
     (FR-018).

## Required Tests And Checks

`tests/ai/test_mcp_tools_panels.py`, against the panel registry with a
temporary tier:

- `scaffold_panel` writes exactly three files; the declaration validates
  against the landed contract; the document's skeleton is not a stub that
  cannot run.
- **The harness is opened in the test browser the end-to-end toolchain
  provides**, renders over stub data, and captures an emission. This is the
  assertion that makes FR-015 real; a test that only checks the harness file
  exists does not.
- The harness is generated from the contract module, asserted by a test that
  fails if the module's message names change and the harness does not.
- `reload_panels` discovers the scaffolded panel with its tier and capability.
- `read_panel_source` round-trips it from each tier it can resolve from.
- `list_panel_examples` behaves with and without corpus examples present.
- A test that reads `block-contract.md` and fails if the ES-module form or the
  retired asset route is still described.

Then:

- `python -m scistudio.qa.governance.gate_record check --mode pre-pr
  --base track/adr-054-spec5-agent-enablement --head HEAD
  --pr-body-file .workflow/local/pr-body.md`
- Pre-PR `finalize`, then `python scripts/scistudio_pr_create.py`, then
  post-PR `finalize`. Base your PR on `track/adr-054-spec5-agent-enablement`.
- Docs: record `--docs-updated src/scistudio/_agent_reference/panel-contract.md`
  and the block-contract path. The agent-facing reference **is** in scope, so
  it is a docs-updated, not a docs-N/A. Add
  `--docs-na "user-docs:the human documentation revision is ADR-054 spec 6,
  issue #2236"` for the human guides.

## Output Required

Per the shared preamble. Additionally: state the four tool names exactly as
registered, because S5-B4 writes them into the catalogs and the count
assertions.

## Stop Conditions

Per the shared preamble.
```
