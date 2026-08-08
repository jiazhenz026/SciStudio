---
title: "ADR-053 Work Import Dispatch Prompts"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 34
  - 42
  - 53
related_specs:
  - adr-053-work-import
language_source: en
---

# ADR-053 Work Import Dispatch Prompts

Filled dispatch prompts for the ADR-053 spec 2 ("Bring in my work") dispatch.
Checklist: `docs/planning/adr-053-work-import-checklist.md`.

Templates used:

- Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
- Audit with context:
  `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
- Audit no context:
  `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## A1 — Availability Probe (#2000)

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-053 spec 2 ("Bring in my work") in full; this
  agent owns the graded agent availability probe.
- Task kind: feature
- Persona: implementer
- Issue: #2000
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2000
- Umbrella PR: #2028 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-work-import
- Agent branch: feat/2000-work-import-availability
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-wi-a1
- Gate record: create your own with `gate_record init` on your branch
- Checklist: docs/planning/adr-053-work-import-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2000` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-work-import.md — FR-031 to FR-036 are your requirements
- docs/adr/ADR-053.md §5.2
- docs/specs/adr-034-multi-provider-agent-chat.md — the registry you build on

## Scope

You own only:

- src/scistudio/ai/agent/availability.py (new)
- src/scistudio/api/routes/ai.py (extend with the new endpoint)
- tests/api/test_agent_availability.py (new)
- frontend/src/lib/api/agentAvailability.ts (new) and its test
- your own rows in docs/planning/adr-053-work-import-checklist.md §8

You must not touch:

- frontend/src/components/** — A4 owns the dialog and the toolbar
- src/scistudio/ai/work_import/** — A2 owns it
- src/scistudio/api/routes/work_import.py and src/scistudio/api/routes/ai_pty/**
  — A3 owns them
- docs/specs/** — A2 owns the only permitted spec edits
- docs/ai-developer/** — governance surface, excluded from this dispatch

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. Three other implementation agents are
  working in parallel on the same feature.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`. Run python with `PYTHONPATH=./src`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- MUST target your PR to track/adr-053-work-import, never to main.
- MUST NOT merge any PR.
- Edit only your checklist rows (§8 of the checklist).
- Record every completed row with a PR, commit, test, report, or gate evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo. Use `TODO(#NNN): <reason>` and cite
an issue, ADR, spec, or follow-up ticket. Do not leave hidden V1, MVP, or later
work. The owner has set a complete-delivery goal: nothing in FR-031 to FR-036
may be deferred.

Known deferred items:

- N/A for this track.

## Work To Do

1. Read `src/scistudio/ai/agent/providers_registry.py` and
   `src/scistudio/api/routes/ai.py`. `GET /api/ai/status` already returns, per
   provider, `{name, available, version, logged_in, label}`. Do NOT build a
   second discovery path (FR-032).
2. Create a shared availability module resolving each provider to exactly one of
   `not_installed`, `not_authenticated`, `call_failed`, `ready` (FR-031).
   `available: false` maps to `not_installed`; `available: true, logged_in:
   false` maps to `not_authenticated` (FR-032).
3. Separate `call_failed` from `ready` with a **live minimal call** to the
   provider CLI (FR-033). A `--version` success and a credential file existing
   do not establish that a call will succeed; this step is the entire point of
   the issue, because it is what catches the authenticated-but-out-of-quota
   user. Keep the call as small and as cheap as the provider allows.
4. `call_failed` MUST report the underlying cause and MUST NOT emit reinstall
   guidance (FR-034). Telling a correctly configured user to reinstall software
   they are already running sends them to fix something that is not broken.
5. The probe MUST NOT block its caller. Probe providers concurrently with a
   timeout; a slow or hanging provider degrades to a reported state, never to a
   stuck surface (FR-035). Reuse the concurrency approach `GET /api/ai/status`
   already uses.
6. Build it as a shared module, not as a Bring In My Work private helper — ADR-053
   §5.2 names the Learning Center agent-setup entry as another consumer (FR-036).
7. Expose `GET /api/ai/availability` returning exactly the manager-fixed
   contract C1 in checklist §7.1. Do not invent a different response shape;
   agent A4 is writing its consumer against C1 in parallel.
8. Add `frontend/src/lib/api/agentAvailability.ts` exporting
   `fetchAgentAvailability()` and the types `AgentAvailabilityState`,
   `ProviderAvailability`, `AgentAvailabilityResponse`. Keep every availability
   type in this module — do not add them to `frontend/src/store/types.ts`, which
   A4 is editing.
