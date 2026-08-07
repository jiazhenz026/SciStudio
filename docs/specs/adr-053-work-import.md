---
spec_id: adr-053-work-import
title: "ADR-053 Bring In My Work — A Guided Agent Session For Carrying Existing Work Across"
status: Draft
feature_branch: guided/codebase-import-spec
created: 2026-08-06
input: "Owner-directed live session (guided): revise ADR-053 sections 4.1 and 5, then author the work-import spec. Import is a permanently available toolbar entry, enabled with a project open, that collects a fixed set of answers and spawns a preconfigured agent chat session. The agent drives the rest, including asking the user for data and checking that the result matches what the user expects. The product does not enforce that check; it states plainly that correctness is not guaranteed and the user must review. Users with no codebase at all — spreadsheet and GUI-software workflows — are a first-class path."
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
    - A dialog collecting the source location, destination tier, and four framing answers before the session starts.
    - Support for users with no codebase at all - spreadsheet and GUI-software workflows - as a first-class path rather than a degraded one.
    - Transcribing from other languages into SciStudio's Python blocks, with the added uncertainty that carries surfaced to the user.
    - Spawning a chat session whose task brief is written to a file under .scistudio/ and referenced by a single visible line, so no provider shows the user a wall of instructions.
    - The task brief's instruction set - its structure, the workflow checklist, the delivery standard, and the working method the agent follows with the user.
    - The caveat copy shown in the import surface stating that the agent can make mistakes, that a check is requested, that equivalence is not guaranteed, and that the user must review the result.
    - Graded agent availability - four states derived from the provider registry plus a live minimal call, with per-state guidance.
    - The entry point contract the Learning Center milestone unlock routes to.
  out:
    - Static codebase scanning, candidate lists, and batch selection UI. ADR-053 section 4.1 as revised no longer calls for them.
    - System enforcement of the agent's verification step, including any check that gates block acceptance on a test file existing.
    - Provider configuration, selection, and the provider registry itself, governed by ADR-034 and implemented by #1994.
    - Reading spreadsheets to infer structure, or importing an external application's saved settings. The no-codebase path works from the user's description alone.
    - Learning Center progress, thresholds, and when the unlock fires, which belong to the Learning Center system spec.
    - Promotion of blocks into the user library after the fact, governed by the ADR-053 personal tool library spec.
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
    - frontend/src/components/BringInMyWorkDialog.tsx
  excludes: []
tests:
  - tests/api/test_agent_availability.py
  - frontend/src/components/__tests__/BringInMyWorkDialog.test.tsx
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

This spec also revises the two decisions in ADR-053 that described a different
design. §4.1 originally recorded that finding block-shaped units is static
analysis that runs with no agent configured, and that this separation "is the
decision, not an implementation detail". §5 originally recorded that every
transcribed block ships with a differential test that is an acceptance criterion
and runnable without the agent. Both were written during the ADR authoring
session and are not the intended design. Issue #2010 records the revision; the
ADR changes land in this PR.

What replaces them is smaller. The feature is **a permanently available toolbar
entry, "Bring in my work", that spawns a preconfigured agent session**. The
product supplies the entry point, a short dialog of framing questions, and the
system prompt. The agent supplies the work: it reads whatever the user has — a
codebase, or their description of how they work today — proposes what could
become blocks, asks the user whatever it needs, writes the blocks, asks for data,
checks that the result matches what the user expects, saves that check in the
project, and reports.

The product does not verify the result and does not pretend to. It says so, in
the import surface, before the user starts. That sentence is treated here as a
feature requirement rather than a disclaimer, because it is what determines
whether a user reviews an imported block or assumes it was checked.

## 2. User Scenarios & Testing

### User Story 1 - A scientist with a codebase carries their analysis across (Priority: P1)

A researcher with a Python repository built up over several years opens
SciStudio, having completed a Learning Center entry or two. They point the
feature at their repository, answer a few questions about what they work on, and
end the session with blocks in their project that do what their scripts did.

**Why this priority**: This is the cohort ADR-053 §4 was written for — the users
with the most existing assets and therefore the highest re-authoring cost. If
this story does not work, the feature has no reason to exist.

**Independent Test**: Point the dialog at a repository, complete the session, and
confirm at least one working block exists in the project that corresponds to code
in that repository.

**Acceptance Scenarios**:

1. **Given** a project is open and an agent is ready, **when** the user activates
   the toolbar entry, **then** the dialog opens with the source, destination, and
   four questions.
2. **Given** the user supplies a repository directory and answers question 1,
   **when** they start the session, **then** a brief file is written under
   `.scistudio/` carrying the source location and every answer given, and the
   session opens showing a single line pointing at it.
3. **Given** a session is running against a repository, **when** the agent has
   written a block, **then** it asks the user for input data and for the expected
   result before reporting the block as done.
4. **Given** the agent has run its check, **when** it reports the outcome,
   **then** the report states what the block was checked against — the original
   run on real data, the user's stated expectation, or neither.

### User Story 2 - A scientist with no code carries their workflow across (Priority: P1)

A researcher who does the same analysis every week in Excel, or in a GUI
application, has never written a script and has no repository to point at. They
describe what they do, and end the session with blocks that perform those steps.

**Why this priority**: Equal to Story 1 rather than below it. These users are the
least likely to own anything reusable today, so they have the most to gain, and
excluding them would leave the largest group of affected users out of a feature
about carrying existing work across.

**Independent Test**: Complete the flow with the no-codebase option selected and
no source path, and confirm the session starts with a prompt built from the
user's description alone.

**Acceptance Scenarios**:

1. **Given** the dialog is open, **when** the user selects "I don't have a
   codebase", **then** the source location field is disabled or hidden and every
   other field remains in effect.
2. **Given** the no-codebase option is selected, **when** the user attempts to
   skip the workflow-description question, **then** the dialog requires an answer
   before the session can start.
3. **Given** a no-codebase session is running, **when** the agent verifies a
   block, **then** it asks whether the user can provide data and what the right
   answer looks like, and its report claims only what it actually checked.

### User Story 3 - A user without a working agent learns exactly what to do (Priority: P2)

