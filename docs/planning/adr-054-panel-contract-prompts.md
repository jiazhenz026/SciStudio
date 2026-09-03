---
title: "ADR-054 Panel Contract Dispatch Prompts"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 48
  - 51
  - 54
language_source: en
---

# ADR-054 Panel Contract Dispatch Prompts

The filled dispatch prompts for the agents listed in
`docs/planning/adr-054-panel-contract-checklist.md` section 6. Each prompt is
filled from the template named in its heading. Prompts are appended as waves are
dispatched; a prompt is never edited after its agent has been dispatched.

## Manager decisions binding on every agent

These are manager rulings on questions the spec leaves to the implementer. They
are recorded here so the audit can check them rather than rediscover them.

- **D-001 — The rename keeps the Python compatibility surface importable.**
  `scistudio.previewers` remains an importable module that re-exports the
  renamed symbols, because FR-045 requires the `scistudio.previewers`
  entry-point group and its `get_previewers()` factory to keep being
  discovered, and a package that supplies that factory imports `PreviewerSpec`
  from that module path. FR-038 permits the retired word to survive in the
  compatibility shim, and this alias is part of it. It carries a deprecation
  note and the ADR-048 addendum's removal condition.
- **D-002 — What "the rename commit changes no behaviour" (SC-011) means
  here.** Files may be moved, and identifiers, imports, module paths, symbol
  names, and the mechanical spelling of a name inside a test may change. No
  assertion's meaning, no fixture behaviour, no control flow, and no test count
  may change. No test may be added or deleted in the rename commit.
- **D-003 — The rename does not touch user-visible copy.** Interface strings a
  person reads stay as they are; revising them belongs to `#2211`, the human
  documentation spec. The rename is a code rename.
- **D-004 — The rename does not change the HTTP wire.** Route paths and
  response field names keep their current spelling in the rename commit.
  Bringing the endpoints under the panel naming is FR-023 behaviour work owned
  by `W3-api`. The one exception is the FR-051 `capabilities` to `features`
  rename, which is explicitly required to land in the rename commit and is
  therefore renamed on both sides of the wire at once.
- **D-005 — The on-disk tier directories keep their names in the rename
  commit.** `~/.scistudio/previewers/`, `<project>/previewers/`, and
  `.scistudio/previewers.json` are read by projects that already exist on
  disk. FR-020 and FR-046 require them to keep working; carrying them over
  under the panel naming is behaviour work owned by `W2-core`.
- **D-006 — `docs/architecture/ARCHITECTURE.md` is not edited.** It is
  owner-controlled and outside this spec's scope. If a drift audit fails
  against it, report the failure to the manager; do not edit the file and do
  not weaken the audit.

---

## W1-rename

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 1, the unified panel contract; this
  agent delivers its first task, the vocabulary rename that every later task is
  written against.
- Task kind: refactor
- Persona: implementer
- Issue: #2229
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2229
- Umbrella PR: #2230 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-spec1-panel-contract
- Agent branch: refactor/2229-panel-rename
- Agent worktree: C:\Users\jiazh\workspace\SciStudio\.worktrees\w1-panel-rename
- Gate record: .workflow/records/2229-refactor-2229-panel-rename.json
  (create it yourself with `gate_record init`)
