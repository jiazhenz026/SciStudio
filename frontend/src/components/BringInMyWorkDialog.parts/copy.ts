/**
 * ADR-053 spec 2 (#2001) — every word the Bring In My Work dialog says.
 *
 * The copy lives in one module because in this feature the wording IS the
 * product: spec §4.5 records that nearly everything the user experiences here
 * is determined by text rather than code. Keeping it here means a reviewer can
 * read the whole user-facing surface in one file, and the tests can assert the
 * shipped words rather than a paraphrase.
 *
 * TWO RULES GOVERN EVERY QUESTION BELOW.
 *
 * FR-006 — no question may require SciStudio knowledge. Not which data types
 * the blocks should use, not whether something should be an interactive block,
 * not how ports should be shaped. A first-day user cannot answer those, and
 * they are exactly what the agent should propose and the user confirm after
 * the work has been read.
 *
 * FR-007 — no question may require software-development knowledge. Not which
 * environment the code runs in, not how dependencies are installed, not which
 * interpreter is used. The target users run their analyses without necessarily
 * knowing any of this, and asking tells them the product is not for them. The
 * agent establishes these facts itself.
 *
 * The rule they share: the dialog asks only about the user's own world.
 *
 * AND ONE THING THAT IS EASY TO LOSE. Each question serves two purposes. It
 * collects context the agent would otherwise guess — and it NAMES A CAPABILITY
 * THE USER HAS NEVER HEARD OF. ADR-053 §1 records that observed users had
 * never heard of interactive blocks, custom previewers, or custom data types.
 * Question 3 introduces interaction and visualisation; question 4 introduces
 * external-application integration; both in the user's own terms. The dialog
 * is a discovery surface as well as a form. A future editor optimising these
 * purely as data collection would remove that second effect without noticing
 * it — please do not be that editor (spec §3, preamble to FR-013).
 *
 * Question 5 is the exception that proves the rule: it names nothing, because
 * its job is to catch whatever the four named questions filtered out (FR-019a).
 * It is not a replacement for any of them — an open question collects far less
 * than a specific one — so it may not be used as grounds for dropping one.
 */

/** The toolbar entry's label (FR-001). Never say "code" here — FR-009 users have none. */
export const ENTRY_LABEL = "Bring in my work";

export const DIALOG_EYEBROW = "Bring in my work";
export const DIALOG_TITLE = "Carry your existing analysis across";

/*
 * THERE IS NO INTRODUCTION, AND THAT IS A DECISION (owner, 2026-08-08).
 *
 * Page one used to open with "You already have a way of doing this work. Tell
 * us a little about it and an agent will sit with you and rebuild it here…" —
 * two sentences of preamble above a page of controls that say the same thing by
 * being there. The owner's verdict on the whole first page was that it is
 * padded, and a user who has just clicked "Bring in my work" does not need to
 * be told what bringing in their work is.
 *
 * The rule that produced this deletion applies to everything in this file:
 * WHERE A CONTROL ALREADY SAYS WHAT IT DOES, THE SENTENCE EXPLAINING IT IS
 * FILLER. Adding one back is a change, not a restoration.
 */

/** Shown when the toolbar entry is reached with no project open (FR-002). */
export const NO_PROJECT_MESSAGE =
  "Open a project first. A session writes its blocks into a project.";

// ---------------------------------------------------------------------------
// FR-037 / FR-038 — the correctness caveat.
// ---------------------------------------------------------------------------

/**
 * ADR-053 §5.1 treats this sentence as load-bearing, not as a disclaimer. It
 * is what determines whether a user reviews an imported block or assumes it
 * was checked, and it is the product's only mechanism for producing an
 * appropriately sceptical reader.
 *
 * FR-037 requires all four claims, in this order:
 *   1. the agent can make mistakes,
 *   2. it has been instructed to check the result against the original logic,
 *   3. that check does not guarantee the logic is identical,
 *   4. the user should review the result themselves.
 *
 * FR-038: it MUST NOT be collapsed into a dismissible notice, and MUST NOT sit
 * anywhere a user could start a session without having seen it. It therefore
 * renders inline, always expanded, directly above the start action — and it is
 * NOT weakened or omitted in no-codebase mode, where nothing was transcribed
 * but the result is no more verified for it.
 */
export const CAVEAT_HEADING = "Before you start";
export const CAVEAT_BODY =
  "The agent can make mistakes. It has been instructed to check that what it builds " +
  "matches the logic of your original work, but that check does not guarantee the logic " +
  "is identical. Review the result yourself before you rely on it.";

