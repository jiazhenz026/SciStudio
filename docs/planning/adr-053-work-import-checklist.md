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

## 2.2 Environment Findings

Verified by the manager on 2026-08-07. These are workstation facts, not repository
defects, and they explain failures an agent or reviewer would otherwise misread.

**A stale editable install poisons subprocess imports.**
`.venv/Lib/site-packages/__editable__.scistudio-0.2.1.pth` points at
`C:\Users\jiazh\Desktop\workspace\SciStudio\src`, a directory that no longer
exists. Any child process that does not receive an explicit `PYTHONPATH` resolves
`scistudio` to that dead path and dies with `ModuleNotFoundError`. This is the
pollution `AGENTS.md` forbids `pip install -e .` in order to prevent, and it has
already happened. Measured effect on `tests/qa/test_gate_record_hooks.py`:

| Invocation | Result |
|---|---|
| `PYTHONPATH=./src` | 3 failed — a relative path resolves against the child's cwd |
| `PYTHONPATH=<absolute>/src` | 15 passed |

Consequence for #2030: three of the nine failures it records as Group B test
defects are this, not test defects. Patching the shipped
`scripts/hooks/check-worktree-write-guard.sh` to inject `PYTHONPATH` would be
compensating in product code for one workstation's broken virtualenv. Worth
resolving before that fix lands.

