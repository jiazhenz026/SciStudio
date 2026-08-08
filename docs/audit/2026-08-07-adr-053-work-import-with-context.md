# Audit: ADR-053 Bring In My Work (with-context)

- Date: 2026-08-07
- Persona: `audit_reviewer`, `with-context` mode
- Agent: `AU1`
- Branch / worktree: `audit/2001-work-import-with-context` @
  `C:/Users/jiazh/workspace/SciStudio-wt-wi-au1`
- Change under review: `origin/main..origin/track/adr-053-work-import`
  (branch head `2c705ceb`, 44 files, +12967 / -134)
- Issues: `#2000`, `#2001`, `#2002`. Umbrella PR `#2028` `[DO NOT MERGE]`.
- Judged against: `docs/specs/adr-053-work-import.md`,
  `docs/adr/ADR-053.md` §4–§5, `docs/planning/adr-053-work-import-checklist.md`,
  the three issues, and the code and tests themselves.

## 1. Summary Judgement

**Recommendation: pass-with-fixes.** No P1. Four P2 and five P3.

This is a faithful, unusually well-documented implementation. The three claims
that carry the most weight — that the brief is byte-identical to spec §4.6, that
the brief is complete on disk *before* the agent process exists, and that the
frozen ADR-034 user-launched PTY route is unchanged — all hold, and I verified
each one by running the check myself rather than reading the claim. Every one of
FR-001 to FR-044 traces to implementation, and 39 of 44 trace to a test that
would fail if the requirement were removed.

The P2s are: two success criteria that do not hold as written (SC-002's
"specific next action" and SC-006's skipped-vs-unanswered distinction, the latter
being a spec defect rather than a code defect), one provider whose availability
probe runs with no tool restriction against a docstring that claims otherwise,
and SC-001's end-to-end half being unverified while two known adjacent defects
sit directly in its path.

## 2. What I Actually Ran

Every claim marked **observed** rests on one of these. All Python was run as
`PYTHONPATH='C:\Users\jiazh\workspace\SciStudio-wt-wi-au1\src'` (absolute — see
checklist §2.2).

| Command | Result |
|---|---|
| `pytest tests/api/test_agent_availability.py tests/ai/test_work_import_brief.py tests/api/test_work_import_session.py -q --no-cov` | **143 passed** |
| `pytest tests/api -k "pty or ai_pty" -q --no-cov` | **108 passed** |
| `pytest tests -q --no-cov` (whole suite) | **exactly 6 failures, all pre-existing `#2030`** — no new failure anywhere |
| `pytest tests/desktop/test_terminal_post_rc.py tests/api/test_mcp_transport_publish.py tests/api/test_filesystem_browse.py tests/qa/test_gate_record_hooks.py tests/cli/test_install.py` | 6 failed / 3 gate-hook tests **passed** — exactly what checklist §2.2 predicts |
| `python -m scistudio.qa.audit.full_audit` | **status `pass`**, 0 errors, 66 info + 6 warning; **0 findings on any file this dispatch touched** |
| `ruff check src tests` / `ruff format --check src tests` | clean / 780 files already formatted |
| `mypy src` | Success, no issues in 347 source files |
| import-linter (13 contracts) | **13 kept, 0 broken** — including "AI must not depend on api" |
| `npm ci && npx vitest run` in `frontend/` | **123 files / 1226 tests passed** |
| `npm run typecheck` / `npm run lint` / `npm run format:check` | clean / 0 errors, 40 pre-existing warnings / clean |
| `diff <(sed -n '672,1047p' docs/specs/…) src/scistudio/ai/work_import/brief_template.md` + `cmp` | **byte-identical** |
| `diff` of spec §4.6 at `origin/main` vs branch head | **byte-identical** (sha256 `fcbfc3d7…5766a0` both sides) |
| `git diff --stat origin/main...HEAD` | `pyproject.toml` **does not appear** |

## 3. Findings

### P1

None.

### P2-1 — `not_installed` and `not_authenticated` guidance gives a direction, not an instruction (SC-002, FR-031)

`frontend/src/components/BringInMyWorkDialog.parts/copy.ts:232-240`

```ts
export const NOT_INSTALLED_BODY =
  "Bring in my work runs a coding-agent CLI that you set up on your own computer. " +
  "Set one of the supported agents up, then open this dialog again.";
…
export const NOT_AUTHENTICATED_BODY =
  "These agents are present but have no valid sign-in. Sign in the way that agent " +
  "expects, then open this dialog again.";
```

FR-031's guidance column requires *"Installation instructions"* and *"Login
instructions for the detected provider"*. SC-002 requires guidance *"naming a
specific next action"*. US3's title is "A user without a working agent learns
**exactly** what to do".

What ships names the providers (`AvailabilityGuidance.tsx:62-68` renders one
bullet per provider in that state) but contains no command, no URL, and no step.
"Sign in the way that agent expects" is precisely the thing the user does not
know. Contrast the `call_failed` branch, which is genuinely specific because it
carries the provider's own error text.

