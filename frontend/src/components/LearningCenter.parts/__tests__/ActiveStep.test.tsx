/**
 * ADR-053 Learning Center (#2057) — the step card's two controls (FR-054a).
 *
 * Steps stopped advancing on their own on 2026-08-10. What replaced it is a
 * Continue the reader presses, and the whole design rests on that button being
 * honest: live exactly when the step is done, inert otherwise, and never
 * missing. These are the cases where a wrong answer strands someone — a step
 * that is finished but whose button stays gray, or one that is unfinished and
 * lets them skip the lesson.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import { resetAppStore } from "../../../testUtils";
import type { TutorialSessionResponse, TutorialStepView } from "../../../lib/api/learningCenter";
import { ActiveStep } from "../ActiveStep";
import { DEFAULT_PLACEMENT } from "../placeDialogue";

function session(
  step: (Partial<TutorialStepView> & { can_go_back?: boolean; revisiting?: boolean }) | null,
  status: "active" | "complete" | "error" = "active",
): void {
  const { can_go_back: canGoBack, revisiting, ...stepFields } = step ?? {};
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
            say: ["Drag the Load block onto the canvas."],
            compacts: [false],
            highlights: [null],
            route_to: null,
            prefill: [],
            awaiting_continue: false,
            satisfied: false,
            ...stepFields,
          },
    satisfied_step_ids: [],
    can_go_back: canGoBack ?? false,
    revisiting: revisiting ?? false,
    status,
    error: null,
    replays: [],
  };
  useAppStore.setState({
    learningCenterSession: payload,
    /*
     * The tutorial's own project, open. A tutorial bound to a project is
     * dormant while that project is not, so every case below that is *about*
     * something else has to start from the project being open.
     */
    currentProject: { id: "p1", path: "/tmp/p1" } as never,
  });
}

/**
 * Put a measurable element where a highlight can find it.
 *
 * `useHighlightRect` resolves a target by attribute and then measures it, and
 * jsdom measures everything as zero-sized — which the hook reads as "not on
 * screen" (FR-089c). A test about whether the ring is drawn has to supply the
 * one thing jsdom will not.
 */
function targetOnScreen(target: string): void {
  const element = document.createElement("div");
  element.setAttribute("data-tutorial-target", target);
  element.getBoundingClientRect = () =>
    ({ top: 100, left: 100, width: 200, height: 40 }) as DOMRect;
  document.body.append(element);
}

beforeEach(() => {
  resetAppStore();
});

afterEach(() => {
  cleanup();
});