**Track-stacked branches need `SCISTUDIO_GATE_BASE`.** The pre-commit and
commit-msg hooks default their diff base to `origin/main`, which pulls the
umbrella's own files into a sub-branch's observed diff and fails
`scope.out-of-scope` on files the agent never touched. Set
`SCISTUDIO_GATE_BASE=origin/track/adr-053-work-import`; this is the documented
#1627 mechanism. `finalize` needs the same base passed explicitly with `--base`.

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
- [x] Sentrux baseline recorded, or N/A reason recorded.
      -> **N/A — unavailable.** No Sentrux MCP server is connected to any runtime
      in this dispatch and no `sentrux` binary is on PATH, so neither the MCP
      calls nor the CLI fallback could run. Recorded as unavailable in every
      agent ledger rather than claimed. The `sentrux_gate` guard itself ran
      inside `gate_record check` and passed with one advisory info finding.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A — no bypass requested or used`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[x]` | Ran on every commit in this dispatch. No bypass label used. It blocked three times and each block was resolved by fixing the cause, never by bypassing: `guard.mod_guard` on `pyproject.toml` (resolved by dropping the edit), `docs.docs_required_or_na` (resolved by recording docs), and `scope.out-of-scope` on track-stacked branches (resolved with `SCISTUDIO_GATE_BASE`) |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[x]` | Passed on every commit. Rejected one merge subject that used a non-conventional type (`merge(...)`), which was rewritten rather than bypassed |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[x]` | The installed pre-push hook is the fast allow shim per ADR-042 Addendum 6; `pre-pr` is the hard checkpoint and is recorded below |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `N/A` | `[!]` | Blocked by `checks.python_tests` (#2030) — the sole unsatisfied obligation. **No bypass label was requested or used.** `SCISTUDIO_SKIP_PREFLIGHT` was not set |

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
    {"key": "claude-code", "label": "Claude Code", "state": "ready",
     "cause": null, "next_step": null, "session_unsupported_reason": null},
    {"key": "codex", "label": "Codex", "state": "call_failed",
     "cause": "quota exceeded", "next_step": null,
     "session_unsupported_reason": null}
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
- `next_step` is the one action that moves this provider out of this state
  (SC-002): which executable to install and where SciStudio looked, or the
  command that signs it in. Populated for `not_installed` and
  `not_authenticated` — the two states FR-031 gives a guidance column to — and
  null for the other two. Composed on the backend because every fact in it
  belongs to the ADR-034 registry.
- `session_unsupported_reason`, when non-null, says this provider cannot be
  handed the opening instruction a SciStudio-started session is delivered with,
  so it MUST NOT be offered as the agent for a session however `ready` it is.
  It is **not** a fifth state and does not affect `state` or the aggregate: the
  provider genuinely answers calls, and the aggregate is read by surfaces that
  ask "is an agent set up", not "can one run a session". Added by the fix track
  after the no-context audit's P1; see §13 and §15.
- Frontend client module `frontend/src/lib/api/agentAvailability.ts` exports
  `fetchAgentAvailability({refresh?})` plus the types `AgentAvailabilityState`,
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
  | `anything_else` | `str \| None` |
  | `skipped` | `frozenset[str]` over `{"workflow_description", "interaction_wishes", "other_software", "anything_else"}` |
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

- [x] Audit agent assigned, or manager audit completed. -> `AU1`, with-context
- [x] Audit report file path assigned.
      -> `docs/audit/2026-08-07-adr-053-work-import-with-context.md`
- [x] Audit report committed. -> see §11.4 for the commit.
- [ ] Audit report merged into final PR evidence path.
- [x] Findings recorded. Track A findings: **P2-1** (`not_installed` /
      `not_authenticated` guidance names the providers but gives no command,
      URL or step — FR-031 asks for instructions, SC-002 for a specific next
      action), **P2-3** (`kimi-code`'s minimal call carries no tool restriction
      and no sandbox, against the module docstring's stated safety invariant;
      `test_the_probe_never_grants_the_cli_tools` asserts a universal but loops
      over four of five providers), **P3-1** (an empty provider registry — the
      case contract C1 names explicitly — renders no guidance and no start
      action, because the frontend derives guidance from provider rows and
      ignores the aggregate `state`). Verified: four states resolve correctly,
      `ready` is reachable only through a live call that exits 0 *and* prints,
      `call_failed` copy contains no "install" and `_REINSTALL_GUIDANCE` strips
      it from provider error text, a wedged provider degrades on wall-clock
      time. `pytest tests/api/test_agent_availability.py` -> 40 passed.
- [x] P1 findings fixed before integration. -> none found.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 8.5 Integration

- [x] Agent output reviewed by manager.
- [x] Scope compliance verified.
- [x] Conflicts resolved intentionally.
- [x] Track merged or integrated.
      -> merge `49d801e0`. `GET /api/ai/availability` reviewed against contract C1; `/status` behaviour unchanged, the probe factored into `_status_rows()` so both endpoints share one discovery. Write set respected exactly; `frontend/src/store/types.ts` untouched as instructed.

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

- [x] `brief_template.md` verbatim from §4.6
      -> `src/scistudio/ai/work_import/brief_template.md`, extracted
      mechanically from the §4.6 fenced block (376 lines, 18,866 bytes).
      Byte-identity is pinned as a permanent regression guard by
      `test_brief_template_is_verbatim_spec_section_4_6`, which re-extracts §4.6
      at test time — if `#2017` edits §4.6, the test fails until the template is
      re-transcribed.
- [x] `ImportSessionContext` per C2
      -> `src/scistudio/ai/work_import/context.py`. Field names, types, and
      order are pinned by `test_context_matches_contract_c2_field_names_and_order`.
      Adds `__post_init__` validation (unknown tier/permission mode, unknown
      skippable question, source-plus-no-codebase, neither-source-nor-no-codebase,
      skipped-and-answered) and list->tuple / list->frozenset normalisation so a
      decoded JSON body can be passed straight in. A3/A4 producers must satisfy
      those invariants.
- [x] `compose_brief` with skip semantics
      -> `src/scistudio/ai/work_import/brief.py`. Substitutes only at the seven
      `{...}` placeholders §4.6 shows in "What they told us"; the four
      `{project}` path literals in "What to deliver" are left alone. Skip wording
      is read out of the template's own `{<answer>, or "<...>"}` alternative
      rather than restated in Python, so FR-021's wording cannot drift from
      §4.6. Provider and permission mode are deliberately absent from the brief
      body — §4.6 gives them no placeholder and FR-026 forbids adding one; they
      reach the spawn instead (FR-044).
- [x] Spec FR-012 correction, `#2003` staleness removal, FR cross-reference
      corrections -> `docs/specs/adr-053-work-import.md`, 23 edits, all outside
      §4.6 (the applier asserts each match is unique, asserts it is not inside
      §4.6, and re-checks §4.6 byte-identity afterwards). FR-012 now states the
      in-session agent writes `~/.scistudio/types/` and `~/.scistudio/blocks/`
      itself with no endpoint involved; the three `#2003`-is-unmerged statements
      (§4.1, §4.3 T-002, §4.5) now record that it merged 2026-08-07; 17 FR
      cross-references in §2, §3 Key Entities, §4.1, §4.2, §4.4, and §4.5 now
      name the requirement they describe.
- [x] `tests/ai/test_work_import_brief.py`
      -> 62 tests. `PYTHONPATH=./src python -m pytest tests/ai/test_work_import_brief.py -q`
      -> 62 passed.

### 9.4 Audit

- [x] Audit agent assigned, or manager audit completed. -> `AU1`, with-context
- [x] Audit report file path assigned.
      -> `docs/audit/2026-08-07-adr-053-work-import-with-context.md`
- [x] Audit report committed. -> see §11.4 for the commit.
- [ ] Audit report merged into final PR evidence path.
- [x] Findings recorded. Track B findings: **P2-2** (SC-006's "distinguishes
      skipped questions from unanswered ones" does not hold and cannot — the
      design deliberately collapses blank into skipped, which is what FR-021
      actually asks for; the fix is a spec correction, not a code change),
      **P3-2** (the eight preset labels and the four question texts exist as
      independent copies in `copy.ts` and `brief_template.md` with no test
      crossing the boundary, although `copy.ts:131-133` claims they are the same
      strings), **P3-5** (spec:563-564 still says `#2003`'s concrete paths are
      "left unresolved"; `status:` is still `Draft`; the `tests:` frontmatter
      lists 2 of the 6 test files). Verified **independently, not from the
      reported sha256**: `diff` and `cmp` of spec lines 672-1047 against
      `brief_template.md` -> byte-identical; §4.6 at `origin/main` vs branch head
      -> byte-identical (`sha256 fcbfc3d7…5766a0` both sides); 12 of the ~17 FR
      cross-reference corrections spot-checked against the requirements they now
      name, all correct; every remaining FR/SC citation outside §4.6 re-read, no
      surviving mis-citation. `pytest tests/ai/test_work_import_brief.py`
      -> 62 passed.
- [x] P1 findings fixed before integration. -> none found.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 9.5 Integration

- [x] Agent output reviewed by manager.
- [x] Scope compliance verified.
- [x] Conflicts resolved intentionally.
- [x] Track merged or integrated.
      -> merge `e379089d`. §4.6 byte-identity verified by the manager independently of A2's report: sha256 identical between `origin/main` and the branch. Six post-merge assertions run after the auto-merge to confirm A2's corrections survived alongside A4's identical frontmatter edit. `pyproject.toml` confirmed absent from the diff.

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

- [x] `POST /api/work-import/sessions` ->
      `src/scistudio/api/routes/work_import.py`, routed in
      `src/scistudio/api/app.py`. Response is contract C3 verbatim.
- [x] Brief write-before-spawn ordering ->
      `work_import.create_work_import_session` validates, composes, writes
      (`_write_brief` flushes and `os.fsync`s before the handle closes), then
      spawns. Proved by
      `test_brief_is_complete_on_disk_before_the_agent_is_spawned`, which reads
      the brief from *inside* the spawn call, and by
      `test_no_agent_is_spawned_when_the_brief_cannot_be_written`.
- [x] Per-session brief file naming -> `work_import._new_brief_filename`
      (`<UTC timestamp>-<uuid8>.md` under `.scistudio/work-import/`), opened
      with mode `"x"` so a collision fails loudly instead of overwriting a
      concurrent session's instructions.
- [x] PTY spawn and join for a work-import tab ->
      `ai_pty/engine.py`: the AI Block body was extracted into the shared
      `_open_prespawned_tab`, and `open_work_import_tab` calls it with no
      `block_run_id`, so no AI Block control maps are populated.
      `ai_pty/websocket.py`: the join predicate now also recognises the
      provider-neutral `_engine_prespawned` marker; the user-launched spawn
      contract (query params, spawn semantics, error frames, cap) is unchanged
      and pinned by six regression tests in the new file.
- [x] Contract C2 error mapping -> `ImportSessionContext.__post_init__` raises
      `ValueError` for every answer-shape violation; the endpoint turns each
      into a `400` carrying the dataclass's own message rather than a `500`.
      The endpoint's duplicate skipped-question validator was removed so the
      rule has one owner. Covered by
      `test_answer_shape_violations_are_4xx_with_a_usable_message` (5 cases)
      and `test_a_blank_answer_is_a_valid_session_not_an_error`.
- [x] `tests/api/test_work_import_session.py` -> 41 tests covering FR-022,
      FR-024, FR-027 to FR-030, contract C2 error mapping, contract C3, the
      §7.4 permission-mode trap, and the frozen user-launched route.
      `PYTHONPATH=<worktree>/src python -m pytest tests/api/test_work_import_session.py`
      -> 41 passed. `pytest tests/api -k "pty or ai_pty"` -> 107 passed.
      `pytest tests/api/routes/ai_pty` -> 45 passed.

### 10.4 Audit

- [x] Audit agent assigned, or manager audit completed. -> `AU1`, with-context
- [x] Audit report file path assigned.
      -> `docs/audit/2026-08-07-adr-053-work-import-with-context.md`
- [x] Audit report committed. -> see §11.4 for the commit.
- [ ] Audit report merged into final PR evidence path.
- [x] Findings recorded. **No Track C findings.** The two claims that carry the
      most weight both hold, verified by running the check rather than reading
      it. FR-024: `test_brief_is_complete_on_disk_before_the_agent_is_spawned`
      genuinely proves *ordering* — the recorder reads the file named in the
      opening message from *inside* the `_spawn` call and compares it against an
      independently composed brief, so a spawn racing the write sees no file and
      one racing the close sees a prefix. The frozen ADR-034 user-launched route
      is unchanged: the whole `websocket.py` delta is the join predicate plus
      comments; query-parameter contract, spawn call and its error frames, cap
      check and its frame, registration, both pumps and teardown are untouched;
      `_engine_prespawned` is stamped *before* the `_active_ptys` insert, closing
      the spawn-a-second-agent window; `test_open_engine_initiated_tab_signature_unchanged`
      and the four `test_engine.py` rejection tests still pass because their
      `match=` patterns survive the message-prefix rename. A work-import tab
      registers in no block-run map. `pytest tests/api -k "pty or ai_pty"`
      -> 108 passed; `pytest tests/api/test_work_import_session.py` -> 41 passed.
      No personal-library write path or endpoint exists anywhere in the diff.
- [x] P1 findings fixed before integration. -> none found.
- [x] P2/P3 findings fixed or tracked with owner-approved rationale.
      -> N/A, no Track C findings.

### 10.5 Integration

- [x] Agent output reviewed by manager.
- [x] Scope compliance verified.
- [x] Conflicts resolved intentionally.
- [x] Track merged or integrated.
      -> merge `d328f29a`. The one widened join predicate in the ADR-034-frozen route reviewed line by line; the original `_engine_block_run_id` clause is kept and a work-import tab registers in no block-run map. 108 PTY tests pass on the integrated tree. Merge order A2-before-A3 observed, as A3 required.

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

- [x] Audit agent assigned, or manager audit completed. -> `AU1`, with-context,
      branch `audit/2001-work-import-with-context`, gate ledger
      `.workflow/records/2001-audit-2001-work-import-with-context.json`
- [x] Audit report file path assigned.
      -> `docs/audit/2026-08-07-adr-053-work-import-with-context.md`
- [x] Audit report committed. -> `66175df1` on
      `audit/2001-work-import-with-context`, pushed to `origin`; not opened as a
      PR (pre-flight blocked by `#2030`; manager integrates).
- [ ] Audit report merged into final PR evidence path.
- [x] Findings recorded. Track D findings: **P2-1** (availability guidance copy —
      shared with Track A), **P2-4** (SC-001's "at least one working block" half
      is unverified; §12 carries no evidence and no e2e session was run, while
      `#2020`/`#2022` sit directly in that clause's path), **P3-1** (empty
      registry renders no guidance and no start action). Verified: the caveat has
      no dismiss control, no disclosure element and no `aria-hidden`, renders in
      the dialog's non-scrolling footer immediately above the start button so it
      is on screen whenever the button is, and is not conditioned on
      `hasNoCodebase`; `ProviderPicker` and `PermissionModePicker` are imported
      unchanged and neither file appears in the diff; the `"dangerous"` ->
      `"bypass"` mapping happens once at the request boundary and is pinned on
      both sides, with the backend rejecting the frontend spelling; presets route
      nothing — the only reads of `data_kinds` are a `", ".join` into the brief
      and one emptiness check; no question requires SciStudio or
      software-development knowledge. `npx vitest run` -> 123 files / 1226
      tests passed; `tsc --noEmit` clean; `eslint .` 0 errors; `prettier
      --check` clean.
- [x] P1 findings fixed before integration. -> none found across all four tracks.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

**Overall audit recommendation: pass-with-fixes.** No P1. Four P2 (P2-1
guidance copy, P2-2 SC-006 is a spec defect needing a spec correction not a code
change, P2-3 the untracked `kimi-code` unbounded probe, P2-4 SC-001 unverified
end to end) and five P3. Cross-cutting evidence: `full_audit` **pass**, 0 errors,
**0 findings on any file this dispatch touched**; import-linter **13 kept, 0
broken** including "AI must not depend on api"; `ruff`, `ruff format`, `mypy src`
all clean; the whole Python suite produces **exactly the six pre-existing
`#2030` failures and nothing else**; spec §4.6 **byte-identical** to
`origin/main` and to `brief_template.md`; `pyproject.toml` absent from the diff.
Scope: A1/A2/A3 wrote exactly their §6 write sets; A4 also wrote
`docs/specs/**` frontmatter, which §11.3 declares and §13 contradicts (see the
audit report's P3-3). Sentrux: **N/A — no CLI on `PATH` and no MCP server
connected in this session**; the ledger's own `sentrux_gate` ran under `check`.

### 11.5 Integration

- [x] Agent output reviewed by manager.
- [x] Scope compliance verified.
- [x] Conflicts resolved intentionally.
- [x] Track merged or integrated.
      -> merge `2c705ceb`. Spec frontmatter conflict with A2 resolved deliberately, not by picking a side: both blocks measured byte-identical and A4's spec body identical to base, so A2's file was taken as a strict superset. `ProviderPicker`/`PermissionModePicker` confirmed absent from the diff (FR-042).

### 11.6 Follow-Up: Paged Dialog (owner directive, 2026-08-07)

- Owner: `A4b`, branch `feat/2001-work-import-paged-dialog` in
  `C:/Users/jiazh/workspace/SciStudio-wt-wi-page`; gate ledger
  `.workflow/records/2001-2001-work-import-paged-dialog.json`.
- Owner request (verbatim): *"整体很不错，但是我觉得一个长问卷用户看着很难受，也
  懒得填。我建议弄成翻页的，一页一个问题，第一页是browse，选provider之类的，然后
  第二页开始问题"* — the shipped dialog renders every question on one scrolling
  page; make it paged, one question per page, setup first.
- Presentation only. The request payload and `validateWorkImportRequest`
  (contract C3, §7.3), which answers are required, and the wording of every
  question, help line, example and preset label are unchanged. `copy.ts` gained
  navigation strings and lost none.

- [x] Page layout (owner directive; FR-003)
      -> `frontend/src/components/BringInMyWorkDialog.tsx` plus
      `BringInMyWorkDialog.parts/{pages.ts,PageNav.tsx}`. Five pages: **1**
      setup — source with the directory browse control, "I don't have a
      codebase", destination tier, provider picker, permission mode (FR-008 to
      FR-012, FR-040 to FR-044); **2** question 1 (FR-013, FR-014); **3**
      question 2 (FR-016, FR-017); **4** question 3 (FR-018); **5** question 4
      (FR-019). One question per page, no review page.
- [x] Caveat and start action (FR-004, FR-037, FR-038)
      -> both on page 5, the caveat immediately above the navigation row that
      carries Start, always expanded and with no dismiss control. Paged, this is
      a stronger position than the shared footer it had: no page carries a start
      action without also carrying the caveat, and
      `BringInMyWorkDialog.test.tsx` asserts that over every page rather than
      over the one that happens to render.
- [x] FR-020 required vs skippable, as a navigation rule
      -> `pages.ts` `pageGate`. Source-or-no-codebase and the provider choice
      block page 1; question 1 blocks page 2; question 2 blocks page 3 in
      no-codebase mode. Next is never disabled — pressing it either advances or
      names what is missing and focuses the control that fixes it. The skip
      moved from a checkbox under the box to a labelled button beside Next, with
      `SKIP_HELP` under it; `SKIPPED_NOTE` makes a skip legible when the user
      pages back to it, and typing takes it back.
- [x] FR-016 / FR-017 question 2 decided on page 1, enforced on page 3
      -> both pages read `workflowDescriptionRequired(state)` over state held by
      the dialog, so they cannot disagree. Pinned by a round trip: set the mode
      on page 1, assert the requirement and the longer prompt on page 3, go back,
      unset it, assert the skip returns.
- [x] FR-005 availability surfaces on page 1, not page 5
      -> the provider is chosen on page 1, so page 1 is where "no agent is ready
      to run the session" blocks. A user never answers five pages before finding
      out. The guidance still replaces the start action on page 5 for the case
      where the probe resolves late or a retry fails, and a probe still in flight
      never holds the user up (FR-035).
- [x] FR-021 skips reach the request marked as skipped
      -> unchanged in `buildRequest`; a page paged past without an answer
      resolves to the same payload as an explicit skip. Pinned directly: a walk
      that answers only what FR-020 requires sends
      `skipped: ["workflow_description", "interaction_wishes", "other_software"]`.
- [x] FR-006 / FR-007 guard rewritten to walk every page
      -> `BringInMyWorkDialog.test.tsx`. The old guard searched one render, which
      paged would have checked page 1 and reported on five. It now visits each
      page in turn, checks that page's text **and its placeholders** (the
      examples are attributes, so `textContent` alone missed them), and then
      asserts both that it reached all five pages and that what it read contains
      the real questions — so an empty or missing page fails rather than passes
      by vacuity. Run twice, once per question-2 mode. Verified by mutation: a
      forbidden word planted in question 4's example fails both cases.
