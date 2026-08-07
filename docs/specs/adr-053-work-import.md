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
  is in scope (FR-044). Whether the original can be executed for comparison
  depends on what is installed, which is one of the things FR-040 leaves to the
  agent to work out with the user.

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

**FR-004.** The dialog MUST display the caveat copy required by FR-033 before the
user can start the session.

**FR-005.** The dialog MUST report agent availability and, when an agent is not
usable, MUST show that state's guidance instead of a start action.

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
them. The agent establishes these facts itself (FR-037).

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

**FR-013.** When the personal library is chosen, the system prompt MUST tell the
agent that a block written there must not depend on project-local custom types,
because such a block loads in the originating project and fails everywhere else.
The personal tool library spec covers this for interactive promotion (its FR-021
– FR-024); this feature must not produce the same broken result by another route.

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

**FR-014.** Question 1 — *what kind of data do you usually work with?* — MUST be
presented as multi-select preset options plus a free-text field for anything not
listed. It is the context for every other answer: the same work reads differently
depending on whether its author handles images or transcriptomics.

**FR-015.** Presets MUST cover both the generic shapes (array, table/dataframe,
series) and the user's domain (for example image, time series, spectrum,
multi-omics, spatial omics). Because these are two different levels of
abstraction — a scientist says "time series", not "Series" — they MUST be
visually grouped so it is clear both may be selected, rather than presented as
one flat list where the two readings of the same data compete.

**FR-016.** Preset options MUST NOT be treated as a routing mechanism. The agent
builds what it needs from core types; domain answers supply context only.

```text
TODO(#2012): suggest a matching package instead of authoring duplicate types.
  Out of scope per owner decision — packages are not publicly promoted yet, and
  suggesting one the user cannot obtain is worse than suggesting none.
  Followup: https://github.com/jiazhenz026/SciStudio/issues/2012
```

**FR-017.** Question 2 — *briefly describe your analysis workflow: what goes in,
what comes out?* — MUST be free text. It is skippable **only when a source
location was given**: with a codebase the agent can read the code and treat this
answer as supplementary, but with no codebase it is the only description of the
work that exists, and skipping it would leave the agent nothing to act on.

**FR-018.** In no-codebase mode the question MUST be required, and its prompt text
MUST ask for more detail than the codebase-mode wording — the steps taken, what is
done at each one, and what the user looks at to decide the result is right. This
is the entire input to the session, so the cost of a thin answer is paid
immediately.

**FR-019.** Question 3 — *which steps would you like to be able to interact with
or see the data for?* — MUST be free text, MUST be skippable, and MUST carry
concrete examples (such as subtracting background, or editing a segmentation
mask). Without examples the question is too abstract to answer; with them it also
teaches that interactive blocks and custom previewers exist.

**FR-020.** Question 4 — *which other data analysis software do you use
regularly?* — MUST be free text and MUST be skippable. It informs app-block
integration and tells the user that integrating external applications is possible
at all.

**FR-021.** Questions 3 and 4, and question 2 in codebase mode, MUST each offer an
explicit skip that reads as a legitimate choice — the user is telling the agent to
work it out — rather than as an abandoned field. The source or the no-codebase
option, the destination, and question 1 are required: without a source there is
nothing to read, without a destination there is nowhere to write, and question 1
is the cheapest and most answerable of the four.

**FR-022.** Every collected answer MUST reach the system prompt, and skipped
questions MUST be conveyed as skipped rather than omitted, so the agent can tell
"the user did not say" from "the user said nothing applies".

#### The session

**FR-023.** Starting the session MUST spawn a chat session using the same
mechanism the agent block uses. This feature does not introduce a second way to
run an agent.

**FR-024.** The source location and every dialog answer MUST be composed into the
task brief the session receives. No answer collected may be silently dropped — if
a question is worth asking, its answer reaches the agent.

**FR-045.** The composed brief MUST be written to a file under the project's
`.scistudio/` directory, which is already in the default project `.gitignore` as
per-machine runtime state. The brief is session state, not project content, and
must not enter the user's version history.

**FR-046.** The message the user sees when the session starts MUST be a single
line pointing the agent at that file. The agent reads the brief itself. A user
watching the terminal sees one sentence rather than the full instruction set.