// ---------------------------------------------------------------------------
// Source and destination (FR-008 – FR-012).
// ---------------------------------------------------------------------------

/*
 * The label and the placeholder are the whole question. The help line that used
 * to sit under it — "Point us at the folder your analysis lives in. The agent
 * reads it; it never changes it." — restated a field labelled "Where is your
 * work?" next to a button labelled "Browse…" and a box reading "Choose a
 * folder…", and was cut with the rest of page one's padding (owner, 2026-08-08).
 */
export const SOURCE_LABEL = "Where is your work?";
export const SOURCE_PLACEHOLDER = "Choose a folder…";
export const SOURCE_BROWSE_LABEL = "Browse…";

/**
 * FR-009 — the first-class path for users who work entirely in spreadsheets or
 * in a GUI application. Without this option the dialog cannot be completed at
 * all by the users least likely to have built anything reusable.
 */
export const NO_CODEBASE_LABEL = "I don't have a codebase";
export const NO_CODEBASE_HELP =
  "Choose this if your analysis lives in spreadsheets, or in another program you click " +
  "through, rather than in code. You will be asked to describe it instead.";

export const DESTINATION_LABEL = "Where should the results go?";
export const DESTINATION_OPTIONS = [
  {
    value: "project" as const,
    label: "This project only",
    help: "What the agent builds stays in the project you have open.",
  },
  {
    value: "user_library" as const,
    label: "My personal library",
    help: "What the agent builds is available in every project you open.",
  },
];

// ---------------------------------------------------------------------------
// FR-013 – FR-015 — question 1 and its presets.
// ---------------------------------------------------------------------------

export const Q1_LABEL = "What kind of data do you usually work with?";

/**
 * FR-014 — the presets cover two different levels of abstraction, and they are
 * grouped so it is clear both may be selected. A scientist says "time series",
 * not "Series"; in one flat list those two readings of the same data compete
 * and the user picks one when both are true.
 *
 * THE GROUPING IS NOW THE ONLY THING CARRYING FR-014, so it is not decoration.
 * A help line used to say the quiet part out loud — "The two lists describe the
 * same data in different ways, so picking from both is normal" — and it was cut
 * as padding (owner, 2026-08-08). FR-014 asks for the presets to be "visually
 * grouped so it is clear both may be selected, rather than presented as one
 * flat list", which is a statement about structure; the sentence was one way to
 * carry it and the two labelled boxes are the way the requirement names.
 * Flattening these groups, or dropping their legends, removes the requirement.
 *
 * FR-015 — these are context, never a routing mechanism. Nothing downstream
 * branches on a selection; the agent builds what it needs from core types and
 * reads the domain answers as background.
 *
 * The option labels are reproduced verbatim in the brief's "What they told us"
 * section (spec §4.6), so what the user saw and what the agent reads are the
 * same strings.
 */
export interface DataKindGroup {
  id: string;
  legend: string;
  options: string[];
}

export const DATA_KIND_GROUPS: DataKindGroup[] = [
  {
    id: "arrangement",
    legend: "How the data is arranged",
    options: ["Array", "Table / dataframe", "Series"],
  },
  {
    id: "domain",
    legend: "What the data is",
    options: ["Image", "Time series", "Spectrum", "Multi-omics", "Spatial omics"],
  },
];

export const Q1_OTHER_LABEL = "Anything else you work with";
export const Q1_OTHER_PLACEHOLDER =
  "e.g. flow cytometry readings, chromatograms, electrophysiology traces";

// ---------------------------------------------------------------------------
// FR-016 – FR-019 — questions 2 to 4.
// ---------------------------------------------------------------------------

/**
 * FR-016 / FR-017 — question 2.
 *
 * The question itself is the same in both modes, because it is reproduced in
 * the brief as the user saw it. What changes is what we ask of the answer.
 * With a codebase the agent can read the code and this answer is supplementary,
 * so it is skippable. Without one it is the entire input to the session, so it
 * is required and the prompt asks for considerably more: the steps taken, what
 * is done at each one, and what the user looks at to decide the result is right.
 */
export const Q2_LABEL = "Briefly describe your analysis workflow — what goes in, what comes out?";
export const Q2_HELP_WITH_SOURCE =
  "A couple of sentences is plenty — the agent will also read your code.";
export const Q2_HELP_NO_CODEBASE =
  "This is the only description of your work the agent will have, so please take your " +
  "time: the steps you go through, what you do at each one, and what you look at to " +
  "decide the result came out right.";