A user activates the feature with no agent installed, or with one installed but
not logged in, or logged in but out of quota. In each case they are told the
actual cause and the actual next step.

**Why this priority**: Below the two import stories because it is a supporting
path, but above cosmetic work because the revised ADR-053 §4.1 makes an agent
mandatory — without accurate guidance this state is a dead end rather than a
setup step.

**Independent Test**: Force each of the four availability states and confirm the
dialog shows that state's guidance in place of a start action.

**Acceptance Scenarios**:

1. **Given** no agent CLI is installed, **when** the dialog opens, **then** it
   shows installation guidance instead of a start action.
2. **Given** an agent is installed but has no valid credentials, **when** the
   dialog opens, **then** it shows login guidance for the detected provider.
3. **Given** an agent is authenticated but a live call fails, **when** the dialog
   opens, **then** it reports the concrete cause and does not suggest
   reinstalling.
4. **Given** a provider probe hangs, **when** the dialog opens, **then** it
   renders with a reported state rather than waiting.

### User Story 4 - A user understands the result is not verified (Priority: P2)

A user starting a session is told, before anything happens, that the agent can be
wrong and that reviewing the result is their job.

**Why this priority**: Below the import stories because it changes no mechanism,
but it is the only thing standing between a user and unwarranted trust in
generated code, and ADR-053 §5 treats it as load-bearing rather than as a
disclaimer.

**Independent Test**: Open the dialog and confirm the caveat is present and not
bypassable before the session starts.

**Acceptance Scenarios**:

1. **Given** the dialog is open, **when** the user reaches the start action,
   **then** the caveat stating that correctness is not guaranteed has been shown.
2. **Given** the no-codebase path is selected, **when** the caveat is shown,
   **then** it is not weakened or omitted on the grounds that no transcription
   took place.

### Edge Cases

- **The user points at a directory with no recognisable code.** The session still
  starts; the agent reports what it found and asks rather than failing silently.
- **The user skips every skippable question.** The session starts with source,
  destination, and question 1 only, and the prompt tells the agent the others
  were skipped so it can ask rather than assume.
- **The agent becomes unavailable mid-session.** Blocks and checks already
  written stay in the project. Nothing this spec produces depends on the agent
  remaining reachable after it is written.
- **The user selects the personal library as the destination and the agent writes
  a block depending on a project-local type.** The block would load in this
  project and fail in every other. The prompt must prevent it (FR-013).
- **A provider probe hangs or the binary exists but does not respond.** Treated as
  a reported state, never as a stuck dialog (FR-031).
- **The user's codebase is in another language.** Transcription across languages
  is in scope. Whether the original can be executed for comparison depends on
  what is installed, which the brief leaves to the agent to work out with the
  user (§4.6, "Verifying your work").

## 3. Requirements

### Functional Requirements

#### Entry point

**FR-001.** The feature MUST be reachable from a permanently available entry in
the toolbar, labelled "Bring in my work". It MUST NOT be gated on Learning Center
progress, project count, or elapsed time. ADR-053 §4.2 keeps progress as the
trigger for when the product *volunteers* the capability, never for whether it
can be reached.

**FR-002.** The entry MUST be enabled when a project is open and disabled
otherwise, since a session writes blocks into a project.

**FR-003.** Activating the entry MUST open a dialog that collects the source
location, the destination tier, and four framing answers before any session is
spawned.

**FR-004.** The dialog MUST display the caveat copy required by FR-037 before the
user can start the session.

**FR-005.** The dialog MUST report agent availability and, when **no** agent is
usable, MUST show that state's guidance instead of a start action. When some
providers are usable and others are not, the dialog MUST let the user proceed
with a usable one rather than blocking on the unusable ones.

#### Who the questions are written for

**FR-006.** The dialog MUST NOT ask questions requiring SciStudio knowledge —
which data types the blocks should use, whether something should be an
interactive block, how ports should be shaped. A first-day user cannot answer
these, and they are exactly what the agent should propose and the user confirm
after the work has been read.

**FR-007.** The dialog MUST NOT ask questions requiring software-development
knowledge — which environment the code runs in, how dependencies are installed,
which interpreter is used. The target users run their analyses without
necessarily knowing any of this, and asking tells them the product is not for
them. The agent establishes these facts itself.

The rule these two share: the dialog asks only about the user's own world.

#### Source and destination

**FR-008.** The dialog MUST collect the source location as a text field with a
browse control. The picker MUST accept a **directory**, not only a file.

**FR-009.** The dialog MUST offer an explicit **"I don't have a codebase"**
option. Users who work entirely in spreadsheets or in a GUI application have a
real analysis workflow and no source path, and without this option the dialog
cannot be completed at all — the feature would silently exclude the users least
likely to have built anything reusable.

**FR-010.** Selecting that option MUST disable or hide the source location field,
since there is nothing to point at. Every other field, including the destination
tier, MUST remain in effect.

**FR-011.** The dialog MUST collect the destination tier as a single choice:
blocks land in **this project only**, or in the **personal library** available
across projects.

**FR-012.** When the personal library is chosen, blocks are written to the
user-wide library, which requires the write path defined by the ADR-053 personal
tool library spec (its FR-006). This spec does not define a second write path.

**FR-040.** The dialog MUST let the user choose **which agent** runs the session
when more than one is usable. Availability is not a single boolean: the #1994
registry supports several providers side by side, and a user with two installed
has no way to express a preference otherwise. The choice sits with the source and
destination fields, since all three are decisions about how the session will be
set up.

**FR-041.** The dialog MUST offer the same **permission mode** choice the agent
chat offers — the safe default, or the bypass mode. A session that writes many
files and runs the user's code hits permission prompts constantly, so a user who
wants to grant that up front must be able to, and a user who does not must keep
the default.

**FR-042.** Both controls MUST reuse the existing components — `ProviderPicker`
and `PermissionModePicker` under `frontend/src/components/AIChat/SetupScreen.parts/`
— rather than introducing a second implementation. Provider selection and
permission semantics belong to ADR-034, and a divergent copy here would drift the
moment a provider is added or a permission mode changes.

