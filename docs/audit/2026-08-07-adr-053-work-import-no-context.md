# Audit: ADR-053 Bring In My Work (no-context)

- Date: 2026-08-07
- Persona: `audit_reviewer`, **no-context** mode
- Branch / worktree: `audit/2001-work-import-no-context` @
  `C:/Users/jiazh/workspace/SciStudio-wt-wi-au2`
- Change under review: `origin/main...track/adr-053-work-import`
  (`origin/main` = `b485e293`, branch head = `2c705ceb`)
- Judged against: `docs/specs/adr-053-work-import.md`, `docs/adr/ADR-053.md`,
  `docs/adr/ADR-034.md` / `docs/specs/adr-034-multi-provider-agent-chat.md`,
  and the repository's own tooling under `src/scistudio/qa/`.

Per the dispatch I did not read `docs/planning/adr-053-work-import-checklist.md`,
`docs/planning/adr-053-work-import-dispatch-prompts.md`, `.workflow/records/**`,
any issue or PR text, the branch's commit messages, or any peer audit report.
The diff was read as `git diff origin/main...HEAD -- <paths>`. Everything below
comes from the committed source, the committed specs and ADRs, and commands I
ran myself.

---

## 0. What I actually ran

| Command | Result |
|---|---|
| `pytest tests/api/test_agent_availability.py tests/ai/test_work_import_brief.py tests/api/test_work_import_session.py` | 143 passed |
| `pytest tests/api tests/ai` | 3 failures, **all reproduce at `origin/main`** (§6) |
| `pytest tests/api/test_ai_pty*.py tests/api/test_provider_discovery.py tests/architecture` | all pass (1 pre-existing skip) |
| `npm ci && npx vitest run` (frontend, full suite) | 123 files / 1226 tests passed |
| `npx tsc --noEmit` | clean |
| `npx eslint <changed frontend paths>` | 0 errors (1 pre-existing warning in an untouched file) |
| `npx prettier --check <changed frontend paths>` | clean |
| `ruff check` / `ruff format --check src tests` | clean (780 files) |
| `mypy` over the new backend modules | clean |
| `python -m scistudio.qa.audit.full_audit --repo-root .` | `status: pass`, 0 findings, 9 child reports |
| Byte-compare of spec §4.6's fenced block against `brief_template.md` (own script) | **identical**, 18777 bytes, no CRLF on either side |
| `claude --help` / `codex exec --help` on the installed CLIs | every flag in `MINIMAL_CALLS` exists |
| Own script: `_initial_prompt_argv(descriptor, …)` for all five registry agents | `kimi-code` **raises** (§1, P1-1) |
| Own script: real `POST /api/work-import/sessions` with `provider="kimi-code"` against `create_app()` | **HTTP 500**, orphaned brief written (§1, P1-1) |

---

## 1. Findings

### P1-1 — A session started on `kimi-code` dies with an opaque HTTP 500 and orphans its brief

**What I observed.** I posted a well-formed body to the real endpoint with
`provider: "kimi-code"` (no monkeypatching, real `_spawn`):

```
STATUS: 500
BODY  : {"detail":"Internal Server Error","request_id":"9211d21c96dc4464"}
orphaned brief files written: 1 ['20260807T073310Z-4e14e182.md']
```

The traceback runs
`work_import.py:236` → `engine.py:212` → `engine.py:142` → `_state.py:121`
→ `terminal.py:789` → `terminal.py:852`:

- `src/scistudio/ai/agent/providers_registry.py:652-658` declares
  `prompt_argv_prefix=None` for `kimi-code`, because its first positional is
  parsed as a subcommand.
- `src/scistudio/ai/agent/terminal.py:849-856` raises `ValueError` rather than
  silently dropping the prompt when `prompt_argv_prefix is None`.