This is the one state where the feature is a dead end rather than a setup step,
which is why ADR-053 §4.1 making an agent mandatory raised US3's priority in the
first place.

**Fix**: add a per-provider install/login line. `providers_registry` already owns
the per-provider knowledge; a `login_hint` / `install_hint` field on the
descriptor would keep it in the one place ADR-034 puts provider facts.

### P2-2 — SC-006 does not hold; the implementation collapses "skipped" and "unanswered" on purpose

`src/scistudio/ai/work_import/context.py:123-132`,
`frontend/src/components/BringInMyWorkDialog.parts/formState.ts:139-147`,
`frontend/src/lib/api/workImport.ts:174-183`

SC-006 requires *"the resulting brief distinguishes skipped questions from
unanswered ones."* It does not, and it cannot: `is_skipped()` returns true both
when the user ticked the skip control and when the field is blank, `buildRequest`
pushes every blank optional answer into `skipped[]`, and
`validateWorkImportRequest` *rejects* a body carrying a blank answer that is not
marked skipped (`"…has no answer and is not marked as skipped."`). "Unanswered
but not skipped" is unrepresentable end to end.

**This is a spec defect, not a code defect, and I do not recommend a code
change.** FR-021 — the normative requirement — asks for a different distinction:
*"so the agent can tell 'the user did not say' from 'the user said nothing
applies'"*, i.e. skipped versus answered-with-a-negative. That distinction the
implementation gets exactly right, and `test_blank_answer_is_conveyed_as_skipped`
and `test_skipped_question_renders_as_explicitly_skipped` pin it. SC-006's
second clause is the outlier and contradicts FR-021's own rationale.

**Fix**: reword SC-006's second clause to match FR-021, in the same class of spec
correction this dispatch already made three of. It sits outside §4.6.

### P2-3 — the `kimi-code` availability probe runs an agent with no tool restriction, and the test that claims otherwise excludes it

`src/scistudio/ai/agent/availability.py:350-356`,
`tests/api/test_agent_availability.py:631-643`

The module docstring and the Qoder helper both state the safety invariant
plainly (`availability.py:266-269`):

> `--tools ""` is what makes this safe as well as cheap: with no tools the CLI
> cannot read, write, or execute anything on the user's machine, so a probe fired
> on dialog open has no side effects to reason about.

`kimi-code`'s row is `argv=("--output-format", "text")` with `prompt_flag="-p"`
and nothing else. No tool switch, no sandbox. Its inline comment concedes "no
tool-restriction flag" but the invariant above is then not true of the shipped
system: opening the dialog fires a fully-tool-enabled agent.

The test named `test_the_probe_never_grants_the_cli_tools`, whose docstring reads
*"No probe may read, write, or execute on the user's machine"*, loops over
`("claude-code", "qoder", "qoder-cn")` and separately asserts Codex's read-only
sandbox. `kimi-code` is silently absent. A test that asserts a universal and
checks four of five cases is worse than no test, because it reads as coverage.

Real-world risk is low — the prompt is `"Reply with the single word: ok"` and the
cwd is a fresh `TemporaryDirectory` — but AGENTS.md §3.6 requires a deferral to
be visible in the repository, and this one is not.

**Fix**: minimum, a `TODO(#NNNN)` on the `kimi-code` row and a docstring on
`test_the_probe_never_grants_the_cli_tools` that says what it actually checks.
Better, add whatever bound Kimi Code does offer, or exclude it from live calls
and report it ungradable rather than probing it unbounded.

### P2-4 — SC-001's end-to-end half is unverified, and two known defects sit in its path

SC-001: *"A user with no codebase can complete the flow end to end **and finish
the session with at least one working block in their project**, without providing
any file path."*