**FR-043.** When exactly one provider is usable, the dialog MUST select it rather
than requiring the user to choose. Most users have one agent installed, and
presenting a single-option choice is friction with no decision behind it. The
control stays visible so the user can see which agent will run.

**FR-044.** The selected provider and permission mode MUST be passed to the spawn
(FR-022). A choice the dialog collects but does not apply is worse than not
offering it.

#### The four questions

Each question serves two purposes at once, and the second is easy to lose.

They collect context the agent would otherwise have to guess. They also **name
capabilities the user has never heard of**: ADR-053 §1 records that observed
users had never heard of interactive blocks, custom previewers, or custom data
types. Question 3 introduces interaction and visualisation, and question 4
introduces external-application integration, both framed entirely in the user's
own terms. The dialog is therefore also a discovery surface, in the same sense
ADR-053 §9.2 calls the palette tips strip the cheapest discovery surface in the
product. **A future editor optimising these questions purely as data collection
would remove that second effect without noticing it.**

**FR-013.** Question 1 — *what kind of data do you usually work with?* — MUST be
presented as multi-select preset options plus a free-text field for anything not
listed. It is the context for every other answer: the same work reads differently
depending on whether its author handles images or transcriptomics.

**FR-014.** Presets MUST cover both the generic shapes (array, table/dataframe,
series) and the user's domain (for example image, time series, spectrum,
multi-omics, spatial omics). Because these are two different levels of
abstraction — a scientist says "time series", not "Series" — they MUST be
visually grouped so it is clear both may be selected, rather than presented as
one flat list where the two readings of the same data compete.

**FR-015.** Preset options MUST NOT be treated as a routing mechanism. The agent
builds what it needs from core types; domain answers supply context only.

```text
TODO(#2012): suggest a matching package instead of authoring duplicate types.
  Out of scope per owner decision — packages are not publicly promoted yet, and
  suggesting one the user cannot obtain is worse than suggesting none.
  Followup: https://github.com/jiazhenz026/SciStudio/issues/2012
```

**FR-016.** Question 2 — *briefly describe your analysis workflow: what goes in,
what comes out?* — MUST be free text. It is skippable **only when a source
location was given**: with a codebase the agent can read the code and treat this
answer as supplementary, but with no codebase it is the only description of the
work that exists, and skipping it would leave the agent nothing to act on.

**FR-017.** In no-codebase mode the question MUST be required, and its prompt text
MUST ask for more detail than the codebase-mode wording — the steps taken, what is
done at each one, and what the user looks at to decide the result is right. This
is the entire input to the session, so the cost of a thin answer is paid
immediately.

**FR-018.** Question 3 — *which steps would you like to be able to interact with
or see the data for?* — MUST be free text, MUST be skippable, and MUST carry
concrete examples (such as subtracting background, or editing a segmentation
mask). Without examples the question is too abstract to answer; with them it also
teaches that interactive blocks and custom previewers exist.

**FR-019.** Question 4 — *which other data analysis software do you use
regularly?* — MUST be free text and MUST be skippable. It informs app-block
integration and tells the user that integrating external applications is possible
at all.

**FR-020.** Questions 3 and 4, and question 2 in codebase mode, MUST each offer an
explicit skip that reads as a legitimate choice — the user is telling the agent to
work it out — rather than as an abandoned field. The source or the no-codebase
option, the destination, and question 1 are required.

**FR-021.** Every collected answer MUST reach the brief, and skipped questions
MUST be conveyed as skipped rather than omitted, so the agent can tell "the user
did not say" from "the user said nothing applies".

#### The session

**FR-022.** Starting the session MUST spawn a chat session using the same
mechanism the agent block uses. This feature does not introduce a second way to
run an agent.

**FR-023.** The source location and every dialog answer MUST be composed into the
brief. No answer collected may be silently dropped — if a question is worth
asking, its answer reaches the agent.

**FR-024.** The brief MUST be composed and fully written to disk **before** the
session is spawned. The session's opening message names a file; if that file does
not yet exist, or exists but is incomplete, the agent reads nothing or reads
half a brief, and the session is unrecoverable — it has no other source of
instructions. Spawning MUST NOT race the write.

**FR-025.** The session MUST be an ordinary chat session once started — the user
can talk to it, redirect it, and end it like any other. This is a preconfigured
starting point, not a modal wizard.

#### The task brief

**FR-026.** The brief's content MUST be the text in §4.6, verbatim, with the
user's answers substituted into its final section. It is specified as literal
text rather than as a set of requirements because it is the artefact itself:
restating it as requirements and having an implementer reconstitute it would
introduce exactly the drift the wording is chosen to avoid.

**FR-027.** The composed brief MUST be written to a file under the project's
`.scistudio/` directory, which is already in the default project `.gitignore` as
per-machine runtime state. The brief is session state, not project content, and
must not enter the user's version history.

**FR-028.** The message the user sees when the session starts MUST be a single
line pointing the agent at that file. The agent reads the brief itself. A user
watching the terminal sees one sentence rather than the full instruction set.

**FR-029.** Brief delivery MUST NOT depend on a provider's system-prompt
capability. `SystemPromptStrategy` in the #1994 registry has two values, and only
`FLAG_FILE` (claude-code) can carry a hidden per-session prompt; `codex`,
`kimi-code`, and both Qoder channels are `AMBIENT`, which reads only from the
statically provisioned skills tree and has no per-session channel at all. Routing
the brief through a file and a pointer gives every provider identical behaviour,
and adding a provider later requires nothing of it beyond reading a file it is
told to read.

**FR-030.** Each session MUST get its own brief file. Concurrent sessions in one
project must not overwrite each other's instructions, and a brief that survives
its session lets a user see what their agent was actually told — useful when a
session went wrong.

#### Agent availability

**FR-031.** Availability MUST resolve to one of four states, each with its own
guidance:

| State | Meaning | Guidance |
|---|---|---|
| `not_installed` | No agent CLI found | Installation instructions |
| `not_authenticated` | Installed, no valid credentials | Login instructions for the detected provider |
| `call_failed` | Authenticated, live call failed | The concrete cause — quota, network, provider outage |
| `ready` | Live call succeeded | Which providers are configured |