describe("the step card's controls", () => {
  it("keeps the author's beats separate instead of running them together", () => {
    /*
     * One paragraph per beat, in the order the author wrote them.
     *
     * Where the breaks fall is a writing decision the manifest carries
     * (FR-011d); a surface that joined them back into a single paragraph would
     * discard exactly the thing the author declared.
     */
    session({
      say: ["A block is SciStudio's basic unit of data processing.", "Drag Load onto the canvas."],
      compacts: [false],
    });

    render(<ActiveStep />);

    const line = screen.getByTestId("tutorial-dialogue-line");
    expect(line).toHaveTextContent("A block is SciStudio's basic unit of data processing.");
    expect(line).not.toHaveTextContent("Drag Load onto the canvas.");

    /*
     * Mid-step the chevron says there is more of this step behind it, and the
     * words say what a click does — the chevron alone was a convention rather
     * than an instruction, and mid-step is where a reader meets it first.
     */
    expect(screen.getByTestId("tutorial-dialogue-remaining")).toHaveTextContent("▼");
    expect(screen.getByTestId("tutorial-dialogue-hint")).toHaveTextContent("Click to continue");

    fireEvent.click(line);

    expect(line).toHaveTextContent("Drag Load onto the canvas.");
    /*
     * The last beat of a step whose condition is not met: the re-check appears,
     * and there is still no way forward — the panel is inert because leaving is
     * not yet allowed, not because a button is gray.
     */
    expect(screen.queryByTestId("tutorial-dialogue-remaining")).toBeNull();
    expect(screen.queryByTestId("tutorial-dialogue-hint")).toBeNull();
    expect(screen.getByTestId("tutorial-check-again")).toBeEnabled();
  });

  it("renders nothing for a step that says nothing", () => {
    session({ say: [] });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-dialogue-line")).toHaveTextContent("");
  });

  it("offers only the re-check on a step that is not done", () => {
    /*
     * There is no Continue button anywhere any more (#2136): moving on is the
     * panel's own click. What is left on an unfinished step is the one control
     * the click cannot replace — Check again, for state no mapped event reaches
     * (FR-053) — and no prompt, because clicking would do nothing yet.
     */
    session({ satisfied: false });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-check-again")).toBeEnabled();
    expect(screen.queryByTestId("tutorial-continue")).toBeNull();
    expect(screen.queryByTestId("tutorial-dialogue-hint")).toBeNull();
  });

  it("puts the prompt where the buttons were once the step is satisfied", () => {
    /*
     * #2136. Nothing is being asked of the reader any more — the condition
     * holds — so what is left is to move on, and a button is a heavier thing
     * than that deserves. The panel becomes the control and says so.
     */
    session({ satisfied: true });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-dialogue-hint")).toHaveTextContent("Click to continue");
    expect(screen.queryByTestId("tutorial-continue")).toBeNull();
    expect(screen.queryByTestId("tutorial-check-again")).toBeNull();
  });

  it("gives a reading step the prompt and no buttons at all", () => {
    // FR-012: a step with no `done_when` is ready from the moment it is entered,
    // so it never has anything to press.
    session({ awaiting_continue: true, satisfied: false });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-dialogue-hint")).toBeInTheDocument();
    expect(screen.queryByTestId("tutorial-continue")).toBeNull();
  });

  it("advances on the panel's own click when there is no button to press", async () => {
    const continueStep = vi.fn(() => Promise.resolve());
    session({ satisfied: true });
    useAppStore.setState({ continueActiveTutorialStep: continueStep });

    render(<ActiveStep />);
    expect(continueStep).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("tutorial-dialogue-line"));

    expect(continueStep).toHaveBeenCalledTimes(1);
  });

  it("still moves on from a step that is also showing a button", async () => {
    /*
     * The dead end this prevents. A step with a trigger and no condition keeps
     * its trigger button, and with Continue gone the panel's click is the only
     * way out — so it cannot go inert just because controls are present.
     */
    const continueStep = vi.fn(() => Promise.resolve());
    session({ satisfied: false, awaiting_continue: true, trigger: { label: "Play" } });
    useAppStore.setState({ continueActiveTutorialStep: continueStep });

    render(<ActiveStep />);
    expect(screen.getByTestId("tutorial-trigger")).toBeInTheDocument();
    expect(screen.getByTestId("tutorial-dialogue-hint")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("tutorial-dialogue-line"));

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

    expect(screen.queryByTestId("tutorial-dialogue")).toBeNull();
    expect(screen.queryByTestId("tutorial-continue")).toBeNull();
  });

  it("points again at a step the reader walked back to", () => {
    /*
     * #2138. A revisited step reports satisfied whatever its condition now says
     * — that is what stops the reader being stranded behind a dark Continue —
     * so "satisfied" there means "you did this once", not "you just did it".
     * Hiding the ring on it left the words of a step with nothing pointed at.
     */
    targetOnScreen("plots_new_button");
    session({
      highlights: [{ target: "plots_new_button", args: {} }],
      satisfied: true,
      revisiting: true,
    });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-highlight")).toBeInTheDocument();
  });

  it("stays where it was when the step is satisfied, and only stops pointing", () => {
    /*
     * The flash this prevents. Placement used to be driven by the same rect the
     * ring was, so the moment a step was satisfied the rect went null and
     * `placeCard` docked the surface in the bottom-right corner — for the frame
     * or two before an auto-advancing step moved on, the chat line jumped to
     * the corner of the window and back. Where it stands and whether it points
     * are two questions.
     */
    targetOnScreen("plots_new_button");
    session({
      highlights: [{ target: "plots_new_button", args: {} }],
      satisfied: true,
      compacts: [true],
    });

    render(<ActiveStep />);

    const box = screen.getByTestId("tutorial-dialogue");
    expect(box).toHaveAttribute("data-tutorial-dialogue-anchor", "right");
    expect(screen.queryByTestId("tutorial-highlight")).toBeNull();
  });

  it("stops pointing once the step is satisfied", () => {
    /*
     * A ring still around the New button after the reader created their plot
     * reads as "press it again" — which is how one reader ended up with two
     * plots. What is left to do is Continue, and that is on the card.
     */
    targetOnScreen("plots_new_button");
    session({ highlights: [{ target: "plots_new_button", args: {} }], satisfied: true });

    render(<ActiveStep />);

    expect(screen.queryByTestId("tutorial-highlight")).not.toBeInTheDocument();
  });

  it("takes its default corner when the step points at nothing", () => {
    session({ highlights: [null] });

    render(<ActiveStep />);

    const surface = screen.getByTestId("tutorial-dialogue");
    expect(surface).toHaveAttribute("data-tutorial-dialogue-side", DEFAULT_PLACEMENT.side);
    expect(surface).toHaveAttribute("data-tutorial-dialogue-edge", DEFAULT_PLACEMENT.edge);
    expect(screen.queryByTestId("tutorial-highlight")).not.toBeInTheDocument();
  });

  it("keeps the buttons in view when the step's text is long", () => {
    /*
     * The failure this prevents, seen on the first step of core tutorial 1:
     * five sentences of scene-setting made the card taller than the window, its
     * lower half went off the bottom of the screen, and Continue went with it —
     * so the step could not be finished at all.
     *
     * The dialogue surface answers it structurally: the band is a fixed height
     * the prose cannot push past — fixed outright as of #2136, not merely
     * capped, so the panel is the same size on every beat. Two things still
     * have to hold, and both are asserted rather than one standing in for the
     * other — the line area is bounded, and the prose scrolls inside itself
     * rather than carrying the button row off the edge with it.
     */
    session({
      highlights: [null],
      title: null,
      say: [
        "This project holds one small dataset: a cell viability assay read out by fluorescence. ".repeat(
          12,
        ),
      ],
      compacts: [false],
    });

    render(<ActiveStep />);

    const line = screen.getByTestId("tutorial-dialogue-line");
    expect(line.className).toContain("overflow-y-auto");
    expect(line.className).toContain("h-[4.5rem]");
    expect(line.contains(screen.getByTestId("tutorial-check-again"))).toBe(false);
  });
});