- [x] Frontend tests
      -> `npx vitest run BringInMyWorkDialog` — 2 files, 57 tests passing
      (`BringInMyWorkDialog.test.tsx` 37, `BringInMyWorkDialogPaging.test.tsx`
      20, sharing `BringInMyWorkDialog.harness.tsx`). Full suite `npx vitest
      run` — 124 files / 1257 tests passing. `npm run lint` 0 errors and 40
      warnings, the same 40 as before this change; `tsc --noEmit` clean;
      `prettier --check` clean.
- [x] Out-of-scope files untouched
      -> `frontend/src/lib/api/workImport.ts`,
      `frontend/src/lib/api/agentAvailability.ts`,
      `AIChat/SetupScreen.parts/{ProviderPicker,PermissionModePicker}.tsx`
      (FR-042), all of `src/scistudio/**`, `docs/specs/**`, `docs/adr/**` and
      `pyproject.toml` are absent from the diff.

### 11.7 Follow-Up: Owner Copy Pass (2026-08-08)

- Same owner, same branch and gate ledger as §11.6. Paging itself accepted; this
  is copy plus one behavioural change to the provider picker.
- The pattern behind every item: **the owner wants the affordance, not the
  sentence explaining the affordance.**

- [x] Deleted outright — nine strings, not reworded
      -> `DIALOG_LEAD` (page-1 intro), `SOURCE_HELP`, `Q1_HELP`, `SKIP_HELP`,
      `START_HELP`, `BLOCKED_LEAD` ("Before you go on:"),
      `NO_AGENT_BLOCKS_PAGING`, `PARTIAL_AVAILABILITY_NOTE`, and the long
      per-provider remedy lines beside the picker. `SKIP_LABEL` trimmed to
      `"Skip"`; `SKIPPED_NOTE` replaced by `SKIPPED_MARKER` (`"Skipped"`), a
      chip rather than prose. `START_HELP` and `PARTIAL_AVAILABILITY_NOTE` were
      my judgement under the owner's stated rule, reported for review.
