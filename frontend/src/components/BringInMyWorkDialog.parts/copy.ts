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
 */

/** The toolbar entry's label (FR-001). Never say "code" here — FR-009 users have none. */
export const ENTRY_LABEL = "Bring in my work";

export const DIALOG_EYEBROW = "Bring in my work";
export const DIALOG_TITLE = "Carry your existing analysis across";
export const DIALOG_LEAD =
  "You already have a way of doing this work. Tell us a little about it and an agent " +
  "will sit with you and rebuild it here, step by step, asking you whatever it needs.";

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

export const SOURCE_LABEL = "Where is your work?";
export const SOURCE_HELP =
  "Point us at the folder your analysis lives in. The agent reads it; it never changes it.";
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
export const Q1_HELP =
  "Pick everything that applies. The two lists describe the same data in different ways, " +
  "so picking from both is normal.";

/**
 * FR-014 — the presets cover two different levels of abstraction, and they are
 * grouped so it is clear both may be selected. A scientist says "time series",
 * not "Series"; in one flat list those two readings of the same data compete
 * and the user picks one when both are true.
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
 * FR-020 — the skip affordance.
 *
 * A skip must read as a legitimate choice — the user telling the agent to work
 * it out — rather than as a field they gave up on. Hence a labelled control
 * with its own sentence, not a greyed-out box the user walks past.
 */
export const SKIP_LABEL = "Skip — let the agent work this out";
export const SKIP_HELP =
  "The agent is told you skipped this, so it knows to ask rather than assume.";

export const REQUIRED_MARKER = "Required";

// ---------------------------------------------------------------------------
// FR-005 / FR-031 / FR-034 — agent availability guidance.
// ---------------------------------------------------------------------------

export const AVAILABILITY_PROBING = "Checking which agents are available on this computer…";

export const NOT_INSTALLED_HEADING = "No coding agent found";
export const NOT_INSTALLED_BODY =
  "Bring in my work runs a coding-agent CLI that you set up on your own computer. " +
  "Set one of the supported agents up, then open this dialog again.";

export const NOT_AUTHENTICATED_HEADING = "Your agent needs signing in";
export const NOT_AUTHENTICATED_BODY =
  "These agents are present but have no valid sign-in. Sign in the way that agent " +
  "expects, then open this dialog again.";

/**
 * FR-034 — `call_failed` reports the underlying cause and MUST NOT suggest
 * reinstalling. Telling a correctly configured user to reinstall software they
 * are already running sends them to fix something that is not broken. This
 * branch therefore never uses the word "install" at all, and the test asserts
 * that.
 */
export const CALL_FAILED_HEADING = "Your agent answered, but the call failed";
export const CALL_FAILED_BODY =
  "Nothing on your computer needs changing — the agent is present and signed in. " +
  "The call itself did not go through:";
export const CALL_FAILED_FOOTER = "Try again once that is resolved. Your setup is fine as it is.";

/** Shown next to a usable provider list when some providers are not usable (FR-005). */
export const PARTIAL_AVAILABILITY_NOTE =
  "These agents are not usable right now. You can still start with one of the agents above.";

export const START_LABEL = "Start session";
export const STARTING_LABEL = "Starting…";
export const CANCEL_LABEL = "Cancel";

/** What the session is (FR-025) — a starting point, not a wizard. */
export const START_HELP =
  "This opens an ordinary chat session with everything you just told us already loaded. " +
  "You can talk to it, redirect it, and end it whenever you like.";