export const Q2_PLACEHOLDER_WITH_SOURCE =
  "e.g. I start from the plate reader export and end up with one number per condition.";
export const Q2_PLACEHOLDER_NO_CODEBASE =
  "e.g. I open the week's export in Excel, drop the blank wells, average the three " +
  "replicates, divide everything by the control column, then eyeball the chart to check " +
  "the controls sit where they should.";

/**
 * FR-018 — question 3.
 *
 * The examples are not decoration. Without them the question is too abstract to
 * answer, and with them it also teaches — in the user's own vocabulary — that
 * a step can pause and ask you, and that data can have a viewer of its own.
 * That is the discovery half of this question.
 */
export const Q3_LABEL =
  "Which steps would you like to be able to interact with, or see the data for?";
export const Q3_HELP =
  "For example: choosing a background region to subtract, or fixing a segmentation mask " +
  "by hand. Anywhere you currently squint at something and make a call.";
export const Q3_PLACEHOLDER =
  "e.g. I want to see the image and pick the background patch myself, and check the " +
  "outlines before the measurements run.";

/**
 * FR-019 — question 4. Informs app-block integration, and tells the user that
 * driving their other software from here is possible at all.
 */
export const Q4_LABEL = "Which other data analysis software do you use regularly?";
export const Q4_HELP =
  "Anything you open alongside this work — for example ImageJ or Fiji, Excel, Prism, " +
  "MATLAB, or the software that came with your instrument.";
export const Q4_PLACEHOLDER = "e.g. Fiji for the segmentation, Prism for the final figures";

/**
 * FR-019a — question 5, and the last thing the dialog asks.
 *
 * The four questions above it each ask about one specific thing, which is what
 * makes them answerable — and also what makes them a filter. A user whose most
 * important fact is not their data, their workflow, an interactive step or
 * another program has, until this question, nowhere to put it, and the session
 * starts without it.
 *
 * SO THIS ONE NAMES NOTHING AND ASKS FOR EVERYTHING. The help line lists kinds
 * of things rather than an example answer, because an example here would narrow
 * exactly the question that exists not to. It is skippable for the same reason
 * questions 3 and 4 are: having nothing to add to four specific questions is an
 * ordinary answer to an open one, not a field the user gave up on.
 *
 * Both strings are reproduced in the brief (spec §4.6) as the user saw them —
 * the label and the help line together form the question the agent is shown,
 * so an edit to either without the matching edit to §4.6 makes the brief
 * misreport what was asked.
 */
export const Q5_LABEL = "Is there anything else you want to tell the agent before it starts?";
export const Q5_HELP =
  "Anything the questions above did not ask for — something about your data, a constraint " +
  "you work under, a preference, or how you would like it to work with you.";
export const Q5_PLACEHOLDER =
  "e.g. the instrument writes one folder per run and the folder names matter, and I would " +
  "rather be asked than have it guess.";

/**
 * FR-020 — the skip affordance.
 *
 * A skip must read as a legitimate choice — the user telling the agent to work
 * it out — rather than as a field they gave up on. IT NOW CARRIES THAT
 * STRUCTURALLY RATHER THAN VERBALLY, and that shift is the thing to preserve.
 *
 * The label used to be "Skip — let the agent work this out" and it was followed
 * by a sentence, "The agent is told you skipped this, so it knows to ask rather
 * than assume." The owner cut both as filler (2026-08-08): *skip 就是 skip*.
 * What makes the choice legitimate now is where the control is — a button of
 * its own, sitting beside Next as its peer in the navigation row, the same size
 * and the same prominence, rather than a checkbox tucked under the input where
 * a skip reads as giving up on a field.
 *
 * SO: FR-020 depends on `PageNav` keeping Skip a sibling button of Next. A
 * later change that demotes it to a checkbox, hides it in the question body, or
 * styles it as secondary-to-the-point-of-invisible takes FR-020 with it, and
 * there is no longer any copy that would notice. `BringInMyWorkDialog.test.tsx`
 * asserts that structure directly for exactly this reason.
 */
export const SKIP_LABEL = "Skip";

/**
 * The marker on a question the user skipped, shown when they page back to it.
 *
 * A bare state word, deliberately — it exists so a skip is distinguishable from
 * a blank the user forgot, which is the one thing FR-020 needs it to do. It is
 * the counterpart of `REQUIRED_MARKER` and renders the same way: a chip beside
 * the label, in a neutral colour. Never the attention colour — that belongs to
 * "required and unanswered", and a skip is neither.
 */
export const SKIPPED_MARKER = "Skipped";

export const REQUIRED_MARKER = "Required";

