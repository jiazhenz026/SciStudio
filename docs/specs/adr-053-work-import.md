---
spec_id: adr-053-work-import
title: "ADR-053 Bring In My Work — A Guided Agent Session For Carrying Existing Work Across"
status: Draft
feature_branch: guided/codebase-import-spec
created: 2026-08-06
input: "Owner-directed live session (guided): revise ADR-053 sections 4.1 and 5, then author the codebase import spec. Import is a permanently available toolbar entry, enabled with a project open, that collects a fixed set of answers and spawns a preconfigured agent chat session. The agent drives the rest, including asking the user for data and writing a test that checks the transcription preserves the original logic. The product does not enforce that test; it states plainly that correctness is not guaranteed and the user must review."
owners:
  - "@jiazhenz026"
related_adrs:
  - 34
  - 53
related_specs:
  - adr-034-multi-provider-agent-chat
  - adr-053-personal-tool-library
scope:
  in:
    - Revising ADR-053 section 4.1 from no-agent static scanning to a guided agent session, and section 5 from system-enforced differential tests to an agent workflow with an explicit no-guarantee statement.
    - A toolbar entry labelled "Bring in my work", enabled when a project is open and disabled otherwise.
    - Support for users with no codebase at all - spreadsheet and GUI-software workflows - as a first-class path rather than a degraded one.
    - A dialog collecting a fixed set of framing answers before the session starts.
    - Spawning a chat session preloaded with a system prompt composed from the source path and those answers, reusing the agent block's session mechanism.
    - The system prompt's instruction set - what the agent is told to do, ask, write, and report.
    - The caveat copy shown in the import surface stating that the agent can make mistakes, that a test is requested, that equivalence is not guaranteed, and that the user must review the result.
    - Graded agent availability - four states derived from the provider registry plus a live minimal call, with per-state guidance.
    - The entry point contract the Learning Center milestone unlock routes to.
  out:
    - Static codebase scanning, candidate lists, and batch selection UI. ADR-053 section 4.1 as revised no longer calls for them.
    - Importing from a running instance of an external application, or reading its saved settings. The no-codebase path works from the user description alone.
    - System enforcement of differential tests, including any check that gates block acceptance on a test file existing.
    - Provider configuration, selection, and the provider registry itself, governed by ADR-034 and implemented by #1994.
    - Learning Center progress, thresholds, and when the unlock fires, which belong to the Learning Center system spec.
    - Promotion of imported blocks into the user library, governed by the ADR-053 personal tool library spec.
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/adr-053-work-import.md
    - docs/adr/ADR-053.md
  excludes:
    - docs/user/reference/**
    - docs/user/llms.txt
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - frontend/src/components/ImportCodebaseDialog.tsx
  excludes: []
tests:
  - tests/api/test_agent_availability.py
  - frontend/src/components/__tests__/ImportCodebaseDialog.test.tsx
acceptance_source: adr
language_source: en
---

# ADR-053 Bring In My Work — A Guided Agent Session For Carrying Existing Work Across

## 1. Change Summary

A scientist who already has a working way of doing their analysis is the user
with the most to gain from SciStudio and the highest cost of entry. ADR-053 §4
makes carrying that work across a first-class path rather than asking them to
build it again from nothing.

"Their work" is not always code. Some users have a Python repository built over
years; others do everything in spreadsheets, or in a GUI application, and have
never written a script. Both have a real analysis workflow and both face the same
entry cost, so this spec treats the second as a first-class path rather than a
degraded one — the difference is what the agent reads from, not whether the
feature applies.

This spec is the implementation contract for that path, and it revises the two
decisions in ADR-053 that described a different one. §4.1 originally recorded
that finding block-shaped units is static analysis that runs with no agent
configured, and that this separation "is the decision, not an implementation
detail". §5 originally recorded that every transcribed block ships with a
differential test that is an acceptance criterion and runnable without the agent.
Both were written during the ADR authoring session and are not the intended
design. Issue #2010 records the revision; the ADR changes land in this PR.

What replaces them is smaller. The feature is **a permanently available toolbar
entry, "Bring in my work", that spawns a preconfigured agent session**. The
product supplies the entry point, a short dialog of framing questions, and the
system prompt. The agent supplies the work: it reads whatever the user has —
a codebase, or their description of how they work today — proposes what could
become blocks, asks the user whatever it needs, writes the blocks, asks for data,
checks that the result matches what the user expects, saves that check in the
project, and reports.

The product does not verify the result and does not pretend to. It says so, in
the import surface, before the user starts. That sentence is treated here as a
feature requirement rather than a disclaimer, because it is what determines
whether a user reviews an imported block or assumes it was checked.

## 2. Current State

### 2.1 None Of This Exists

There is no scanning, candidate, transcription, or import code anywhere under
`src/scistudio/`. `src/scistudio/ai/` contains only `agent/` — `mcp/`,
`system_prompt.py`, and `terminal.py`. Unlike the personal tool library spec,
which mostly re-shapes existing behavior, almost everything here is new
construction. The exception is §2.2.

### 2.2 Provider Discovery Already Exists And Is Not Merged Yet

PR #2003 (issue #1994, ADR-034) introduces a provider registry and a discovery
endpoint. `GET /api/ai/status` returns one row per agent provider:

```json
{"name": "claude-code", "available": true, "version": "2.1.141",
 "logged_in": true, "label": "Claude Code"}
```

`available` means the binary was found and `--version` returned within a probe
timeout. `logged_in` comes from a `CredentialProbe` on the provider descriptor —
a credential file path and, where the CLI offers one, an auth-status command.
Probes run concurrently on worker threads, are bounded by a timeout, and never
block or 500 the endpoint.

This covers two of the four states ADR-053 §5.2 requires and is a dependency of
this spec that is **not yet merged**. §5 below builds on it rather than
reinventing it.

### 2.3 Agent Sessions Are PTY-Hosted CLIs

The agent is a CLI running on the user's machine under a PTY
(`src/scistudio/ai/agent/terminal.py`), not an API client. It therefore has the
user's shell, the user's filesystem, and the user's Python environments. This is
what makes the design in §4 viable: the agent can run the user's original script
using the environment that script was written for, which a SciStudio-hosted
runner could not do without reproducing that environment.

## 3. Entry Point And Framing Dialog

**FR-001.** Import MUST be reachable from a permanently available entry in the
toolbar. It MUST NOT be gated on Learning Center progress, project count, or
elapsed time. ADR-053 §4.2 keeps progress as the trigger for when the product
*volunteers* the capability, never for whether it can be reached.

**FR-002.** The entry MUST be enabled when a project is open and disabled
otherwise, since an import session writes blocks into a project.

**FR-003.** Activating the entry MUST open a dialog that collects the source
location, the destination tier, and four framing answers before any session is
spawned.

**FR-004.** The dialog MUST display the caveat copy required by §6 before the
user can start the session.

**FR-005.** The dialog MUST report agent availability (§5) and, when an agent is
not usable, MUST show that state's guidance instead of a start action.

### 3.1 Who The Questions Are Written For

The dialog's users are scientists, not developers, and it is their first day.
Two exclusions follow, and every question below satisfies both.

**FR-006.** The dialog MUST NOT ask questions requiring SciStudio knowledge —
which data types the blocks should use, whether something should be an
interactive block, how ports should be shaped. A first-day user cannot answer
these, and they are exactly what the agent should propose and the user confirm
after the code has been read.

**FR-007.** The dialog MUST NOT ask questions requiring software-development
knowledge — which environment the code runs in, how dependencies are installed,
which interpreter is used. The target users run their analyses without
necessarily knowing any of this, and asking tells them the product is not for
them. The agent establishes these facts itself (§7).

The rule these two share: the dialog asks only about the user's own world.

### 3.2 Page One — Source And Destination

**FR-008.** The first page MUST collect the source location as a text field with
a browse control. The picker MUST accept a **directory**, not only a file.

**FR-036.** The first page MUST offer an explicit **"I don't have a codebase"**
option. Users who work entirely in spreadsheets or in a GUI application have a
real analysis workflow and no source path, and without this option the dialog
cannot be completed at all — the feature would silently exclude the users least
likely to have built anything reusable.

**FR-037.** Selecting that option MUST disable or hide the source location
field, since there is nothing to point at. Every other field, including the
destination tier, MUST remain in effect.

**FR-009.** The first page MUST collect the destination tier as a single choice:
blocks land in **this project only**, or in the **personal library** available
across projects.

**FR-010.** When the personal library is chosen, blocks are written to the
user-wide library, which requires the write path defined by the ADR-053 personal
tool library spec (its FR-006). This spec does not define a second write path.

**FR-011.** When the personal library is chosen, the system prompt MUST tell the
agent that a block written there must not depend on project-local custom types,
because such a block loads in the originating project and fails everywhere else.
The personal tool library spec covers this for interactive promotion (its
FR-021 – FR-024); import must not produce the same broken result by another
route.

### 3.3 The Four Questions

Each question serves two purposes at once, and the second is easy to lose.

They collect context the agent would otherwise have to guess. They also **name
capabilities the user has never heard of**: ADR-053 §1 records that observed
users had never heard of interactive blocks, custom previewers, or custom data
types. Question 2 introduces interaction and visualisation, and question 3
introduces external-application integration, both framed entirely in the user's
own terms. The dialog is therefore also a discovery surface, in the same sense
ADR-053 §9.2 calls the palette tips strip the cheapest discovery surface in the
product. **A future editor optimising these questions purely as data collection
would remove that second effect without noticing it.**

**FR-012.** Question 1 — *what kind of data do you usually work with?* — MUST be
presented as multi-select preset options plus a free-text field for anything not
listed. It is the context for every other answer: the same code reads differently
depending on whether its author works with images or with transcriptomics.

**FR-013.** Presets MUST cover both the generic shapes (array, table/dataframe,
series) and the user's domain (for example image, time series, spectrum,
multi-omics, spatial omics). Because these are two different levels of
abstraction — a scientist says "time series", not "Series" — they MUST be
visually grouped so it is clear both may be selected, rather than presented as
one flat list where the two readings of the same data compete.

**FR-014.** Preset options MUST NOT be treated as a routing mechanism. The agent
builds what it needs from core types; domain answers supply context only. When
packages become publicly available the agent should instead suggest a matching
package rather than authoring duplicate types, which requires a package
discovery mechanism that does not exist yet.

```text
TODO(#2012): suggest a matching package instead of authoring duplicate types.
  Out of scope per owner decision — packages are not publicly promoted yet, and
  suggesting one the user cannot obtain is worse than suggesting none.
  Followup: https://github.com/jiazhenz026/SciStudio/issues/2012
```

**FR-015.** Question 2 — *briefly describe your analysis workflow: what goes in,
what comes out?* — MUST be free text. It is skippable **only when a source
location was given**: with a codebase the agent can read the code and treat this
answer as supplementary, but with no codebase it is the only description of the
work that exists, and skipping it would leave the agent nothing to act on.

**FR-038.** In no-codebase mode the question MUST be required, and its prompt
text MUST ask for more detail than the codebase-mode wording — the steps taken,
what is done at each one, and what the user looks at to decide the result is
right. This is the entire input to the session, so the cost of a thin answer is
paid immediately.

**FR-016.** Question 3 — *which steps would you like to be able to interact with
or see the data for?* — MUST be free text, MUST be skippable, and MUST carry
concrete examples (such as subtracting background, or editing a segmentation
mask). Without examples the question is too abstract to answer; with them it
also teaches that interactive blocks and custom previewers exist.

**FR-017.** Question 4 — *which other data analysis software do you use
regularly?* — MUST be free text and MUST be skippable. It informs app-block
integration and tells the user that integrating external applications is
possible at all.

**FR-018.** Questions 2, 3, and 4 MUST each offer an explicit skip that reads as
a legitimate choice — the user is telling the agent to work it out — rather than
as an abandoned field. Question 1 and the page-one fields are required: without
a source there is nothing to read, without a destination there is nowhere to
write, and question 1 is the cheapest and most answerable of the four.

**FR-019.** Every collected answer MUST reach the system prompt, and skipped
questions MUST be conveyed as skipped rather than omitted, so the agent can tell
"the user did not say" from "the user said nothing applies". The prompt's
behaviour when questions are skipped is specified in §7.

## 4. The Session

**FR-020.** Starting the session MUST spawn a chat session using the same
mechanism the agent block uses. Import does not introduce a second way to run an
agent.

**FR-021.** The source path and every dialog answer MUST be composed into the
spawned session's system prompt. No answer collected may be silently dropped —
if a question is worth asking, its answer reaches the agent.

**FR-022.** The system prompt MUST instruct the agent to ask the user when it
needs information rather than assuming. The design premise of ADR-053 §4.1 is
that the hard questions in import are ones only the user can answer, so an agent
that guesses instead of asking defeats the flow.

**FR-023.** The session MUST be an ordinary chat session once started — the user
can talk to it, redirect it, and end it like any other. Import is a preconfigured
starting point, not a modal wizard.

## 5. Agent Availability

**FR-024.** Availability MUST resolve to one of four states, each with its own
guidance:

| State | Meaning | Guidance |
|---|---|---|
| `not_installed` | No agent CLI found | Installation instructions |
| `not_authenticated` | Installed, no valid credentials | Login instructions for the detected provider |
| `call_failed` | Authenticated, live call failed | The concrete cause — quota, network, provider outage |
| `ready` | Live call succeeded | Which providers are configured |

**FR-025.** The probe MUST build on the provider registry and
`GET /api/ai/status` from #1994 (§2.2) rather than introducing a second
discovery path. `available: false` maps to `not_installed`;
`available: true, logged_in: false` maps to `not_authenticated`.

**FR-026.** Distinguishing `call_failed` from `ready` MUST require a **live
minimal call**. `--version` succeeding and a credential file existing do not
establish that a call will succeed. This is the increment this spec adds over
#1994, and it is the one that catches the authenticated-but-out-of-quota user.

**FR-027.** `call_failed` MUST report the underlying cause and MUST NOT suggest
reinstalling. Telling a correctly configured user to reinstall software they are
already running sends them to fix something that is not broken.

**FR-028.** The probe MUST NOT block the import dialog from rendering. A slow or
hanging provider MUST degrade to a reported state, never to a stuck surface.

**FR-029.** Availability MUST be consumable by any agent-dependent surface, not
only import. ADR-053 §5.2 names the Learning Center agent-setup entry as another
consumer.

## 6. What The Product Says About Correctness

**FR-030.** The import surface MUST state, before the session starts, that the
agent can make mistakes, that it has been instructed to write tests checking the
transcription preserves the original logic, that this does not guarantee the
logic is identical, and that the user should review the result themselves.

**FR-031.** This statement MUST NOT be collapsed into a dismissible notice or
placed where a user can start a session without having seen it. It is the
product's only mechanism for producing an appropriately sceptical reader, and
ADR-053 §5 treats it as load-bearing rather than as a disclaimer.

**FR-032.** The product MUST NOT enforce the existence of a test, and MUST NOT
gate block acceptance on one. Enforcement would be theatre: a test file's
existence says nothing about whether it tests anything, and a user who wants the
block without a test would produce an empty one.

## 7. The Agent's Instructions

The system prompt is the mechanism that makes the flow work, since almost
nothing in §4 is enforced by the product. Its full content is not yet decided
(§8). What is decided is the checklist it must carry:

**FR-033.** The prompt MUST instruct the agent to:

1. Read the codebase at the given path and propose what could become blocks.
2. Ask the user which of those matter rather than converting everything.
3. Write blocks into the project.
4. Tell the user it needs to check that the transcription preserves the original
   logic, and ask for input data and for what the correct answer looks like.
5. Write a test comparing the original code against the new block.
6. Save that test in the project directory.
7. Run it and report what happened, including failures.
8. State its uncertainties explicitly — an inferred port type, a configuration
   field it could not determine, a dependency it could not resolve.

**FR-034.** The prompt MUST make step 8 an expectation rather than an option. An
agent reporting "I inferred this input is an AnnData but I am not certain" is
more useful than one that guesses silently, because the first can be checked in
seconds and the second cannot be checked at all.

**FR-035.** Tests MUST be saved inside the project directory. The value of the
test is that it can be rerun by hand later, which requires the user to be able to
find it.

### 7.1 Verification Without An Original To Compare Against

**FR-039.** The prompt MUST instruct the agent differently depending on whether
a source location was given. With a codebase there is an original implementation
to run, so step 5 is a genuine comparison: same input through the old code and
the new block. With no codebase there is nothing to run — the only reference is
what the user says the answer should be. The agent MUST ask for input data and
the expected result and assert against that, and MUST NOT describe the outcome as
a comparison against the original.

**FR-040.** The prompt MUST make the agent state which of the two it did. "This
matches your original script on the data you gave me" and "this produces the
result you told me to expect" are different claims with different strength, and a
user who cannot tell them apart cannot calibrate how much to trust the block.

**FR-041.** In no-codebase mode the caveat in §6 is more load-bearing, not less.
There is no original implementation to disagree with, so the only check on the
agent's understanding is the user's own review. The caveat copy MUST NOT be
weakened or hidden in this mode on the grounds that no transcription took
place.

## 8. Open Questions

**OQ-1.** *Resolved.* The dialog's contents are specified in §3.

**OQ-2.** *The system prompt's full text.* §7 records the checklist it must
carry. The wording, the framing of the task, how much SciStudio block-authoring
context to include, and how it relates to the existing
`src/scistudio/ai/agent/system_prompt.py` are all open.

**OQ-3.** *Where tests are saved within the project.* FR-035 requires the project
directory. Whether a conventional subdirectory is specified, and whether the
agent or the product chooses the filename, is open.

**OQ-4.** *Dependency on #2003.* This spec builds on a provider registry that is
not merged. If import is implemented first, FR-025 has nothing to consume.

**OQ-5.** *Issue coverage.* #2000, #2001, and #2002 predate this design and
describe the superseded scan-then-transcribe flow. They likely need rewriting to
match: #2001's static-scan scope no longer exists, and none of the three covers
the no-codebase path.

**OQ-6.** *How far the no-codebase path goes.* This spec supports a user who
describes their workflow in prose. It does not read spreadsheets to infer
structure, nor import an external application's saved settings. Whether either is
worth doing is open, and both would be additive rather than a change to what is
specified here.

## 9. Test Plan

| Area | Test |
|---|---|
| Entry enablement | Toolbar entry enabled with a project open, disabled without one (FR-002) |
| Source picker | The browse control accepts a directory, not only a file (FR-008) |
| No-codebase mode | The option is offered; selecting it disables the source field and leaves the destination tier in effect (FR-036, FR-037) |
| Question 2 conditionality | Skippable with a source location, required without one (FR-015, FR-038) |
| Verification mode | The composed prompt instructs comparison against the original in codebase mode and assertion against user-stated expectations without one (FR-039) |
| Destination tier | Both choices are offered; choosing the personal library routes writes to the user-wide library rather than the project (FR-009, FR-010) |
| Library-mode constraint | In personal-library mode the composed prompt carries the project-local-type warning (FR-011) |
| Preset grouping | Generic shapes and domain options are visually grouped so both can be selected (FR-013) |
| Required vs skippable | Source, destination, and question 1 are required; questions 2-4 each offer an explicit skip (FR-018) |
| Skip is conveyed | A skipped question reaches the prompt marked as skipped rather than being omitted (FR-019) |
| Prompt composition | Every dialog answer and the source path appear in the composed system prompt (FR-021) |
| Caveat presence | The caveat copy is present and the session cannot be started without it having been shown (FR-030, FR-031) |
| Availability states | All four states resolve correctly, including authenticated-but-failing (FR-024, FR-026) |
| Availability guidance | `call_failed` reports its cause and does not suggest reinstalling (FR-027) |
| Probe non-blocking | A hanging provider yields a reported state rather than a stuck dialog (FR-028) |
| No enforcement | Nothing blocks a block on the absence of a test file (FR-032) |

## 10. Implementation Plan

### 10.1 Affected Files

| File | Action | Why |
|---|---|---|
| `docs/adr/ADR-053.md` | modify | Revise §4.1 and §5; synchronise §1.1, §6, §7, §8, §9.5 |
| `frontend/src/components/ImportCodebaseDialog.tsx` | create | The framing dialog, caveat copy, and availability guidance |
| Toolbar component | modify | The import entry (FR-001, FR-002) |
| Agent session spawn path | modify | Accept a composed system prompt (FR-020, FR-021) |
| Availability probe module | create | Four-state resolution over the #1994 registry (§5) |

Concrete paths for the last three depend on #2003's final shape and are left
unresolved rather than guessed.

### 10.2 Sequence

1. ADR-053 revision (this PR).
2. Availability probe over the merged provider registry (§5), which is
   independently useful and unblocks other agent-dependent surfaces.
3. Toolbar entry and dialog shell with the caveat copy (§3, §6).
4. System prompt composition and session spawn (§4).
5. Prompt content iteration (OQ-2), which is expected to continue after the
   feature ships.

### 10.3 Risks

**The prompt is the product.** Nearly everything users experience here is
determined by prompt text rather than code, so quality is not fixed by review of
a diff and will need iteration against real sessions. This is accepted; the
alternative is a large product surface built on guesses about the user's
codebase.

**No agent means no feature.** The revised §4.1 gives up the property that
something useful happened before the user configured an agent. Graded
availability (§5) limits the damage by telling the user exactly what to do, but a
user without an agent now meets a setup step instead of a result.

**The caveat can be ignored.** FR-030 puts it where the user starts, which is the
best available position, and it is still a sentence people skip. The design
accepts this: the honest statement is better than a false guarantee, even when
some users do not read it.

**The no-codebase path has a weaker floor.** With a codebase, a wrong
transcription can in principle be caught by running the original. Without one,
the only reference is what the user remembers or computes by hand, so a
misunderstanding that both the agent and the user share will survive
verification. FR-040 keeps the two cases from being reported as if they were
equally strong, but the underlying asymmetry is real and is accepted: the
alternative is excluding these users, who are precisely the ones with nothing
reusable today.

**The dependency is unmerged.** §5 builds on #2003.

## 11. Assumptions

| Assumption | Source |
|---|---|
| Import is a permanently available toolbar entry, enabled with a project open | owner |
| The flow is a preconfigured agent session, not a scan-then-select pipeline | owner |
| The dialog collects a fixed question set that becomes part of the system prompt | owner |
| Differential testing is prompt-driven and not system-enforced | owner |
| Tests are saved in the project directory | owner |
| The import surface states plainly that correctness is not guaranteed | owner |
| The Learning Center unlock only routes to this entry point | owner |
| Users with no codebase are in scope, and the entry is labelled "Bring in my work" rather than naming code | owner |
| A prose description of a spreadsheet or GUI workflow is enough for the agent to work from | owner |
| ADR-053 §4.1 and §5 as originally written were the authoring agent's decisions, not the intended design | owner |
| The agent has the user's shell and can run the original script in its own environment | existing-system |
