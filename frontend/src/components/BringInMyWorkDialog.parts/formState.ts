/**
 * ADR-053 spec 2 (#2001) — the dialog's form state and the rules over it.
 *
 * Everything the dialog collects is described here, and the two derivations
 * that matter — what still blocks the start action, and what the request body
 * looks like — are pure functions so they can be asserted directly rather than
 * inferred from rendered output.
 */
import type { PermissionMode } from "../AIChat/SetupScreen.parts/types";
import type {
  WorkImportDestinationTier,
  WorkImportSessionRequest,
  WorkImportSkippableQuestion,
} from "../../lib/api/workImport";
import { toBackendPermissionMode } from "../../lib/api/workImport";

/**
 * FR-020 / FR-021 — an optional answer is either given or SKIPPED, and skipped
 * is a real value rather than an absence. `skipped` records the user ticking
 * the skip control; an empty box the user simply walked past means the same
 * thing to the agent ("they did not say"), so it resolves the same way.
 */
export interface OptionalAnswer {
  text: string;
  skipped: boolean;
}

export const EMPTY_ANSWER: OptionalAnswer = { text: "", skipped: false };

export interface WorkImportFormState {
  sourceLocation: string;
  hasNoCodebase: boolean;
  destinationTier: WorkImportDestinationTier;
  /** FR-013 — selected preset labels, in the order the user sees them. */
  dataKinds: string[];
  dataKindsOther: string;
  workflowDescription: OptionalAnswer;
  interactionWishes: OptionalAnswer;
  otherSoftware: OptionalAnswer;
  /** FR-040 / FR-043 — null until a usable provider is chosen or preselected. */
  provider: string | null;
  /** FR-041 — the safe mode is the default; the user opts out of it. */
  permissionMode: PermissionMode;
}

export const INITIAL_FORM_STATE: WorkImportFormState = {
  sourceLocation: "",
  hasNoCodebase: false,
  destinationTier: "project",
  dataKinds: [],
  dataKindsOther: "",
  workflowDescription: { ...EMPTY_ANSWER },
  interactionWishes: { ...EMPTY_ANSWER },
  otherSoftware: { ...EMPTY_ANSWER },
  provider: null,
  permissionMode: "safe",
};

function trimmedOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

/**
 * FR-016 / FR-017 — question 2 is skippable ONLY when a source location was
 * given. With a codebase the agent reads the code and this answer is
 * supplementary; without one it is the only description of the work that
 * exists, and skipping it would leave the agent nothing to act on.
 */
export function workflowDescriptionRequired(state: WorkImportFormState): boolean {
  return state.hasNoCodebase;
}

/**
 * FR-010 — selecting "I don't have a codebase" takes the source field out of
 * play and leaves EVERY other field in effect, including the destination tier.
 */
export function sourceFieldDisabled(state: WorkImportFormState): boolean {
  return state.hasNoCodebase;
}

/**
 * What still stands between the user and a session, in the user's own words.
 *
 * Returned as sentences rather than a boolean so the dialog can say why the
 * start action is unavailable. A disabled button with no explanation is the
 * same dead end FR-005 closes for availability.
 */
export function blockingReasons(
  state: WorkImportFormState,
  opts: { projectDir: string | null; agentUsable: boolean },
): string[] {
  const reasons: string[] = [];
  if (!opts.projectDir) {
    reasons.push("Open a project first. A session writes its blocks into a project.");
  }
  if (!state.hasNoCodebase && !state.sourceLocation.trim()) {
    reasons.push('Say where your work is, or choose "I don\'t have a codebase".');
  }
  if (state.dataKinds.length === 0 && !state.dataKindsOther.trim()) {
    reasons.push("Choose at least one kind of data, or write in your own.");
  }
  if (workflowDescriptionRequired(state) && !state.workflowDescription.text.trim()) {
    reasons.push(
      "Describe your analysis workflow. With no codebase to read, this is the only " +
        "description of your work the agent will have.",
    );
  }
  if (!opts.agentUsable) {
    reasons.push("No agent is ready to run the session.");
  } else if (!state.provider) {
    reasons.push("Choose which agent runs the session.");
  }
  return reasons;
}

export function canStart(
  state: WorkImportFormState,
  opts: { projectDir: string | null; agentUsable: boolean },
): boolean {
  return blockingReasons(state, opts).length === 0;
}

/**
 * FR-021 / FR-023 — compose the request body.
 *
 * Every collected answer reaches the brief, and a question the user did not
 * answer is carried as SKIPPED rather than dropped, so the agent can tell "the
 * user did not say" from "the user said nothing applies". An unanswered
 * optional question and an explicitly skipped one are the same claim, so they
 * resolve to the same payload.
 */
export function buildRequest(
  state: WorkImportFormState,
  projectDir: string,
): WorkImportSessionRequest {
  const skipped: WorkImportSkippableQuestion[] = [];

  const resolve = (
    key: WorkImportSkippableQuestion,
    answer: OptionalAnswer,
    required: boolean,
  ): string | null => {
    const value = answer.skipped && !required ? null : trimmedOrNull(answer.text);
    if (value === null) skipped.push(key);
    return value;
  };

  const workflowDescription = resolve(
    "workflow_description",
    state.workflowDescription,
    workflowDescriptionRequired(state),
  );
  const interactionWishes = resolve("interaction_wishes", state.interactionWishes, false);
  const otherSoftware = resolve("other_software", state.otherSoftware, false);

  return {
    project_dir: projectDir,
    source_location: state.hasNoCodebase ? null : trimmedOrNull(state.sourceLocation),
    has_no_codebase: state.hasNoCodebase,
    destination_tier: state.destinationTier,
    data_kinds: [...state.dataKinds],
    data_kinds_other: trimmedOrNull(state.dataKindsOther),
    workflow_description: workflowDescription,
    interaction_wishes: interactionWishes,
    other_software: otherSoftware,
    skipped,
    // `canStart` guarantees a provider before this runs; the fallback keeps the
    // function total without inventing a default provider (ADR-034 FR-020c).
    provider: state.provider ?? "",
    permission_mode: toBackendPermissionMode(state.permissionMode),
  };
}