**FR-047.** Brief delivery MUST NOT depend on a provider's system-prompt
capability. `SystemPromptStrategy` in the #1994 registry has two values, and only
`FLAG_FILE` (claude-code) can carry a hidden per-session prompt; `codex`,
`kimi-code`, and both Qoder channels are `AMBIENT`, which reads only from the
statically provisioned skills tree and has no per-session channel at all. Routing
the brief through a file and a pointer gives every provider identical behaviour,
and adding a provider later requires nothing of it beyond reading a file it is
told to read.

**FR-048.** Each session MUST get its own brief file. Concurrent sessions in one
project must not overwrite each other's instructions, and a brief that survives
its session lets a user see what their agent was actually told — useful when a
session went wrong.

**FR-025.** The system prompt MUST instruct the agent to ask the user when it
needs information rather than assuming. The design premise of ADR-053 §4.1 is
that the hard questions here are ones only the user can answer, so an agent that
guesses instead of asking defeats the flow.

**FR-026.** The session MUST be an ordinary chat session once started — the user
can talk to it, redirect it, and end it like any other. This is a preconfigured
starting point, not a modal wizard.

#### Agent availability

**FR-027.** Availability MUST resolve to one of four states, each with its own
guidance:

| State | Meaning | Guidance |
|---|---|---|
| `not_installed` | No agent CLI found | Installation instructions |
| `not_authenticated` | Installed, no valid credentials | Login instructions for the detected provider |
| `call_failed` | Authenticated, live call failed | The concrete cause — quota, network, provider outage |
| `ready` | Live call succeeded | Which providers are configured |

**FR-028.** The probe MUST build on the provider registry and `GET /api/ai/status`
from #1994 rather than introducing a second discovery path. `available: false`
maps to `not_installed`; `available: true, logged_in: false` maps to
`not_authenticated`.

**FR-029.** Distinguishing `call_failed` from `ready` MUST require a **live
minimal call**. `--version` succeeding and a credential file existing do not
establish that a call will succeed. This is the increment this spec adds over
#1994, and it is the one that catches the authenticated-but-out-of-quota user.

**FR-030.** `call_failed` MUST report the underlying cause and MUST NOT suggest
reinstalling. Telling a correctly configured user to reinstall software they are
already running sends them to fix something that is not broken.

**FR-031.** The probe MUST NOT block the dialog from rendering. A slow or hanging
provider MUST degrade to a reported state, never to a stuck surface.

**FR-032.** Availability MUST be consumable by any agent-dependent surface, not
only this one. ADR-053 §5.2 names the Learning Center agent-setup entry as
another consumer.

#### What the product says about correctness

**FR-033.** The import surface MUST state, before the session starts, that the
agent can make mistakes, that it has been instructed to check that the result
matches the original logic, that this does not guarantee the logic is identical,
and that the user should review the result themselves.

**FR-034.** This statement MUST NOT be collapsed into a dismissible notice or
placed where a user can start a session without having seen it. It is the
product's only mechanism for producing an appropriately sceptical reader.

**FR-035.** The product MUST NOT enforce the existence of a test, and MUST NOT
gate block acceptance on one. Enforcement would be theatre: a test file's
existence says nothing about whether it tests anything, and a user who wants the
block without a test would produce an empty one.

#### The agent's instructions

The system prompt is the mechanism that makes the flow work, since almost nothing
above is enforced by the product.

**FR-036.** The prompt MUST instruct the agent to:

1. Read what the user has — the codebase at the given path, or their description
   of how they work — and propose what could become blocks.
2. Ask the user which of those matter rather than converting everything.
3. Write blocks into the project.
4. Tell the user it needs to check that the result matches the original logic,
   and ask for input data and for what the correct answer looks like.
5. Write a check comparing the result against that reference.
6. Save that check in the project directory.
7. Run it and report what happened, including failures.
8. State its uncertainties explicitly — an inferred port type, a configuration
   field it could not determine, a dependency it could not resolve.

**FR-037.** The prompt MUST require the agent to establish the runtime facts it
needs — which environment the user's code runs in, how to invoke it — **by
investigating rather than by asking the user**, who by FR-007 may not know. The
instruction MUST be written as an objective rather than a technique, because
provider capabilities differ across the registry and an instruction naming a
specific mechanism would be unexecutable on providers lacking it.

**FR-038.** The prompt MUST instruct the agent on what to do when questions were
skipped: infer, then confirm with the user, rather than proceeding silently on an
assumption.