The product half is implemented and tested
(`test_no_codebase_session_is_a_first_class_path`, and the dialog test *"a
no-codebase session cannot start without question 2, and can with it"*). The
second half needs a live agent session, and there is none: checklist §12
Verification Evidence is entirely `[ ]` with no evidence recorded, §14 Final
Readiness likewise, and no `docs/ai-developer/e2e/` scenario was run.

That matters more than usual here because checklist §2.1 records two open
defects that attack exactly this clause — `#2020` (the agent runtime registers no
type directory, so a drop-in type may not be visible) and `#2022` (a drop-in
block cannot import a drop-in type and is then skipped silently). Both are
correctly out of scope, but together they mean "at least one working block" is
the claim most likely to fail in a real session, and it is the one claim nobody
has observed.

**Fix**: run one live no-codebase session before the final PR, or record SC-001's
second half explicitly as owner-accepted-unverified with `#2020`/`#2022` named.
This is a manager/e2e action, not a code change.

### P3-1 — an empty provider registry renders a dialog with no agent section, no guidance and no start action

`frontend/src/components/BringInMyWorkDialog.parts/AvailabilityGuidance.tsx:91-92`
with `BringInMyWorkDialog.tsx:266-277`

Contract C1 explicitly contemplates the case: *"`not_installed` when the registry
yields no agent providers."* The backend produces it correctly
(`aggregate_state([])` → `NOT_INSTALLED`, verified by
`test_empty_registry_reports_not_installed`). The frontend derives guidance from
provider *rows* only and ignores the aggregate `state`, so with an empty
`providers` array and a successful probe, `guidanceGroups()` returns `[]`,
`AvailabilityGuidance` returns `null`, `agentUsable` is false so no start action
renders — and the user sees a dialog with no agent section and no explanation.

Unreachable in production (`agent_descriptors()` always yields the five
registered providers, pinned by `test_every_registry_agent_has_a_minimal_call`),
which is why this is P3 and not P2. Deriving from rows is otherwise the right
call and `availability.ts:36-44` explains why. One line — fall back to the
aggregate `state` when `providers` is empty — closes it.

### P3-2 — the eight preset labels are duplicated across the Python/TypeScript boundary with nothing pinning them

`frontend/src/components/BringInMyWorkDialog.parts/copy.ts:141-152` and
`src/scistudio/ai/work_import/brief_template.md:310-312`

`copy.ts:131-133` makes the claim explicitly:

> The option labels are reproduced verbatim in the brief's "What they told us"
> section (spec §4.6), so what the user saw and what the agent reads are the same
> strings.

They match today — I compared all eight. Nothing enforces it. `tests/ai` asserts
the brief side; the frontend tests assert the frontend side; no test crosses.
Editing either list silently breaks the property the brief's own preamble relies
on (*"Each question is reproduced as they saw it, including the examples and
options we offered them"*). The four question texts have the same exposure.

Not fixable by a unit test on either side alone; the cheap version is a Python
test that reads `copy.ts` and asserts the eight labels appear in the template.

### P3-3 — checklist drift: §13's account of A4's scope boundary contradicts §11.3

`docs/planning/adr-053-work-import-checklist.md:741` says:

> A4 stopped at the scope boundary rather than editing another agent's file,
> which is correct. Reassigned the frontmatter migration to A2.

A4's own commit `ce431fd0` on `feat/2001-work-import-dialog` **does** contain the
`docs/specs/adr-053-work-import.md` frontmatter edit, and its message says so
("Also migrates docs/specs/adr-053-work-import.md frontmatter"). §6 lists
`docs/specs/**` as out of scope for A4. §11.3's last row is accurate and honest
about it — "**Manager review requested**: `docs/specs/**` was outside A4's
original write set" — so the checklist contains two contradictory accounts of the
same event.

No harm in content: the manager made the identical change in `4c411589`, the
merge was clean, and the resulting frontmatter is correct. But §13 is an
append-only drift log and is currently wrong about what happened.

### P3-4 — gate-evidence accuracy: one stale commit SHA, two null finalizations

- `.workflow/records/2002-feat-2002-work-import-brief.json` records
  `commit.sha = bc9572d5…`. That commit exists but is **not an ancestor of the
  umbrella head** — it was superseded by `ba1a49ba` on rebase and never
  re-finalized. The ledger points at a commit that is not in the delivered
  history.
- `.workflow/records/2001-feat-2001-work-import-dialog.json` has
  `commit: null` and `pull_request: null` — A4's ledger was never finalized at
  all.
- `.workflow/records/2000-adr-053-work-import.json` (manager) has
  `pull_request: null` although umbrella PR `#2028` exists.

All four track ledgers reconcile `fail` on `checks.python_tests`, which is the
known `#2030` blocker and correctly not a finding against this work (§4 below).
These three are separate and are ordinary bookkeeping, fixable at final
finalization.

### P3-5 — spec staleness the corrections pass did not reach

`docs/specs/adr-053-work-import.md:563-564` still reads:

> Concrete paths for the last four depend on `#2003`'s final shape and are left
> unresolved rather than guessed.

`#2003` merged and all four paths are now concrete and shipped. This is the same
class as the two `#2003`-staleness corrections the dispatch *did* make. Related:
the spec is still `status: Draft` with the feature fully implemented, and its
`tests:` frontmatter lists two of the six test files that now cover it
(`tests/ai/test_work_import_brief.py`, `tests/api/test_work_import_session.py`,
and three frontend files are missing). Checklist §13.1 already flags what fires
when `status` flips; the `tests:` list is not covered there.

## 4. Pre-existing failures — confirmed, not caused here

**Observed, not taken on trust.** I ran the **whole** Python suite against the
branch head. It produced exactly six failures, and they are exactly the six
below — nothing this dispatch touched fails, and nothing new fails anywhere in
the suite.

Running the five files `#2030` names in isolation:

- 6 fail: `test_terminal_post_rc.py` (2), `test_mcp_transport_publish.py` (2),
  `test_filesystem_browse.py::test_overlength_path_returns_400_not_500`,
  `test_install.py::test_claude_and_codex_share_identical_mcp_env`.
- 3 **pass**: all three `tests/qa/test_gate_record_hooks.py` write-guard tests —
  because I used an absolute `PYTHONPATH`. This reproduces checklist §2.2's
  measurement exactly and confirms those three are the stale-editable-install
  artefact, not test defects.

Pre-existence is not merely asserted: none of those five test files, and none of
the modules they exercise, appears in `git diff --stat origin/main...HEAD`. The
only modified backend files are `availability.py`, `work_import/**`,
`api/routes/work_import.py`, `api/routes/ai.py`, `api/app.py` (one router
include) and `api/routes/ai_pty/**`. Identical test + identical subject ⇒
identical result. `#2030` records the same failures on `main`.

`#2020`, `#2022`, `TODO(#2012)` and `#2032` are out of scope and I did not
re-litigate them; `#2020`/`#2022` are cited in P2-4 only as risk to SC-001, not
as findings.

## 5. FR → implementation → test coverage map

**Every FR traces to implementation. 39 of 44 trace to a test.** No untracked
gap. Abbreviations: `av.py` = `src/scistudio/ai/agent/availability.py`;
`wi/` = `src/scistudio/ai/work_import/`; `wi.py` =
`src/scistudio/api/routes/work_import.py`; `parts/` =
`frontend/src/components/BringInMyWorkDialog.parts/`; `t_avail` =
`tests/api/test_agent_availability.py`; `t_brief` =
`tests/ai/test_work_import_brief.py`; `t_sess` =
`tests/api/test_work_import_session.py`; `t_dlg` =
`frontend/src/components/__tests__/BringInMyWorkDialog.test.tsx`; `t_bar` =
`…/BringInMyWorkToolbarEntry.test.tsx`; `t_wi` = `…/workImport.test.ts`;
`t_tabs` = `frontend/src/store/__tests__/terminalTabsSlice.workImport.test.ts`.

| FR | Implementation | Test |
|---|---|---|
| FR-001 | `Toolbar.tsx:191-220` — permanent, no gate | `t_bar` "labelled … and enabled with a project open" |
| FR-002 | `Toolbar.tsx:205` `disabled={!currentProject}`; `BringInMyWorkDialog.tsx:169` | `t_bar` "disabled with no project open" |
| FR-003 | `BringInMyWorkDialog.tsx:238-313` | `t_bar` "opens the dialog when activated" + all `t_dlg` |
| FR-004 | `BringInMyWorkDialog.tsx:320-321` caveat above start | `t_dlg` "cannot be bypassed before the start action" |
| FR-005 | `parts/availability.ts:42-44`; `BringInMyWorkDialog.tsx:266-277,342` | `t_dlg` ×3 (no-start, partial, per-state) |
| FR-006 | `parts/copy.ts` question set | `t_dlg` "asks nothing that needs SciStudio or software-development knowledge" |
| FR-007 | same | same |
| FR-008 | `parts/SourceAndDestination.tsx:43-68`; `BringInMyWorkDialog.tsx:155` `openNativeDialog("directory", …)` | `t_dlg` "asks for a directory, not a file" |
| FR-009 | `parts/SourceAndDestination.tsx:75-87` | `t_dlg`, `t_wi` |
| FR-010 | `parts/formState.ts:78-80`; source + browse disabled, rest live | `t_dlg` "…leaves the rest in effect", `t_wi` |
| FR-011 | `parts/copy.ts:98-110`; `SourceAndDestination.tsx:90-112` | `t_dlg:164`, `t_brief` `test_each_destination_tier_renders_its_own_answer` |
| FR-012 | **no write path exists** — verified by grep; brief carries the tier | `t_brief` `test_both_tiers_carry_the_full_destination_guidance` (negative req.) |
| FR-013 | `parts/DataKindsQuestion.tsx`; presets + free text | `t_dlg` ×2 |
| FR-014 | `parts/copy.ts:141-152` two groups | `t_dlg` "groups the presets so both readings … can be selected" |
| FR-015 | **nothing branches on a preset** — only `data_kinds` join + emptiness check | verified by grep (§6); `t_brief` |
| FR-016 | `parts/formState.ts:70-72` | `t_dlg`, `t_wi` "question 2 blocks in no-codebase mode only" |
| FR-017 | `parts/copy.ts:175-184` longer no-codebase wording; `FreeTextQuestion.tsx:70` no skip when required | `t_dlg`, `t_wi` |
| FR-018 | `parts/copy.ts:194-201` incl. both spec examples | `t_dlg` "question 3 carries concrete examples" |
| FR-019 | `parts/copy.ts:207-211` | `t_dlg` "questions 3 and 4 are skippable" |
| FR-020 | `FreeTextQuestion.tsx:70-84`; `formState.ts:89-115` | `t_dlg` "a skip reads as a choice", `t_wi` ×3 |
| FR-021 | `wi/brief.py:143-178` (fallback read **from the template**); `formState.ts:139-155` | `t_brief` ×5, `t_wi` ×4, `t_dlg` |
| FR-022 | `ai_pty/engine.py:_open_prespawned_tab` shared with AI Block; `open_work_import_tab` | `t_sess` `test_the_returned_tab_is_a_live_registered_pty` |
| FR-023 | `wi/brief.py:89-121`; `formState.ts:157-172` | `t_brief` `test_every_collected_answer_reaches_the_brief`, `t_wi` |
| FR-024 | `wi.py:224-241` — compose, `_write_brief` (flush + `os.fsync` + close), **then** spawn | `t_sess` `test_brief_is_complete_on_disk_before_the_agent_is_spawned` (reads the file *inside* the spawn) + `…when_the_brief_cannot_be_written` |
| FR-025 | `terminalTabsSlice.ts:214-220` `source:"user"`, no block maps | `t_tabs` "not an AI-block tab", `t_sess` `test_work_import_tab_carries_no_ai_block_semantics` |
| FR-026 | `wi/brief_template.md` byte-identical to §4.6 | `t_brief` `test_brief_template_is_verbatim_spec_section_4_6` (re-extracts §4.6 at test time) |
| FR-027 | `wi.py:63` `(".scistudio","work-import")` | `t_sess` `test_brief_lands_under_dot_scistudio` + `…default_project_ignore_file_excludes_the_brief` |
| FR-028 | `wi.py:78-85` one sentence | `t_sess` `test_opening_message_is_a_single_line_naming_the_brief` |
| FR-029 | prompt delivered as positional argv, not a system prompt | `t_sess` `test_delivery_is_identical_across_system_prompt_strategies` + `…both_system_prompt_strategies` |
| FR-030 | `wi.py:66-75` timestamp+uuid8, opened `"x"` | `t_sess` `test_two_sessions_in_one_project_get_distinct_brief_files`, `…a_brief_outlives_its_session` |
| FR-031 | `av.py:109-124` four-state enum | `t_avail` ×5 (one per state + all-in-one-report) |
| FR-032 | `av.py:477-489` `_presence_state` off the status row; `ai.py:_status_rows` shared | `t_avail` `test_availability_runs_on_the_status_endpoints_own_discovery` |
| FR-033 | `av.py:442-469` `_live_call_cause`; READY only when the call returns 0 **and** prints | `t_avail` `test_ready_requires_the_live_call_to_succeed`, `…whose_live_call_fails` |
| FR-034 | `av.py:367-405` `_REINSTALL_GUIDANCE` strip + honest fallbacks; `copy.ts:249-253` never says "install" | `t_avail` ×2, `t_dlg` "never suggests reinstalling" |
| FR-035 | `av.py:191-199` two independent bounds; `useAgentAvailability.ts:44-91` 10 s client cap | `t_avail` `test_a_hanging_provider_degrades_to_a_reported_state` (wall-clock), `t_dlg` ×2 |
| FR-036 | `av.py` is a leaf under `ai.agent`; `GET /api/ai/availability`; types in `lib/api/agentAvailability.ts` | import-linter "AI must not depend on api" kept; `t_avail` memoisation-across-callers |
| FR-037 | `copy.ts:72-76` — all four claims, in order | `t_dlg` "is present, in full, with the session start action" |
| FR-038 | `CorrectnessCaveat.tsx` — no dismiss, no collapse; rendered in the **non-scrolling footer** above the button | `t_dlg` "not dismissible and cannot be bypassed", "not weakened or omitted in no-codebase mode" |
| FR-039 | **negative requirement** — nothing added enforces a test | **no test** (see below) |
| FR-040 | `AgentSetup.tsx:64-70` `ProviderPicker` | `t_dlg` "lets the user choose between two usable providers" |
| FR-041 | `AgentSetup.tsx:93-97` `PermissionModePicker`; `formState.ts:56` default `"safe"` | `t_dlg` "defaults to the safe permission mode" |
| FR-042 | both components **imported unchanged**; neither file appears in the diff | verified by `git diff --stat` (structural, stronger than a test) |
| FR-043 | `parts/availability.ts:100-108` `resolveSelectedProvider` | `t_dlg` "preselects the single usable provider and keeps the control visible" |
| FR-044 | `formState.ts:170-171`; `wi.py:236-241`; response round-trip | `t_dlg` "the chosen provider and permission mode reach the request", `t_wi` ×3, `t_sess` ×2 |

**FRs with no dedicated test, and why each is acceptable:**

- **FR-039** — a pure "MUST NOT". Nothing in the 44-file diff enforces a test or
  gates block acceptance; I grepped for it and there is no such code to test.
  §4.4's verification row asks for a check that has no subject. Acceptable as a
  vacuous truth; noting it so it is not mistaken for coverage.
- **FR-012** — as corrected, this requires the *absence* of a write path. I
  confirmed by grep that every `~/.scistudio/{types,blocks}` reference in the
  tree is pre-existing scan-dir registration in modules untouched by this diff
  (`ai/agent/mcp/runtime.py`, `api/runtime/_projects.py`,
  `core/types/{registry,serialization}.py`, `blocks/io/_unified_dispatch.py`).
  No endpoint, no writer, nothing new. §4.6 sends the agent there itself.
- **FR-042** — structurally guaranteed rather than tested: `ProviderPicker.tsx`
  and `PermissionModePicker.tsx` do not appear in the diff at all.
- **FR-015** — enforced by absence; see §6.
- **FR-003** — covered transitively by every dialog test.

## 6. Verification of the specific claims I was asked to check

**Claim 3 — four states, live call, no cross-state guidance.** Holds, with P2-1
on the *quality* of two states' guidance. `_presence_state` (`av.py:477-489`)
decides only `not_installed` / `not_authenticated` and returns `None` for an
installed+authenticated provider; `READY` is reachable **only** through
`_live_call_cause` returning `None`, which requires exit 0 *and* non-empty
stdout (`av.py:434-439`). A presence check cannot produce `ready`. Guidance is
rendered one block per state from that state's own copy
(`AvailabilityGuidance.tsx:47-72`); the `call_failed` copy contains the string
"install" nowhere, and `_REINSTALL_GUIDANCE` (`av.py:367-370`) additionally
strips reinstall lines out of the provider's own error text, falling back to an
honest `_CAUSE_NO_MESSAGE` rather than an empty string. **FR-034 holds.**

**Claim 4 — brief byte-identity.** **Verified myself, not trusted.** §4.6's
fenced body is spec lines 672–1047; `diff` and `cmp` against
`brief_template.md` both report identical, and the file is UTF-8 with LF. The
seven substitution points are matched *positionally* (`brief.py:52-65`) because
two of them carry identical text, and `compose_brief` raises
`BriefTemplateError` rather than emitting a half-composed brief if the count
drifts. The skip wording is extracted from the template's own
`{<answer>, or "<…>"}` alternative (`brief.py:166-178`) instead of restated in
Python — which is the right call, and means FR-021's wording cannot drift from
§4.6. The four `{project}` literals in "What to deliver" sit outside the answers
section and are correctly left alone.

**Claim 5 — write-before-spawn.** **The test genuinely proves ordering.** The
spawn recorder (`t_sess:100-131`) parses the brief path out of the opening
message and reads the file *from inside* the `_spawn` call, recording both
`brief_exists_at_spawn` and `brief_text_at_spawn`; the assertion compares that
captured text against an independently composed brief. A spawn that raced the
write sees no file; one that raced the close sees a prefix. Both fail. This is
the right shape — not an after-the-fact existence assertion. `_write_brief`
flushes and `os.fsync`s before the handle closes (`wi.py:168-172`) and opens
with mode `"x"`, so a filename collision fails loudly rather than overwriting a
concurrent session's instructions.

**Claim 6 — the caveat.** Holds in both modes. `CorrectnessCaveat.tsx` has no
dismiss control, no disclosure element, no `aria-hidden`. It renders in the
dialog's **fixed footer** (`BringInMyWorkDialog.tsx:320`), outside the
`overflow-y-auto` question region, immediately above the start button — so it is
on screen whenever the button is, at any scroll position. Nothing conditions it
on `hasNoCodebase`. All four FR-037 claims are present in
`CAVEAT_BODY` in the required order.

**Claim 7 — questions readable by a first-day scientist.** Holds. I read all four
as the target user. Q2/Q3/Q4 are entirely about the user's own world and carry
concrete, domain-flavoured examples ("the plate reader export", "Fiji for the
segmentation, Prism for the final figures"). Q1's *arrangement* group ("Array /
Table / dataframe / Series") is the closest thing to jargon, but FR-014
*mandates* those exact generic shapes, the group legends ("How the data is
arranged" / "What the data is") disambiguate them, and `Q1_HELP` says explicitly
that picking from both lists is normal. No question asks about interpreters,
environments, dependencies, port shapes, data types, or block kinds. The reused
`PermissionModePicker` is also clean — ADR-034 FR-021e already stripped CLI flag
names from it.

**Claim 8 — presets route nothing.** **Verified by grep, not by comment.** The
only reads of `data_kinds` anywhere are: the `", ".join` in
`brief.py:153-155`, tuple normalisation in `context.py:89`, request plumbing in
`wi.py:212-213` and `formState.ts:162`, and the *emptiness* check in
`formState.ts:100` that makes question 1 required. No lookup table, no `match`,
no per-value branch, no package or type resolution. FR-015 holds.

**Claim 9 — component reuse and the `dangerous` → `bypass` mapping.** Both hold.
`AgentSetup.tsx:12-13` imports `PermissionModePicker` and `ProviderPicker` from
`AIChat/SetupScreen.parts/` and supplies props only; neither component file
appears in the diff. The mapping is `toBackendPermissionMode` /
`fromBackendPermissionMode` (`workImport.ts:82-94`) applied at exactly one place
each — request build and response attach — and pinned on both sides:
`t_wi` "maps the frontend spelling to the backend spelling" / "maps the backend
spelling back", and `t_sess` `test_backend_permission_spelling_is_accepted_and_applied`
plus `test_frontend_permission_spelling_is_rejected` (the backend refuses
`"dangerous"`, which is what makes the boundary real rather than tolerated).

**Claim 10 — the frozen ADR-034 user-launched route.** **Unchanged.** The whole
`websocket.py` delta is the join predicate plus comments:

```python
if candidate is not None and (
    getattr(candidate, "_engine_prespawned", False) or getattr(candidate, "_engine_block_run_id", None)
):
```

Everything else in `pty_endpoint` is untouched: query-parameter parsing and the
four validation branches (`websocket.py:39-67`), the cap check and its error
frame (`:106-117`), the spawn call and its `FileNotFoundError` / generic
handlers (`:119-137`), registration, both pump tasks, and teardown. Verified two
further ways. First, `_open_prespawned_tab` stamps `_engine_prespawned` **before**
inserting into `_active_ptys` (`engine.py`), closing the window in which a WS
arriving between insert and stamp would spawn a second agent over the top.
Second, the pre-existing regression tests still pass: `test_public_surface.py`'s
`test_open_engine_initiated_tab_signature_unchanged` (the IPC parameter list is
byte-for-byte the same list) and the four `test_engine.py` rejection tests, whose
`pytest.raises(match=…)` patterns ("unknown provider", "permission_mode must
be", "cwd must be an existing", "PTY cap") all survive the message-prefix rename
from `open_engine_initiated_tab:` to `pre-spawned PTY tab:`. `pytest tests/api -k
"pty or ai_pty"` → **108 passed**. A work-import tab acquires no AI Block
semantics: `block_run_id=None` means `_engine_block_run_id` is never stamped and
`_engine_tab_to_run` / `_engine_run_to_run_dir` are never populated
(`t_sess` `test_work_import_tab_carries_no_ai_block_semantics`), and an unmarked
registered PTY is still never joined (`test_an_unmarked_registered_pty_is_never_joined`).

One pre-existing property worth stating so it is not mistaken for new: the join
branch ignores the `provider` and `dangerous` query parameters, since the PTY
already exists. That is ADR-035 behaviour for AI Block tabs and is unchanged;
`tab_id` is a 12-hex uuid returned only to the initiating client.

**Claim 11 — no personal-library write path.** **Confirmed.** No endpoint, no
writer, no filesystem call targeting `~/.scistudio/{types,blocks}` anywhere in
the diff. The destination tier travels as data only: dialog → request →
`ImportSessionContext.destination_tier` → one substituted phrase in the brief
(`brief.py:150-151`). §4.6 is what sends the agent to those directories, using
its own shell. FR-012 as corrected is honoured exactly.

**Claim 12 — scope compliance.**
- Spec §4.6 is **byte-identical** to `origin/main`: `sha256
  fcbfc3d77f211054aa0a3009189cc24969b779bec2a4e718a9e21de1bf5766a0` on both
  sides, and `diff` reports no lines.
- `pyproject.toml` **does not appear** in `git diff --stat origin/main...HEAD`.
  The #2032 withdrawal is clean.
- A1 (`73bdbdf1`), A2 (`ba1a49ba`) and A3 (`7b0233e3`, `5729c859`) each wrote
  exactly their §6 write set and nothing else.
- **A4 (`ce431fd0`) wrote `docs/specs/adr-053-work-import.md`, which §6 lists as
  out of scope for it.** Frontmatter only, identical to the change the manager
  independently made in `4c411589`, declared in §11.3 with manager review
  requested and recorded as a ledger amendment. Substantively fine; the drift
  log's account of it is not — see **P3-3**.

**Claim 13 — the three classes of spec correction.** All landed and all correct.
- **FR-012 rewrite** (spec:287-292): now states the in-session agent writes
  `~/.scistudio/types/` and `~/.scistudio/blocks/` itself with no endpoint
  involved. Matches §4.6's "Where things go" block (spec:800-811 /
  `brief_template.md:129-140`) and matches the code (nothing writes there).
- **`#2003` / implementation-issue staleness**: §4.1:508-516, §4.3 T-002 and
  §4.5:649-661 now record the merge and the issue rewrites. I confirmed against
  the live issues — `#2000`, `#2001` and `#2002` all carry a 2026-08-07 rewrite
  banner.
- **FR cross-references**: I spot-checked **12**, not the six asked for, and all
  12 name the requirement they describe:

| Site | Was | Now | Correct? |
|---|---|---|---|
| §2 edge case, project-local type in library mode | FR-013 | FR-026 | ✓ — FR-026 governs the brief's content; FR-013 is question 1 |
| §2 edge case, hanging probe | FR-031 | FR-035 | ✓ — verbatim FR-035 |
| Key Entities, `AgentAvailability` derivation | FR-028, FR-029 | FR-032, FR-033 | ✓ — registry + live call |
| Key Entities, shared consumption | FR-032 | FR-036 | ✓ |
| §4.1, "two of the four states" | FR-027 | FR-031 | ✓ — FR-031 is the four-state table |
| §4.1, "reporting obligations" | FR-039 | **SC-007** | ✓ — SC-007 is the no-restatement criterion; FR-039 is test non-enforcement |
| §4.2, availability probe module | FR-027–FR-032 | FR-031–FR-036 | ✓ |
| §4.4, preset grouping | FR-015 | FR-014 | ✓ — FR-014 defines the grouping; FR-015 is the anti-routing rule |
| §4.4, question 2 conditionality | FR-017, FR-018 | FR-016, FR-017 | ✓ |
| §4.4, `call_failed` guidance | FR-030 | FR-034 | ✓ |
| §4.4, caveat presence | FR-033, FR-034 | FR-037, FR-038 | ✓ |
| §4.5, "puts it where the user starts" | FR-034 | FR-038 | ✓ |

I then re-read **every** FR/SC reference remaining in the spec outside §4.6 and
found no surviving mis-citation. The count ("17 references, 23 edits") is
consistent with what I counted. The one staleness the pass did not reach is
P3-5.

## 7. Missing tests, docs and gate evidence

- **Tests**: FR-039 and FR-012 have none, both correctly (negative
  requirements); FR-042 is structurally guaranteed. The two real gaps are the
  unpinned cross-boundary preset/question strings (**P3-2**) and
  `test_the_probe_never_grants_the_cli_tools` asserting a universal it does not
  check (**P2-3**).
- **Docs**: the spec is the docs deliverable and it landed. Outstanding:
  `status: Draft`, the stale "concrete paths … left unresolved" sentence, and an
  incomplete `tests:` frontmatter list (**P3-5**). No user-facing documentation
  exists for the feature; the checklist records `N/A` for AI-docs impact, which
  is right, but nothing states whether `docs/user/**` is expected. Worth an
  owner decision before the final PR rather than a finding.
- **Gate evidence**: present and substantive for all four tracks — declared
  scope, docs and test events, 10–22 check events each, and reconcile events.
  Three bookkeeping defects in **P3-4**. All four reconcile `fail` on
  `checks.python_tests` only, which is `#2030`.
- **Sentrux**: **N/A — unavailable.** No `sentrux` binary on `PATH` and no
  Sentrux MCP server is connected in this session. The gate ledger's own
  `sentrux_gate` guard ran as part of `check` and emits
  `sentrux.free_tier.advisory-missing-evidence`, which is the same signal the
  implementer ledgers carry.

## 8. Checklist drift

- **P3-3** above: §13 row 5 contradicts §11.3's last row about A4's spec write.
- §12 Verification Evidence: all eight rows `[ ]` with no evidence, although the
  targeted, frontend and full-audit checks have all been run repeatedly by the
  tracks and again by me. §14 Final Readiness likewise all `[ ]`. Both are
  manager rows and the dispatch is not finished, so this is expected state
  rather than drift — noted so the manager closes them rather than inheriting
  them.
- §8.2, §9.2 and §10.2 Dispatch rows are all `[ ]` while the matching §8.3, §9.3
  and §10.3 Implementation rows are all `[x]` with artifacts — which cannot both
  be true, since the agents were demonstrably dispatched from
  `docs/planning/adr-053-work-import-dispatch-prompts.md`. Only §11.2 (Track D)
  is filled in. Cosmetic, but §3 requires every completed row to carry an
  artifact and these are completed work recorded as not started.

## 9. Recommendation

**pass-with-fixes.**

Nothing here blocks merge on correctness. Before the final PR I would want:

1. **P2-3** closed — a tracked `TODO(#NNNN)` on the `kimi-code` minimal call and
   an honest docstring on `test_the_probe_never_grants_the_cli_tools`. This is
   the only finding where the shipped code and a stated invariant disagree, and
   AGENTS.md §3.6 requires the deferral to be visible.
2. **P2-2** closed as a spec correction (reword SC-006's second clause to match
   FR-021). No code change.
3. **P2-1** and **P2-4** either fixed or recorded as owner-accepted with a
   follow-up issue. P2-1 is a real product gap in the one path US3 exists to
   serve; P2-4 is an e2e action, not a code change.
4. **P3-3** and **P3-4** corrected as bookkeeping at final finalization.

P3-1, P3-2 and P3-5 are fine as tracked follow-ups.