**FR-032.** The probe MUST build on the provider registry and `GET /api/ai/status`
from #1994 rather than introducing a second discovery path. `available: false`
maps to `not_installed`; `available: true, logged_in: false` maps to
`not_authenticated`.

**FR-033.** Distinguishing `call_failed` from `ready` MUST require a **live
minimal call**. `--version` succeeding and a credential file existing do not
establish that a call will succeed. This is the increment this spec adds over
#1994, and it is the one that catches the authenticated-but-out-of-quota user.

**FR-034.** `call_failed` MUST report the underlying cause and MUST NOT suggest
reinstalling. Telling a correctly configured user to reinstall software they are
already running sends them to fix something that is not broken.

**FR-035.** The probe MUST NOT block the dialog from rendering. A slow or hanging
provider MUST degrade to a reported state, never to a stuck surface.

**FR-036.** Availability MUST be consumable by any agent-dependent surface, not
only this one. ADR-053 §5.2 names the Learning Center agent-setup entry as
another consumer.

#### What the product says about correctness

**FR-037.** The import surface MUST state, before the session starts, that the
agent can make mistakes, that it has been instructed to check that the result
matches the original logic, that this does not guarantee the logic is identical,
and that the user should review the result themselves.

**FR-038.** This statement MUST NOT be collapsed into a dismissible notice or
placed where a user can start a session without having seen it. It is the
product's only mechanism for producing an appropriately sceptical reader.

**FR-039.** The product MUST NOT enforce the existence of a test, and MUST NOT
gate block acceptance on one. Enforcement would be theatre: a test file's
existence says nothing about whether it tests anything, and a user who wants the
block without a test would produce an empty one.


### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `ImportSessionContext` | Everything the dialog collects, composed into the brief before the session is spawned | `source_location` (nullable), `has_no_codebase` (bool), `destination_tier` (`project` \| `user_library`), `data_kinds` (preset selections + free text), `workflow_description`, `interaction_wishes`, `other_software`, a skipped/answered marker per optional question, plus `provider` and `permission_mode` | Written into the brief file before spawn (FR-023, FR-024, FR-027); per-session, gitignored, not product state |
| `AgentAvailability` | The graded result of probing a provider | `state` (`not_installed` \| `not_authenticated` \| `call_failed` \| `ready`), `cause` (populated for `call_failed`), `providers` (populated for `ready`) | Derived from the #1994 provider registry rows plus a live call (FR-028, FR-029); consumed by this dialog and by any other agent-dependent surface (FR-032) |

## 4. Implementation Plan

### 4.1 Technical Approach

**Almost nothing here exists yet.** There is no scanning, candidate,
transcription, or import code anywhere under `src/scistudio/`;
`src/scistudio/ai/` contains only `agent/` — `mcp/`, `system_prompt.py`, and
`terminal.py`. Unlike the personal tool library spec, which mostly re-shapes
existing behavior, this is new construction with two exceptions.

**Provider discovery already exists and is not merged yet.** PR #2003 (issue
#1994, ADR-034) introduces a provider registry and `GET /api/ai/status`, which
returns per provider `{name, available, version, logged_in, label}`. `available`
means the binary was found and `--version` returned within a probe timeout;
`logged_in` comes from a `CredentialProbe` on the provider descriptor. Probes run
concurrently on worker threads and never block or 500 the endpoint. This covers
two of the four states in FR-027, so the availability work here is an increment
over #1994 rather than a parallel implementation — and it is a dependency that
has not landed.

**Agent sessions are PTY-hosted CLIs**, not API clients
(`src/scistudio/ai/agent/terminal.py`). The agent therefore has the user's shell,
filesystem, and Python environments. This is what makes FR-037 viable: the agent
can run the user's original code in the environment that code was written for,
which a SciStudio-hosted runner could not do without reproducing that
environment.

**The brief is a task brief, not a tutorial.** `compose_system_prompt(project_dir)`
already assembles a SKILL.md base, a tool catalog, and a project-context block,
and `agent_provisioning/skills.py` provisions seven skills into every project
(`scistudio`, `-build-workflow`, `-write-block`, `-debug-run`, `-inspect-data`,
`-project-qa`, `-write-plot`), loaded on demand. The brief composed here adds
only what is true of this session — the task, the user's answers, and the
reporting obligations — per FR-039.

**Delivery is by file reference, not by prompt injection.** Today the composed
system prompt reaches claude through `_write_system_prompt_tempfile` and
`--append-system-prompt @<path>`, while the AI block's instruction is passed as
claude's positional `[prompt]` argument and is therefore echoed in the terminal
(the #1789 comment records why: a system prompt does not make the agent act, and
typing into a raw-mode TUI never submits). Neither route generalises. The
`--append-system-prompt` flag only exists for `FLAG_FILE` providers, and the
positional route shows the user everything it carries.

So the brief is written to a file under `.scistudio/` and the session's opening
message is one line naming that file. This works identically on every provider,
including `AMBIENT` ones with no per-session prompt channel, and keeps the
terminal readable. It also means the existing prompt machinery is untouched:
`compose_system_prompt` keeps its current signature and responsibility, and this
feature adds a brief file rather than a second prompt-assembly path.

### 4.2 Affected Files

| File | Action | Rationale |
|---|---|---|
| `docs/adr/ADR-053.md` | modify | Revise §4.1 and §5; generalise §4 to users without code; synchronise §1.1, §6, §7, §8, §9.5 |
| `docs/specs/adr-053-work-import.md` | create | This spec |
| `frontend/src/components/BringInMyWorkDialog.tsx` | create | The framing dialog, caveat copy, and availability guidance (FR-003 – FR-021) |
| `frontend/src/components/AIChat/SetupScreen.parts/ProviderPicker.tsx` | reuse | Provider selection, unchanged (FR-042) |
| `frontend/src/components/AIChat/SetupScreen.parts/PermissionModePicker.tsx` | reuse | Permission mode, unchanged (FR-042) |
| Toolbar component | modify | The entry and its enablement rule (FR-001, FR-002) |
| Agent session spawn path | modify | Accept a composed task brief (FR-023, FR-024) |
| Availability probe module | create | Four-state resolution over the #1994 registry (FR-027 – FR-032) |
| Import brief template | create | The brief text from §4.6, with substitution points for the dialog's answers (FR-026) |