describe("the expression a beat is delivered with (#2136)", () => {
  it("changes with the beat, not with the step's state", () => {
    /*
     * The whole point of FR-011f. Nothing about the session changes between
     * these two clicks — same step, same condition, unsatisfied throughout —
     * and her face changes anyway, because the author wrote it that way.
     */
    session({
      say: ["Welcome.", "Now watch this.", "Your turn."],
      say_moods: ["idle", "explain", "curious"],
      compacts: [false],
    });

    render(<ActiveStep />);
    const line = screen.getByTestId("tutorial-dialogue-line");
    const moodNow = () => screen.getByTestId("tutorial-dialogue-sprite").getAttribute("data-mood");

    expect(moodNow()).toBe("idle");
    fireEvent.click(line);
    expect(moodNow()).toBe("explain");
    fireEvent.click(line);
    expect(moodNow()).toBe("curious");
  });

  it("rests on a beat the author said nothing about", () => {
    session({ say: ["Welcome."], compacts: [false] });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-dialogue-sprite")).toHaveAttribute("data-mood", "idle");
  });
});

describe("a tutorial whose project is not open", () => {
  it("shows nothing once the project has been closed", () => {
    /*
     * Project -> Close project clears the frontend's project and makes no
     * request at all, so the session in the store outlives it — and the
     * character was left standing on the welcome screen of a product with
     * nothing open. The backend draws the same line for the same reason
     * (`_is_live`); this is the frontend's half of it.
     */
    session({ say: ["Welcome."] });
    useAppStore.setState({ currentProject: null });

    render(<ActiveStep />);

    expect(screen.queryByTestId("tutorial-dialogue")).toBeNull();
  });

  it("shows nothing while some other project is open", () => {
    session({ say: ["Welcome."] });
    useAppStore.setState({ currentProject: { id: "someone-elses", path: "/tmp/mine" } as never });

    render(<ActiveStep />);

    expect(screen.queryByTestId("tutorial-dialogue")).toBeNull();
  });

  it("still shows a tutorial that has no project of its own", () => {
    // A reading tutorial belongs to no project, so there is nothing to gate on.
    session({ say: ["Welcome."] });
    const held = useAppStore.getState().learningCenterSession as TutorialSessionResponse;
    useAppStore.setState({
      currentProject: null,
      learningCenterSession: { ...held, project_id: null, project_path: null },
    });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-dialogue")).toBeInTheDocument();
  });
});