- [x] FR-014 re-based on structure (owner cut the sentence that carried it)
      -> the two labelled, bordered `fieldset` groups with their own legends are
      what FR-014 actually names ("visually grouped … rather than … one flat
      list"). `BringInMyWorkDialog.test.tsx` now asserts the two groups exist
      separately, each legend is visible, each group holds its own options, and
      the two competing readings ("Series" / "Time series") are both selectable.
- [x] FR-020 re-based on structure (owner cut the copy that carried it)
      -> three properties, each asserted directly: Skip is a `<button>` not a
      checkbox; it is a sibling of the primary action inside
      `work-import-nav-actions`; it lives in the navigation row, not in the
      question body. Documented in `PageNav.tsx` and `copy.ts` so a change that
      demotes the control is visibly a change to FR-020.
- [x] One dropdown for every provider, replacing the note beside the picker
      -> `AgentSetup.tsx` no longer renders an unusable-provider block at all.
      Every provider is an option in the reused `ProviderPicker`, greyed and
      disabled when it cannot run a session, with a short suffix naming its
      state (`(not installed)`, `(not signed in)`, `(call failed)`,
      `(not available)`). The AI chat's pattern, per the owner.
- [x] `ProviderPicker` extended, not forked (FR-042)
      -> new optional prop `optionOverrides?: Readonly<Record<string,
      ProviderOptionOverride>>`, where `ProviderOptionOverride = { hint: string
      | null; selectable: boolean }`. Absent or missing an entry, the component
      falls back per provider to today's `available`/`logged_in` derivation, so
      the AI chat is untouched. Both the option ordering and the `disabled`
      attribute read one predicate, `isSelectable`, so a greyed provider cannot
      sort as if it were choosable. **Scope**: `ProviderPicker.tsx` was outside
      §11.1's write set; the manager lifted that restriction explicitly for this
      change, recorded as a gate-ledger amendment.
- [x] Regression test proving the AI chat is unchanged
      -> new `frontend/src/components/AIChat/__tests__/ProviderPicker.test.tsx`.
      Renders the picker exactly as the chat does — no `optionOverrides` — and
      pins the whole option list as data: value, text and `disabled` for every
      entry including the placeholder, in DOM order, over rows covering all four
      two-boolean combinations. A third case passes an override map naming a
      provider that is not in the list, pinning per-provider fallback. Existing
      `SetupScreen.test.tsx` and `ProviderExtensibility.test.tsx` pass unchanged.
- [x] `not_authenticated` is greyed here although the AI chat allows it
      -> verified against the spawn rather than assumed. `spawn_agent` appends
      the opening line as a positional argv element
      (`terminal.py::_initial_prompt_argv`, the `[-- <prompt>]` tail), so there
      is exactly one delivery attempt and it happens at process start; nothing
      types it into the PTY afterwards. That line is the agent's only route to
      the brief, which is its only source of instructions (FR-024, FR-028).
      Independently, contract C1 grades `ready` only on a live minimal call
      succeeding (FR-033), which a signed-out CLI cannot do, so `isUsable`
      already excludes it and `canStart` would refuse it — a selectable option
      the dialog then refuses to start on is worse than a greyed one.
- [x] The dead-end guidance survives (FR-031, SC-002, both audits' P2)
      -> `AvailabilityGuidance` is unchanged and still renders **only** when no
      provider is usable, in place of the picker and the start action, still
      blocking page 1. `AgentSetup.tsx` documents the two branches as answers to
      two different questions so a later reader does not unify them.
- [x] Required-field message: direct, and in the attention colour, on every
      blocking page
      -> the lead-in is gone and each reason states the fact
      (`Required: where your work is, or "I don't have a codebase".`). Rendered
      with `role="alert" aria-live="assertive"` on `bg-red-50` / `text-red-700`,
      matching `frontend/src/components/Git/CommitDialog.tsx` — the
      repository's existing dialog error treatment. Applies to pages 1, 2 and 3
      (question 2 in no-codebase mode) because it renders in the shared footer
      for whichever page is blocking. FR-020's other half is asserted: the
      attention colour never reaches a skipped question, which keeps a neutral
      chip.
- [x] Guard against the filler returning
      -> `BringInMyWorkDialog.test.tsx` walks every page asserting the nine cut
      phrases are absent by their exact words, so a re-add is a visible test
      edit rather than a silent regression.
- [x] Frontend tests
      -> `npx vitest run BringInMyWorkDialog` — 61 tests; `npx vitest run
      ProviderPicker SetupScreen ProviderExtensibility` — 28 tests. Full suite
      `npx vitest run` — **125 files / 1265 tests passing**. `npm run lint` 0
      errors and the same 40 pre-existing warnings; `tsc --noEmit` clean;
      `prettier --check .` clean.

**Reported, not fixed — out of scope.** `Install the Qoder CLI CLI` is composed
by `install_hint` in `src/scistudio/ai/agent/availability.py:659` (A1's file,
#2000): `f"Install the {descriptor.label} CLI so that …"` appends `CLI` to a
label that already ends in it. Two providers are affected — `Qoder CLI` and
`Qoder CLI (China)` — and `src/scistudio/blocks/ai/ai_block.py:604` repeats the
pattern in its own error text. The fix is to use the label as-is when it already
contains `CLI` as a word. Not applied: the manager's scope lift covered
`ProviderPicker.tsx` only, and `src/scistudio/**` belongs to another track. After
this change the string appears only in the no-usable-provider guidance.

## 12. Verification Evidence

All commands below were run by the manager on the **integrated** umbrella tree
(`track/adr-053-work-import`), not on an individual agent branch. Per-track
evidence is in each agent's gate ledger.

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Targeted backend tests | `pytest tests/ai/test_work_import_brief.py tests/api/test_agent_availability.py tests/api/test_work_import_session.py` | `[x]` | 191 passed (143 at first integration; +5 orphan reclamation, +42 from the audit and copy rounds, +1 duplicated-CLI) |
| Frozen PTY route regression | `pytest tests/api -k "pty or ai_pty"` | `[x]` | 109 passed |
| Frontend suite | `npx vitest run` in `frontend/` | `[x]` | 125 files, 1265 passed |
| Frontend smoke check | toolbar entry with and without a project; dialog in codebase mode, no-codebase mode, and no-usable-agent | `[x]` | run by A4 against the real component tree; re-verified by the with-context audit |
| **Live desktop run** | Electron + vite + runtime, all three on this branch | `[x]` | Owner drove the real desktop app on 2026-08-07/08 and accepted the result. Four availability states observed against real binaries on the owner's machine, including the FR-033 case a presence check would have called ready |
| Spec §4.6 byte-identity | `sha256` of the fenced block at `origin/main` vs head, and vs `brief_template.md` | `[x]` | identical on all three; independently re-verified by the with-context audit with `diff` and `cmp` |
| Scope compliance | `git diff --name-only origin/main...HEAD` against the §6 write sets | `[x]` | `pyproject.toml` absent from the diff; A1/A2/A3 inside their write sets; A4 also wrote `docs/specs/**` (declared, see §13) |
| Full audit | `full_audit` via `gate_record check` | `[x]` | pass, 0 errors, 0 findings on touched files |
| Import contracts | `lint-imports` | `[x]` | 13 contracts kept, 0 broken |
| Lint / format / types | `ruff check`, `ruff format --check`, `mypy`, `tsc --noEmit`, `eslint`, `prettier --check` | `[x]` | clean |
| With-context audit | `docs/audit/2026-08-07-adr-053-work-import-with-context.md` | `[x]` | pass-with-fixes, no P1 |
| No-context audit | `docs/audit/2026-08-07-adr-053-work-import-no-context.md` | `[ ]` | dispatched |
| Sentrux | `mcp__sentrux__*` / `sentrux scan .` | `[x]` | **N/A — unavailable.** No Sentrux MCP server is connected to any runtime in this dispatch and no `sentrux` binary is on PATH. Recorded as unavailable in every agent ledger rather than claimed; the `sentrux_gate` guard itself ran inside `check` and passed with one advisory info finding |
| Gate ledger check (pre-PR) | `gate_record check --mode pre-pr --base origin/main --head HEAD --pr-body-file .workflow/local/pr-body.md` | `[!]` | blocked by `checks.python_tests` (#2030), the sole unsatisfied obligation on every agent branch and on the integrated tree. See §2.2 |
| Gate finalize (pre-PR) | `gate_record finalize --commit <sha> --pr-body-file … --closes "#2000" --closes "#2001" --closes "#2002"` | `[!]` | blocked by the same obligation |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run` | `[!]` | blocked by the same obligation |

### 12.1 What Is Not Verified By A Test

**SC-001's second half.** "A user with no codebase can complete the flow end to
end **and finish the session with at least one working block in their project**."
The product half — dialog completes with no file path, brief composes, session
spawns — is covered by the suites above. The clause after "and" depends on what
the agent does once it is running, which FR-039 deliberately leaves unenforced,
so no test in this PR can establish it. Establishing it needs a live session
against a configured agent. Not run; flagged to the owner rather than recorded
as passing. `#2020` and `#2022` sit directly in that clause's path.

**FR-039 and the corrected FR-012** are negative requirements — that no test
gate exists, and that no write path exists. Verified by absence in the diff and
by grep, not by a test.

**FR-042** is structural: neither `ProviderPicker.tsx` nor
`PermissionModePicker.tsx` appears in the diff, which is the whole assertion.

## 13. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-08-07 | manager | Spec FR-012 asserted the personal-library destination depends on the personal tool library spec's FR-006 write endpoint. §4.6 has the agent write those directories directly with its shell, so no endpoint is involved. | Owner directive: correct FR-012 in this dispatch and build no write path. Assigned to A2. | `#2001` |
| 2026-08-07 | manager | Spec §4.1 and §4.5 state that `#2003` is unmerged. It merged 2026-08-07. | Owner directive: correct the stale statements. Assigned to A2. | `#2001` |
| 2026-08-07 | manager | Spec §4.4 and the Key Entities table cite FR numbers that do not match the requirements they name (for example "Preset grouping (FR-015)" where FR-014 defines presets, and "Availability states (FR-027, FR-029)" where FR-031 and FR-033 define them). | Owner set a complete-delivery goal with no deferrals, and these references misdirect anyone implementing from the spec. Corrected in this dispatch, outside §4.6. A2 found 17, from two systematic off-by-N drifts left by later FR insertions. | `#2001` |
| 2026-08-07 | manager | I extended A2's scope to `pyproject.toml` to declare `ai/work_import/**/*.md` as package data, on the stated premise that `compose_brief` would fail on a wheel install. A2 measured three clean builds and disproved it: the template already ships via setuptools' `include-package-data` plus the setuptools-scm git file-finder, and the repository's only wheel build (`ci.yml`) runs against a checkout that has `.git`. | Reverted the entry and its pinning test on the umbrella. The premise for the scope extension was false, and keeping the edit would put a `governance_touch` declaration on a feature PR for hardening the spec does not ask for. The hardening is real and is tracked separately. | `#2032` |
| 2026-08-07 | manager | A4 could not commit at all: creating `BringInMyWorkDialog.tsx` made the spec's `planned_governs.files` entry resolve, and `planned_surface_findings` raises ERROR on a resolved planned file regardless of spec status. | A4 stopped at the scope boundary rather than editing another agent's file, which was correct, and I reassigned the migration to A2. On its second run A4 also applied the migration itself, declaring it as a ledger amendment, so **both branches carried it**. The two frontmatter blocks were byte-identical and A4 changed nothing else in the spec; the merge took A2's file wholesale because it is a strict superset. Corrected here after the with-context audit found this row asserting only A4's first-run behaviour. | `#2001` |
| 2026-08-07 | manager | `python_tests` is unsatisfiable on this Windows workstation, blocking PR creation for every agent and for the final PR. Verified on the umbrella base with no feature code present: the same failures. | Agents instructed to push branches instead of opening PRs; manager integrates. Root cause is partly environmental — see §2.2. Escalated to the owner. | `#2030` |
| 2026-08-07 | fix | Contract C1 gained two fields after the audits: `next_step` and `session_unsupported_reason`. C1 was declared frozen in §7.1 as the seam two tracks were built against in parallel, so extending it is drift against that declaration. | Both audits found guidance that named no action, and the no-context audit's P1 was a provider being offered for a session it cannot run — neither is fixable inside the three-field shape. Both new fields are additive and nullable, so no existing consumer breaks; both are backed by the ADR-034 registry, which is where the facts already live. Pinned in `test_response_matches_contract_c1`. | `#2001` |
| 2026-08-07 | fix | The spec's `governs` block was expanded from three files to the real surface, which enlarges the dormant precondition in §13.1 rather than clearing it: flipping `status` now requires `docs/adr/ADR-053.md` to cover about twenty paths instead of one. | `status` deliberately left `Draft`. ADR-053 declares `agent_editable: false`, so the flip is an owner action; the files it would need to cover are listed in §13.1 so the owner has the whole edit in one place rather than discovering it from a failing audit. | `#2001` |
| 2026-08-07 | manager | The spec's `status: Draft` understates a fully implemented feature, but flipping it activates `_active_governance` in `closure.py`/`doc_drift.py`, which would require `docs/adr/ADR-053.md`'s `governs.files` to cover the dialog path. ADR-053 declares `agent_editable: false`, so no agent may make that edit. | **Owner directive 2026-08-07: leave it at Draft — it does not affect the implementation.** The spec's `governs.files` and `tests:` are still expanded to describe the change; only the status flip is deferred to the owner. | owner |
| 2026-08-07 | manager | Owner directed the manager to carry the dispatch through to the final PR without further check-ins, while `#2030` and the merge decision remain open. | Completing every step the manager is authorised to take: fixes, integration, verification, gate evidence, and the final PR body with closing keywords. Not taken: merging to `main`, applying a bypass label, and touching another session's uncommitted `#2030` work — all three need owner authorisation. | `#2030` |

| 2026-08-07 | manager | CI's CodeQL check reports five `py/path-injection` alerts. **Three are pre-existing** — `validation.py:44`, `validation.py:47`, and `engine.py`, all first seen 2026-05-22; the first two files are untouched by this PR and the third only moved line numbers under A3's refactor. **Two are new**: `work_import.py` where the brief directory is created and the brief written. | `project_dir` reaches those lines only through `_validate_project_dir`, the same validator the frozen PTY route uses, whose own docstring records that CodeQL flags it regardless and that the alert is accepted given the allowlist check. Every appended segment is a module constant or generated filename. The rationale is now recorded at the two new sites, with the one honest difference stated: the PTY route only makes the directory a subprocess `cwd`, this one creates directories and writes a file under it. **Not silently accepted — dismissing a CodeQL alert needs repository-admin rights the manager does not have, so this is an owner decision.** No project-marker hardening was invented: no such helper exists in the repository, and adding one would change endpoint behaviour on a security path without an audit round. | owner |

| 2026-08-07 | manager | **Codex review, P1 — accepted as a rule violation.** Five agents were given rows in this one checklist and run in parallel. `docs/ai-developer/specific_rules/agent-dispatch.md` §8 makes two agents editing one file without manager sequencing a hard fail; assigning disjoint *sections* does not satisfy it. | The dispatch had already run. Outcome recorded honestly rather than rationalised: four of the five auto-merged because the sections were disjoint, and the fifth (the fix track) conflicted and was resolved by hand, keeping both sides. The rule exists because that outcome was luck, not design. A future dispatch of this shape must make the manager the sole checklist writer and have agents report rows back, or sequence the writes explicitly. | `#2001` |
| 2026-08-07 | manager | **Codex review, P1 — accepted.** The committed dispatch prompts told agents to run `gate_record check --mode pre-pr` and the PR wrapper without `--base`. On a stacked branch `resolve_default_base()` falls back to `origin/main`, pulling the umbrella's own commits into the agent's observed diff and failing `scope.out-of-scope` on files it never touched. | A1 hit exactly this and reported it mid-flight; I passed the fix to A3 and A4 by message, so the live dispatch recovered — but the committed prompt, which is what a future reader copies, still carried the defect. Corrected: every `check`, `finalize`, and wrapper invocation in the prompts now passes `--base`, and the `SCISTUDIO_GATE_BASE` export is spelled out for the hooks that take none. | `#2001` |
| 2026-08-07 | manager | **Codex review, P1 — accepted.** A2's prompt required a test asserting "every context field reaches the output" while also requiring the brief to match §4.6 verbatim. The two cannot both hold: C2 carries `provider` and `permission_mode`, §4.6 has no placeholder for either, and FR-026 forbids adding one. | A2 found the same contradiction and stopped to ask rather than resolving it silently; I ruled for FR-026 and it pinned the decision with a test. The committed prompt still carried the impossible instruction. Corrected to require only fields §4.6 gives a substitution point, and to say explicitly that provider and permission mode ride on the context for the spawn. | `#2002` |
| 2026-08-07 | manager | **Codex review, P1 — accepted, real defect, fixed with tests.** A pre-spawned work-import PTY whose WebSocket never arrives is never reclaimed: only `pty_endpoint`'s teardown pops `_active_ptys`. A dismissed dialog, a navigation, or a failed WebSocket leaves a live agent holding a cap slot, and enough of them exhaust `MAX_ACTIVE_PTYS` and refuse every agent chat until restart. Bring In My Work made this reachable in ordinary use, where the AI Block's handoff is driven by a workflow run. | Added `reclaim_orphaned_prespawned_tabs()` in `ai_pty/engine.py`, called at both points a slot is about to be needed. An entry is orphaned only when pre-spawned, never joined, and past a 120 s grace; `pty_endpoint` stamps `_engine_joined` on join so a live session is never reaped. Five tests, including the cap-exhaustion case that failed before the fix and the AI Block orphan whose run maps must also be cleared. | `#2001` |
| 2026-08-07 | manager | **Codex review, P2 — accepted.** Only the generic template path was recorded for the no-context audit prompt, while `agent-dispatch.md` requires each filled prompt saved or linked, so a reviewer could not check what surfaces and instructions AU2 actually received. | The filled AU2 prompt is now committed verbatim in the prompts file. It leaks nothing into that audit: the prompt is context-free by construction and the audit has already run. My original reason for withholding it confused "the audit must not see context" with "the reader must not see the prompt". | `#2001` |

| 2026-08-07 | manager | Owner drove the live desktop build and found the dialog too long to fill in: "一个长问卷用户看着很难受，也懒得填". | Paged it, one question per page, page 1 for setup — which is also the shape #2001 already describes, separating "dialog, page one" from "the four questions". The single scrolling page was A4's own reading. §11.6. | `#2001` |
| 2026-08-08 | manager | Owner's copy pass on the paged build: nine strings were prose explaining the control beside them, the required-field message read as condescending and was too quiet to see, and the unusable-agent list was filler. | Cut all nine. Required fields say `Required: …` in the red banner `CommitDialog` already uses, on every blocking page. Unusable agents moved into the one dropdown, greyed with a short suffix — the pattern the AI chat already uses, which the owner named. §11.7. | `#2001` |
| 2026-08-08 | manager | Lifting `ProviderPicker.tsx` out of scope was mine to authorise and I did. FR-042 forbids a second provider implementation. | Extending the shared component serves FR-042's purpose better than a fork: one optional prop, absent for the AI chat, whose behaviour is pinned by a new regression test fixing the whole option list as data. `SetupScreen.tsx` has zero diff lines, verified independently. | `#2001` |
| 2026-08-17 | implementer | Owner directive after the feature shipped: *"加一个问用户的问题放最后：问用户在开始之前还有别的想和 agent 说的东西吗？然后这个问题的答案一起放进 prompt，允许跳过这个问题"* — the four questions each ask about one specific thing, so a user whose most important fact is none of those four has nowhere to put it. | Added question 5 as FR-019a: free text, asked last, skippable like questions 3 and 4, carried to the brief as `anything_else` through the same skipped/answered machinery. Contract C2's field table above is updated with it; nothing about the existing four questions changed. | `#2070` |
| 2026-08-08 | manager | The dialog agent declined to fix `Install the Qoder CLI CLI` because it lives in `availability.py`, outside the scope I gave it. That was correct. | Fixed by the manager. My first attempt wrote a literal backspace byte into the source — a regex escape eaten between the heredoc and Python — which `grep` showed as fine and `cat -A` showed as `^H`. Rewritten without a regex. The test walks the whole registry rather than the two known offenders. | `#2000` |

## 13.1 Dormant Preconditions

Recorded because they are invisible today and will fire later.

`docs/specs/adr-053-work-import.md` is `status: Draft`. `_active_governance` in
both `closure.py` and `doc_drift.py` evaluates a spec's `governs` block only
when status is `Planned` or `Implemented`, so the block is currently not
checked. Whoever flips that status must expect two findings:

- `closure.unresolved-file-claim` will require
  `frontend/src/components/BringInMyWorkDialog.tsx` to exist in the same tree.
  Satisfied once A4 is integrated.
- `doc-drift.missing-adr-governance` will require `docs/adr/ADR-053.md`'s own
  `governs.files` to cover that path. **It does not today** — ADR-053 lists the
  tutorial and palette files only. `docs/adr/ADR-053.md` is out of scope for
  this dispatch.

**Updated 2026-08-07 by the fix track (§15).** Both audits found the spec's
`governs` block describing three files where the change created about twenty,
and naming neither new API entry point; it now describes the real surface —
three modules, four contracts, `GET /api/ai/availability`,
`POST /api/work-import/sessions`, and every file this feature owns. That makes
the precondition above **larger**, not smaller: a status flip now needs
ADR-053's `governs.files` to cover all of them, not just the dialog.

`status` was deliberately left at `Draft`. Flipping it is blocked on an owner
edit to `docs/adr/ADR-053.md`, whose frontmatter declares
`agent_editable: false` — no agent in this dispatch may make that edit, and
flipping the status without it turns a dormant precondition into a failing
audit. **This is an owner action, not a deferral by an agent.** Files ADR-053
would have to cover, beyond the tutorial and palette entries it lists today:

- `src/scistudio/ai/agent/availability.py`
- `src/scistudio/ai/work_import/**`
- `src/scistudio/api/routes/work_import.py`
- `frontend/src/components/BringInMyWorkDialog.tsx`
- `frontend/src/components/BringInMyWorkDialog.parts/**`
- `frontend/src/lib/api/agentAvailability.ts`, `frontend/src/lib/api/workImport.ts`

## 14. Final Readiness

- [x] All dispatched agents have final outputs.
      -> A1 #2000, A2 #2002, A3 and A4 #2001, AU1 and AU2 audits, and the fix
      track. Seven branches, all reviewed and merged into the umbrella.
- [x] Manager reviewed every changed file.
      -> Reviewed by diff, not by agent summary. Independently re-verified the
      claims most likely to be wrong: §4.6 byte-identity by sha256 at both ends,
      the widened join predicate in the ADR-034-frozen route line by line, the
      P1 reproduction against the real endpoint before and after, the six
      post-merge assertions on the A2/A4 spec collision, and the recorded
      ledger commits against actual history.
- [x] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
      -> `.workflow/records/2000-adr-053-work-import.json`; Sentrux recorded as
      unavailable with the reason (§4), pre-PR and post-PR finalize both run.
- [x] PR closes every issue fixed by the dispatch (`#2000`, `#2001`, `#2002`).
      -> PR #2028 body carries all three closing keywords.
- [!] CI passed.
      -> **15 of 16 checks pass. One is red: `CodeQL`.** Passing:
      `Test (Python 3.11)`, `Test (Python 3.13)`, `Frontend`, `Full Audit`,
      `Type Check`, `Import Contracts`, `Architecture Tests`, `Lint & Format`,
      `Wheel Release Smoke`, `Verify Workflow Compliance`, `Deferral discipline
      ratchet`, `Semantic duplication ratchet`, and all three CodeQL `Analyze`
      jobs. Both Python test jobs passing settles #2030: those six failures are
      Windows-only. The red `CodeQL` check is five `py/path-injection` alerts,
      three pre-existing and two new, analysed in §13 — accept-or-harden is an
      owner decision because dismissing an alert needs repository-admin rights.
      CI also caught the deferral ratchet, which the local tier-selected set did
      not include for this diff; fixed and now green.
- [x] Checklist final state matches PR and gate record.

### 14.1 What The Manager Did Not Do, And Why

Three actions were available and were not taken, because each needs owner
authorisation that was not given:

- **Merging to `main`.** No AI agent merges without explicit administrator
  authorisation (`docs/ai-developer/rules.md` §3).
- **Applying a bypass label.** `admin-approved:bypass` would have let the PR
  wrapper past `checks.python_tests`. The owner authorised neither the label nor
  the bypass, and `SCISTUDIO_SKIP_PREFLIGHT` was never set.
- **Committing another session's uncommitted `#2030` fix.** A fix for those nine
  failures exists as uncommitted work in `SciStudio-wt-2028` on branch
  `test/2030-windows-test-failures`. It is not this dispatch's work and taking it
  would overwrite a parallel session.

PR #2028 was converted from the `[DO NOT MERGE]` umbrella PR into the final
review PR rather than opened as a second PR: GitHub permits one open PR per
branch pair, and the umbrella branch is the final PR's head.

### 14.2 Open For The Owner

| Item | Why it needs the owner |
|---|---|
| CodeQL: 2 new `py/path-injection` alerts | Only a repository admin can accept or dismiss a code-scanning alert. Analysis and the pre-existing/new split are in §13. This is the one CI check still red. |
| `#2030` | Blocks the local pre-PR gate only. CI is Linux and these nine pass there. Read §2.2 first: three of the nine are a stale editable install, not test defects, so patching the shipped hook would compensate in product code for one workstation's broken venv. |
| Merge authorisation | Policy: no AI merge without explicit administrator authorisation. |
| Spec `status` flip | Owner-directed to stay `Draft`. Flipping it needs `docs/adr/ADR-053.md` to govern ~20 paths; that ADR declares `agent_editable: false`. The exact list is in §13.1. |
| `#2032` | Packaging hardening split out of this PR to keep a `governance_touch` declaration off a feature PR. |
| SC-001's agent-outcome half | Needs a live session against a configured agent. Not run. See §12.1. |
