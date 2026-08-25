/**
 * ADR-053 Learning Center (#2136) — the dialogue surface's two forms.
 *
 * Tested here rather than through `ActiveStep` because the placement is a prop:
 * driving the compact form from the top would mean arranging a highlight that
 * covers a canvas, and jsdom measures every element as zero-sized. The seam the
 * component was split on is the seam the test uses.
 */

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DialogueSurface } from "../DialogueSurface";
import type { DialoguePlacement } from "../placeDialogue";

const STAGE = { top: 70, left: 290, width: 960, height: 540 };
/** Where `placeCard` would put a chat line beside a target in the palette. */
const CARD = { top: 220, bottom: null, left: 300, maxHeight: 400, side: "right" as const };

function surface(
  placement: DialoguePlacement,
  compact: boolean,
  extra: Partial<Parameters<typeof DialogueSurface>[0]> = {},
) {
  return (
    <DialogueSurface
      card={CARD}
      compact={compact}
      controls={<button type="button">Continue</button>}
      heading={<span>Welcome</span>}
      line="Drag Load onto the canvas."
      mood="curious"
      onAdvance={null}
      placement={placement}
      remaining={0}
      speaker="Mio"
      stage={STAGE}
      {...extra}
    />
  );
}

afterEach(() => {
  cleanup();
});

describe("the full form", () => {
  it("stands the character up beside the panel", () => {
    render(surface({ side: "left", edge: "bottom" }, false));

    expect(screen.getByTestId("tutorial-dialogue-sprite")).toBeInTheDocument();
    expect(screen.queryByTestId("tutorial-dialogue-avatar")).toBeNull();
    expect(screen.getByTestId("tutorial-dialogue-line")).toHaveTextContent(
      "Drag Load onto the canvas.",
    );
  });

  it("is laid out inside the stage rather than over the window", () => {
    /*
     * The whole point of the stage box: everything the product puts around the
     * canvas — the rail, the preview panel, the tab strip — stays uncovered
     * because the surface is never over it in the first place.
     */
    render(surface({ side: "left", edge: "bottom" }, false));

    const box = screen.getByTestId("tutorial-dialogue");
    expect(box.style.top).toBe("70px");
    expect(box.style.left).toBe("290px");
    expect(box.style.width).toBe("960px");
    expect(box.style.height).toBe("540px");
  });

  it("faces her own dialogue from either side", () => {
    /*
     * The art is drawn facing screen-left, so the side she stands on decides
     * which of the two baked sets she wears. Same expression, different file.
     */
    const { unmount } = render(surface({ side: "left", edge: "bottom" }, false));
    const facingRight = screen.getByTestId("tutorial-dialogue-sprite").getAttribute("src");
    unmount();

    render(surface({ side: "right", edge: "bottom" }, false));
    const facingLeft = screen.getByTestId("tutorial-dialogue-sprite").getAttribute("src");

    expect(facingRight).not.toBe(facingLeft);
  });
});

