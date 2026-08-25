/**
 * ADR-053 Learning Center (#2135) — the question the end of a tutorial turns on.
 *
 * `finishing` decides whether the panel's click is replaced by two buttons, and
 * it is worth testing away from the DOM because both ways of getting it wrong
 * are expensive and neither is visible in a screenshot. Answering yes too
 * early puts an ending in front of a reader who is halfway through, and the
 * click that ordinarily moves to the next beat stops working for the rest of
 * the step. Answering no on the genuine last beat leaves the tutorial finished
 * by a click anywhere on the panel — and that click closes the project the
 * reader has spent the whole tutorial building.
 *
 * `index` is zero-based, the way `StepProgressRing` reads it, so the last step
 * is `total - 1` and the boundary is worth a case of its own: a one-step
 * tutorial is on its last step from the moment it starts.
 */

import { describe, expect, it } from "vitest";

import type { TutorialSessionResponse, TutorialStepView } from "../../../lib/api/learningCenter";
import { finishing, type StepFlowInput } from "../stepFlow";

function sessionOf(
  step: TutorialStepView,
  status: "active" | "complete" | "error" = "active",
): TutorialSessionResponse {
  return {
    source_kind: "core",
    source_id: "",
    tutorial_id: "welcome",
    title: "Welcome to SciStudio",
    project_id: "p1",
    project_path: "/tmp/p1",
    step,
    satisfied_step_ids: [],
    can_go_back: true,
    revisiting: false,
    status,
    error: null,
    replay: null,
  };
}

/**
 * The last step of a five-step tutorial, on its last beat, with nothing left
 * to ask for — the one arrangement `finishing` is supposed to say yes to.
 *
 * Every case below starts from it and moves exactly one thing, so a failure
 * names the condition that broke rather than the fixture that drifted.
 */
function flow(
  fields: Partial<TutorialStepView> = {},
  extra: Partial<StepFlowInput> = {},
): StepFlowInput {
  const step: TutorialStepView = {
    id: "wrap-up",
    index: 4,
    total: 5,
    title: null,
    say: ["You can keep exploring in this project, or start your next one."],
    compacts: [false],
    highlights: [null],
    route_to: null,
    prefill: [],
    awaiting_continue: true,
    satisfied: false,
    ...fields,
  };

  return {
    session: sessionOf(step),
    step,
    onLastBeat: true,
    revisiting: false,
    ...extra,
  };
}

describe("whether the click ahead of the reader ends the tutorial (#2135)", () => {
  it("says yes on the last beat of the last step, once it may be left", () => {
    expect(finishing(flow())).toBe(true);
  });

  it("says yes on a tutorial that is one step long", () => {
    // The zero-based boundary. A single-step tutorial is on its last step from
    // its first frame, and `index >= total - 1` has to hold at 0 of 1 or that
    // tutorial finishes on a stray click with no ending offered at all.
    expect(finishing(flow({ index: 0, total: 1 }))).toBe(true);
  });

  it("says no in the middle of a tutorial, however finished the step is", () => {
    /*
     * A satisfied step in the middle is ready to be left and is not the end of
     * anything. Reading "ready to continue" as "ready to finish" would put the
     * two endings under every completed step and take the panel's own click
     * away for the rest of the tutorial.
     */
    expect(finishing(flow({ index: 2, satisfied: true }))).toBe(false);
  });

  it("says no on the last step while there is still text to be shown", () => {
    /*
     * The reader is on an earlier beat of the closing step. The buttons are
     * what they are told to press instead of clicking the panel, so offering
     * them here would strand the rest of the step's writing behind an ending
     * the reader had already been handed.
     */
    expect(finishing(flow({ satisfied: true }, { onLastBeat: false }))).toBe(false);
  });

  it("says no on a last step whose condition has not been met", () => {
    /*
     * A closing step that asks for something — the tutorial is on its last
     * step but the reader is not finished. Both halves have to hold, because
     * an ending offered here would let them skip the only thing the step was
     * asking for.
     */
    expect(finishing(flow({ awaiting_continue: false, satisfied: false }))).toBe(false);
  });
});
