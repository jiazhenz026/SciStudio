---
title: "A3 Dispatch Prompt — Panel Authoring Skill And Scaffold"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 51
language_source: en
---

# A3 Dispatch Prompt — Panel Authoring Skill And Scaffold (#2197)

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Interactive blocks are the worst-taught authoring surface in the repository; give the embedded agent a dedicated skill and a scaffold that starts from a working panel.
- Task kind: feature
- Persona: implementer
- Issue: #2197
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2197
- Umbrella PR: #2198 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/interactive-panel-quality
- Agent branch: docs/2197-panel-authoring-skill
- Agent worktree: .worktrees/docs-2197-panel-authoring-skill
- Gate record: .workflow/records/2197-docs-2197-panel-authoring-skill.json (create it with `gate_record init`)
- Checklist: docs/planning/interactive-panel-quality-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2197` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-051-interactive-blocks.md — the contract you are teaching.

## Scope

You own only:

- src/scistudio/_skills/**
- src/scistudio/_agent_reference/block-contract.md
- src/scistudio/cli/templates/**
- A new self-contained module for the interactive scaffold helper (see
  Coordination for why it is separate).
- frontend/src/App.parts/InteractiveModals.parts/panelModuleLoader.ts —
  **the file's header comment only**, nothing else.
- tests/**

You must not touch:

- src/scistudio/ai/agent/mcp/tools_authoring.py — see Coordination.
- src/scistudio/blocks/**
- src/scistudio/workflow/**
- src/scistudio/agent_provisioning/**
- Any frontend behavior. Your only frontend edit is the comment above.
- Any tutorial asset. You may READ
  `src/scistudio/tutorials/core/what-is-a-type/assets/panels/review_labels/panel.mjs`
  as the reference implementation, but do not modify it.

If you need an out-of-scope path, stop and report back.
Do not edit it.

## Coordination

- You are not alone in this codebase.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- **`src/scistudio/ai/agent/mcp/tools_authoring.py` is sequenced away from
  you.** Agent A2 (#2196) owns it exclusively for this dispatch because
  `ReloadBlocksResult` and `scaffold_block` live in the same module. Implement
  the interactive scaffold as a self-contained helper with one clear entry
  point, and report its import path and signature. The manager wires
  `scaffold_block` to call it after #2196 merges. Do not open that file, and do
  not work around the rule by adding a shim inside it.
- Agent A1 (#2195) is changing `InteractiveModals.tsx` and `DynamicPanel.tsx`.
  Your only frontend edit is the `panelModuleLoader.ts` header comment, so you
  do not overlap — but do not touch anything else in that directory.
- Agent A2 owns the validation implementation. Your skill must ROUTE to it, not
  reimplement it. If you need its exact diagnostic vocabulary before A2 lands,
  use the failure codes named in issue #2196 (`export_missing`,
  `not_a_panel_module`, `api_version_mismatch`, `import_failed`,
  `mount_failed`) — they come from
  `frontend/src/App.parts/InteractiveModals.parts/panelModuleLoader.ts` and are
  stable.
- The manager explicitly assigns you a final PR to `main` (not to the umbrella
  branch). Your PR body must close #2197 with a closing keyword.
- MUST NOT merge any PR unless the owner explicitly authorizes it.
- Edit only your checklist rows (§9.3 of the checklist).
- Record every completed row with a PR, commit, test, report, or gate evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- The `scaffold_block` wiring is not deferred work — it is sequenced to the
  manager (checklist §2.1). Report the helper's signature and stop there.

## Work To Do

Read the issue in full; it enumerates exactly what an authoring agent has today
and the two documentation defects that push it straight into known failure
codes.

1. **A dedicated interactive-panel authoring skill** under
   `src/scistudio/_skills/scistudio/`, alongside `scistudio-write-block`. Match
   the existing skills' shape and length — they are task flows that point at the
   contract, not copies of it. It must:
   - state as **non-negotiable** that the panel gives the user a reachable way
     to both confirm and cancel (this is the defect that reached users);
   - carry a minimal working panel module the agent can start from;
   - route to the validation surfaces (`reload_blocks` diagnostics and
     `validate_workflow`) so the agent self-debugs;
   - be routed to from `scistudio-write-block/SKILL.md`, whose interactive
     coverage today is three lines.

2. **An interactive scaffold.** A self-contained helper (see Coordination) that
   emits both halves:
   - `blocks/<name>.py` — `InteractiveMixin`, `execution_mode`, a correctly
     filled `PanelManifest` with a real `module_url` shaped
     `/api/blocks/panels/<panel_id>/<file>` and a real `asset_root`, and a
     `prepare_prompt` stub;
   - the panel module skeleton beside it — **default** export carrying
     `apiVersion` and `mount`, `mount` returning `{ unmount() {...} }`, and
     confirm and cancel controls already wired to `host.confirm` /
     `host.cancel`.

   The generated pair must be correct as generated: it should register, and it
   should mount with working controls, with no further edits. The agent then
   fills the payload reduction, the content area, and the compute body.

3. **Documentation corrections.** Both are live sources of the errors users are
   hitting:
   - `src/scistudio/_agent_reference/block-contract.md` shows the module as
     exporting `{ apiVersion: "1", mount(container, host) }` without saying it
     must be the **default** export, while `export_name` defaults to
     `"default"` — this produces `export_missing`. State it.
   - The same section's example names `index.js` while the only working example
     is `panel.mjs`, and the `module_url` shape is easy to get wrong — this
     produces `import_failed`. Make the example and the stated shape consistent
     with what actually ships and what the route actually serves
     (`/api/blocks/panels/{panel_id}/{asset_path}`, router prefix
     `/api/blocks`, `src/scistudio/api/routes/blocks.py:492`).
   - `frontend/src/App.parts/InteractiveModals.parts/panelModuleLoader.ts` line
     8 documents the route as `/api/interactive/panels/...`, which does not
     exist. Fix the comment text only.
   - Check whether `docs/package-development/blocks.md` states the same contract
     and needs the same corrections.

4. Tests for the scaffold output shape: the generated block registers, and the
   generated panel module satisfies the contract (default export, `apiVersion`,
   `mount` returning `{ unmount }`, confirm and cancel referenced).

## Required Tests And Checks

- Targeted pytest for the scaffold helper and its output.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr` to run
  tier-selected checks and reconcile the gate ledger before PR creation
  (receipt behavior is folded into the ledger per ADR-042 Addendum 6; there is
  no separate `gate_receipt` command)
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2197"` before PR creation
- `python scripts/scistudio_pr_create.py` for the final PR (do not use
  `gh pr create` directly)
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr <url> --pr-body-file <path>` after PR is created

If you end up editing anything under `docs/ai-developer/**`, that is a
governance surface and requires `--governance-touch true` in your ledger. The
skills you are writing live under `src/scistudio/_skills/**`, which is product
surface, not governance.

## Output Required

Before reporting done, provide:

- Changed file paths.
- The scaffold helper's import path and signature, for the manager's wiring step.
- Tests/checks run and results.
- Checklist rows updated.
- PR number or commit.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file — in particular, if you conclude the scaffold
  cannot be delivered without editing `tools_authoring.py`.
- The contract as documented and the contract as implemented disagree somewhere
  else than the two defects named above — report the discrepancy rather than
  guessing which side is right.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- CI or local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
```
