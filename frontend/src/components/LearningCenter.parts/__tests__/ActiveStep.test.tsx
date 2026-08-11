/**
 * ADR-053 Learning Center (#2057) — the step card's two controls (FR-054a).
 *
 * Steps stopped advancing on their own on 2026-08-10. What replaced it is a
 * Continue the reader presses, and the whole design rests on that button being
 * honest: live exactly when the step is done, inert otherwise, and never
 * missing. These are the cases where a wrong answer strands someone — a step
 * that is finished but whose button stays grey, or one that is unfinished and
 * lets them skip the lesson.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import { resetAppStore } from "../../../testUtils";
import type { TutorialSessionResponse, TutorialStepView } from "../../../lib/api/learningCenter";
import { ActiveStep } from "../ActiveStep";

function session(
  step: Partial<TutorialStepView> | null,
  status: "active" | "complete" = "active",
): void {
  const payload: TutorialSessionResponse = {
    source_kind: "core",
    source_id: "",
    tutorial_id: "welcome",
    title: "Welcome to SciStudio",
    project_id: "p1",
    project_path: "/tmp/p1",
    step:
      step === null
        ? null
        : {
            id: "drag-load",
            index: 0,
            total: 5,
            title: null,
            say: "Drag the Load block onto the canvas.",
            highlight: null,
            route_to: null,
            prefill: [],
            awaiting_continue: false,
            satisfied: false,
            ...step,
          },
    satisfied_step_ids: [],
    status,
    error: null,
    replay: null,
  };
  useAppStore.setState({ learningCenterSession: payload });
}

beforeEach(() => {
  resetAppStore();
});

afterEach(() => {
  cleanup();
});

describe("the step card's controls", () => {
  it("shows both controls on a step that is not done", () => {
    /*
     * Present, not absent. A control that appears only once it is usable
     * teaches the reader to hunt for it; one that is always in the same corner
     * lets its lit/grey state carry the only bit that actually changes.
     */
    session({ satisfied: false });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-continue")).toBeDisabled();
    expect(screen.getByTestId("tutorial-check-again")).toBeEnabled();
  });

  it("lights Continue once the backend reports the step satisfied", () => {
    session({ satisfied: true });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-continue")).toBeEnabled();
  });

  it("lights Continue on a reading step, which has no condition to meet", () => {
    // FR-012: a step with no `done_when` is ready from the moment it is entered.
    session({ awaiting_continue: true, satisfied: false });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-continue")).toBeEnabled();
  });

  it("advances only when Continue is pressed", async () => {
    const continueStep = vi.fn(() => Promise.resolve());
    session({ satisfied: true });
    useAppStore.setState({ continueActiveTutorialStep: continueStep });

    render(<ActiveStep />);
    expect(continueStep).not.toHaveBeenCalled();

    screen.getByTestId("tutorial-continue").click();

    expect(continueStep).toHaveBeenCalledTimes(1);
  });

  it("re-checks without advancing when Check again is pressed", () => {
    const evaluateStep = vi.fn(() => Promise.resolve());
    const continueStep = vi.fn(() => Promise.resolve());
    session({ satisfied: false });
    useAppStore.setState({
      evaluateActiveTutorialStep: evaluateStep,
      continueActiveTutorialStep: continueStep,
    });

    render(<ActiveStep />);
    screen.getByTestId("tutorial-check-again").click();

    expect(evaluateStep).toHaveBeenCalledTimes(1);
    expect(continueStep).not.toHaveBeenCalled();
  });

  it("shows no card at all once the tutorial is complete", () => {
    /*
     * Finishing opens the Learning Center (`useLearningCenter`), which is where
     * the next tutorial is. A card in the corner saying "complete" beside it
     * was the same news twice, in the smaller of the two places, with two dead
     * buttons under it.
     */
    session(null, "complete");

    render(<ActiveStep />);

    expect(screen.queryByTestId("tutorial-active-step")).toBeNull();
    expect(screen.queryByTestId("tutorial-continue")).toBeNull();
  });

  it("stops pointing once the step is satisfied", () => {
    /*
     * A ring still around the New button after the reader created their plot
     * reads as "press it again" — which is how one reader ended up with two
     * plots. What is left to do is Continue, and that is on the card.
     */
    session({ highlight: { target: "plots_new_button", args: {} }, satisfied: true });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-active-step")).toHaveAttribute(
      "data-tutorial-card-side",
      "docked",
    );
  });

  it("docks the card when the step points at nothing", () => {
    session({ highlight: null });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-active-step")).toHaveAttribute(
      "data-tutorial-card-side",
      "docked",
    );
    expect(screen.queryByTestId("tutorial-highlight")).not.toBeInTheDocument();
  });

  it("keeps the buttons in view when the step's text is long", () => {
    /*
     * The failure this prevents, seen on the first step of core tutorial 1:
     * five sentences of scene-setting made the card taller than the window, its
     * lower half went off the bottom of the screen, and Continue went with it —
     * so the step could not be finished at all.
     *
     * Three things have to hold together, and all three are asserted rather
     * than one standing in for the others: the card is bounded (`maxHeight`),
     * it hangs from the bottom of the window so growth goes upward (`bottom`,
     * with no `top`), and the button row does not scroll away with the prose
     * (`shrink-0`, outside the scrolling region). Any one of them alone lets
     * the bug back in.
     */
    session({
      highlight: null,
      title: null,
      say: "This project holds one small dataset: a cell viability assay read out by fluorescence. ".repeat(
        12,
      ),
    });

    render(<ActiveStep />);

    const card = screen.getByTestId("tutorial-active-step");
    expect(card.style.maxHeight).not.toBe("");
    expect(card.style.bottom).not.toBe("");
    expect(card.style.top).toBe("");

    const buttons = screen.getByTestId("tutorial-continue").parentElement;
    expect(buttons?.className).toContain("shrink-0");
    const scroller = card.querySelector(".overflow-y-auto");
    expect(scroller).not.toBeNull();
    expect(scroller?.contains(screen.getByTestId("tutorial-continue"))).toBe(false);
  });
});