describe("going back (#2138)", () => {
  it("offers nothing at the first beat of a step with nothing behind it", () => {
    session({ say: ["Only this."] });

    render(<ActiveStep />);

    expect(screen.queryByTestId("tutorial-back")).toBeNull();
  });

  it("rewinds a beat before it rewinds a step", () => {
    /*
     * The reader is not making that distinction — they clicked past something
     * and want it back — so one control does both, and within a step it costs
     * the backend nothing.
     */
    const backStep = vi.fn(() => Promise.resolve());
    session({ say: ["First beat.", "Second beat."], can_go_back: true });
    useAppStore.setState({ backActiveTutorialStep: backStep });

    render(<ActiveStep />);
    const line = screen.getByTestId("tutorial-dialogue-line");
    fireEvent.click(line);
    expect(line).toHaveTextContent("Second beat.");

    fireEvent.click(screen.getByTestId("tutorial-back"));

    expect(line).toHaveTextContent("First beat.");
    expect(backStep).not.toHaveBeenCalled();
  });

  it("goes back a step once there are no beats left to rewind", () => {
    const backStep = vi.fn(() => Promise.resolve());
    session({ say: ["Only this."], can_go_back: true });
    useAppStore.setState({ backActiveTutorialStep: backStep });

    render(<ActiveStep />);
    fireEvent.click(screen.getByTestId("tutorial-back"));

    expect(backStep).toHaveBeenCalledTimes(1);
  });

  it("opens the step it lands on at its last beat, not its first", () => {
    /*
     * Rewinding wants the line immediately before the one on screen, which is
     * the end of the previous step. Arriving at the top of it would make one
     * press back cost the whole step's reading again.
     */
    const backStep = vi.fn(() => Promise.resolve());
    session({ id: "two", say: ["Only this."], can_go_back: true });
    useAppStore.setState({ backActiveTutorialStep: backStep });

    const { rerender } = render(<ActiveStep />);
    fireEvent.click(screen.getByTestId("tutorial-back"));

    // The backend answers with the previous step, as the store's adopt would.
    session({ id: "one", say: ["Its first beat.", "Its last beat."], can_go_back: false });
    rerender(<ActiveStep />);

    expect(screen.getByTestId("tutorial-dialogue-line")).toHaveTextContent("Its last beat.");
  });
});

describe("the step's trigger button (#2061)", () => {
  it("renders the manifest's label and posts the trigger on press", async () => {
    const triggerActiveTutorialStep = vi.fn().mockResolvedValue(undefined);
    useAppStore.setState({ triggerActiveTutorialStep });
    session({ trigger: { label: "Play" } });

    render(<ActiveStep />);

    const button = screen.getByTestId("tutorial-trigger");
    expect(button).toHaveTextContent("Play");
    button.click();
    expect(triggerActiveTutorialStep).toHaveBeenCalledTimes(1);
  });

  it("renders no trigger button when the step declares none", () => {
    session({ trigger: null });

    render(<ActiveStep />);

    expect(screen.queryByTestId("tutorial-trigger")).toBeNull();
  });

  it("surfaces a trigger failure beside the button, retryable", () => {
    /*
     * FR-060's trigger revision: the failure lives on the step card, the
     * session stays active, and the button stays pressable.
     */
    session({ trigger: { label: "Play" } });
    useAppStore.setState({ learningCenterTriggerError: "step 'watch': write action failed" });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-dialogue-problem")).toHaveTextContent(
      "write action failed",
    );
    expect(screen.getByTestId("tutorial-trigger")).toBeEnabled();
  });
});

describe("a session that stopped", () => {
  it("says so even though the tutorial's project is not open", () => {
    /*
     * The case that made this necessary: a driver that failed on the very first
     * step, before the project had been opened. Every other surface here is
     * conditional on that project, so the reader was left pressing a tutorial
     * that did nothing, with nothing on screen to say why.
     */
    session({ say: ["Welcome."] }, "error");
    useAppStore.setState({
      currentProject: null,
      learningCenterSession: {
        ...(useAppStore.getState().learningCenterSession as TutorialSessionResponse),
        error: "TypeError: something went wrong",
      },
    });

    render(<ActiveStep />);

    const banner = screen.getByTestId("tutorial-problem-banner");
    expect(banner).toHaveTextContent("TypeError: something went wrong");
    expect(banner).toHaveTextContent("Welcome to SciStudio");
    expect(screen.queryByTestId("tutorial-dialogue")).toBeNull();
  });

  it("offers the way out, because the step's own leave control is gone with it", () => {
    const leave = vi.fn(() => Promise.resolve());
    session({ say: ["Welcome."] }, "error");
    useAppStore.setState({ leaveActiveTutorial: leave });

    render(<ActiveStep />);
    fireEvent.click(screen.getByRole("button", { name: "Leave tutorial" }));

    expect(leave).toHaveBeenCalledTimes(1);
  });
});

