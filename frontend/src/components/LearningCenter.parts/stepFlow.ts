/**
 * ADR-053 Learning Center — the three questions a step's controls turn on.
 *
 * May the reader leave this step, does it want something from them, and does it
 * leave by itself? All three are read off the step view the backend sent plus
 * where the reader is in the beats, and none of them re-derives a condition:
 * spec §4.1 puts judging on the backend, and FR-002 removed the frontend
 * predicates that used to duplicate it.
 *
 * Pure, and out here rather than inline in `ActiveStep`, because they are the
 * part worth testing directly — a reading step, a step with a trigger, a step
 * the reader has walked back into — and none of those needs a DOM.
 */

import type { TutorialSessionResponse, TutorialStepView } from "../../lib/api/learningCenter";

export interface StepFlowInput {
  session: TutorialSessionResponse | null;
  step: TutorialStepView | null;
  /** Whether the step's last beat is the one on screen. */
  onLastBeat: boolean;
  /** #2138 — whether the reader is behind the furthest step they reached. */
  revisiting: boolean;
}

function live(input: StepFlowInput): TutorialStepView | null {
  if (input.session?.status !== "active") return null;
  return input.step;
}

/**
 * FR-054b — whether the reader may leave this step.
 *
 * A reading step is always ready, having no condition to meet (FR-012); a step
 * with one is ready when the backend says it holds. Either way, only once its
 * last beat has been shown, so nobody leaves a step whose text they have not
 * been given.
 */
export function canContinue(input: StepFlowInput): boolean {
  const step = live(input);
  if (step === null || !input.onLastBeat) return false;
  return step.satisfied || step.awaiting_continue;
}

/**
 * Whether this beat asks the reader to *do* something (#2136).
 *
 * What decides between buttons and a prompt. The earlier rule was that both
 * controls are always present, lit or gray, so a reader never has to hunt for
 * one; that holds for a manual and fails for a scene, where most beats are a
 * sentence and a grayed-out Continue under every one of them is a toolbar
 * bolted to a line of dialogue.
 *
 * A satisfied step never counts, whatever else it declares: what is left to do
 * on it is move on, and that is the click.
 */
export function needsAction(input: StepFlowInput): boolean {
  const step = live(input);
  if (step === null || !input.onLastBeat || step.satisfied) return false;
  return Boolean(step.trigger) || !step.awaiting_continue;
}

/**
 * #2135 — whether the click ahead of the reader is the end of the tutorial.
 *
 * The last beat of the last step, ready to be left. What is different about
 * that click is that it is not reversible and not small: it completes the
 * session, and by default closes the project the reader has spent the whole
 * tutorial building. So it is asked for with buttons rather than taken from a
 * click anywhere on the panel, and this is the question that swaps them in.
 *
 * `index` is zero-based, as `StepProgressRing` reads it.
 */
export function finishing(input: StepFlowInput): boolean {
  const step = live(input);
  if (step === null) return false;
  return step.index >= step.total - 1 && canContinue(input);
}

/**
 * FR-054c — whether this step moves on without being asked.
 *
 * The step's own declaration, gated on the reading being finished. Never behind
 * the reader: a revisited step reports satisfied whatever its condition now
 * says (#2138), so without that guard walking back into an auto-advancing step
 * would bounce straight forward again.
 */
export function advancesItself(input: StepFlowInput): boolean {
  const step = live(input);
  if (step === null || input.revisiting || !input.onLastBeat) return false;
  return (step.auto_advance ?? false) && step.satisfied;
}