Concrete paths for the last four depend on #2003's final shape and are left
unresolved rather than guessed.

### 4.3 Implementation Sequence

| Task | Title | Story | Depends on | Verification |
|---|---|---|---|---|
| T-001 | ADR-053 revision (§4.1, §5, §4 generalisation) | — | — | Full audit passes; no stale references to no-agent scanning |
| T-002 | Availability probe with four-state resolution over the merged provider registry | US3 | #2003 merged | `tests/api/test_agent_availability.py` covers all four states |
| T-003 | Toolbar entry and enablement | US1, US2 | — | Enabled with a project open, disabled without |
| T-004 | Dialog shell, source/destination page, caveat copy | US1, US2, US4 | T-003 | Caveat present and not bypassable; directory picker accepts a directory |
| T-005 | No-codebase option and its conditional field behaviour | US2 | T-004 | Source field disabled; question 2 becomes required |
| T-006 | The four questions, presets, grouping, and skip semantics | US1, US2 | T-004 | Preset grouping renders; skips are distinguishable from answers |
| T-007 | Prompt composition from the collected context | US1, US2 | T-004, T-006 | Every answer and the mode appear in the composed brief |
| T-008 | Session spawn wired to the composed brief | US1, US2 | T-007 | A session opens carrying the brief |
| T-009 | Availability guidance surfaced in the dialog | US3 | T-002, T-004 | Each state shows its own guidance in place of a start action |
| T-010 | Brief template transcribed from §4.6 and wired to substitution | US1, US2, US4 | T-007 | Composed brief matches §4.6 outside the substituted section |

T-010 is expected to continue after the feature ships; prompt quality is not
settled by a single review (see §4.5).

### 4.4 Verification Plan

| Area | Test |
|---|---|
| Entry enablement | Toolbar entry enabled with a project open, disabled without one (FR-002) |
| Source picker | The browse control accepts a directory, not only a file (FR-008) |
| No-codebase mode | The option is offered; selecting it disables the source field and leaves the destination tier in effect (FR-009, FR-010) |
| Destination tier | Both choices are offered; choosing the personal library routes writes to the user-wide library (FR-011, FR-012) |
| Provider choice | With two usable providers the user can pick between them; with one it is preselected and still visible (FR-040, FR-043) |
| Permission mode | Both modes are offered and the default is the safe one (FR-041) |
| Selection is applied | The chosen provider and permission mode reach the spawned session (FR-044) |
| Partial availability | One usable and one unusable provider lets the user proceed rather than blocking (FR-005) |
| Library-mode constraint | In personal-library mode the composed brief carries the project-local-type warning (FR-013) |
| Preset grouping | Generic shapes and domain options are visually grouped so both can be selected (FR-015) |
| Question 2 conditionality | Skippable with a source location, required without one (FR-017, FR-018) |
| Required vs skippable | Source-or-no-codebase, destination, and question 1 required; questions 3 and 4 each offer an explicit skip (FR-021) |
| Skip is conveyed | A skipped question reaches the brief marked as skipped rather than being omitted (FR-022) |
| Brief composition | Every dialog answer and the source location appear in the composed brief (FR-024) |
| Brief location | The brief is written under `.scistudio/` and is not picked up by git in a project using the default ignore file (FR-027) |
| Write before spawn | The brief file exists and is complete before the session is spawned; a session is never started against a missing or partial file (FR-024) |
| Visible message | Session start shows one line referencing the brief, not the brief's contents (FR-028) |
| Provider independence | Brief delivery is identical for a `FLAG_FILE` and an `AMBIENT` provider (FR-029) |
| Concurrent sessions | Two sessions started in one project get distinct brief files (FR-030) |
| Availability states | All four states resolve correctly, including authenticated-but-failing (FR-027, FR-029) |
| Availability guidance | `call_failed` reports its cause and does not suggest reinstalling (FR-030) |
| Probe non-blocking | A hanging provider yields a reported state rather than a stuck dialog (FR-031) |
| Caveat presence | The caveat is present and the session cannot be started without it having been shown (FR-033, FR-034) |
| No enforcement | Nothing blocks a block on the absence of a test file (FR-035) |
| Brief fidelity | The composed brief matches §4.6 verbatim outside the substituted answers section (FR-026) |
| Answer substitution | Each question appears with its own text and the user's answer, or an explicit skip marker (FR-021, FR-026) |

Lint, type, and docs checks run through the standard gate. This PR is docs-only;
the tests above land with the implementing tasks.

### 4.5 Risks And Rollback

**The prompt is the product.** Nearly everything users experience here is
determined by prompt text rather than code, so quality is not fixed by reviewing
a diff and will need iteration against real sessions. Accepted; the alternative
is a large product surface built on guesses about the user's work.

**No agent means no feature.** The revised §4.1 gives up the property that
something useful happened before the user configured an agent. Graded
availability limits the damage by telling the user exactly what to do, but a user
without an agent now meets a setup step instead of a result.

**The no-codebase path has a weaker floor.** With a codebase, a wrong
transcription can in principle be caught by running the original. Without one,
the only reference is what the user remembers or computes by hand, so a
misunderstanding the agent and the user share will survive verification. The
brief keeps the two cases from being reported as equally strong (§4.6,
"Verifying your work"), but the asymmetry is real and accepted: the alternative is excluding these users, who are precisely
the ones with nothing reusable today.

**The caveat can be ignored.** FR-034 puts it where the user starts, which is the
best available position, and it is still a sentence people skip. The honest
statement is better than a false guarantee, even when some users do not read it.

**Cross-language transcription fails semantically, not visibly.** Translating
from another language can produce code that runs and returns plausible numbers
while differing in index base, axis convention, or division behaviour. The brief
requires the agent to flag these points, which helps a reviewing user and does
nothing for one who does not read. Where the original cannot be executed there is
no automatic check that would catch it either.

**The dependency is unmerged.** T-002 builds on #2003.