- `src/scistudio/api/routes/work_import.py:242-247` catches only
  `FileNotFoundError` and `RuntimeError`. `ValueError` escapes, so FastAPI
  returns a bare 500 and the registry's own explanation — the one sentence that
  tells the user what to do — never reaches the caller. The frontend surfaces
  it as the string `Internal Server Error` (`frontend/src/lib/api/core.ts:66-88`,
  rendered at `BringInMyWorkDialog.tsx:323-327`).
- The brief was written at `work_import.py:227` before the spawn, so a failed
  session leaves a file behind in the user's project with no cleanup.

**Why this reaches a real user.** `kimi-code` can legitimately be graded
`ready`: its live minimal call (`availability.py:353-356`) uses `-p`, which Kimi
Code *does* support. A `ready` provider is offered in the picker
(`availability.ts:56-64`) and, when it is the only usable one, is
**auto-selected** by FR-043 (`availability.ts:100-108`). A user whose only agent
is Kimi Code therefore fills in the whole dialog, presses Start, and gets
`Internal Server Error`.

**Requirements broken.**

- FR-029: *"Routing the brief through a file and a pointer gives every provider
  identical behaviour, and adding a provider later requires nothing of it beyond
  reading a file it is told to read."* Delivery in fact depends on the provider
  having a positional prompt argument. `open_work_import_tab`'s docstring
  (`engine.py:170-211`) asserts the opposite in as many words.
- FR-022 / FR-024 for that provider: no session starts at all.
- Dispatch question 8: a 500 where a 4xx (or, better, exclusion at the picker)
  is correct, and the information the caller needs is lost.

**The guard already exists elsewhere and was not carried over.**
`src/scistudio/blocks/ai/ai_block.py:611-622` refuses at config time with
`descriptor.prompt_unsupported_reason`, with a comment explaining that the
alternative is *"an opaque PTY exit code"*. The work-import path shares
`_open_prespawned_tab` with the AI Block but not this check.

**Why the tests did not catch it.**
`tests/api/test_work_import_session.py:400-421`
(`test_delivery_is_identical_across_system_prompt_strategies`) is parametrised
over **every** registry agent key, including `kimi-code`, and passes — because
the `spawn` fixture (`:134-148`) monkeypatches `ai_pty._state._spawn` with
`_SpawnRecorder`, which never calls `spawn_agent`. The test proves the endpoint
hands the prompt to `_spawn`; it does not prove `_spawn` can deliver it. This is
precisely the shape of assertion the dispatch asked me to look for: the test
claims FR-029 ("delivery is identical across providers") and establishes
something strictly weaker.

---

### P2-1 — `call_failed` copy states something false and prescribes an action the user cannot take

`frontend/src/components/BringInMyWorkDialog.parts/copy.ts:249-253`:

```
CALL_FAILED_HEADING = "Your agent answered, but the call failed"
CALL_FAILED_BODY    = "Nothing on your computer needs changing — the agent is
                       present and signed in. The call itself did not go through:"
CALL_FAILED_FOOTER  = "Try again once that is resolved. Your setup is fine as it is."
```

Three problems, each evidenced by this change's own code:

1. **"Nothing on your computer needs changing" is often false.** The
   implementation's own measurement table
   (`src/scistudio/ai/agent/availability.py:294-307`) records the observed
   `kimi-code` failure as *"No model configured."* — a local configuration
   problem the user must fix on their computer. The dialog would tell that user
   their setup is fine and to try again, which will never help.