**FR-039.** The prompt MUST NOT restate what the agent already knows. Skills
covering block authoring, workflow construction, plotting, data inspection, and
debugging are already provisioned into every project and loaded on demand.
Restating them here would both waste prompt budget and create a second source of
truth that drifts from the skills when they change.

**FR-040.** The prompt MUST instruct the agent to find something to verify
against, flexibly rather than by a fixed rule. If the codebase contains data it
can use, it tells the user it intends to verify with that data. If it finds none,
it asks whether the user can provide some. With no codebase it asks the same
question. The user may decline, and the agent proceeds and says so.

**FR-041.** However the check was done, the prompt MUST make the agent state what
it was checked against. "This matches your original script on the data you gave
me", "this produces the result you told me to expect", and "I could not run the
original, so I only checked that the logic reads the same" are three claims of
very different strength, and a user who cannot tell them apart cannot calibrate
how much to trust the block. Reading the original and concluding the logic
matches is not verification and MUST NOT be reported as though it were.

**FR-042.** Checks MUST be saved inside the project directory. Their value is that
they can be rerun by hand later, which requires the user to be able to find them.
[NEEDS CLARIFICATION: whether a conventional subdirectory is fixed, and whether
the agent or the product chooses the filename.]

**FR-043.** With no codebase the caveat in FR-033 is more load-bearing, not less.
There is no original implementation to disagree with, so the only check on the
agent's understanding is the user's own review. The caveat copy MUST NOT be
weakened or hidden in that case on the grounds that no transcription took place.

#### The brief's structure

**FR-049.** [NEEDS CLARIFICATION: the sixth section's content — guidance for
situations that arise, such as when to ask rather than assume and when to check
in rather than continue — is not yet decided.] The brief MUST be organised into
six sections in this order: the
agent's role and an outline of the session's workflow; the detailed checklist;
the delivery standard; the working method; the user's answers; and guidance for
handling situations that arise. Requirements are stated before the user's
specifics so the agent reads what is being asked of it before it reads what this
particular user said, and the situational guidance comes last so it is closest to
the work.

**FR-050.** The role section MUST open by telling the agent what it is doing
today — helping this user carry a body of existing work into SciStudio — and
summarising the workflow in a sentence or two before the checklist expands it.

**FR-051.** The workflow the checklist expands is: read the user's answers; read
their codebase if there is one; establish how their code actually runs; infer
what they need; design an implementation plan; take that plan to the user and
discuss it; implement; verify; and close with concrete suggestions and next
steps.

**FR-052.** Establishing how the user's code runs MUST come early, before
implementation rather than before verification. Discovering late that the
original cannot be executed — an uninstalled language runtime, an unavailable
environment — changes how verification can work at all (FR-040, FR-041), and the
user should learn that at the start rather than at the end.

#### The delivery standard

**FR-053.** The brief MUST state what a complete session delivers:

1. **Types** for the kinds of data the user works with most.
2. **IO blocks** for the file formats those types need, where core does not
   already handle them.
3. **Blocks** decomposing the user's one or two most common workflows step by
   step, generalised rather than transcribed literally.
4. **At least one interactive block**, where the user's work has a step that
   warrants one.
5. **App blocks** wrapping external software the user named.
6. **At least one previewer**, where a type the user works with benefits from
   one.
7. **A demo workflow** assembling the delivered blocks into one of the user's
   real analyses. Optional.
8. **The verification checks** written during the session, saved in the project.

**FR-054.** The brief MUST state that quantities are ceilings, not quotas, and
that core types are checked first. Core already provides `Array`, `DataFrame`,
`Series`, `Text`, `Artifact`, and `CompositeData`; a user working with tables
needs no new type, and a target of "about three types" will otherwise produce
empty wrappers authored to meet a number. Producing fewer than the target,
with a reason, is a correct outcome.

**FR-055.** For the same reason, "at least one interactive block" and "at least
one previewer" MUST be conditional on the user's work warranting them. Where it
does not, the agent says why rather than delivering something nobody asked for.

**FR-056.** The brief MUST tell the agent that **previewers have no user-level
tier**. Blocks and types can be written to the personal library; previewers are
discovered only from core, packages, and the project. A previewer written into
the user library is silently never loaded. When the user chose the personal
library as their destination, the agent delivers types and blocks there and
keeps previewers in the project, and says so.