// ---------------------------------------------------------------------------
// FR-005 / FR-031 / FR-034 — agent availability guidance.
// ---------------------------------------------------------------------------

export const AVAILABILITY_PROBING = "Checking which agents are available on this computer…";

/**
 * FR-031's guidance column for `not_installed` and `not_authenticated` reads
 * "Installation instructions" and "Login instructions for the detected
 * provider"; SC-002 requires guidance "naming a specific next action"; US3's
 * title is "A user without a working agent learns EXACTLY what to do".
 *
 * These two bodies are therefore a frame, not the guidance. The instruction is
 * per provider and it comes from the backend, in `next_step` on each provider
 * row — the executable to install and the directories SciStudio searched, or the
 * command that signs that CLI in. Those facts belong to the ADR-034 registry,
 * and a second copy of them in this file would be wrong the first time a
 * provider is added. `AvailabilityGuidance` renders one line per provider; what
 * these strings do is say what the list beneath them is.
 *
 * The earlier wording ("Set one of the supported agents up", "Sign in the way
 * that agent expects") named no action at all — and "the way that agent
 * expects" is precisely what a user in this state does not know. Both audits on
 * 2026-08-07 found it independently.
 */
export const NOT_INSTALLED_HEADING = "No coding agent found";
export const NOT_INSTALLED_BODY =
  "Bring in my work runs a coding-agent CLI that you install on your own computer. " +
  "Here is what SciStudio looked for, and where:";
export const NOT_INSTALLED_FOOTER = "Install any one of them, then open this dialog again.";

export const NOT_AUTHENTICATED_HEADING = "Your agent needs signing in";
export const NOT_AUTHENTICATED_BODY =
  "These agents are installed but have no valid sign-in. Here is how to sign each one in:";
export const NOT_AUTHENTICATED_FOOTER = "Sign in to any one of them, then open this dialog again.";

/**
 * FR-034 — `call_failed` reports the underlying cause and MUST NOT suggest
 * reinstalling. Telling a correctly configured user to reinstall software they
 * are already running sends them to fix something that is not broken. This
 * branch therefore never uses the word "install" at all, and the test asserts
 * that.
 *
 * What it also must not do is assert the opposite. The earlier wording said
 * "Nothing on your computer needs changing … Your setup is fine as it is",
 * which FR-034 does not license and which this feature's own measurements
 * contradict: the observed `kimi-code` failure is "No model configured", a
 * local configuration problem the user has to fix on their computer. Not
 * naming a fix is honest; asserting there is nothing to fix is not.
 *
 * "Try again" is likewise only sayable because there is now a control that
 * does it: `CHECK_AGAIN_LABEL` re-probes with `refresh=true`, bypassing the
 * 60-second server-side memoisation that would otherwise re-serve the same
 * failure to a user who had just fixed it.
 */
export const CALL_FAILED_HEADING = "Your agent answered, but the call failed";
export const CALL_FAILED_BODY =
  "The agent is installed and signed in, so this is not a setup problem SciStudio " +
  "can see. This is what it reported:";
export const CALL_FAILED_FOOTER =
  "If that is something you can resolve — a quota, a network, a model setting — " +
  "resolve it and check again.";

export const CHECK_AGAIN_LABEL = "Check again";
export const CHECKING_AGAIN_LABEL = "Checking…";

/**
 * The fourth reason a provider is not usable here, and the only one that is not
 * an availability state.
 *
 * A CLI whose first positional argument is parsed as a subcommand cannot be
 * handed the one line that points a session at its brief (FR-029), so it cannot
 * run a session however healthy it is. Saying so plainly matters more than it
 * looks: the agent works, the user has it set up correctly, and the failure is
 * a limitation of that CLI's command line rather than anything they did. The
 * per-provider reason comes from the registry itself, which is where that
 * limitation is recorded.
 */
export const SESSION_UNSUPPORTED_HEADING = "That agent cannot run this kind of session";
export const SESSION_UNSUPPORTED_BODY =
  "These agents are set up correctly and work fine as a chat tab. They just cannot " +
  "be handed a task to start with, which is how this session begins:";
export const SESSION_UNSUPPORTED_FOOTER =
  "Use one of the other supported agents for this, then open this dialog again.";

/** Guidance for a report naming no providers at all (contract C1's empty registry). */
export const NO_PROVIDERS_BODY =
  "SciStudio has no agent providers registered, so there is nothing to check. This " +
  "is a fault in this build rather than anything on your computer — please report it.";