2. **The sanitiser can strip the only actionable line and leave the false
   reassurance standing.** `_REINSTALL_GUIDANCE`
   (`availability.py:367-370`) drops any line matching
   `download .*install(er)?` / `re-?install` / `npm install -g`. A CLI that fails
   with *"your version is out of date; download the new installer"* loses that
   line, falls back to `_CAUSE_NO_MESSAGE` (`availability.py:379`, *"reported an
   error but produced no readable message"*), and the user is then told their
   setup is fine. FR-034 forbids *suggesting* reinstalling; it does not license
   asserting that nothing is wrong.
3. **"Try again" has no control.** `useAgentAvailability`
   (`useAgentAvailability.ts:71-107`) calls `fetchAgentAvailability()` with no
   arguments, so `refresh=true` (`agentAvailability.ts:78-84`) is never used
   anywhere in the product. The only way to retry is to close and reopen the
   dialog, and within `CACHE_TTL_SECONDS = 60` (`availability.py:206`) that
   returns the memoised failure. A user who fixes their quota and immediately
   retries is told it still failed.

Nothing in the test suite asserts the content of `CALL_FAILED_BODY` or
`CALL_FAILED_FOOTER`; `BringInMyWorkDialog.test.tsx:284-298` asserts only that
the panel contains the cause and does not match `/install/i`.

---

### P2-2 — The `not_installed` and `not_authenticated` states do not carry the guidance FR-031 and ADR-053 §5.2 require, and the tests assert something weaker

FR-031's table (spec `:446-451`) and the identical table in `docs/adr/ADR-053.md:469-474`
specify the guidance column as **"Installation instructions"** and **"Login
instructions for the detected provider"**. SC-002 (spec `:1058-1060`) requires
each state to present *"guidance naming a specific next action"*.

What ships (`copy.ts:232-240`):

- `not_installed`: *"Bring in my work runs a coding-agent CLI that you set up on
  your own computer. Set one of the supported agents up, then open this dialog
  again."* No install command, no link, no per-provider detail. The provider
  rows beneath it (`AvailabilityGuidance.tsx:62-68`) render bare labels, because
  `cause` is `null` for this state by construction (`availability.py:150-153`).
- `not_authenticated`: *"These agents are present but have no valid sign-in. Sign
  in the way that agent expects, then open this dialog again."* This is the
  explicit **absence** of "login instructions for the detected provider" — it
  tells the user to already know the answer.

The tests do not close the gap:

- `BringInMyWorkDialog.test.tsx:260-270` asserts only that
  `work-import-guidance-not_installed` exists and that no start action renders.
  It would pass with an empty body.
- `BringInMyWorkDialog.test.tsx:272-282` claims *"shows sign-in guidance for the
  detected provider"* and asserts only `/sign/i` plus the provider label. It
  would pass with the string "sign" and the label alone.

I could not trace FR-031's guidance column for two of its four rows to either an
implementation or a test.

---

### P2-3 — The client probe timeout is shorter than the server's own budget, so a slow-but-working agent is reported as failed and the feature is withheld

| Bound | Value | Location |
|---|---|---|
| Client probe cap | **10 s** | `useAgentAvailability.ts:44` |
| Server per-call timeout | 15 s | `availability.py:191` |
| Server report budget | 20 s | `availability.py:199` |
| Slowest observed successful call (Qoder) | 8.3 s | `availability.py:294-303` |

`availability.py:185-190` justifies 15 s as *"roughly 1.8x headroom for a cold
CLI start or a slow network without turning a working provider into a reported
failure."* The client then discards that headroom: at 10 s it aborts locally,
sets `probeError`, and `availability` stays `null`. The dialog
(`BringInMyWorkDialog.tsx:266-277`, `:342-352`) then renders the `call_failed`
guidance block and **no start action at all**.

So a user with a working Qoder install — 8.3 s on the owner's own machine,
1.7 s of margin — is told *"Your agent answered, but the call failed … the agent
is present and signed in … Your setup is fine as it is"* and cannot start a
session. There is no `AbortController`, so the request keeps running and the
backend does eventually memoise a `ready` report; the user's only recovery is to
close and reopen the dialog and hope the 60 s cache is still warm.

This contradicts FR-031 (a provider whose live call succeeds is `ready`),
FR-005, and SC-002 (*"no state presents guidance for a different state's
cause"*). No test covers the interaction of the two timeouts; the only
timeout test (`BringInMyWorkDialog.test.tsx:339-352`) uses a never-resolving
promise, which cannot distinguish "slow" from "broken".

---

### P2-4 — The frozen `WS /api/ai/pty/{tab_id}` route was modified while the in-repo "do not modify" marker was left standing

**Which route.** `src/scistudio/api/routes/ai_pty/engine.py:1-6` — unchanged by
this diff — still reads:

> *"The existing `WS /api/ai/pty/{tab_id}` route in `._websocket` is the
> user-launched path … That route is FROZEN per ADR-034 — do not modify."*

**It changed.** `src/scistudio/api/routes/ai_pty/websocket.py:69-95` widens the
join predicate from `getattr(candidate, "_engine_block_run_id", None)` to
`getattr(candidate, "_engine_prespawned", False) or getattr(candidate,
"_engine_block_run_id", None)`. `ai_pty/__init__.py:45-54` deletes the previous
sentence asserting that ADR-035 extended the package *"without modifying the
existing `WS /api/ai/pty/{tab_id}` handler"* and replaces it with a claim that
the handler is *"otherwise unchanged"*.

**Observable behaviour — I checked, and it is preserved.** `_engine_prespawned`
is stamped only by `_open_prespawned_tab` (`engine.py:153`), which also
stamps `_engine_block_run_id` whenever `block_run_id is not None`, so every
AI Block tab satisfies the old predicate too and joins exactly as before; an
unmarked PTY still takes the spawn path. `tests/api/test_work_import_session.py:665-754`
pins the query-parameter contract, spawn semantics, error frames, teardown, cap,
and the unmarked-PTY case, and `tests/api/test_ai_pty.py`,
`test_ai_pty_audit_fixes.py`, `test_ai_pty_engine_spawn.py` all pass on this
branch.

**One observable difference I did find.** The pre-spawn error strings changed
from `open_engine_initiated_tab: …` to `pre-spawned PTY tab: …`
(`engine.py:128-140` vs. the deleted lines). `internal_routes.py:100-108`
returns those strings verbatim to the AI Block worker and routes on
`"cap" in msg.lower()`, which still matches the new cap message. No test pinned
the old strings, so nothing failed — but the frozen route's diagnostic surface
is not byte-identical.

**Why this is still a finding.** The freeze marker is a committed statement that
now contradicts the code beside it, and no ADR, addendum, or spec in this diff
records the exception. Either the marker needs amending to name the permitted
extension, or the change needs an owner ruling. This is a documentation/
governance defect, not a behavioural one.

---

### P2-5 — The spec's `governs` frontmatter does not cover the surfaces this change created, and the spec is still `Draft`

`docs/specs/adr-053-work-import.md:35-56`, after this change:

```yaml
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/adr-053-work-import.md
    - docs/adr/ADR-053.md
    - frontend/src/components/BringInMyWorkDialog.tsx
planned_governs: {…all empty…}
tests:
  - tests/api/test_agent_availability.py
  - frontend/src/components/__tests__/BringInMyWorkDialog.test.tsx
```

The change created, and no spec governs:

- `src/scistudio/ai/agent/availability.py`
- `src/scistudio/ai/work_import/**` (4 files including `brief_template.md`)
- `src/scistudio/api/routes/work_import.py`
- `frontend/src/components/BringInMyWorkDialog.parts/**` (9 files)
- `frontend/src/lib/api/workImport.ts`, `frontend/src/lib/api/agentAvailability.ts`

`governs.entry_points` is `[]` although the change adds two:
`GET /api/ai/availability` (`ai.py:128-171`) and
`POST /api/work-import/sessions` (`work_import.py:175`). `tests:` names 2 of the
5 test files that landed.

`docs/ai-developer/specific_rules/document-standards.md:132-137` is explicit:
*"`governs` is the current implementation or refactor surface and must resolve
when the spec is active … if those surfaces already exist, the spec must move
them into `governs` and advance its implementation state instead of remaining
pre-implementation."* The spec's `status:` is still `Draft`.

I confirmed the repository's own tooling does **not** catch this:
`python -m scistudio.qa.audit.full_audit` reports `status: pass` with 0 findings.

---

### P3 findings

1. **Backend does not enforce FR-020's "question 1 is required."**
   `ImportSessionContext.__post_init__` (`context.py:88-121`) validates the
   source/no-codebase pair, the destination tier, the permission mode, the
   provider, and the skip shape — but accepts empty `data_kinds` **and** null
   `data_kinds_other`. The resulting brief tells the agent *"They selected:
   Nothing from the list. / They added: Nothing."* for a question the user never
   answered, which is exactly the "did not say" vs. "nothing applies" confusion
   FR-021 exists to prevent. Only the dialog (`formState.ts:100-102`) enforces it.

2. **`ImportSessionContext.is_skipped` is production-dead.** `context.py:123-132`
   is called only from `tests/ai/test_work_import_brief.py:413`. Brief
   composition never consults `context.skipped` — `_render_slot`
   (`brief.py:143-157`) branches on whether the answer text is blank. The
   behaviour is correct; the method is unused surface.

3. **Nothing keeps the dialog's preset labels equal to the brief's.**
   `copy.ts:141-152` lists `Array · Table / dataframe · Series · Image · Time
   series · Spectrum · Multi-omics · Spatial omics`; `brief_template.md` lists
   the same eight, and §4.6 says the options are reproduced *"as they saw it."*
   They match today. No test crosses the language boundary, so the first edit to
   either side silently makes the brief misreport what the user was offered.

4. **Spec §4.2 contradicts its own edit.** The same change declared #2003
   *"merged on 2026-08-07"* and removed the unmerged-dependency risk
   (`:508-516`, `:649-651`), but left `:563-564` reading *"Concrete paths for the
   last four depend on #2003's final shape and are left unresolved rather than
   guessed"* — for four surfaces that now exist at known paths.

5. **Spec Key Entities still contradicts FR-026.** The `ImportSessionContext`
   row (`:495`) describes the record as *"Everything the dialog collects,
   composed into the brief"* and lists `provider` and `permission_mode` among its
   attributes, while FR-026 requires the brief to be §4.6 verbatim and §4.6 has
   no slot for either. The implementation resolved this toward FR-026, argued it
   in `brief.py:23-28`, and pinned it at
   `tests/ai/test_work_import_brief.py:341` — which I judge correct. The same
   edit that fixed every other stale cross-reference in this table did not fix
   this row.

6. **Source modules cite a planning document as the contract authority.**
   `context.py:9-13` ("Field names, types, and order are fixed by contract C2 in
   `docs/planning/adr-053-work-import-checklist.md` §7.2"),
   `work_import/__init__.py:15`, `workImport.ts:4`, `useAgentAvailability.ts:6`,
   and unqualified "contract C1/C2" references at `brief.py:31`,
   `availability.py:128, 156, 173`. Planning documents are not governing specs
   under AGENTS.md §3.4; when the checklist is archived these references dangle.

7. **An empty provider list produces a silent dead end.** If the report is
   `{state: "not_installed", providers: []}` with no probe error,
   `guidanceGroups` returns `[]`, `AvailabilityGuidance` returns `null`
   (`AvailabilityGuidance.tsx:92`), and the blocking-reasons list is gated on
   `agentUsable` (`BringInMyWorkDialog.tsx:329`). The user gets a dialog with
   questions, no start action, and no explanation.

8. **A failed spawn orphans the brief.** `work_import.py:226-247` writes the
   brief and then spawns; every spawn failure path leaves the file behind with no
   cleanup. FR-030 wants briefs to outlive their sessions, so this is defensible —
   but a brief for a session that never existed is not the artefact FR-030
   describes. I observed one such file in the P1-1 reproduction.

9. **`MINIMAL_CALLS` is a second per-provider table outside the ADR-034
   registry** (`availability.py:314-359`), in an area the spec puts out of scope
   (*"Provider configuration … and the provider registry itself, governed by
   ADR-034"*, spec `:31`). The module argues the case
   (`availability.py:288-313`) and
   `tests/api/test_agent_availability.py:606-614` pins the table against
   `agent_keys()`, which is a real mitigation. Noting it because it is the second
   place a sixth provider must be edited.

10. **The picker hides non-ready providers entirely** (`availability.ts:56-64`),
    which loses ADR-034 FR-021a's *"marks an option the user cannot launch but
    should still see, so the supported set stays discoverable"* property inside
    this dialog. The separate unusable list (`AgentSetup.tsx:77-86`) mitigates it
    and the reasoning is written down; flagged only because the two ADRs disagree.

---

## 2. Requirements traced to both an implementation and a failing-if-wrong test

I traced all 44 functional requirements. These are the ones I judged fully
covered — implementation present, and a test that would fail if it were wrong:

FR-001, FR-002, FR-003, FR-004, FR-008, FR-009, FR-010, FR-011, FR-013, FR-014,
FR-016, FR-017, FR-018, FR-019, FR-020, FR-021, FR-023, FR-024, FR-025, FR-026,
FR-027, FR-028, FR-030, FR-032, FR-033, FR-034 (backend half), FR-035 (backend
half), FR-037, FR-038, FR-040, FR-041, FR-042, FR-043, FR-044.

Two deserve specific credit:

- **FR-024 (write before spawn)** is genuinely established, not approximated.
  `_SpawnRecorder.__call__` (`test_work_import_session.py:103-131`) parses the
  brief path **out of the opening message** and reads the file **inside the spawn
  call**, then `:238-253` asserts the snapshot equals the fully composed brief. A
  spawn that raced the write sees no file; one that raced the `close`/`fsync`
  sees a prefix. Both fail. This is the opposite of the weak "file exists
  afterwards" assertion the dispatch warned about.
- **FR-026 (brief verbatim from §4.6)** holds byte-for-byte. I extracted §4.6's
  fenced block from the spec myself and compared bytes: 18777 == 18777,
  identical, and neither file carries CRLF. `test_work_import_brief.py:101-108`
  performs the same comparison, so it cannot silently drift.

FR-029 is implemented and tested **only up to the `_spawn` boundary** — see
P1-1.

## 3. Requirements I could not trace to both

| Requirement | Implementation | Test | Note |
|---|---|---|---|
| FR-029 | partial | weaker than the claim | P1-1: fails for `kimi-code` in the real spawn path |
| FR-031 guidance (`not_installed`, `not_authenticated`) | **absent** | **absent** | P2-2 |
| FR-005 / FR-031 under a slow provider | present but defeated by the client cap | absent | P2-3 |
| FR-006, FR-007 | present | proxy only | `BringInMyWorkDialog.test.tsx:238-256` greps the rendered dialog for forbidden vocabulary. SC-004 says "measured by review", so a proxy is what the spec asks for. Accepted. |
| FR-015 ("presets MUST NOT be a routing mechanism") | implementation-by-absence | none | I grepped: nothing downstream branches on a preset value. Untestable except as a negative. |
| FR-039 ("MUST NOT enforce the existence of a test") | implementation-by-absence | none | Nothing in the diff gates on a test file. Untestable except as a negative. |
| FR-036 ("consumable by any agent-dependent surface") | present (`ai.py:130-170`, shared module placement) | endpoint only | The second consumer (Learning Center) does not exist yet, so the claim cannot be fully exercised. |
| FR-012 | present | present | Verified independently that `~/.scistudio/blocks` and `~/.scistudio/types` are real scan dirs (`ai/agent/mcp/runtime.py:108`, `api/runtime/_projects.py:64`, `core/types/registry.py:93`) and that previewers have **no** user tier (`previewers/__init__.py:117`, `previewers/project.py:41-82`, `previewers/registry.py:154-217`). §4.6's claims about both are accurate. |

## 4. Dispatch questions, answered directly

3. **Byte-identity of the reproduced instruction text** — verified myself,
   identical (§0, §2).
4. **Does the implementation make the distinction a presence check cannot?** —
   Yes. `resolve_availability` (`availability.py:524-559`) decides
   `not_installed` / `not_authenticated` from the status row and issues a real
   subprocess call only for rows that pass presence; `ready` is granted only on
   exit 0 with non-empty stdout (`availability.py:432-439`). I confirmed every
   flag in `MINIMAL_CALLS` exists on the installed `claude` and `codex` CLIs.
   One residual approximation: exit 0 with any stdout counts as success, so a CLI
   that printed a banner and exited without contacting its service would be
   graded `ready`. Not observed on the two CLIs I could check.
5. **User-facing copy prescribing an action that would not help** — yes, twice:
   P2-1 and P2-2.
6. **The frozen route** — `WS /api/ai/pty/{tab_id}`; it changed; observable
   behaviour is preserved and pinned by tests, except for internal error-message
   text returned to the AI Block worker. The "do not modify" marker was left in
   place. P2-4.
7. **Are the spec's own edits internally consistent?** — Mostly yes: every
   FR-number cross-reference in the edit is now correct (I checked all 17 against
   the renumbered body), and the FR-012 rewrite is grounded in real runtime
   behaviour. Two residual inconsistencies: P3-4 and P3-5.
8. **500 where 4xx is correct / information lost** — P1-1 (unhandled
   `ValueError` → bare 500). Elsewhere the error mapping is deliberate and good:
   `work_import.py:185-198` turns every contract-C2 violation into a 400 carrying
   the dataclass's own message, and
   `test_work_import_session.py:523-550` pins that they are 4xx and never 500.
9. **Anything the spec says should not exist** — no. The two new endpoints and
   the `.scistudio/work-import/` brief directory are all required by FR-022 /
   FR-027 / FR-036. FR-012's "no endpoint is involved" is scoped to the personal
   library write path, which this change correctly does not implement. Nothing
   enforces a test file's existence (FR-039).

## 5. What I could not verify

- Live behaviour of `kimi-code`, `qoder`, and `qoder-cn` — not installed on this
  machine. The `MINIMAL_CALLS` argv for those three rests on the module's own
  documented observations, which I could not reproduce.
- Whether a real billed call to `claude` or `codex` with the exact probe argv
  returns exit 0 and prints `ok` — I declined to spend the owner's quota. Flag
  existence is verified.
- Anything about the ADR-053 revision itself: `docs/adr/ADR-053.md` is unchanged
  by this diff and already on `origin/main`.

## 6. Test failures, and whether they belong to this change

Three failures in `pytest tests/api tests/ai` on this branch:

- `tests/api/test_filesystem_browse.py::TestBrowseFilesystem::test_overlength_path_returns_400_not_500`
- `tests/api/test_mcp_transport_publish.py::test_project_open_route_starts_project_mcp_socket`
- `tests/api/test_mcp_transport_publish.py::test_project_open_route_rebinds_missing_project_mcp_socket`

I checked out `origin/main` (`b485e293`) in this worktree and ran the same two
files: **all three reproduce identically**. They are pre-existing Windows
environment artifacts, unrelated to this change.

## 7. Recommendation

**Block.**

P1-1 makes the feature unusable — with an opaque `Internal Server Error` and a
stray file in the user's project — for any user whose working agent is Kimi Code,
which the dialog will auto-select for them. The fix is small and the precedent is
already in the repository (`ai_block.py:611-622`): refuse `prompt_argv_prefix is
None` providers with the descriptor's own explanation, before the brief is
written, as a 4xx; and exclude them from the picker so a user is never offered a
provider that cannot run a session. The FR-029 test should exercise the real
`spawn_agent` argv assembly for every provider rather than a stubbed `_spawn`.

The four P2s are all narrow and independently fixable, and P2-2 and P2-3 both
land on User Story 3, which is the story about not leaving a user in a dead end.

Everything else in this change is of high quality. The brief pipeline is
verbatim-verified end to end, the write-before-spawn ordering is proved from
inside the spawn rather than after it, the graded-availability module is honest
about its own costs and bounds, and the regression pins around the frozen WS
route are the right ones. The problems are at the edges — one provider, two
copy blocks, one timeout constant, and the spec's own bookkeeping.