**FR-057.** Every delivered type and block MUST carry the user-facing metadata
that makes it usable from the palette and canvas: a colour, a description, and
for blocks an icon, named input and output ports, and configurable parameters
exposed as config rather than hardcoded.

**FR-058.** Each block MUST perform a single step. Bundling several processing
stages into one block reproduces the coarse-block pattern ADR-053 §3 identifies
as the reason nothing accumulates, which would make this feature import the
problem rather than solve it.

**FR-059.** Where the user's work involves data large enough to need streaming or
chunked handling, the agent MUST confirm the scale with the user and MUST consult
SciStudio's existing mechanisms for large data before designing its own.

**FR-060.** The brief MUST state that the delivery standard describes the whole
session's output, not a single hand-off. The agent shows each piece as it is
finished rather than accumulating everything and presenting it at the end.

#### The working method

**FR-061.** Before implementing, the agent MUST present its plan to the user and
MUST wait for a response before proceeding.

**FR-062.** That plan MUST explain SciStudio's abstractions **in terms of the
user's own work** — that the kind of data they handle becomes a type, that each
step of their analysis becomes a block, that a step where they currently make a
judgement can pause for them, that a thing they need to look at can have its own
viewer. This is the feature's most effective teaching moment: ADR-053 §1 records
that observed users had never heard of interactive blocks, custom previewers, or
custom data types, and an explanation grounded in the user's own data lands where
documentation and tips do not. **A future editor trimming this as unnecessary
product exposition would remove the mechanism, not the padding.**

**FR-063.** The plan MUST give reasons for the decomposition it proposes, not
just its result — why a step was split out, and what reusing it later would look
like. Reasons teach the granularity FR-058 requires and give the user something
to disagree with; a bare list can only be accepted.

**FR-064.** When the user rejects or corrects the plan, the agent MUST revise its
understanding and re-present, rather than patching the original around the
objection.

**FR-065.** The agent MUST work in small batches — a couple of blocks, shown and
confirmed, before continuing. Left unsaid, an agent's default is to finish
everything it can see, which produces more generated code than the user can
evaluate at exactly the moment they have least reason to trust it.

**FR-066.** When a verification check fails, the agent MUST treat the
transcription as the suspect. It MUST NOT relax the check to make it pass. If the
original itself is at fault, it says so; if it cannot resolve the failure, it
reports the failure. This is the counterpart to FR-041: that one forbids
overstating what was verified, this one forbids concealing that it was not.

**FR-044.** Transcription from other languages into Python blocks is in scope.
The prompt MUST require the agent to say when it has translated across languages
and to flag the constructs where the translation could plausibly differ in
meaning rather than only in syntax. Cross-language mistakes tend to be semantic —
index bases, default axis conventions, integer division — and they produce code
that runs and yields plausible-looking numbers, which is exactly the class of
error a user is least able to spot by reading.

### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `ImportSessionContext` | Everything the dialog collects, composed into the system prompt at spawn time | `source_location` (nullable), `has_no_codebase` (bool), `destination_tier` (`project` \| `user_library`), `data_kinds` (preset selections + free text), `workflow_description`, `interaction_wishes`, `other_software`, and a skipped/answered marker per optional question | Composed into the brief file at spawn time (FR-024, FR-045); per-session, gitignored, not product state |
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
| `frontend/src/components/BringInMyWorkDialog.tsx` | create | The framing dialog, caveat copy, and availability guidance (FR-003 – FR-022) |
| Toolbar component | modify | The entry and its enablement rule (FR-001, FR-002) |
| Agent session spawn path | modify | Accept a composed task brief (FR-023, FR-024) |
| Availability probe module | create | Four-state resolution over the #1994 registry (FR-027 – FR-032) |
| Import prompt template | create | The agent's instruction set (FR-036 – FR-043) |

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
| T-010 | Prompt content — instruction set, mode split, environment investigation | US1, US2, US4 | T-007 | Reviewed against FR-036 – FR-043 |

T-010 is expected to continue after the feature ships; prompt quality is not
settled by a single review (see §4.5).

### 4.4 Verification Plan