9. Write `tests/api/test_agent_availability.py` covering all four states,
   explicitly including authenticated-but-failing, plus a hanging-probe case
   proving the probe degrades to a reported state rather than blocking, plus the
   aggregate-state ranking from C1.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/api/test_agent_availability.py -q`
- `npm --prefix frontend test -- agentAvailability`
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/track/adr-053-work-import --head HEAD`
  to run tier-selected CI-equivalent checks and reconcile the gate ledger
  before PR creation. **Pass `--base` explicitly.** These are stacked branches:
  `resolve_default_base()` falls back to `origin/main` when neither `--base`
  nor `SCISTUDIO_GATE_BASE` is set, which pulls the umbrella's own commits
  into your observed diff and fails `scope.out-of-scope` on files you never
  touched. `export SCISTUDIO_GATE_BASE=origin/track/adr-053-work-import` also
  covers the pre-commit and commit-msg hooks, which take no `--base`
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2000"` before PR creation
- `python scripts/scistudio_pr_create.py --base track/adr-053-work-import` for
  the PR (do not use `gh pr create` directly)
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr <url> --pr-body-file <path>` after the PR is created
- Sentrux: record MCP availability or the CLI fallback in your ledger.

If the task changes wrapper, hook, gate-record, receipt, CI, or AI-runtime
behavior, check whether these docs need updates and record updated paths or
N/A rationale: `docs/ai-developer/rules.md`,
`docs/ai-developer/specific_rules/gated-workflow.md`,
`docs/ai-developer/specific_rules/agent-dispatch.md`, and
`docs/ai-developer/templates/*dispatch*.md`.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results.
- Checklist rows updated.
- PR number or commit.
- Any blocker or scope issue.
- The exact response payload your endpoint returns, so the manager can confirm
  it matches contract C1.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- Contract C1 cannot be satisfied as written.
- A live minimal call cannot be made safely or cheaply for some provider.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- CI or local checks fail for unclear reasons.
- You cannot add/update required tests.
```

## A2 — Brief Template And Composition (#2002)

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-053 spec 2 ("Bring in my work") in full; this
  agent owns the agent task brief and the spec corrections.
- Task kind: feature
- Persona: implementer
- Issue: #2002
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2002
- Umbrella PR: #2028 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-work-import
- Agent branch: feat/2002-work-import-brief
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-wi-a2
- Gate record: create your own with `gate_record init` on your branch
- Checklist: docs/planning/adr-053-work-import-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2002` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-work-import.md — §4.6 is the artefact you transcribe;
  FR-021, FR-023, FR-026 are your requirements
- docs/adr/ADR-053.md §5

## Scope

You own only:

- src/scistudio/ai/work_import/__init__.py (new)
- src/scistudio/ai/work_import/context.py (new)
- src/scistudio/ai/work_import/brief.py (new)
- src/scistudio/ai/work_import/brief_template.md (new)
- tests/ai/test_work_import_brief.py (new)
- docs/specs/adr-053-work-import.md — three corrections only, all outside §4.6
- your own rows in docs/planning/adr-053-work-import-checklist.md §9

You must not touch:

- docs/specs/adr-053-work-import.md §4.6 (the brief body inside the fenced
  markdown block). Issue #2017 is editing that section; changing it here creates
  a merge conflict the owner explicitly asked to avoid.
- docs/adr/ADR-053.md — the ADR revision already landed in PR #2006
- src/scistudio/api/** — A1 and A3 own the API surface
- frontend/** — A1 and A4 own it
- docs/ai-developer/** — governance surface, excluded from this dispatch

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. Three other implementation agents are
  working in parallel on the same feature.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`. Run python with `PYTHONPATH=./src`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- MUST target your PR to track/adr-053-work-import, never to main.
- MUST NOT merge any PR.
- Edit only your checklist rows (§9 of the checklist).
- Record every completed row with a PR, commit, test, report, or gate evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo. Use `TODO(#NNN): <reason>` and cite
an issue, ADR, spec, or follow-up ticket. The owner has set a complete-delivery
goal: nothing in your scope may be deferred. The spec's existing
`TODO(#2012)` stays deferred and is not yours to resolve.

Known deferred items:

- `TODO(#2012)` — suggest a matching package instead of authoring duplicate
  types. Stays deferred; do not implement it.
- `#2013` — previewer-authoring skill. The brief works around its absence; do
  not add the skill.

## Work To Do

1. Transcribe the markdown block in `docs/specs/adr-053-work-import.md` §4.6
   into `src/scistudio/ai/work_import/brief_template.md` **verbatim**. FR-026
   requires the composed brief to match that text exactly outside the
   substituted answers section. Do not paraphrase, reflow, re-title, or
   "improve" any sentence. It is given as literal text precisely so no
   reconstitution step can drift from it.
2. Implement `ImportSessionContext` in `context.py` with exactly the fields in
   the manager-fixed contract C2 (checklist §7.2). A3 and A4 are writing
   producers of this shape in parallel; do not rename fields.
3. Implement `compose_brief(context) -> str` in `brief.py`. It substitutes only
   at the `{...}` placeholders §4.6 shows, in the "What they told us" section.
4. Skipped questions MUST be conveyed as skipped, never omitted (FR-021), so the
   agent can tell "the user did not say" from "the user said nothing applies".
   §4.6 supplies the exact skip wording for each question — use it.
5. Every collected answer MUST reach the brief (FR-023). No answer the dialog
   collects may be silently dropped.
6. Layering: `scistudio.ai.work_import` is a leaf. It MUST NOT import from
   `scistudio.api` or `scistudio.blocks`. Check `pyproject.toml`'s
   import-linter contracts before you finish.
7. Correct three factual defects in `docs/specs/adr-053-work-import.md`, all
   outside §4.6:
   a. **FR-012** currently says the personal-library destination "requires the
      write path defined by the ADR-053 personal tool library spec (its
      FR-006)". That is false: §4.6 instructs the agent to write
      `~/.scistudio/blocks/` and `~/.scistudio/types/` directly with its shell,
      so no endpoint is involved. Rewrite it to state that the personal-library
      destination is written directly by the in-session agent, that this spec
      defines no write path, and that it does not depend on the personal tool
      library spec's write endpoint. Owner directive, 2026-08-07.
   b. **`#2003` staleness.** §4.1 says "Provider discovery already exists and is
      not merged yet" and "it is a dependency that has not landed"; §4.5 carries
      the risk "The dependency is unmerged. T-002 builds on #2003"; §4.3 T-002
      depends on "#2003 merged". PR #2003 merged on 2026-08-07. Correct every
      such statement to reflect that the registry has landed. Owner directive,
      2026-08-07.
   c. **Wrong FR cross-references.** §4.4's verification table and the §3 Key
      Entities table cite FR numbers that do not match the requirements they
      name — for example "Preset grouping (FR-015)" where FR-014 defines the
      presets, "Question 2 conditionality (FR-017, FR-018)" where FR-016 and
      FR-017 define it, "Availability states (FR-027, FR-029)" where FR-031 and
      FR-033 define them, and the Key Entities row citing FR-028/FR-029/FR-032
      for availability. Audit every FR reference outside §4.6 against the
      requirement it names and correct the ones that point at the wrong
      requirement. Change only the reference, never the requirement text.
8. Write `tests/ai/test_work_import_brief.py` covering: the composed brief
   matches the template verbatim outside the substituted section; each question
   renders with its own text, its examples, and its preset options, so the agent
   reads answers in the context they were given; a skipped question renders as
   explicitly skipped rather than omitted; both destination tiers render their
   own guidance; every context field **that §4.6 gives a substitution point**
   reaches the output. Do **not** assert that `provider` and `permission_mode`
   appear in the brief: §4.6 has no placeholder for either, FR-026 forbids
   adding one, and FR-044 sends both to the spawn rather than the brief. They
   ride on the context for the endpoint's use only.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/ai/test_work_import_brief.py -q`
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr`
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2002"` before PR creation
- `python scripts/scistudio_pr_create.py --base track/adr-053-work-import` for the PR
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr <url> --pr-body-file <path>` after the PR is created
- Docs: your spec edit is a docs change; record it with
  `gate_record amend --docs-updated docs/specs/adr-053-work-import.md`.
- Sentrux: record MCP availability or the CLI fallback in your ledger.

If the task changes wrapper, hook, gate-record, receipt, CI, or AI-runtime
behavior, check whether these docs need updates and record updated paths or
N/A rationale: `docs/ai-developer/rules.md`,
`docs/ai-developer/specific_rules/gated-workflow.md`,
`docs/ai-developer/specific_rules/agent-dispatch.md`, and
`docs/ai-developer/templates/*dispatch*.md`.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results.
- Checklist rows updated.
- PR number or commit.
- Any blocker or scope issue.
- A diff of the three spec corrections, so the manager can confirm §4.6 is
  untouched.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- A §4.6 sentence appears wrong or contradictory. Report it; do not fix it.
- The verbatim requirement conflicts with lint, formatting, or docs checks.
- Contract C2 cannot be satisfied as written.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- You cannot add/update required tests.
```

## A3 — Session Endpoint And Spawn (#2001 backend)

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-053 spec 2 ("Bring in my work") in full; this
  agent owns the backend session endpoint and the agent session spawn.
- Task kind: feature
- Persona: implementer
- Issue: #2001
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2001
- Umbrella PR: #2028 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-work-import
- Agent branch: feat/2001-work-import-session
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-wi-a3
- Gate record: create your own with `gate_record init` on your branch
- Checklist: docs/planning/adr-053-work-import-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2001` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-work-import.md — FR-022 to FR-030 are your requirements
- docs/adr/ADR-034 and docs/specs/adr-034-multi-provider-agent-chat.md — the
  provider registry and the frozen PTY route
- docs/adr/ADR-035 §3.10 — the engine-initiated PTY tab path you reuse

## Scope

You own only:

- src/scistudio/api/routes/work_import.py (new)
- src/scistudio/api/app.py — the router include line only
- src/scistudio/api/routes/ai_pty/** — only what the work-import spawn and join
  require, under the constraint below
- tests/api/test_work_import_session.py (new)
- your own rows in docs/planning/adr-053-work-import-checklist.md §10

You must not touch:

- frontend/** — A4 owns the dialog, the toolbar, and the store
- src/scistudio/ai/work_import/** — A2 owns the brief, the context dataclass,
  and `compose_brief`; import them, do not write them
- src/scistudio/api/routes/ai.py — A1 owns it
- docs/specs/** — A2 owns the only permitted spec edits
- docs/ai-developer/** — governance surface, excluded from this dispatch

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. Three other implementation agents are
  working in parallel on the same feature.
- A2 is writing `src/scistudio/ai/work_import/` in parallel. Its interface is
  fixed by contract C2 in checklist §7.2 — write your code against C2 and stub
  it locally if A2 has not landed yet. Do not create your own copy of
  `ImportSessionContext`.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`. Run python with `PYTHONPATH=./src`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- MUST target your PR to track/adr-053-work-import, never to main.
- MUST NOT merge any PR.
- Edit only your checklist rows (§10 of the checklist).

## TODO And Deferral Rule

Deferred work must be tracked in the repo. Use `TODO(#NNN): <reason>` and cite
an issue, ADR, spec, or follow-up ticket. The owner has set a complete-delivery
goal: nothing in FR-022 to FR-030 may be deferred.

Known deferred items:

- N/A for this track.

## Work To Do

1. Read `src/scistudio/api/routes/ai_pty/engine.py`, `websocket.py`, and
   `_state.py` before designing anything. The AI Block already spawns a PTY
   from the server side with a prompt delivered as a positional CLI argument
   (`open_engine_initiated_tab`, `_spawn(..., prompt=...)`), and the frontend
   joins that PTY over the existing WS route. FR-022 requires you reuse this
   mechanism rather than introduce a second way to run an agent.
2. Implement `POST /api/work-import/sessions` exactly per manager-fixed contract
   C3 (checklist §7.3). A4 is writing the consumer against C3 in parallel; do
   not change the shape.
3. Order of operations is fixed by FR-024: validate the request, compose the
   brief with A2's `compose_brief`, write the brief file and close it, **then**
   spawn. The session's opening message names a file; if spawn races the write,
   the agent reads nothing or half a brief and the session is unrecoverable,
   because it has no other source of instructions. Prove the ordering in a test,
   not by inspection.
4. Write the brief under the project's `.scistudio/` directory (FR-027), which
   is already in the default project `.gitignore` as per-machine runtime state.
   Verify that claim against the actual project template rather than trusting
   it; if it is not ignored, stop and report.
5. One brief file per session (FR-030). Concurrent sessions in one project must
   not overwrite each other's instructions, and a surviving brief lets a user
   see what their agent was actually told.
6. The visible session-start message is a **single line** naming the brief file
   (FR-028). The agent reads the brief itself; a user watching the terminal sees
   one sentence rather than the full instruction set.
7. Delivery MUST NOT depend on a provider's system-prompt capability (FR-029).
   Only `FLAG_FILE` providers can carry a hidden per-session prompt; `codex`,
   `kimi-code`, and both Qoder channels are `AMBIENT`. Routing through a file
   plus a pointer gives every provider identical behaviour. Do not touch
   `compose_system_prompt` — this feature adds a brief file, not a second
   prompt-assembly path.
8. Validate `permission_mode` in the backend spelling `"safe" | "bypass"`. The
   frontend union is `"safe" | "dangerous"`; A4 maps at the request boundary.
   Pin your side with a test (checklist §7.4).
9. Make the frontend able to join the PTY you pre-spawned. **Constraint:** the
   user-launched route in `ai_pty/websocket.py` is frozen by ADR-034. Its
   engine-initiated join branch currently recognises a pre-spawned PTY only by
   `_engine_block_run_id`, which is AI-Block-specific. Extending that predicate
   so a work-import tab joins its own pre-spawned PTY is acceptable **only if**
   the user-launched spawn contract — query parameters, spawn semantics, error
   frames, cap behaviour — is unchanged and you add a regression test pinning it.
   Do not attach AI-Block semantics (`_engine_tab_to_run`,
   `_engine_run_to_run_dir`, block cancel/done frames) to a work-import tab. If
   you conclude a broader change to that route is required, **stop and report to
   the manager** rather than proceeding.
10. Write `tests/api/test_work_import_session.py` covering: the brief exists and
    is complete before spawn; two sessions in one project get distinct brief
    files; the brief lands under `.scistudio/` and is ignored by the default
    project ignore file; the opening message is exactly one line and names the
    brief; delivery is identical for a `FLAG_FILE` and an `AMBIENT` provider;
    the permission-mode spelling is validated and a bad value is rejected;
    user-launched PTY behaviour is unchanged.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/api/test_work_import_session.py -q`
- `PYTHONPATH=./src python -m pytest tests/api -k "pty or ai_pty" -q` — prove
  you did not regress the frozen route
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr`
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2001"` before PR creation
- `python scripts/scistudio_pr_create.py --base track/adr-053-work-import` for the PR
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr <url> --pr-body-file <path>` after the PR is created
- Sentrux: record MCP availability or the CLI fallback in your ledger.

If the task changes wrapper, hook, gate-record, receipt, CI, or AI-runtime
behavior, check whether these docs need updates and record updated paths or
N/A rationale: `docs/ai-developer/rules.md`,
`docs/ai-developer/specific_rules/gated-workflow.md`,
`docs/ai-developer/specific_rules/agent-dispatch.md`, and
`docs/ai-developer/templates/*dispatch*.md`.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results.
- Checklist rows updated.
- PR number or commit.
- Any blocker or scope issue.
- Exactly what you changed under `ai_pty/`, and the evidence that the
  user-launched route still behaves identically.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The ADR-034 freeze on the user-launched PTY route blocks the join.
- `.scistudio/` turns out not to be gitignored in the project template.
- Contract C2 or C3 cannot be satisfied as written.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- You cannot add/update required tests.
```

## A4 — Toolbar Entry And Dialog (#2001 frontend)

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-053 spec 2 ("Bring in my work") in full; this
  agent owns the toolbar entry and the framing dialog.
- Task kind: feature
- Persona: implementer
- Issue: #2001
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2001
- Umbrella PR: #2028 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-work-import
- Agent branch: feat/2001-work-import-dialog
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-wi-a4
- Gate record: create your own with `gate_record init` on your branch
- Checklist: docs/planning/adr-053-work-import-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2001` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-work-import.md — FR-001 to FR-021 and FR-037 to FR-044 are
  your requirements; §2 User Stories 1 to 4 are your acceptance scenarios
- docs/adr/ADR-053.md §4

## Scope

You own only:

- frontend/src/components/BringInMyWorkDialog.tsx and a
  BringInMyWorkDialog.parts/ directory if the file would otherwise grow large
- frontend/src/components/Toolbar.tsx and frontend/src/components/Toolbar.parts/**
- frontend/src/store/terminalTabsSlice.ts, frontend/src/store/types.ts,
  frontend/src/store/uiSlice.ts
- frontend/src/components/AIChat/** — only what attaching the session tab needs
- frontend/src/lib/api/workImport.ts (new)
- the matching tests under frontend/src/components/__tests__/ and
  frontend/src/store/__tests__/
- your own rows in docs/planning/adr-053-work-import-checklist.md §11

You must not touch:

- src/scistudio/** — A1, A2, and A3 own the backend
- frontend/src/lib/api/agentAvailability.ts — A1 owns it; import it
- frontend/src/components/AIChat/SetupScreen.parts/ProviderPicker.tsx and
  PermissionModePicker.tsx — FR-042 requires you **reuse** these unchanged, not
  fork or modify them. If one genuinely cannot be reused as-is, stop and report.
- docs/specs/** — A2 owns the only permitted spec edits
- docs/ai-developer/** — governance surface, excluded from this dispatch

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. Three other implementation agents are
  working in parallel on the same feature.
- A1 is writing `frontend/src/lib/api/agentAvailability.ts` in parallel. Its
  interface is fixed by contract C1 in checklist §7.1 — write your consumer
  against C1 and stub it locally if A1 has not landed yet.
- A3 is writing `POST /api/work-import/sessions` in parallel. Its interface is
  fixed by contract C3 in checklist §7.3 — write your caller against C3.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- MUST target your PR to track/adr-053-work-import, never to main.
- MUST NOT merge any PR.
- Edit only your checklist rows (§11 of the checklist).

## TODO And Deferral Rule

Deferred work must be tracked in the repo. Use `TODO(#NNN): <reason>` and cite
an issue, ADR, spec, or follow-up ticket. The owner has set a complete-delivery
goal: no requirement in your range may be deferred, and no question may be
dropped "for now".

Known deferred items:

- `TODO(#2012)` — the spec defers suggesting a matching package instead of
  authoring duplicate types. Presets are context only; do not use them as a
  routing mechanism (FR-015).

## Work To Do

1. Add a permanently available toolbar entry labelled **"Bring in my work"**
   (FR-001). It MUST NOT be gated on Learning Center progress, project count, or
   elapsed time — the threshold in ADR-053 §4.2 governs when the product
   *volunteers* the capability, never whether it can be reached. Enabled when a
   project is open, disabled otherwise (FR-002), because a session writes blocks
   into a project.
2. Build the dialog. Page one collects: source location as a text field with a
   browse control that accepts a **directory**, not only a file (FR-008); an
   explicit **"I don't have a codebase"** option (FR-009) that disables or hides
   the source field while leaving every other field in effect (FR-010);
   destination tier as a single choice between this project only and the
   personal library (FR-011); provider selection (FR-040); permission mode
   (FR-041).
3. FR-042: **reuse** `ProviderPicker` and `PermissionModePicker` from
   `AIChat/SetupScreen.parts/`. A divergent copy would drift the moment a
   provider is added or a permission mode changes. When exactly one provider is
   usable, preselect it rather than presenting a one-option choice, and keep the
   control visible so the user can see which agent will run (FR-043).
4. The caveat (FR-037): state, before the session can start, that the agent can
   make mistakes, that it has been instructed to check that the result matches
   the original logic, that this does not guarantee the logic is identical, and
   that the user should review the result themselves. It MUST NOT be collapsed
   into a dismissible notice or placed where a user can start a session without
   having seen it (FR-038), and it MUST NOT be weakened or omitted in
   no-codebase mode. This is the product's only mechanism for producing an
   appropriately sceptical reader; treat it as a feature requirement, not a
   disclaimer.
5. The four questions, per FR-013 to FR-021. Read the preamble above FR-013 in
   the spec before writing them: each question also **names a capability the
   user has never heard of**, so the dialog is a discovery surface as well as a
   data-collection one. Do not optimise the wording purely as data collection.
   - Q1, data kinds: multi-select presets plus free text (FR-013). Presets cover
     both generic shapes (array, table/dataframe, series) and domain kinds
     (image, time series, spectrum, multi-omics, spatial omics), **visually
     grouped** so it is clear both may be selected (FR-014).
   - Q2, workflow description: free text, skippable **only when a source
     location was given**; required in no-codebase mode with wording that asks
     for more detail (FR-016, FR-017).
   - Q3, interaction wishes: free text, skippable, and it MUST carry concrete
     examples such as subtracting background or editing a segmentation mask —
     without them the question is too abstract to answer (FR-018).
   - Q4, other software: free text, skippable (FR-019).
   - Skips must read as a legitimate choice, not an abandoned field (FR-020),
     and must reach the request marked as skipped rather than omitted (FR-021),
     so the agent can tell "the user did not say" from "nothing applies".
6. FR-006 and FR-007 are hard constraints on every question you write: no
   question may require SciStudio knowledge (which data types, whether something
   should be interactive, how ports are shaped) and none may require
   software-development knowledge (which environment, how dependencies install,
   which interpreter). The dialog asks only about the user's own world. A
   first-day scientist must be able to answer every field.
7. Availability (FR-005): call `fetchAgentAvailability()` per contract C1. When
   **no** provider is usable, show that state's guidance in place of a start
   action. When some are usable and others are not, let the user proceed with a
   usable one rather than blocking. Never render a stuck dialog waiting on a
   probe (FR-035) — the dialog renders with a reported state.
8. Starting the session: POST to `/api/work-import/sessions` per contract C3,
   mapping the frontend permission mode `"safe" | "dangerous"` to the backend
   `"safe" | "bypass"` (checklist §7.4). Add the returned `tab_id` as a terminal
   tab in `running` state carrying the returned provider and permission mode,
   and connect it to the existing PTY WS route so it joins the pre-spawned
   session. The result MUST be an ordinary chat session the user can talk to,
   redirect, and end like any other (FR-025) — a preconfigured starting point,
   not a modal wizard.
9. Tests, covering at minimum: the toolbar entry is enabled with a project open
   and disabled without one; the caveat is present and not bypassable in both
   modes; the no-codebase option disables the source field and makes Q2
   required; preset groups render and both groups are selectable; skipped
   questions are distinguishable from answered ones in the submitted payload;
   one usable provider is preselected and still visible; two usable providers
   are both choosable; the chosen provider and permission mode reach the
   request; each availability state shows its own guidance and `call_failed`
   never suggests reinstalling.

## Required Tests And Checks

- `npm --prefix frontend test -- BringInMyWorkDialog Toolbar workImport`
- `npm --prefix frontend run lint` and the repository's type check
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr`
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2001"` before PR creation
- `python scripts/scistudio_pr_create.py --base track/adr-053-work-import` for the PR
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr <url> --pr-body-file <path>` after the PR is created
- A frontend smoke check of the toolbar entry and the dialog in both modes.
- Sentrux: record MCP availability or the CLI fallback in your ledger.

If the task changes wrapper, hook, gate-record, receipt, CI, or AI-runtime
behavior, check whether these docs need updates and record updated paths or
N/A rationale: `docs/ai-developer/rules.md`,
`docs/ai-developer/specific_rules/gated-workflow.md`,
`docs/ai-developer/specific_rules/agent-dispatch.md`, and
`docs/ai-developer/templates/*dispatch*.md`.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results.
- Checklist rows updated.
- PR number or commit.
- Any blocker or scope issue.
- The exact caveat copy you shipped and where it sits in the flow.
- The exact request payload the dialog sends, so the manager can confirm C3.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- `ProviderPicker` or `PermissionModePicker` cannot be reused unchanged.
- A question cannot be written without requiring SciStudio or
  software-development knowledge.
- Contract C1 or C3 cannot be satisfied as written.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- You cannot add/update required tests.
```

## AU1 — Audit With Context

```markdown
[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: with-context
- Issue: #2001
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2001
- Owner request: Implement ADR-053 spec 2 ("Bring in my work") in full and
  deliver one reviewable PR.
- Umbrella PR: #2028 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-work-import
- Audit branch: audit/2001-work-import-with-context
- Audit worktree: C:/Users/jiazh/workspace/SciStudio-wt-wi-au1
- Gate record: create your own with `gate_record init` on your branch
- Checklist: docs/planning/adr-053-work-import-checklist.md
- PRs or commits to audit: the integrated state of track/adr-053-work-import
- Audit report path: docs/audit/2026-08-07-adr-053-work-import-with-context.md

## Required Reading

Read and follow:

- The GitHub issues `#2000`, `#2001`, `#2002` and all owner instructions in them.
- The manager checklist.
- The PR descriptions, changed files, and CI results for the audited work.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/personas/audit-reviewer.md
- docs/specs/adr-053-work-import.md and docs/adr/ADR-053.md

## Audit Goal

Verify the claimed work against the issues, checklist, governing docs, code,
tests, gate evidence, and CI.

Report findings first. Use severity:

- P1: blocks merge or breaks contract.
- P2: should fix before completion.
- P3: improvement or follow-up.

## Scope

Audit these claims:

- Every functional requirement FR-001 to FR-044 in
  `docs/specs/adr-053-work-import.md` is implemented, or has a tracked,
  owner-visible reason it is not. The owner set a complete-delivery goal, so an
  untracked gap is a P1.
- Success criteria SC-001 to SC-011 in the same spec hold against the
  implementation.
- The four availability states resolve correctly, `call_failed` requires a live
  call, and no state emits another state's guidance — in particular an
  authenticated user whose call failed is never told to reinstall.
- The composed brief matches spec §4.6 verbatim outside the substituted answers
  section, and skipped questions render as skipped rather than omitted.
- The brief is written under `.scistudio/`, one file per session, complete
  before the session spawns.
- The caveat is present, not dismissible, and shown before a session can start
  in both codebase and no-codebase modes.
- The three spec corrections landed and §4.6 is byte-identical to its state
  before this dispatch.
- Scope compliance: no agent wrote outside its assigned write set, and no
  personal-library write path or endpoint was created.

Audit these files or surfaces:

- src/scistudio/ai/agent/availability.py and src/scistudio/api/routes/ai.py
- src/scistudio/ai/work_import/**
- src/scistudio/api/routes/work_import.py and src/scistudio/api/routes/ai_pty/**
- frontend/src/components/BringInMyWorkDialog*, Toolbar*, and the store changes
- frontend/src/lib/api/agentAvailability.ts and workImport.ts
- docs/specs/adr-053-work-import.md
- tests/api/test_agent_availability.py, tests/ai/test_work_import_brief.py,
  tests/api/test_work_import_session.py, and the frontend tests

Do not write feature code.
MUST write the audit report to the repository file named above.
MUST make the audit report available for merge into the final PR.
Only write the audit report and your assigned checklist audit rows.

## Coordination

- MUST work only on your assigned audit branch.
- MUST work only in your assigned audit worktree.
- MUST NOT use `pip install -e .`.
- MUST NOT merge any PR.
- MUST NOT fix implementation code unless the manager explicitly changes your
  role to fix agent.
- Edit only your checklist audit rows.

## Checks

Run or verify:

- `PYTHONPATH=./src python -m pytest tests/api/test_agent_availability.py tests/ai/test_work_import_brief.py tests/api/test_work_import_session.py -q`
- `PYTHONPATH=./src python -m pytest tests/api -k "pty or ai_pty" -q`
- `npm --prefix frontend test -- BringInMyWorkDialog Toolbar workImport agentAvailability`
- A frontend smoke check of the toolbar entry and dialog, or an N/A reason.
- Sentrux MCP or CLI, or an N/A reason.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md`

## Output Required

- Audit report path.
- Commit or PR that contains the audit report file.
- Findings ordered by severity.
- Checklist drift, if any.
- Scope drift, if any.
- Missing tests/docs/gate evidence, if any.
- CI status.
- Recommendation: pass, pass-with-fixes, or block.

## Stop Conditions

Stop and report back if:

- You need to change implementation code.
- Required evidence is unavailable.
- The audit scope conflicts with AGENTS.md, ADR, spec, or gate record.
```

## AU2 — Audit No Context

Recorded verbatim so a reviewer can verify what the no-context audit was
actually told. Committing it leaks nothing into that audit: the prompt is
context-free by construction, and the audit has already run.

- Audit mode: `no-context`
- Audit branch: `audit/2001-work-import-no-context`
- Audit worktree: `C:/Users/jiazh/workspace/SciStudio-wt-wi-au2`
- Audit report path: `docs/audit/2026-08-07-adr-053-work-import-no-context.md`

```markdown
[DISPATCH-TEMPLATE-V1: audit-no-context]

You are an independent audit reviewer. Work ONLY in your worktree. **Do not write feature code.**

## Persona and mode

- Persona: `audit_reviewer`
- Audit mode: **no-context**
- Branch under review: `track/adr-053-work-import` (also your PR base)
- Audit report path: `docs/audit/2026-08-07-adr-053-work-import-no-context.md`

## What no-context means here — read carefully

You are deliberately **not** being told what the implementing agents claimed, what any
planning checklist asserts, what the commit messages argue, or what any manager concluded.
Those are the artefacts most likely to make you agree with a wrong answer.

**You MUST NOT read, and MUST NOT let into your reasoning:**

- `docs/planning/adr-053-work-import-checklist.md` and
  `docs/planning/adr-053-work-import-dispatch-prompts.md`
- any GitHub issue or pull request body or comment
- `git log` commit messages on this branch, and `.workflow/records/**` gate ledgers
- `docs/audit/2026-08-07-adr-053-work-import-with-context.md`, if it appears

**You MAY and SHOULD use:** the committed source code, the committed tests, the committed
specifications and ADRs under `docs/`, generated facts under `docs/audit/latest/`, and any
tool output you run yourself.

Read the diff as `git diff origin/main...HEAD -- <paths>` so you see the change without
reading its commit messages.

## What you are auditing

A feature that lets a user bring existing work into SciStudio through a guided agent
session. Its surfaces, by path:

- `src/scistudio/ai/agent/availability.py` and the endpoints in `src/scistudio/api/routes/ai.py`
- `src/scistudio/ai/work_import/**`
- `src/scistudio/api/routes/work_import.py`, and the changes to `src/scistudio/api/routes/ai_pty/**`
- `frontend/src/components/BringInMyWorkDialog*`, `frontend/src/components/Toolbar*`,
  `frontend/src/store/**`, `frontend/src/lib/api/agentAvailability.ts`,
  `frontend/src/lib/api/workImport.ts`
- `tests/api/test_agent_availability.py`, `tests/ai/test_work_import_brief.py`,
  `tests/api/test_work_import_session.py`, and the frontend tests beside those components

The governing documents are `docs/specs/adr-053-work-import.md` and `docs/adr/ADR-053.md`.
Read them yourself and form your own view of what they require. Note that the spec itself
was modified in this change — judge whether each modification is *correct*, not merely
whether it was made.

## Your job

Independently determine whether the implementation does what the committed specification
says it should, and whether the tests would actually catch it if it did not.

Questions worth answering, though do not treat this as an exhaustive list — find what is
actually wrong:

1. Does every functional requirement in the spec have an implementation **and** a test that
   would fail if the implementation were wrong? Report each requirement you cannot trace to
   both.
2. Are there tests that assert something weaker than the requirement they claim to cover? A
   test asserting a file exists after a spawn does not establish that it existed *before* the
   spawn.
3. The spec requires a body of instruction text to be reproduced verbatim from one of its own
   sections. Verify byte-identity yourself.
4. The spec requires distinguishing states that a presence check cannot distinguish. Does the
   implementation actually make the distinction the spec demands, or does it approximate it?
5. Does any user-facing copy tell a user to do something that would not fix their problem?
6. One pre-existing route is marked frozen by an ADR. Determine which, whether it changed, and
   whether any observable behaviour of it differs.
7. Are the specification's own edits internally consistent with the rest of the specification
   and with the code?
8. Is there any error path that returns a 500 where a 4xx is correct, or that loses information
   the caller needs?
9. Does anything in the change create a file, endpoint, or write path that the specification
   says should not exist?

## Coordination

- MUST work only on your assigned audit branch and worktree. MUST NOT `pip install -e .`.
- MUST NOT merge any PR. MUST NOT fix implementation code.
- Write **only** the audit report file.
- Commit the report and push your branch. **Do not open a PR.**

## Checks to run

Run the test suites named above and the repository's own audit tooling, and report what you
observe. If some tests fail, determine for yourself whether the failures relate to this change
by reproducing them at `origin/main` — do not assume either way.

## Output Required

- Audit report path and the commit containing it.
- Findings ordered by severity: **P1** blocks merge or breaks a contract; **P2** should fix;
  **P3** improvement.
- Each finding with file:line and the evidence you gathered yourself.
- Requirements you could not trace to an implementation, a test, or both.
- **Recommendation: pass, pass-with-fixes, or block.**

## Stop Conditions

Stop and report if you need to change implementation code, if required evidence is
unavailable, or if the audit scope conflicts with AGENTS.md, an ADR, or a spec.
```

The operating-environment preamble each agent also received — worktree root, absolute
`PYTHONPATH`, the Windows commit trap, `SCISTUDIO_GATE_BASE` — is identical across
dispatches and is recorded in checklist §2.2 and §3.1.
