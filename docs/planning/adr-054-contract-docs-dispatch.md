---
title: "ADR-054 Phase A Contract Documentation Dispatch"
status: Draft
owners: ["@jiazhenz026"]
related_adrs: [49, 52, 54, 55]
language_source: en
---

# ADR-054 Phase A Contract Documentation Dispatch

[DISPATCH-TEMPLATE-V1: adr_author]

## Task Identity

- Repository: SciStudio.
- Owner request: implement ADR-054 Panels and MiniApps, adapting Phase A to ADR-055 enterprise features.
- Task kind: docs; persona: adr_author; issue: #2293.
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2293.
- Umbrella PR: #2353 `[DO NOT MERGE]`; protected branch: main.
- Umbrella branch: `codex/2296-adr054-coordination`.
- Agent branch: `codex/2293-panel-contract-docs`.
- Agent worktree: `.worktrees/adr054-contract-docs`.
- Gate record: `.workflow/records/2293-panel-contract-docs.json`.
- Checklist: `docs/planning/adr-054-panels-checklist.md` on the manager branch.

## Required Rules

Read issue #2293, owner decisions, AGENTS.md, common rules, gated workflow,
agent dispatch, docs-change, document-standards, the adr-author skill and persona.
Read ADR-049, ADR-052, ADR-054, both ADR-054 specs, and the manager enterprise
matrix. A preserves the current sidebar entry; D changes MiniApps/All Previewers.

## Scope

You own only your gate ledger and these documentation paths:

- `docs/planning/adr-049-package-validator/contracts/*.json`, narrowly for panel contract rows and the existing isolation row.
- `docs/planning/adr-054-contract-notes.md` and `docs/planning/adr-054-owner-doc-proposal.md`.
- `docs/user/reference/**` and `docs/user/llms.txt`, only through canonical generators and only if the integrated public surface changes the output.

Do not edit production code, tests, other ledgers, AI governance files, or
`docs/architecture/ARCHITECTURE.md`. Owner-controlled ADR edits are initially
proposal-only: prepare exact focused patches as text in the proposal document,
then return them for manager/owner review before applying. If another path is
needed, report it before editing.

## Coordination

Use only the assigned branch/worktree; do not share writable trees or use
`pip install -e .`. Do not revert sibling work. Deliver focused commits for
manager review and cherry-pick into `codex/2293-panels-phase-a`. The manager owns
the final PR to main closing #2293; do not create or merge a separate PR. Read
sibling implementation notes from their branches as needed. Do not spawn agents.
Return checklist evidence; the manager updates the shared checklist.

## TODO And Deferral Rule

Track deferrals in the repository with issue references. B core migrations are
#2294, C full author guides are #2295, D MiniApps are #2354. This dispatch lands
only A contract evidence. Do not mark B/C/D as implemented. Legacy removal,
Python preview reads, and notebook/sync remain tracked by #2288.

## Work To Do

1. Inspect the integrated A1/A3 implementation and A2 SDK/library notes. Add
   truthful ADR-049 contract table coverage for descriptor/discovery, unified
   routing, context authority, static token confinement, SDK bridge and validator
   symbols. Match the existing table schema and script inventory; distinguish
   runtime checks from still-planned package validator enforcement.
2. Update the PV-12-001 isolation wording only as needed to distinguish legacy
   preview assets from the new noncredentialed sandbox/token path. Preserve
   legacy requirements and all existing evidence. No invented ADR-049 addendum:
   the historical checklist named one that does not exist on this baseline.
3. Prepare exact focused ADR/spec proposed patches: move only now-existing A
   surfaces from planned_governs into governs in ADR-054 and the two specs;
   retain D-only planned surfaces. Keep Proposed/Draft status and no acceptance
   date. Record the owner's sidebar choice, existing ADR-055 seam adaptation,
   and the two explicitly tracked temporary compiled interactive core windows.
   Do not resolve the pending core-id override ambiguity without owner input.
4. Prepare architecture text only if needed, labeled as a proposal. Inventory
   the true author-facing Python changes. Do not invent a public panels Python
   API; A1 internals must stay internal. Regenerate public references with
   `scripts/docs/build_reference.py --generate-only` if output changes.
5. Record exact checks and unresolved owner decisions in contract notes. Send
   the protected-document proposal early so implementation checks can progress.

## Required Tests And Checks

- Initialize/plan/amend the gate before edits; docs-only implementation tests
  are N/A with a recorded rationale.
- Run `scripts/audit/check_package_contract_tables.py` using its supported CLI,
  and relevant doc validation through `gate_record check`.
- Run generated-reference checks if generation changed artifacts.
- Sentrux MCP is unavailable; record only actual gate-selected CLI evidence.
- Do not change wrapper/hook/gate/CI behavior. AI workflow docs updates are N/A.
- Manager owns integrated pre-PR check, finalize, gate-aware PR creation,
  post-PR provenance, and CI. Do not claim slice-level CI or overall completion.

## Output Required

Changed paths, focused commits, table/doc check results, exact protected-doc
proposal, implementation truth gaps, and checklist evidence. Continue the
independent in-scope work while waiting for an owner decision.

## Stop Conditions

Report before out-of-scope edits, unresolved owner-contract conflicts, unclear
check failures, missing implementation facts, or missing validation support.
Never weaken schema, documentation, or governance checks to clear a gate.
