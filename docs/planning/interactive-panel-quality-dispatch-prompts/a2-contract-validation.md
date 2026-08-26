---
title: "A2 Dispatch Prompt — Interactive Contract Validation"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 51
language_source: en
---

# A2 Dispatch Prompt — Interactive Contract Validation (#2196)

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: AI-authored interactive blocks reach users broken; give the authoring agent an automatic way to find its own contract errors, mounted where it cannot route around them.
- Task kind: feature
- Persona: implementer
- Issue: #2196
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2196
- Umbrella PR: #2198 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/interactive-panel-quality
- Agent branch: feat/2196-interactive-contract-validation
- Agent worktree: .worktrees/feat-2196-interactive-validation
- Gate record: .workflow/records/2196-feat-2196-interactive-contract-validation.json (create it with `gate_record init`)
- Checklist: docs/planning/interactive-panel-quality-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2196` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-051-interactive-blocks.md — the panel manifest and host
  contract this validates.

## Scope

You own only:

- src/scistudio/blocks/registry/**
- src/scistudio/ai/agent/mcp/tools_authoring.py  (you own this file exclusively;
  see Coordination)
- src/scistudio/ai/agent/mcp/_reload.py
- src/scistudio/workflow/validator.py
- src/scistudio/agent_provisioning/**
- A new module for the shared validation implementation, placed where it can be
  imported by the registry, the workflow validator, and the hook without a
  circular import. Justify the placement in the module docstring.
- tests/**

You must not touch:

- frontend/**
- src/scistudio/_skills/**
- src/scistudio/_agent_reference/**
- src/scistudio/cli/templates/**
- Any tutorial asset.

If you need an out-of-scope path, stop and report back.
Do not edit it.

`src/scistudio/blocks/**` is a protected core path. Your PR needs the
`admin-approved:core-change` label, whose provenance CI verifies. Record the
expected label with `gate_record amend --admin-label admin-approved:core-change`
and tell the manager when you open the PR so the owner can apply it. That label
authorizes the protected path only; it is not a gate bypass.

## Coordination

- You are not alone in this codebase.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- **`src/scistudio/ai/agent/mcp/tools_authoring.py` is sequenced to you.** Agent
  A3 (#2197) also has a claim on that file (`scaffold_block`, line 319) and has
  been told not to open it. Change only what `reload_blocks` and
  `ReloadBlocksResult` need. Do not refactor `scaffold_block` or the
  surrounding module — the manager wires A3's work in after your PR merges.
- Agent A1 (#2195) is changing the interactive modal's frontend at the same
  time. You do not touch the frontend, and it does not touch the backend.
- The manager explicitly assigns you a final PR to `main` (not to the umbrella
  branch). Your PR body must close #2196 with a closing keyword.
- MUST NOT merge any PR unless the owner explicitly authorizes it.
- Edit only your checklist rows (§8.3 of the checklist).
- Record every completed row with a PR, commit, test, report, or gate evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- Proving that a confirm/cancel control is actually bound to a DOM element is
  out of reach without executing the module, and executing it is out of scope
  (see below). This is a deliberate design limit, not deferred work — the owner
  accepted it, and the host-owned escape hatch in #2195 is the guarantee that
  covers it. Do not file a TODO for it; state the limit in the docstring of the
  check that searches for `host.cancel`.

## Work To Do

Read the issue in full — it lists each failure mode with the frontend failure
code it produces. That mapping is the deliverable's core: every diagnostic you
emit must name the same code the user's error surface would show
(`export_missing`, `not_a_panel_module`, `api_version_mismatch`,
`import_failed`, `mount_failed`), so the agent's vocabulary and the user's error
text agree.

1. **One shared validation implementation.** Two groups of checks:

   *Manifest and filesystem (deterministic):* `module_url` non-empty,
   site-relative, shaped `/api/blocks/panels/<panel_id>/<file>` with a
   `panel_id` matching the manifest; `asset_root` set and an existing directory;
   the file `module_url` names exists under `asset_root` with a suffix in
   `_ALLOWED_ASSET_SUFFIXES` (`src/scistudio/previewers/assets.py:33`); declared
   `css` entries resolve the same way. Note the real route is
   `/api/blocks/panels/{panel_id}/{asset_path}` — router prefix `/api/blocks`,
   `src/scistudio/api/routes/blocks.py:492`.

   *Panel module source (static, never executed):* an export matching
   `export_name` exists (default `default`); it carries `apiVersion` and
   `mount`; `apiVersion` major matches the backend `PANEL_API_VERSION`;
   `unmount` appears; `host.confirm` and `host.cancel` are referenced; no remote
   imports.

   **Two severities.** Hard error for the deterministic manifest/filesystem
   checks and for a missing export / `apiVersion` / `mount` — these fail at
   runtime with certainty. `Warning:` advisory for `host.confirm` /
   `host.cancel` / `unmount` not found — a string search cannot prove a control
   is wired, so these must never block.

2. **Surface 1 — registry scan and `reload_blocks`.** Today
   `_validate_interactive_capability`
   (`src/scistudio/blocks/registry/_capability.py:285-330`) raises and the
   scanner drops the block silently; `reload_blocks`
   (`src/scistudio/ai/agent/mcp/tools_authoring.py:422-449`) returns only
   `{reloaded, added, removed}`. The authoring agent sees the block vanish from
   `list_blocks` with no reason.

   Collect rejection reasons during the scan and return them from
   `reload_blocks` as a `rejected` list of `{block, reasons[], fix}`. This turns
   the agent's existing `write -> reload_blocks -> list_blocks` loop into a
   validation loop with no new tool. Fix the silent drop for **every**
   scan-time rejection, not only interactive ones — that is the same defect.

3. **Surface 2 — workflow validator.** Feed the same checks through
   `scistudio.workflow.validator.validate_workflow` so `validate_workflow`,
   `write_workflow`'s post-write verification, and run start all refuse a
   workflow whose interactive block is hard-invalid, before the user reaches a
   paused block and a broken panel. Hard errors make the workflow invalid;
   advisories use the existing `Warning:` prefix convention that
   `src/scistudio/ai/agent/mcp/tools_workflow/read.py:204-250` already honours.

4. **Surface 3 — PostToolUse hook.** Add a provisioned hook modelled on
   `src/scistudio/agent_provisioning/templates/hook_enforce_concrete_port_types.py`
   that stderr-warns right after a write. **Its matcher must cover panel `.js`
   and `.mjs` files.** The existing block-write hook regex is
   `(?:^|/)blocks/[^/]+\.py$`
   (`hook_enforce_list_blocks_before_block_write.py:32`), so a hand-written
   panel module is currently touched by no hook at all. Register it in
   `src/scistudio/agent_provisioning/hooks.py` following the existing pattern.

5. Tests for every check at both severities, and one test per surface.

6. Docs. Update `docs/package-development/blocks.md` if this changes what a
   package author must satisfy. Adding a provisioned hook changes AI-runtime
   behavior, so explicitly check whether these need updates and land the update
   or an N/A rationale: `docs/ai-developer/rules.md`,
   `docs/ai-developer/specific_rules/gated-workflow.md`,
   `docs/ai-developer/specific_rules/agent-dispatch.md`,
   `docs/ai-developer/templates/*dispatch*.md`. Editing anything under
   `docs/ai-developer/**` requires `--governance-touch true` in your ledger.

## Out Of Scope — Do Not Do These

- Do not execute the panel module. The backend depends on no JS runtime
  (`shutil.which` is used widely but never for `node`) and this task must not
  introduce one.
- Do not add a `scistudio validate-block` CLI entry point. The embedded agent
  is denied the CLI by `hook_deny_scistudio_cli.py`, so it would go unused.
- Do not add a new MCP tool. The owner's explicit reason: a tool the agent must
  remember to call is a tool the agent will not call. The three surfaces above
  are mounted on paths the agent cannot route around.

## Required Tests And Checks

- Targeted pytest for the new validation module and each surface.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr` to run
  tier-selected checks and reconcile the gate ledger before PR creation
  (receipt behavior is folded into the ledger per ADR-042 Addendum 6; there is
  no separate `gate_receipt` command)
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2196"` before PR creation
- `python scripts/scistudio_pr_create.py` for the final PR (do not use
  `gh pr create` directly)
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr <url> --pr-body-file <path>` after PR is created

This task changes hook and AI-runtime behavior — the AI-docs impact check above
is required, not optional.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results.
- Checklist rows updated.
- PR number or commit.
- Confirmation that you requested `admin-approved:core-change`.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The shared validation cannot be placed without a circular import.
- You believe a check cannot be made reliable statically — report it rather
  than shipping a false hard error.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- CI or local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
```