describe("the last click of the tutorial (#2135)", () => {
  /**
   * The closing step of a five-step tutorial, on its only beat, with its
   * condition met — the one arrangement that puts the two endings up.
   */
  function atTheEnd(): void {
    session({
      id: "wrap-up",
      index: 4,
      total: 5,
      say: ["You can keep exploring in this project, or start your next one."],
      compacts: [false],
      satisfied: true,
    });
  }

  it("asks which ending the reader wants instead of taking one from a stray click", () => {
    /*
     * Everywhere else in a tutorial the panel is the way forward, and that is
     * cheap: the worst a misfire costs is a beat the reader has to walk back
     * to. Here it completes the session and closes the project they have spent
     * the whole tutorial building, so the panel goes inert and the ending is
     * asked for with buttons.
     */
    const continueStep = vi.fn(() => Promise.resolve());
    atTheEnd();
    useAppStore.setState({ continueActiveTutorialStep: continueStep });

    render(<ActiveStep />);

    expect(screen.getByTestId("tutorial-finish-stay")).toBeInTheDocument();
    expect(screen.getByTestId("tutorial-finish-catalogue")).toBeInTheDocument();
    expect(screen.queryByTestId("tutorial-dialogue-hint")).toBeNull();

    fireEvent.click(screen.getByTestId("tutorial-dialogue-line"));

    expect(continueStep).not.toHaveBeenCalled();
  });

  it("records staying before it posts the continue, not after", () => {
    /*
     * The order is the whole mechanism. The session completes on the response,
     * and what reacts to a completed session is an effect in
     * `useLearningCenter` that never sees this click — so which button was
     * pressed has to already be in the store when the request goes out. Record
     * it afterwards and the reader who asked to stay watches their project
     * close anyway.
     */
    const continueStep = vi.fn(() => Promise.resolve());
    const setStayOnFinish = vi.fn();
    atTheEnd();
    useAppStore.setState({
      continueActiveTutorialStep: continueStep,
      setLearningCenterStayOnFinish: setStayOnFinish,
    });

    render(<ActiveStep />);
    fireEvent.click(screen.getByTestId("tutorial-finish-stay"));

    expect(setStayOnFinish).toHaveBeenCalledWith(true);
    expect(continueStep).toHaveBeenCalledTimes(1);
    expect(setStayOnFinish.mock.invocationCallOrder[0]).toBeLessThan(
      continueStep.mock.invocationCallOrder[0],
    );
  });

  it("finishes the way finishing has always worked when the catalogue is chosen", () => {
    /*
     * The other ending, and the one the tutorial used to take without asking:
     * the catalogue opens and the project closes behind the reader. It is
     * still a choice they can make, and it has to be the one that says `false`
     * — a button that recorded nothing would leave whatever the previous
     * tutorial's reader had chosen standing.
     */
    const continueStep = vi.fn(() => Promise.resolve());
    const setStayOnFinish = vi.fn();
    atTheEnd();
    useAppStore.setState({
      continueActiveTutorialStep: continueStep,
      setLearningCenterStayOnFinish: setStayOnFinish,
    });

    render(<ActiveStep />);
    fireEvent.click(screen.getByTestId("tutorial-finish-catalogue"));

    expect(setStayOnFinish).toHaveBeenCalledWith(false);
    expect(continueStep).toHaveBeenCalledTimes(1);
  });

  it("leaves the panel alone on every step before the last one", () => {
    /*
     * The endings belong to the closing step only. Offering them earlier would
     * replace the click that carries the whole reading with a pair of buttons
     * that end the tutorial — the most expensive place in the product to be
     * one step out.
     */
    session({ index: 2, total: 5, satisfied: true });

    render(<ActiveStep />);

    expect(screen.queryByTestId("tutorial-finish-stay")).toBeNull();
    expect(screen.queryByTestId("tutorial-finish-catalogue")).toBeNull();
    expect(screen.getByTestId("tutorial-dialogue-hint")).toBeInTheDocument();
  });
});