| Area | Test |
|---|---|
| Entry enablement | Toolbar entry enabled with a project open, disabled without one (FR-002) |
| Source picker | The browse control accepts a directory, not only a file (FR-008) |
| No-codebase mode | The option is offered; selecting it disables the source field and leaves the destination tier in effect (FR-009, FR-010) |
| Destination tier | Both choices are offered; choosing the personal library routes writes to the user-wide library (FR-011, FR-012) |
| Library-mode constraint | In personal-library mode the composed brief carries the project-local-type warning (FR-013) |
| Preset grouping | Generic shapes and domain options are visually grouped so both can be selected (FR-015) |
| Question 2 conditionality | Skippable with a source location, required without one (FR-017, FR-018) |
| Required vs skippable | Source-or-no-codebase, destination, and question 1 required; questions 3 and 4 each offer an explicit skip (FR-021) |
| Skip is conveyed | A skipped question reaches the brief marked as skipped rather than being omitted (FR-022) |
| Brief composition | Every dialog answer and the source location appear in the composed brief (FR-024) |
| Brief location | The brief is written under `.scistudio/` and is not picked up by git in a project using the default ignore file (FR-045) |
| Visible message | Session start shows one line referencing the brief, not the brief's contents (FR-046) |
| Provider independence | Brief delivery is identical for a `FLAG_FILE` and an `AMBIENT` provider (FR-047) |
| Concurrent sessions | Two sessions started in one project get distinct brief files (FR-048) |
| Availability states | All four states resolve correctly, including authenticated-but-failing (FR-027, FR-029) |
| Availability guidance | `call_failed` reports its cause and does not suggest reinstalling (FR-030) |
| Probe non-blocking | A hanging provider yields a reported state rather than a stuck dialog (FR-031) |
| Caveat presence | The caveat is present and the session cannot be started without it having been shown (FR-033, FR-034) |
| No enforcement | Nothing blocks a block on the absence of a test file (FR-035) |
| Verification framing | The composed brief instructs the agent to find data to verify against, to ask when it finds none, and to accept a refusal (FR-040) |
| Claim strength | The brief requires the agent to state what it checked against and forbids reporting a read-through as verification (FR-041) |
| Cross-language | The brief requires the agent to flag language translation and its semantic risk points (FR-044) |
| Brief structure | The composed brief contains the six sections in the specified order (FR-049) |
| Ceilings not quotas | The delivery standard states that targets are upper bounds and that core types are checked first (FR-054, FR-055) |
| Previewer tier | The brief states that previewers cannot go to the personal library (FR-056) |
| Plan before implementation | The brief requires presenting a plan and waiting for a response (FR-061) |
| Plan explains abstractions | The brief requires the plan to explain types, blocks, interaction, and previewers in the user's own terms (FR-062) |
| Failure honesty | The brief forbids relaxing a failing check to make it pass (FR-066) |

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
misunderstanding the agent and the user share will survive verification. FR-041
keeps the two cases from being reported as equally strong, but the asymmetry is
real and accepted: the alternative is excluding these users, who are precisely
the ones with nothing reusable today.

**The caveat can be ignored.** FR-034 puts it where the user starts, which is the
best available position, and it is still a sentence people skip. The honest
statement is better than a false guarantee, even when some users do not read it.

**Cross-language transcription fails semantically, not visibly.** Translating
from another language can produce code that runs and returns plausible numbers
while differing in index base, axis convention, or division behaviour. FR-044
requires the agent to flag these points, which helps a reviewing user and does
nothing for one who does not read. Where the original cannot be executed there is
no automatic check that would catch it either.

**The dependency is unmerged.** T-002 builds on #2003.

**The implementation issues describe a superseded design.** #2000, #2001, and
#2002 were written against the scan-then-transcribe flow that ADR-053 §4.1 no
longer describes. #2001's static-scan scope does not exist any more, none of the
three covers the no-codebase path, and none reflects the delivery standard in
FR-053. They need rewriting before implementation starts, or an implementer will
build from them rather than from this spec.

**Rollback**: every element is additive — a toolbar entry, a dialog, a prompt
template, and a probe. Removing the toolbar entry disables the feature without
affecting anything else; blocks and checks already written into projects are
ordinary project files and survive independently.

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
| Environment investigation is delegated to the agent rather than asked of the user | owner |
| ADR-053 §4.1 and §5 as originally written were the authoring agent's decisions, not the intended design | owner |
| The agent has the user's shell and can run the original code in its own environment | existing-system |
| Provisioned skills already cover block authoring, so the brief need not repeat them | existing-system |