**The implementation issues describe a superseded design.** #2000, #2001, and
#2002 were written against the scan-then-transcribe flow that ADR-053 §4.1 no
longer describes. #2001's static-scan scope does not exist any more, none of the
three covers the no-codebase path, and none reflects the delivery standard in
§4.6. They need rewriting before implementation starts, or an implementer will
build from them rather than from this spec.

**Rollback**: every element is additive — a toolbar entry, a dialog, a prompt
template, and a probe. Removing the toolbar entry disables the feature without
affecting anything else; blocks and checks already written into projects are
ordinary project files and survive independently.

### 4.6 The Task Brief

This is the brief's content, verbatim (FR-026). The final section's placeholders
are substituted with the dialog's answers; everything else is fixed text.

```markdown
# Your task today

You are helping this user bring a body of existing work into SciStudio.

They already have a way of doing their analysis — a codebase, or a routine they
carry out by hand in spreadsheets or another application. It works, and it took
them a long time to build. Your job is to carry it across, not to ask them to
build it again.

Your workflow is: read what they told us, look at their code if there is any,
work out how it runs, form a view of what they need, design a plan, **discuss
that plan with them**, implement it, verify it, and finish by telling them what
they now have and what to do next.

You are talking to a scientist, not a developer. They may not know what a
virtual environment is, and they have almost certainly never heard of most of
SciStudio's concepts. Explain things in terms of their work, not ours.

# The steps

1. **Read their answers.** They are at the end of this document. Note what they
   skipped — a skipped question means they did not tell us, not that the answer
   is "none".

2. **See what is already here.** List the blocks and types the project already
   has, and the ones in their personal library if that is where things are going.
   Some may be from a previous session, or from a tutorial. Reuse what fits
   instead of building a second version of it, and know what names are taken
   before you write anything.

3. **Read their work.** If they gave a source location, read it. Get a sense of
   what the code does before deciding anything. If they have no codebase, their
   description of their workflow is what you have; read it closely.

4. **Work out how their code runs.** Which environment, which interpreter, which
   command, what it needs installed. **Investigate this yourself — do not ask
   them.** They may genuinely not know. Look for environment files, lockfiles,
   READMEs, notebook metadata, whatever the repository offers.

   Do this early. If it turns out you cannot run their original at all — the
   language is not installed, the environment cannot be reconstructed — that
   changes what verification can mean later, and they should hear it now rather
   than at the end.

5. **Form a view.** Which parts of their work are worth carrying across. Which
   steps are separable. What data flows between them. Where a person currently
   makes a judgement call.

6. **Design a plan, then discuss it with them.** See "Before you implement"
   below. This is the most important step in the session.

7. **Implement**, in small batches. See "How to work" below.

8. **Verify**, and report honestly what you checked. See "Verifying your work"
   below.

9. **Close.** Tell them what they now have, how to use it, what you were unsure
   about, and what they might do next.

# What to deliver

A complete session delivers the following. Treat the numbers as **ceilings, not
quotas** — see the note at the end of this section.

1. **Types** for the kinds of data they work with most. Aim for around three.
   Ask them which matter if their work spans more than that; they cannot review
   a large number of new concepts at once.

2. **Load and save blocks** for the file formats those types need, where
   SciStudio's core does not already handle the format. Their TIFFs, their
   instrument's export format, whatever they actually open.

3. **Blocks** covering their one or two most common workflows, decomposed step
   by step. Generalise them — a block should work on the next dataset too, not
   only on the file they showed you.

4. **At least one interactive block**, where their work has a step that warrants
   one. If they told you which steps they would like to interact with, follow
   that. If they did not, work out where a human judgement is actually being
   made and propose it.

5. **App blocks** wrapping any external software they named. Look up how that
   software is actually driven — its CLI, its API — install what is needed, and
   make sure their data reaches it and comes back.

6. **At least one previewer**, where a type they work with is something they need
   to look at rather than just pass along. Design the interaction around what
   they would actually do with it, and ask them what they think.

7. **A demo workflow** assembling what you built into one of their real
   analyses — and it must actually run, end to end, on data that is there. Wire
   the blocks together, set the parameters, point it at real input, and run it
   yourself before you hand it over. This is the thing that shows them what they
   now have; a workflow that errors on first click undoes the whole session.

8. **The verification checks** you wrote along the way, saved in the project.

**Every type and block must be usable by a human.** A colour, a real
description, and for blocks an icon, clearly named input and output ports, and
the parameters they would want to change exposed as configuration rather than
hardcoded. A block nobody can tell apart from another block in the palette has
not been delivered.

**One block does one step.** Do not bundle several stages into a single block
because their script happened to do them in one function. The whole reason their
existing work is hard to reuse is that it is not separable; reproducing that
here would defeat the point.

**Name types for what they are, not for where they came from.** `Image` and
`Mask` will be reusable across their next project; `RawMicroscopyImage2024` and
`CellposeSegmentationMask` will not. Reach for the general name unless something
about their work genuinely needs the distinction.

**On the numbers.** They are upper bounds. Check what SciStudio's core types
already cover before authoring a new one — core has `Array`, `DataFrame`,
`Series`, `Text`, `Artifact`, and `CompositeData`, and a user working with tables
does not need a new type. Delivering fewer types than the target, and saying why,
is a correct outcome. Authoring an empty wrapper to reach a number is not.
The same applies to the interactive block and the previewer: if their work
genuinely does not warrant one, say so instead of inventing one.

**Where things go.** They chose one of two destinations in the dialog. Check
which, at the end of this document, before you write anything.

*If they chose **this project only*** — everything goes in the project:
`{project}/types/`, `{project}/blocks/`, `{project}/previewers/`. Nothing else to
think about.

*If they chose their **personal library*** — types and blocks go to
`~/.scistudio/types/` and `~/.scistudio/blocks/`, so they are available in every
project they open. Two things follow from that:

- **A block in the personal library must not depend on a type that only exists in
  this project.** It would work here and fail everywhere else, which is worse
  than not having it — the block appears in their palette and breaks when used.
  If a block needs a custom type, that type goes to the personal library too.
- **Previewers cannot go to the personal library at all.** SciStudio discovers
  previewers from core, from installed packages, and from the project — there is
  no user-level tier. A previewer written to `~/.scistudio/` is silently never
  loaded, with no error. Put previewers in `{project}/previewers/` and tell them
  that this one stays with the project while their blocks and types travel.

**If their data is large** — the kind of size where loading a file whole is not
an option — confirm the scale with them, and look at how SciStudio already
handles large data before designing anything of your own.

# If they have no codebase

Some users have no code at all — they do the same analysis every week in a
spreadsheet, or by clicking through another application. They have a real
workflow; what they lack is a file you can read.

**Their description is your entire input.** Read it closely, and expect it to be
incomplete — not because they were careless, but because everyone omits the parts
they do by reflex.

**Fill the gaps by asking specific questions, not open ones.** "Tell me more
about your workflow" puts the work back on them and they will not know where to
start. "You said you clean up the data first — what does that involve? Are you
removing rows, or adjusting values?" is answerable. Work through their steps one
at a time.

**Confirm your understanding before you build anything.** Play their workflow
back to them in your own words and let them correct it. With a codebase you can
check your reading against the source; here there is nothing to check against
except them, so check against them more often.

**Nothing will catch a misunderstanding automatically.** There is no original to
run, so if you and they have the same wrong idea about what a step does, it will
survive everything you both do. That is the reason for confirming early, asking
narrowly, and being explicit about what you assumed.

**Verification works differently.** See below — you will be asking them for input
data and for what the right answer looks like, because that is the only reference
that exists.

# Before you implement

Once you have a plan and before you write anything, **tell them what you intend
to do, and wait for their answer.**

Explain it in terms of their work. Something like:

> SciStudio turns the kind of data you work with into a named type, and each step
> of your analysis into a block you can reuse. Steps where you currently make a
> judgement can pause and ask you. Anything you need to look at can have its own
> viewer.
>
> Looking at your code, your usual run is: load the raw images, subtract
> background, segment, then measure per-cell intensity. I would add an `Image`
> type and a `Mask` type, and a block for each of those four steps.
>
> I would make background subtraction interactive — it looks like you pick the
> background region by eye, so the block can show you the image and let you
> choose, rather than guessing a value.
>
> You said you always check the segmentation before trusting the numbers, so I
> would do two things for `Mask`. A viewer, so you can see the outlines over the
> original image whenever you click a result. And an editing block in the
> workflow, so a run can pause and let you fix a bad mask before the measurement
> step runs on it.
>
> Does that match how you actually work? Anything I have misunderstood, or
> anything you would want done differently?

**Say why you split things the way you did**, not just what the pieces are —
"background subtraction is its own block because you will want it for other
images too". Reasons let them disagree with you. A bare list can only be
accepted.

**Then stop and wait.** Do not present a plan and start building in the same
breath. If they correct you, rework your understanding and show them again —
do not patch your original plan around their objection.

# How to work

**Never overwrite anything of theirs.** This is the one mistake in this session
that cannot be undone, and it has two forms:

- **Files you write.** Before writing a block or a type, check whether that name
  is already taken — in the project, and in their personal library if that is the
  destination. Something already there may be a tool they built and rely on. Pick
  a different name, or ask them, but never write over it.
- **Files their code writes.** Their scripts produce output, often to fixed paths
  — `results/`, `output.csv`, a figure directory. If you run their code to check
  your work, it will write those files, over whatever is there now. Look at what
  a script writes before you run it. Run it on a copy, or in a scratch directory,
  or with the output path pointed somewhere harmless. If you cannot tell where it
  writes, ask them before running it.

They may not notice for weeks, and by then the original is gone.

**Confirm each block actually loaded.** Writing the file is not the same as
having a working block. If a block fails to import — a library that is not
installed, a typo, a bad port declaration — SciStudio skips it silently: it does
not appear in the palette, and nothing tells you. After writing one, list the
blocks and confirm yours is there. If it is not, find out why before moving on.
This matters more than usual here, because you are transcribing code that depends
on their libraries, which may not be installed on this side.

**Work in small batches.** Build a couple of things, show them, get a reaction,
then continue. Do not convert everything you can see in one pass. They cannot
review a large amount of generated code, and if they cannot review it they will
not trust any of it.

**Ask when you do not know.** You are talking to the only person who can answer
most of the questions that matter here — which parts of their work matter, what
counts as a reasonable input, whether a result is right. Guessing is worse than
asking, because a wrong guess looks the same as a right one.

**Talk to them as you go.** Do not disappear and return with everything
finished. Show each piece as you complete it.

**Say what you are unsure about.** If you inferred a port type, could not work
out what a configuration value should be, or could not resolve a dependency, say
so plainly. "I think this input is an AnnData but I am not certain" is more
useful than a confident guess, because they can check it in seconds.

**If you translated from another language**, say so, and point out the places
where the translation could plausibly mean something different rather than just
look different — index bases, default axis conventions, integer division. Those
mistakes produce code that runs and gives plausible numbers, which is exactly
what a person reading it will not catch.

# Verifying your work

You need to establish that what you built does what their original did.

**Find something to check against.** If their codebase contains data you can use,
tell them you intend to verify with it. If you cannot find any, ask whether they
can give you a small example. If they have no codebase, ask the same thing — some
input, and what the right answer looks like.

They may decline. That is their call; carry on and say that you could not verify.

**Write the check as a file and save it in the project**, so they can run it
again later — six months from now, after somebody edits the block.

**Report exactly what you checked.** These are three different claims and they
are not equally strong:

- "I ran your original on the data you gave me and the block produces the same
  result."
- "The block produces the result you told me to expect."
- "I could not run your original, so I have only read it and the logic appears to
  match."

The third is **not verification**. Never report it as though it were.

**If a check fails, suspect your own work first.** Do not relax the check to make
it pass. If their original turns out to be the problem, tell them. If you cannot
resolve it, report the failure — a failing check they know about is far more
useful than a passing one that means nothing.

# What they told us

Each question is reproduced as they saw it, including the examples and options we
offered them, so you can read their answer in the context it was given. What they
did *not* select is informative too.

**Where their work is:** {source_location, or "They said they do not have a
codebase."}

**Where the results should go:** {this project only | their personal library,
available in every project}

---

**We asked:** *What kind of data do you usually work with?*
They could select any of: Array · Table / dataframe · Series · Image ·
Time series · Spectrum · Multi-omics · Spatial omics — and write in anything not
listed.

**They selected:** {selected presets, or "Nothing from the list."}
**They added:** {free text, or "Nothing."}

---

**We asked:** *Briefly describe your analysis workflow — what goes in, what comes
out?*

**They said:** {answer, or "Skipped. They did not answer this."}

---

**We asked:** *Which steps would you like to be able to interact with, or see the
data for? For example: choosing a background region to subtract, or fixing a
segmentation mask by hand.*

**They said:** {answer, or "Skipped. They did not answer this — which means we do
not know, not that there are none. Work out for yourself where a human judgement
is being made, and propose it."}

---

**We asked:** *Which other data analysis software do you use regularly?*

**They said:** {answer, or "Skipped. They did not answer this."}

# When things come up

You already know what SciStudio is and that `mcp__scistudio__*` is how you reach
it. Beyond that, a few things worth keeping in mind:

- **Look things up** in the task skills and in `user-guide/` in this project —
  `writing-blocks.md`, `custom-types.md`, `data-types.md`, `api-reference/`.
  Answer their questions from those rather than from memory, and say you are not
  sure rather than inventing a feature they will go looking for.
- **Never modify their original code.** Read it as much as you like. If you find
  a bug in it, tell them and let them decide.
- **Install dependencies into `~/.scistudio/`** with `pip install --target`,
  never into whatever environment is active. Theirs took effort to get right.
- **Shell for their world, MCP for ours.** Read and run their code with the
  shell; create blocks, workflows, and runs only through `mcp__scistudio__*`.
  Never hand-write `workflows/*.yaml`.
- **Reply in the language they write to you in.**
- **Say when you are stuck** — a dependency that will not install, software with
  no scriptable interface, a format you cannot read. Do not quietly substitute
  something easier and present it as what they asked for.
- **Use a checklist tool if you have one**, and dispatch sub-agents for
  investigation if you can — working out their environment or how some external
  software is driven does not need to occupy your conversation with them.
- **Save and report each piece as you finish it.** This may be a long session,
  and partial work they know about is better than complete work you never
  handed over.
- **Small things matter more than you would think.** A colour that makes a block
  findable at a glance, a description that says what it actually does, a port
  named in their words instead of `input_1`, a sensible default so they do not
  have to fill in a form before anything runs. If a few minutes of work would
  visibly improve what they see and touch, do it — do not skip it because nobody
  put it on a list. This is the difference between something they keep using and
  something they abandon.
```

## 5. Success Criteria

### Measurable Outcomes

**SC-001.** A user with no codebase can complete the flow end to end and finish
the session with at least one working block in their project, without providing
any file path.

**SC-002.** Each of the four availability states presents guidance naming a
specific next action, and no state presents guidance for a different state's
cause — in particular, an authenticated user whose call failed is never told to
install or reinstall anything.

**SC-003.** No session can begin without the correctness caveat having been
displayed, in either mode.

**SC-004.** No question in the dialog requires knowledge of SciStudio concepts or
of software-development concepts to answer. Measured by review of the question
set against FR-006 and FR-007 at each change to it.

**SC-005.** Every agent verification report identifies what it checked against —
the original run on real data, the user's stated expectation, or neither — so
claims of different strength are never presented as equivalent.

**SC-006.** A user who skips every skippable question can still start a session,
and the resulting brief distinguishes skipped questions from unanswered ones.

**SC-008.** Starting a session displays at most one line of instruction text to
the user, on every supported provider.

**SC-009.** A session that produces no new type, no interactive block, or no
previewer because the user's work did not warrant one is a passing outcome, and
the brief's wording makes that explicit rather than implying a shortfall.

**SC-010.** No delivered block performs more than one processing step, and every
delivered block and type carries a colour, a description, and — for blocks — an
icon, named ports, and configurable parameters.

**SC-011.** The plan presented before implementation explains what a type, a
block, an interactive step, and a previewer are, using the user's own data and
workflow as the examples.

**SC-007.** The composed brief contains no restatement of block authoring,
workflow construction, plotting, inspection, or debugging guidance, all of which
are already provisioned as skills. Measured by review at each prompt change.

## 6. Assumptions

| Assumption | Source |
|---|---|
| The feature is a permanently available toolbar entry, enabled with a project open | owner |
| The flow is a preconfigured agent session, not a scan-then-select pipeline | owner |
| The dialog collects a fixed question set that becomes part of the system prompt | owner |
| Verification is prompt-driven and not system-enforced | owner |
| Checks are saved in the project directory | owner |
| The import surface states plainly that correctness is not guaranteed | owner |
| Users with no codebase are in scope, and the entry is labelled "Bring in my work" rather than naming code | owner |
| A prose description of a spreadsheet or GUI workflow is enough for the agent to work from | owner |
| Verification is a flexible agent-led conversation rather than a fixed rule, and the user may decline to supply data | owner |
| Transcribing from other languages is in scope | owner |
| The brief is delivered as a file under `.scistudio/` with a one-line pointer, so the user is not shown a wall of instructions | owner |
| The brief is organised as role, checklist, delivery standard, working method, user answers, situational guidance | owner |
| The delivery standard covers types, IO blocks, workflow blocks, an interactive block, app blocks, a previewer, an optional demo workflow, and the verification checks | owner |
| The agent presents its plan in the user's own terms before implementing, and waits | owner |
| `.scistudio/` is gitignored in projects, so a brief written there stays out of version history | existing-system |
| The Learning Center unlock only routes to this entry point | owner |
| Provider selection and permission mode appear on the dialog's first page, reusing the agent chat's existing controls | owner |
| Environment investigation is delegated to the agent rather than asked of the user | owner |
| ADR-053 §4.1 and §5 as originally written were the authoring agent's decisions, not the intended design | owner |
| The agent has the user's shell and can run the original code in its own environment | existing-system |
| Provisioned skills already cover block authoring, so the brief need not repeat them | existing-system |