/*
 * THERE IS NO NOTE BESIDE THE PICKER (owner, 2026-08-08).
 *
 * A paragraph used to sit under the provider picker when some agents were
 * usable and some were not — "These agents are not usable right now. You can
 * still start with one of the agents above." — followed by a full remedy for
 * each. The whole block is gone: every provider is now an option in the one
 * dropdown, greyed with a short suffix when it cannot run a session, which is
 * what the AI chat does. `AgentSetup` carries the reasoning, and
 * `availability.ts::PROVIDER_STATE_HINT` carries the suffixes.
 *
 * The per-state guidance below this line survives untouched, and only renders
 * when NO provider is usable. It is not a longer version of the suffix; it is
 * the only thing on screen in the one state where the user has to act.
 */

export const START_LABEL = "Start session";
export const STARTING_LABEL = "Starting…";
export const CANCEL_LABEL = "Cancel";

/*
 * THE START ACTION EXPLAINS ITSELF, so there is no help line under it.
 *
 * It used to carry "This opens an ordinary chat session with everything you
 * just told us already loaded. You can talk to it, redirect it, and end it
 * whenever you like." Two reasons it is gone (owner, 2026-08-08). It describes
 * what a button labelled "Start session" does, which is the pattern being cut
 * everywhere on these pages. And it sat directly above the correctness caveat,
 * which is the one paragraph on that page a user MUST read (FR-037, FR-038,
 * ADR-053 §5.1) — a second grey paragraph competing with it made the page worse
 * at the only job it cannot fail at.
 *
 * FR-025 is unaffected: it requires the spawned session to BE an ordinary chat
 * session, which it is, not that the dialog say so.
 */

// ---------------------------------------------------------------------------
// Paging — navigation copy only.
// ---------------------------------------------------------------------------

/**
 * Owner directive, 2026-08-07: a long questionnaire is unpleasant to look at
 * and users will not bother filling it in. The dialog is therefore a sequence
 * of pages — setup first, then ONE QUESTION PER PAGE — which is also the shape
 * #2001 described in the first place ("Dialog, page one" and "Dialog, the four
 * questions" as separate groups).
 *
 * EVERYTHING BELOW IS NAVIGATION COPY, and that boundary is the point. Not one
 * question, help line, example or preset label changes with paging. What the
 * user is asked, and in which words, is fixed by FR-006 – FR-019 and reproduced
 * verbatim in the brief (spec §4.6): the agent is told "here is what we asked
 * and here is what they answered", so a user must have seen the same strings
 * the agent is shown. Paging changes where the words appear, never the words.
 */

/**
 * The step names in the progress indicator. They label a dot, not a page, so
 * they are short — the question itself is on the page in full.
 */
export const SETUP_STEP_TITLE = "Setup";
export const Q1_STEP_TITLE = "Your data";
export const Q2_STEP_TITLE = "Your workflow";
export const Q3_STEP_TITLE = "Stepping in";
export const Q4_STEP_TITLE = "Other software";
export const Q5_STEP_TITLE = "Anything else";

export const PROGRESS_LABEL = "Progress";

/**
 * "A run of pages of unknown length is its own kind of unpleasant." The user can
 * see where they are and how much is left at every step, which is the whole
 * reason a paged form is bearable at all.
 */
export function stepStatus(step: number, total: number): string {
  return `Step ${step} of ${total}`;
}

export const BACK_LABEL = "Back";
export const NEXT_LABEL = "Next";

/*
 * THE BLOCKED-PAGE MESSAGE HAS NO LEAD-IN AND NO EXPLANATION.
 *
 * It used to open with "Before you go on:", which the owner read as
 * disrespectful (2026-08-08) — the dialog coaxing an adult through a form. The
 * reasons themselves now state the fact and nothing else, each one beginning
 * "Required:" where it is a required field; they live with the rules that
 * produce them, in `formState.ts`.
 *
 * The other half of that note was about colour: an incomplete page has to be
 * visible at a glance rather than read for, so the message renders in the
 * repository's dialog error treatment (`bg-red-50` / `text-red-700`, the shape
 * `Git/CommitDialog.tsx` uses) rather than in a muted hint colour, on EVERY
 * page that can block. FR-020's other half is why that treatment must never
 * reach a skip: attention colour means "required and unanswered", and a skipped
 * question is a legitimate answer.
 *
 * There is also no sentence explaining why the setup page holds the user when
 * no agent is usable. The blocked-page message already says "No agent is ready
 * to run the session."; a second line saying there is no point answering the
 * questions yet was the same fact twice (owner, 2026-08-08).
 */