- Checklist: docs/planning/adr-054-panel-contract-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2229` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-054-panel-contract.md, in particular FR-038 to FR-041,
  FR-051, task T-001 in section 4.3, SC-011, and the "The rename runs first"
  paragraph in section 4.1.
- The manager decisions D-001 to D-006 in
  docs/planning/adr-054-panel-contract-prompts.md.

## Scope

You own the whole tree for one purpose only: the mechanical rename of the
previewer concept to the panel concept.

- src/scistudio/previewers/** -> src/scistudio/panels/**
- every Python import, symbol, and identifier that names the concept
- frontend/src/** file names, symbols, and identifiers that name the concept
- tests/previewers/** -> tests/panels/**, and every test identifier that names
  the concept

You must not touch:

- docs/architecture/**  (owner-controlled; D-006)
- docs/user/**, docs/package-development/**  (owned by #2211)
- src/scistudio/_skills/**, src/scistudio/_agent_reference/**
- src/scistudio/plot/runtime.py
- docs/planning/adr-054-panel-contract-checklist.md except your own rows
- any behaviour at all

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- Do NOT open a pull request. Push your branch; the manager integrates it into
  the umbrella branch.
- MUST NOT merge any PR.
- Edit only your checklist rows.
- Record every completed row with a commit, test, or gate evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- TODO(#2211): user-visible interface copy still says previewer; the human
  documentation revision owns it.

## Work To Do

This is T-001. Its whole value is that it is reviewable at its size because it
provably changes nothing. Work in this order.

1. Establish the baseline. Run, and record the result:
   `PYTHONPATH=./src python -m pytest tests/previewers tests/api/test_previewers.py
   tests/api/test_previewer_discovery.py tests/api/test_interactive_panels.py
   tests/architecture tests/adr052_contract -q --no-cov -p no:randomly`
   and the frontend suite for the previewer and interactive-panel surfaces.
   It is green on the branch point; if it is not, stop and report.
2. Rename the Python subsystem: `src/scistudio/previewers/` becomes
   `src/scistudio/panels/`. Use `git mv` so history follows.
3. Rename the Python symbols the concept names: `PreviewerSpec` becomes
   `PanelSpec`, and so on for every symbol, function, parameter, local, and
   docstring mention that names the concept. Keep the names of things that are
   not the concept.
4. Per D-001, leave `src/scistudio/previewers/__init__.py` in place as a thin
   module that re-exports the renamed symbols under their old names, with a
   deprecation docstring that says it exists for the `scistudio.previewers`
   entry-point group (FR-045) and will be removed under the ADR-048 addendum's
   condition. It must contain no logic of its own.
5. FR-051: the free-form `capabilities` tuple that carries feature tags such as
   table and sort becomes `features`, everywhere it is written and read,
   including the API response field and the frontend that reads it, so that the
   word capability is left free to name only the displaying or producing
   capability that later tasks introduce.
6. Rename the frontend files and symbols that name the concept. Move
   `frontend/src/components/DataPreview.parts/dynamicPreviewer.ts`,
   `previewerHostApi.ts`, the previewer store slices, the previewer palette,
   and their tests to the panel spelling. Do not merge, delete, or restructure
   anything; later tasks do that.
7. Move `tests/previewers/` to `tests/panels/` and update identifiers. Obey
   D-002: no assertion's meaning changes and no test is added or deleted.
8. Obey D-003, D-004 and D-005: user-visible copy, HTTP route paths, response
   field names other than the FR-051 rename, and the on-disk tier directory
   names are all left alone.
9. Update `tests/architecture/test_layer_deps.py` and the ADR-052 frozen
   public-symbol inventory only as far as the rename requires to keep them
   passing. If the inventory's stability markers cannot be carried across the
   rename mechanically, stop and report rather than guessing; deriving them is
   FR-041 and belongs to a later task.
10. Re-run the baseline commands from step 1. They must produce the same result
    as they did before the rename.
11. Produce, and include in your report, the list of every name you renamed as
    `old -> new`, and a statement of anything you deliberately left with the
    retired spelling and why.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/panels tests/api tests/architecture
  tests/adr052_contract -q --no-cov -p no:randomly`
- the frontend test suite for the renamed surfaces (`npm test` in `frontend/`,
  narrowed to the affected files, then the whole suite once)
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record init
  --task-kind refactor --persona implementer --runtime claude-code
  --branch refactor/2229-panel-rename --issue 2229
  --base-ref track/adr-054-spec1-panel-contract
  --owner-directive "<the owner request above>" --include "<your real scope>"`
  Recording `--base-ref` is mandatory: this branch is stacked on the track
  branch, and without it the gate measures your work against origin/main and
  reads other agents' commits as yours.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check
  --mode local --base track/adr-054-spec1-panel-contract --head HEAD`
- Do not run `gate_record finalize` and do not create a PR; the manager owns
  the final gate evidence and the PR.
- Sentrux: run it if the MCP or CLI is available; record explicitly if it is
  not.

If the task changes wrapper, hook, gate-record, receipt, CI, or AI-runtime
behavior, check whether these docs need updates and record updated paths or
N/A rationale: `docs/ai-developer/rules.md`,
`docs/ai-developer/specific_rules/gated-workflow.md`,
`docs/ai-developer/specific_rules/agent-dispatch.md`, and
`docs/ai-developer/templates/*dispatch*.md`.

## Output Required

Before reporting done, provide:

- Changed file paths, and the `old -> new` rename table.
- Tests/checks run and results, before and after.
- Checklist rows updated.
- The commit sha on `refactor/2229-panel-rename`, pushed.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- A rename cannot be made without changing behaviour.
- A test would have to change its meaning to keep passing.
- The ADR-052 stability markers cannot be carried across mechanically.
- The task conflicts with AGENTS.md, the ADR, the spec, or the gate record.
- CI or local checks fail for unclear reasons.
```