describe("a beat that asks for nothing", () => {
  it("prompts instead of offering controls, and the panel is the control", () => {
    const onAdvance = vi.fn();
    render(surface({ side: "left", edge: "bottom" }, false, { controls: null, onAdvance }));

    expect(screen.getByTestId("tutorial-dialogue-hint")).toHaveTextContent("Click to continue");
    expect(screen.queryByRole("button", { name: "Continue" })).toBeNull();

    fireEvent.click(screen.getByTestId("tutorial-dialogue-line"));

    expect(onAdvance).toHaveBeenCalledTimes(1);
  });

  it("says nothing when a click would do nothing", () => {
    /*
     * A session that has stopped, or a step waiting on the reader with no
     * controls of its own: prompting for a click that leads nowhere is worse
     * than prompting for nothing.
     */
    render(surface({ side: "left", edge: "bottom" }, false, { controls: null, onAdvance: null }));

    expect(screen.queryByTestId("tutorial-dialogue-hint")).toBeNull();
  });

  it("does not also advance when the click was for a control in the heading", () => {
    /*
     * The heading's three controls — back, the catalogue link, leave — all sit
     * inside the panel, which is itself the click target. Before this, pressing
     * back also advanced the reading, so on the last beat pressing back moved
     * the reader forward a whole step.
     */
    const onAdvance = vi.fn();
    const onHeadingPress = vi.fn();
    render(
      surface({ side: "left", edge: "bottom" }, false, {
        controls: null,
        onAdvance,
        heading: (
          <button onClick={onHeadingPress} type="button">
            Back
          </button>
        ),
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Back" }));

    expect(onHeadingPress).toHaveBeenCalledTimes(1);
    expect(onAdvance).not.toHaveBeenCalled();
  });

  it("still moves on while it is holding controls", () => {
    /*
     * The panel used to go inert whenever controls were showing, because
     * Continue was one of them. With Continue gone it is the only way forward,
     * and a step carrying a trigger would otherwise be a dead end (#2136).
     */
    const onAdvance = vi.fn();
    render(surface({ side: "left", edge: "bottom" }, false, { onAdvance }));

    fireEvent.click(screen.getByTestId("tutorial-dialogue-line"));

    expect(onAdvance).toHaveBeenCalledTimes(1);
  });
});

describe("poking her", () => {
  it("pulls a face for half a second, then goes back to the one the beat wrote", () => {
    vi.useFakeTimers();
    try {
      render(surface({ side: "left", edge: "bottom" }, false, { mood: "explain" }));
      const sprite = () => screen.getByTestId("tutorial-dialogue-sprite");
      expect(sprite()).toHaveAttribute("data-mood", "explain");

      fireEvent.click(sprite());
      expect(["curious", "angry", "success"]).toContain(sprite().getAttribute("data-mood"));

      act(() => {
        vi.advanceTimersByTime(500);
      });

      expect(sprite()).toHaveAttribute("data-mood", "explain");
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not touch the reading — a poke is not a click on the panel", () => {
    const onAdvance = vi.fn();
    render(surface({ side: "left", edge: "bottom" }, false, { controls: null, onAdvance }));

    fireEvent.click(screen.getByTestId("tutorial-dialogue-sprite"));

    expect(onAdvance).not.toHaveBeenCalled();
  });
});

describe("the compact form", () => {
  it("swaps the standing character for an avatar", () => {
    render(surface({ side: "left", edge: "bottom" }, true));

    expect(screen.getByTestId("tutorial-dialogue-avatar")).toBeInTheDocument();
    expect(screen.queryByTestId("tutorial-dialogue-sprite")).toBeNull();
  });

  it("keeps the line and the controls, because the reader still has to act", () => {
    render(surface({ side: "left", edge: "bottom" }, true, { remaining: 1 }));

    expect(screen.getByTestId("tutorial-dialogue-line")).toHaveTextContent(
      "Drag Load onto the canvas.",
    );
    expect(screen.getByTestId("tutorial-dialogue-speaker")).toHaveTextContent("Mio");
    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument();
    expect(screen.getByTestId("tutorial-dialogue-remaining")).toHaveTextContent("▼");
  });

  it("is marked as compact so the shape is visible to anything measuring it", () => {
    render(surface({ side: "right", edge: "top" }, true));

    const box = screen.getByTestId("tutorial-dialogue");
    expect(box).toHaveAttribute("data-tutorial-dialogue-compact", "true");
    expect(box).toHaveAttribute("data-tutorial-dialogue-side", "right");
    expect(box).toHaveAttribute("data-tutorial-dialogue-edge", "top");
  });

  it("floats beside the lit target rather than sitting on the canvas", () => {
    /*
     * The whole reason the compact form exists is that it can go to the thing
     * it is talking about — a palette entry in the left panel, the Restore
     * button in the bottom one. Anchored to the stage it could reach neither.
     */
    render(surface({ side: "left", edge: "bottom" }, true));

    const box = screen.getByTestId("tutorial-dialogue");
    expect(box.style.top).toBe("220px");
    expect(box.style.left).toBe("300px");
    expect(box.style.height).toBe("");
    expect(box).toHaveAttribute("data-tutorial-dialogue-anchor", "right");
  });

  it("wears the resting face whatever the beat declares", () => {
    /*
     * An expression changing inside a small circle beside the control the
     * reader is meant to be looking at competes with it. The standing form
     * keeps the full range; this one points, and pointing is all.
     */
    const { unmount } = render(surface({ side: "left", edge: "bottom" }, true));
    const resting = screen.getByTestId("tutorial-dialogue-avatar").getAttribute("src");
    unmount();

    render(surface({ side: "left", edge: "bottom" }, true, { mood: "error" }));

    expect(screen.getByTestId("tutorial-dialogue-avatar")).toHaveAttribute("src", resting);
    expect(screen.getByTestId("tutorial-dialogue-avatar")).toHaveAttribute("data-mood", "idle");
  });
});

describe("the one piece of markup a beat may carry (#2135)", () => {
  /**
   * The beat the six core levels are written in: a sentence of explanation,
   * then the half the reader has to act on, marked by its author.
   */
  const BEAT = "A block is a unit of processing. **Drag Load onto the canvas.**";

  it("sets the instruction apart without showing the markers that said so", () => {
    /*
     * Both halves of this are the point. The emphasized run has to be a real
     * `strong`, because that is what carries the distinction to a screen
     * reader as well as to the eye; and the asterisks have to be gone, because
     * an author who writes `**` and sees `**` learns that the emphasis does
     * not work and stops using it.
     */
    render(surface({ side: "left", edge: "bottom" }, false, { line: BEAT }));

    const line = screen.getByTestId("tutorial-dialogue-line");
    expect(within(line).getByText("Drag Load onto the canvas.").tagName).toBe("STRONG");
    expect(line.textContent).toBe("A block is a unit of processing. Drag Load onto the canvas.");
    expect(line.textContent).not.toContain("*");
  });

  it("leaves the explanation around it as ordinary text", () => {
    /*
     * Emphasis only means anything against something unemphasised. A renderer
     * that bolded the whole line because one run of it was marked would leave
     * the reader with no instruction to find.
     */
    render(surface({ side: "left", edge: "bottom" }, false, { line: BEAT }));

    const line = screen.getByTestId("tutorial-dialogue-line");
    const explanation = within(line).getByText("A block is a unit of processing.");
    expect(explanation.tagName).toBe("SPAN");
    expect(explanation.closest("strong")).toBeNull();
  });
});

describe("a beat that has not finished arriving (#2135)", () => {
  /**
   * The suite-wide stub from `vitest.setup.ts`, which answers "reduce" so that
   * every other assertion in this file reads a finished line.
   */
  const reduced = window.matchMedia;

  /*
   * This block is the exception, and has to say so out loud: it is about what
   * the panel does *while* the line is still typing, which under the suite's
   * default never happens. The stub goes back afterwards, because a
   * non-reduced answer left behind would give every later file a typewriter
   * that types and put the failures somewhere unrelated to this one.
   */
  beforeEach(() => {
    window.matchMedia = ((query: string) => ({
      media: query,
      matches: false,
      onchange: null,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    window.matchMedia = reduced;
  });

  it("invites no click until the sentence has landed", () => {
    /*
     * The chevron is what says the beat is over; showing it beside a sentence
     * still arriving would make it mean nothing, and the words beside it would
     * be inviting a click that only finishes the typing.
     */
    render(
      surface({ side: "left", edge: "bottom" }, false, {
        controls: null,
        onAdvance: vi.fn(),
        remaining: 2,
      }),
    );

    expect(screen.queryByTestId("tutorial-dialogue-hint")).toBeNull();
    expect(screen.queryByTestId("tutorial-dialogue-remaining")).toBeNull();
  });

  it("finishes the line on the first click and moves on only with the second", () => {
    /*
     * The rule that keeps the pacing from costing the reader anything. Without
     * it, an impatient click advances past a sentence that was never on screen
     * — so the typewriter would have taken text away rather than given it a
     * rhythm.
     */
    const onAdvance = vi.fn();
    render(
      surface({ side: "left", edge: "bottom" }, false, {
        controls: null,
        onAdvance,
        remaining: 2,
      }),
    );

    fireEvent.click(screen.getByTestId("tutorial-dialogue-line"));

    expect(onAdvance).not.toHaveBeenCalled();
    expect(screen.getByTestId("tutorial-dialogue-hint")).toBeInTheDocument();
    expect(screen.getByTestId("tutorial-dialogue-remaining")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("tutorial-dialogue-line"));

    expect(onAdvance).toHaveBeenCalledTimes(1);
  });
});
