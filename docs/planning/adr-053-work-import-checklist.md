---
title: "ADR-053 Work Import Agent Dispatch Checklist"
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

# ADR-053 Work Import Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Implement ADR-053 spec 2 — `docs/specs/adr-053-work-import.md`
  ("Bring in my work") — in full, via dispatched implementation and audit
  agents, ending in one reviewable final PR.
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#2000`, `#2001`, `#2002`
- Gate record: `.workflow/records/2000-adr-053-work-import.json`
- Branch/worktree plan: manager branch `track/adr-053-work-import` in
  `C:/Users/jiazh/workspace/SciStudio-wt-work-import`; agent branches use
  `<type>/<issue>-work-import-<slug>` with one dedicated worktree each. Agent
  branches are **not** named under `track/adr-053-work-import/` — git cannot
  create a ref below an existing branch ref of the same name.
- Protected branch: `main`
- Umbrella branch: `track/adr-053-work-import`
- Umbrella PR: `#2028`
- Umbrella PR title: `[DO NOT MERGE] ADR-053 spec 2: Bring in my work`
- Final PR target: `main`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`
- Filled dispatch prompts: `docs/planning/adr-053-work-import-dispatch-prompts.md`

## 2. Scope

- In scope:
  - `src/scistudio/ai/agent/availability.py` and its API surface (#2000)
  - `src/scistudio/ai/work_import/**` — brief template, context, composition (#2002)
  - `src/scistudio/api/routes/work_import.py` and the work-import PTY session
    spawn (#2001 backend half)
  - `frontend/src/components/BringInMyWorkDialog*` and the toolbar entry
    (#2001 frontend half)
  - `docs/specs/adr-053-work-import.md` — FR-012 correction, #2003 staleness,
    and the incorrect FR cross-references outside §4.6
  - `docs/planning/adr-053-work-import-*.md`
  - `docs/audit/2026-08-07-adr-053-work-import-*.md`
  - tests under `tests/api/**`, `tests/ai/**`, and the matching frontend tests
- Out of scope:
  - `docs/specs/adr-053-work-import.md` §4.6 (the brief body). #2017 edits it;
    touching it here creates a merge conflict. Permitted spec edits are
    confined to outside §4.6: FR-012, the stale `#2003` statements, and the
    incorrect FR cross-references.
  - `docs/adr/ADR-053.md` — the ADR revision already landed in PR #2006.
  - `docs/specs/adr-053-personal-tool-library.md` and its FR-006 write endpoint.
    The personal-library destination is written directly by the in-session
    agent's shell; this feature defines no write path and depends on no
    endpoint.
  - Static codebase scanning, candidate lists, batch selection UI — removed by
    the ADR revision.
  - Any system enforcement of the agent's verification step (FR-039).
  - Learning Center progress, thresholds, and the milestone unlock (#1999).
  - Provider configuration and the provider registry itself (ADR-034, #1994).
  - `docs/ai-developer/**` — governance surface, not in this dispatch.
- Protected paths:
  - `docs/ai-developer/**` — excluded, must not be edited.
  - `src/scistudio/api/routes/ai_pty/websocket.py` — the user-launched PTY route
    is frozen by ADR-034. See track C's constraint in §8.
- Deferred work:
  - `TODO(#2012)` already recorded in the spec: package suggestion instead of
    duplicate type authoring. Stays deferred.
  - `#2013` — previewer-authoring skill. The brief works around its absence;
    not in this dispatch.

## 2.1 Known Adjacent Defects (Not Blockers)

Recorded by the owner on 2026-08-07. Neither blocks this dispatch, but both
reduce how well a real import session performs, so they are named here so a
reviewer does not read a weak session result as a defect in this work.

| Issue | Effect on an import session | Handling |
|---|---|---|
| `#2020` | The agent runtime registers no type directory, so a drop-in type may not be visible to the runtime the session writes into. | Out of scope. Tracked separately. |
| `#2022` | A drop-in block cannot import a drop-in type and is then skipped silently. | Out of scope. §4.6 of the spec already instructs the agent to confirm each block actually loaded after writing it, which is the mitigation available from inside a session. |

## 3. Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Every completed row MUST include an artifact:
  PR link, commit, test command, report path, or gate-record entry.
- Chat messages are not checklist evidence.
- Agents edit only their own rows.
- Scope changes require gate-record amendment before work continues.

### 3.1 Windows Commit Trap

`git commit` fails with `ExecutableNotFoundError: Executable /bin/sh not found`
when tracked files are modified but unstaged. pre-commit stashes the unstaged
changes with `git checkout -- .`, which fires the post-checkout hook, which
re-enters pre-commit and dies. Stage every modified tracked file — including the
gate ledger, which `gate_record check` rewrites — before committing. The same
message printed *after* a successful commit is post-commit noise and is
harmless.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created.
      -> `track/adr-053-work-import` in `C:/Users/jiazh/workspace/SciStudio-wt-work-import`
- [x] Existing issue linked, or new issue created only if none exists.
      -> `#2000`, `#2001`, `#2002` all open; no new issue created.
- [x] Gate record started.
      -> `.workflow/records/2000-adr-053-work-import.json`
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created.
- [x] Umbrella PR opened. -> `#2028`
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found.
      -> gate checks run with `PYTHONPATH=./src`; no editable install performed.
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and linked
      below. -> `docs/planning/adr-053-work-import-dispatch-prompts.md`
- [ ] Sentrux baseline recorded, or N/A reason recorded.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A — no bypass requested or used`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `N/A` | `[ ]` | |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `N/A — this dispatch changes no wrapper, hook,
  gate-record, CI, or AI-runtime behavior. Feature docs land as the spec
  correction plus this checklist.`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A1` | `implementer` | `N/A` | prompts §A1 | Graded agent availability probe over the provider registry | `feat/2000-work-import-availability` | `C:/Users/jiazh/workspace/SciStudio-wt-wi-a1` | `src/scistudio/ai/agent/availability.py`, `src/scistudio/api/routes/ai.py`, `tests/api/test_agent_availability.py`, `frontend/src/lib/api/agentAvailability.ts` (+ its test) | `frontend/src/components/**`, `src/scistudio/ai/work_import/**`, `src/scistudio/api/routes/ai_pty/**`, `docs/specs/**` | `#2000` | `[ ]` |
| `A2` | `implementer` | `N/A` | prompts §A2 | Brief template transcribed verbatim from spec §4.6, session context, composition | `feat/2002-work-import-brief` | `C:/Users/jiazh/workspace/SciStudio-wt-wi-a2` | `src/scistudio/ai/work_import/{__init__,context,brief}.py`, `src/scistudio/ai/work_import/brief_template.md`, `tests/ai/test_work_import_brief.py`, `docs/specs/adr-053-work-import.md` (FR-012 + `#2003` staleness only) | `src/scistudio/api/**`, `frontend/**`, spec §4.6 body | `#2002` | `[ ]` |
| `A3` | `implementer` | `N/A` | prompts §A3 | Work-import session endpoint: validate, compose, write brief, spawn PTY tab | `feat/2001-work-import-session` | `C:/Users/jiazh/workspace/SciStudio-wt-wi-a3` | `src/scistudio/api/routes/work_import.py`, `src/scistudio/api/app.py` (router include only), `src/scistudio/api/routes/ai_pty/**`, `tests/api/test_work_import_session.py` | `frontend/**`, `src/scistudio/ai/work_import/**`, `src/scistudio/api/routes/ai.py`, `docs/specs/**` | `#2001` | `[ ]` |
| `A4` | `implementer` | `N/A` | prompts §A4 | Toolbar entry, Bring In My Work dialog, availability guidance, session start | `feat/2001-work-import-dialog` | `C:/Users/jiazh/workspace/SciStudio-wt-wi-a4` | `frontend/src/components/BringInMyWorkDialog*`, `frontend/src/components/Toolbar*`, `frontend/src/store/{terminalTabsSlice,types,uiSlice}.ts`, `frontend/src/components/AIChat/**`, `frontend/src/lib/api/workImport.ts`, matching tests | `src/scistudio/**`, `frontend/src/lib/api/agentAvailability.ts`, `docs/specs/**` | `#2001` | `[ ]` |
| `AU1` | `audit_reviewer` | `with-context` | prompts §AU1 | Verify claimed work against issues, spec, checklist, code, tests, CI | `audit/2001-work-import-with-context` | `C:/Users/jiazh/workspace/SciStudio-wt-wi-au1` | `docs/audit/2026-08-07-adr-053-work-import-with-context.md`, own checklist rows | all implementation code | `#2001` | `[ ]` |
| `AU2` | `audit_reviewer` | `no-context` | prompts §AU2 | Independent conformance of the implemented surface against repository docs, code, tests | `audit/2001-work-import-no-context` | `C:/Users/jiazh/workspace/SciStudio-wt-wi-au2` | `docs/audit/2026-08-07-adr-053-work-import-no-context.md` | all implementation code | `N/A` | `[ ]` |

## 7. Fixed Interface Contracts

These are manager decisions, made before dispatch so parallel agents do not
have to negotiate. An agent that believes a contract is wrong MUST stop and
report rather than diverge from it.

### 7.1 C1 — Availability API (A1 owns, A4 consumes)

`GET /api/ai/availability`

```json
{
  "state": "ready",
  "providers": [
    {"key": "claude-code", "label": "Claude Code", "state": "ready", "cause": null},
    {"key": "codex", "label": "Codex", "state": "call_failed", "cause": "quota exceeded"}
  ]
}
```

- Per-provider `state` is one of `not_installed`, `not_authenticated`,
  `call_failed`, `ready` (FR-031).
- Aggregate `state` is `ready` when any provider is `ready`; otherwise the most
  actionable state present, ranked `call_failed` > `not_authenticated` >
  `not_installed`; `not_installed` when the registry yields no agent providers.
  This is what lets FR-005 hold: a mixed result must not block the user.
- `cause` is populated only for `call_failed` and MUST NOT contain reinstall
  guidance (FR-034).
- Frontend client module `frontend/src/lib/api/agentAvailability.ts` exports
  `fetchAgentAvailability()` plus the types `AgentAvailabilityState`,
  `ProviderAvailability`, `AgentAvailabilityResponse`.

### 7.2 C2 — Brief composition (A2 owns, A3 consumes)

- `src/scistudio/ai/work_import/context.py` — frozen dataclass
  `ImportSessionContext` with exactly these fields:

  | Field | Type |
  |---|---|
  | `source_location` | `str \| None` |
  | `has_no_codebase` | `bool` |
  | `destination_tier` | `Literal["project", "user_library"]` |
  | `data_kinds` | `tuple[str, ...]` |
  | `data_kinds_other` | `str \| None` |
  | `workflow_description` | `str \| None` |
  | `interaction_wishes` | `str \| None` |
  | `other_software` | `str \| None` |
  | `skipped` | `frozenset[str]` over `{"workflow_description", "interaction_wishes", "other_software"}` |
  | `provider` | `str` (provider-registry key) |
  | `permission_mode` | `Literal["safe", "bypass"]` |

- `src/scistudio/ai/work_import/brief.py` — `compose_brief(context) -> str`.
- `src/scistudio/ai/work_import/brief_template.md` — spec §4.6 verbatim.
- Layering: `scistudio.ai.work_import` is a leaf. It MUST NOT import from
  `scistudio.api` or `scistudio.blocks`.

### 7.3 C3 — Session API (A3 owns, A4 consumes)

`POST /api/work-import/sessions`

Request body is `ImportSessionContext` in snake_case plus `project_dir`
(absolute path). Response 200:

```json
{
  "tab_id": "a1b2c3d4e5f6",
  "title": "Bring in my work",
  "brief_path": ".scistudio/work-import/<session-id>.md",
  "provider": "claude-code",
  "permission_mode": "safe"
}
```

Backend order is fixed by FR-024: validate, compose (C2), write the brief file
and close it, **then** spawn. A session is never spawned against a missing or
partial brief.

The frontend adds a terminal tab carrying the returned `tab_id` in `running`
state and connects `WS /api/ai/pty/{tab_id}` with the existing query
parameters, joining the already-spawned PTY. No new WS frame type is
introduced; the frontend initiated the request and already holds the `tab_id`.

### 7.4 Known boundary trap

The frontend permission-mode union is `"safe" | "dangerous"`
(`AIChat/SetupScreen.parts/types.ts`); the backend PTY spawn takes
`"safe" | "bypass"` (`ai_pty/engine.py`). A4 maps at the request boundary; A3
validates the backend spelling. Both must have a test that pins the mapping.

## 8. Track A: Availability Probe (#2000)

### 8.1 Track Scope

- Owner: `A1`
- In scope:
  - Four-state resolution built on the existing provider registry and
    `GET /api/ai/status` — no second discovery path (FR-032).
  - A live minimal call to separate `call_failed` from `ready` (FR-033).
  - Non-blocking probe behaviour (FR-035).
  - A shared, reusable module — Bring In My Work is the first consumer, not the
    only one (FR-036).
- Out of scope:
  - The dialog and its guidance rendering (A4).
  - Provider configuration and the registry itself.
- Required docs:
  - `N/A — the spec already specifies FR-031 to FR-036; no doc change follows
    from implementing them.`
- Required tests:
  - `tests/api/test_agent_availability.py` covering all four states, including
    authenticated-but-failing, plus a hanging-probe case.

### 8.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Audit mode recorded when persona is `audit_reviewer`. -> `N/A`
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 8.3 Implementation

- [x] Availability module -> `src/scistudio/ai/agent/availability.py`
  (four-state resolution, per-provider minimal-call table, aggregate ranking,
  memoised shared report; leaf module importing only stdlib and
  `providers_registry`, so any surface can consume it — FR-031, FR-033, FR-036)
- [x] `GET /api/ai/availability` endpoint -> `src/scistudio/api/routes/ai.py`
  (returns contract C1 verbatim; grades the rows `GET /api/ai/status` already
  produces rather than adding a second discovery path — FR-032. Accepts
  `?refresh=true` to bypass the memoised report for an explicit retry control.)
- [x] Frontend availability client -> `frontend/src/lib/api/agentAvailability.ts`
  (`fetchAgentAvailability()` plus `AgentAvailabilityState`,
  `ProviderAvailability`, `AgentAvailabilityResponse`; every availability type
  lives here rather than in `store/types.ts`)
- [x] `tests/api/test_agent_availability.py` -> 40 tests: all four states,
  authenticated-but-failing, reinstall-guidance stripping (FR-034), a wedged
  provider that ignores its own timeout asserted on elapsed wall-clock time
  (FR-035), the full C1 aggregate ranking, minimal-call table completeness
  against `agent_keys()`, and one end-to-end test driving both endpoints from
  one set of discovery fakes. Client tests in
  `frontend/src/lib/api/__tests__/agentAvailability.test.ts` (7 tests).

**Live minimal call (FR-033), per provider.** Every argv was executed against
the installed binary on the owner's workstation on 2026-08-07 and timed:

| Provider | Observed | Wall clock | Cost / size |
|---|---|---|---|
| `claude-code` | exit 0, printed `ok` | 2.5 s | $0.0021 (haiku; $0.0346 unpinned) |
| `codex` | exit 0, printed `ok` | 4.9 s | ~14.9k context tokens |
| `kimi-code` | exit 1, "No model configured." | 0.7 s | no request billed |
| `qoder-cn` | exit 0, printed `ok` | 8.3 s | not reported by the CLI |
| `qoder` | not installed; shares the CN argv | — | — |

The Kimi row is the FR-033 case observed rather than contrived: the credential
file was present, so every presence check called it logged in, and the live call
failed immediately with a readable cause.

Three things bound the cost, since a live call is a real billed request:
`not_installed` and `not_authenticated` are decided from the status row and
never call at all; the probe runs tool-free (`--tools ""`, or Codex's read-only
sandbox) in a throwaway working directory so no project config is loaded; and
the report is memoised for 60 s and shared across surfaces. Per-call timeout is
15 s (~1.8x the slowest observed call), with a second, independent budget on the
whole report so a wedged child cannot hold the response.

### 8.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 8.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 9. Track B: Brief Template And Composition (#2002)

### 9.1 Track Scope

- Owner: `A2`
- In scope:
  - `brief_template.md` transcribed **verbatim** from spec §4.6, substitution
    points only where §4.6 shows `{...}` placeholders (FR-026).
  - `ImportSessionContext` per contract C2.
  - `compose_brief`, including skipped-versus-unanswered rendering (FR-021).
  - The three spec corrections named in §2, all outside §4.6.
- Out of scope:
  - Any rewording of §4.6 itself. #2017 edits that section.
  - The endpoint, the dialog, and the spawn.
- Required docs:
  - `docs/specs/adr-053-work-import.md` — FR-012 correction, removal of the
    stale "#2003 is unmerged" statements, and correction of the FR
    cross-references that name the wrong requirement (§4.4 and the Key Entities
    table). All three are confined to text outside §4.6.
- Required tests:
  - `tests/ai/test_work_import_brief.py`: the composed brief matches the
    template verbatim outside the substituted section; each question renders
    with its own text, examples and preset options; a skipped question renders
    as explicitly skipped rather than omitted; both destination tiers render.

### 9.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Audit mode recorded when persona is `audit_reviewer`. -> `N/A`
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 9.3 Implementation

- [ ] `brief_template.md` verbatim from §4.6 -> `<artifact>`
- [ ] `ImportSessionContext` per C2 -> `<artifact>`
- [ ] `compose_brief` with skip semantics -> `<artifact>`
- [ ] Spec FR-012 correction, `#2003` staleness removal, FR cross-reference
      corrections -> `<artifact>`
- [ ] `tests/ai/test_work_import_brief.py` -> `<artifact>`

### 9.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 9.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 10. Track C: Session Endpoint And Spawn (#2001 backend)

### 10.1 Track Scope

- Owner: `A3`
- In scope:
  - `POST /api/work-import/sessions` per contract C3.
  - Brief file written under the project's `.scistudio/`, one file per session
    (FR-027, FR-030), fully written before spawn (FR-024).
  - Spawn through the same mechanism the agent block uses (FR-022), with a
    single visible line naming the brief (FR-028), identical on `FLAG_FILE` and
    `AMBIENT` providers (FR-029).
- Out of scope:
  - The dialog, the store, and any frontend file.
  - The brief's text and `compose_brief` (A2).
  - `src/scistudio/api/routes/ai.py` (A1).
- Constraint — the frozen route:
  `src/scistudio/api/routes/ai_pty/websocket.py` hosts the user-launched PTY
  route, frozen by ADR-034. The engine-initiated join branch there currently
  recognises a pre-spawned PTY only by `_engine_block_run_id`. Extending that
  predicate so a work-import tab joins its pre-spawned PTY is acceptable **only
  if** the user-launched spawn contract — query parameters, spawn semantics,
  error frames, cap behaviour — is unchanged and a regression test pins it. If
  A3 concludes a broader change to that route is required, it MUST stop and
  report to the manager rather than proceed.
- Required docs:
  - `N/A — spec FR-022 to FR-030 already specify this surface; the correction to
    FR-012 is owned by A2.`
- Required tests:
  - `tests/api/test_work_import_session.py`: brief exists and is complete before
    spawn; two sessions in one project get distinct brief files; the brief lands
    under `.scistudio/` and is ignored by the default project ignore file; the
    opening message is one line naming the brief; delivery is identical for a
    `FLAG_FILE` and an `AMBIENT` provider; the permission-mode spelling is
    validated; user-launched PTY behaviour is unchanged.

### 10.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Audit mode recorded when persona is `audit_reviewer`. -> `N/A`
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 10.3 Implementation

- [ ] `POST /api/work-import/sessions` -> `<artifact>`
- [ ] Brief write-before-spawn ordering -> `<artifact>`
- [ ] Per-session brief file naming -> `<artifact>`
- [ ] PTY spawn and join for a work-import tab -> `<artifact>`
- [ ] `tests/api/test_work_import_session.py` -> `<artifact>`

### 10.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 10.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 11. Track D: Toolbar Entry And Dialog (#2001 frontend)

### 11.1 Track Scope

- Owner: `A4`
- In scope:
  - Permanent toolbar entry "Bring in my work", enabled with a project open
    (FR-001, FR-002).
  - Dialog page one: source with a directory picker, "I don't have a codebase",
    destination tier, provider picker, permission mode, caveat copy
    (FR-003 to FR-012, FR-037, FR-038, FR-040 to FR-044).
  - The four questions with presets, grouping, and skip semantics
    (FR-013 to FR-021).
  - Availability guidance in place of a start action when no provider is usable
    (FR-005).
  - Starting the session through `POST /api/work-import/sessions` and attaching
    the returned tab.
- Out of scope:
  - Any backend file.
  - `frontend/src/lib/api/agentAvailability.ts` (A1 owns it; import it).
  - Rewording the caveat away from what FR-037 requires it to state.
- Required docs:
  - `N/A — the spec is the contract for this surface and needs no amendment to
    implement it.`
- Required tests:
  - `frontend/src/components/__tests__/BringInMyWorkDialog.test.tsx` and a
    toolbar test, covering: entry enabled/disabled by project state; caveat
    present and not bypassable in both modes; no-codebase option disables the
    source field and makes question 2 required; preset grouping renders and both
    groups are selectable; skips are distinguishable from answers in the
    submitted payload; a single usable provider is preselected and still
    visible; two usable providers are both choosable; the chosen provider and
    permission mode reach the request; each availability state shows its own
    guidance.

### 11.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded.
      -> `docs/planning/adr-053-work-import-dispatch-prompts.md` §A4
- [x] Correct prompt template selected.
      -> `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
- [x] Audit mode recorded when persona is `audit_reviewer`. -> `N/A`
- [x] Agent branch/worktree assigned.
      -> `feat/2001-work-import-dialog` in `C:/Users/jiazh/workspace/SciStudio-wt-wi-a4`
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 11.3 Implementation

- [x] Toolbar entry and enablement (FR-001, FR-002)
      -> `frontend/src/components/Toolbar.tsx`; permanently rendered for both
      tab kinds, disabled without an open project. Verified by
      `frontend/src/components/__tests__/BringInMyWorkToolbarEntry.test.tsx`.
- [x] Dialog page one incl. caveat (FR-003 – FR-012, FR-037, FR-038)
      -> `frontend/src/components/BringInMyWorkDialog.tsx`,
      `BringInMyWorkDialog.parts/{SourceAndDestination,CorrectnessCaveat,copy}.tsx|ts`.
      The caveat renders inline, always expanded, immediately above the start
      action, in both modes.
- [x] No-codebase mode (FR-009, FR-010, FR-017)
      -> `BringInMyWorkDialog.parts/formState.ts` (`sourceFieldDisabled`,
      `workflowDescriptionRequired`). Source field and browse control disable;
      destination, presets, provider and permission mode stay in effect;
      question 2 becomes required with longer prompt wording.
- [x] The four questions (FR-013 – FR-021)
      -> `BringInMyWorkDialog.parts/{copy.ts,DataKindsQuestion.tsx,FreeTextQuestion.tsx}`.
      Presets are grouped into "How the data is arranged" and "What the data
      is"; skipped answers reach the request in `skipped[]` with a `null` value
      rather than being omitted.
- [x] Availability guidance (FR-005, FR-031, FR-034, FR-035)
      -> `BringInMyWorkDialog.parts/{AvailabilityGuidance.tsx,availability.ts,useAgentAvailability.ts}`.
      One guidance block per non-ready state; the start action is absent when no
      provider is `ready`; `call_failed` reports its cause and its copy contains
      no "install" at all; a hanging probe is capped at 10 s and degrades to a
      reported state.
- [x] Session start and tab attach (FR-022, FR-025, FR-044; contract C3, §7.4)
      -> `frontend/src/lib/api/workImport.ts`,
      `frontend/src/store/{terminalTabsSlice,types,uiSlice}.ts`. `POST
      /api/work-import/sessions`, then `addWorkImportTerminalTab` adds the
      returned `tab_id` in `running` state with `source: "user"`, which mounts
      `TerminalView` and joins `WS /api/ai/pty/{tab_id}`. Permission mode is
      mapped `dangerous -> bypass` at the request boundary and back on the
      response.
- [x] Request validation against A2's `ImportSessionContext` rules
      -> `frontend/src/lib/api/workImport.ts` (`validateWorkImportRequest`).
      Enforced in the dialog before submit and again inside
      `startWorkImportSession`, so a body the endpoint would reject never
      leaves: non-blank `provider`; backend permission-mode spelling; exactly
      one of `source_location` / `has_no_codebase`; `skipped` restricted to the
      three question keys with no duplicates; no question both skipped and
      answered; blank answers sent as skipped.
- [x] Frontend tests
      -> `npm --prefix frontend test -- BringInMyWorkDialog Toolbar workImport`
      — 5 files, 80 tests, all passing. Full suite: 122 files / 1200 tests
      passing. `npm --prefix frontend run lint` 0 errors,
      `npm --prefix frontend run typecheck` clean, `npm --prefix frontend run build` clean.
- [x] Spec frontmatter migration (ADR-042 lifecycle, forced by this track)
      -> `docs/specs/adr-053-work-import.md`: once
      `frontend/src/components/BringInMyWorkDialog.tsx` exists, the spec's
      `planned_governs.files` entry resolves and `full_audit` raises
      `doc-drift.planned-file-is-resolved` / `closure.planned-file-is-resolved`
      at ERROR severity, blocking every commit. The path moved to
      `governs.files`; `planned_governs.files` is now empty. Frontmatter only —
      no FR text, no body prose, nothing in §4.6. Recorded as a gate-ledger
      amendment. **Manager review requested**: `docs/specs/**` was outside A4's
      original write set.
- [x] Contract C1 integration — resolved. This branch is rebased onto
      `origin/track/adr-053-work-import` at `49d801e0`, which carries A1's real
      `frontend/src/lib/api/agentAvailability.ts`. The dialog consumes C1
      through the single seam
      `BringInMyWorkDialog.parts/useAgentAvailability.ts` and typechecks and
      tests green against A1's module, not a local double: `tsc --noEmit`
      clean, and `vitest run BringInMyWorkDialog Toolbar workImport
      agentAvailability terminalTabsSlice.workImport` → 6 files / 87 tests
      passing. A1's optional `{ refresh?: boolean }` argument is
      backward-compatible with the zero-argument call this seam makes.

### 11.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 11.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 12. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | |
| Targeted tests | `pytest tests/api/test_agent_availability.py tests/ai/test_work_import_brief.py tests/api/test_work_import_session.py` | `[ ]` | |
| Frontend tests | `npm test -- BringInMyWorkDialog Toolbar agentAvailability` | `[ ]` | |
| Frontend smoke check | manual or scripted UI check of the toolbar entry and dialog | `[ ]` | |
| Pre-push gate check | `python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/main --head HEAD` | `[ ]` | |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2000" --closes "#2001" --closes "#2002"` | `[ ]` | |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run --title "<title>" --body "<body>"` | `[ ]` | |

## 13. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-08-07 | manager | Spec FR-012 asserted the personal-library destination depends on the personal tool library spec's FR-006 write endpoint. §4.6 has the agent write those directories directly with its shell, so no endpoint is involved. | Owner directive: correct FR-012 in this dispatch and build no write path. Assigned to A2. | `#2001` |
| 2026-08-07 | manager | Spec §4.1 and §4.5 state that `#2003` is unmerged. It merged 2026-08-07. | Owner directive: correct the stale statements. Assigned to A2. | `#2001` |
| 2026-08-07 | manager | Spec §4.4 and the Key Entities table cite FR numbers that do not match the requirements they name (for example "Preset grouping (FR-015)" where FR-014 defines presets, and "Availability states (FR-027, FR-029)" where FR-031 and FR-033 define them). | Owner set a complete-delivery goal with no deferrals, and these references misdirect anyone implementing from the spec. Corrected in this dispatch, outside §4.6. Assigned to A2. | `#2001` |

## 14. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch (`#2000`, `#2001`, `#2002`).
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
