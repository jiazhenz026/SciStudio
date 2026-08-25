/**
 * ADR-053 Learning Center (#2136) — the dialogue surface a step is delivered on.
 *
 * Presentation only. It is handed a mood, a line, and a corner; it owns no
 * session state, decides nothing about advancing, and never reads the store.
 * `ActiveStep` does all of that, which keeps the geometry and the wiring
 * separately testable — the split `placeCard`/`ActiveStep` already uses.
 *
 * **It is one box, always the same box.** Width and height are both fixed; a
 * long beat scrolls inside the line area rather than stretching the panel. A
 * panel sized to its text moves its own words and its own buttons on every
 * click, so the reader has to find both again each time — and a visual novel's
 * box is the same box all evening precisely so they never have to. It is also
 * what lets `placeDialogue` treat all four corners as available and satisfy
 * FR-089 by standing somewhere else entirely.
 *
 * **The character stands beside the panel, never over it.** They are one group
 * on one layer, and nothing in that group covers anything else in it, so a gap
 * does the work an overlap used to. The gap is measured to her outline rather
 * than to her image's edge, which is what `MIO_FACING_INSET` exists for. She is
 * `pointer-events: none`, so the product underneath stays clickable through
 * every pixel of her, and the panel is opaque, so nothing of the application
 * shows through the text.
 *
 * **The panel is how you move on; the buttons do other things.** Moving to the
 * next beat and moving to the next step are both a click on the panel, marked
 * by "Click to continue…" wherever a click would do something. There is no
 * Continue button: one that appeared only once the step was finished, beside a
 * prompt saying the same thing, was two ways to do one thing. What controls the
 * panel does carry — this step's trigger, and Check again — do something the
 * click cannot, and a press on one of them never also advances the reading.
 *
 * **A compact form that goes to the thing it is talking about.** The character
 * shrinks to an avatar and the panel to a chat line — the shape a messaging app
 * uses, and for the same reason: it is the smallest thing that still reads as
 * somebody speaking. Unlike the scene it is not anchored to the canvas: it is
 * placed beside the lit target, wherever that is, so a step about one entry in
 * the palette says so next to that entry rather than from the far corner of the
 * workspace. `placeCard` owns that geometry and satisfies FR-089 by never
 * covering the target. Which steps take this form is the author's declaration
 * (FR-011e); the rule the six levels follow is that a ring around one small
 * control gets it, and a ring around a whole surface does not.
 *
 * The palette is the product's own — `canvas` for the panel, `ink` for the text,
 * `ember` for the name plate. The panel is the same light surface the rest of
 * the application uses, because a dark slab dropped onto a light product reads
 * as a foreign object rather than as part of it.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import {
  MIO_CANVAS,
  MIO_COMPACT_AVATAR,
  MIO_FACING_INSET,
  MIO_POKE_CURIOUS,
  spriteFor,
  type MioMood,
} from "./mio";
import { beatLength, beatSegments, type BeatSegment } from "./beatText";
import { CARD_WIDTH, type CardPlacement } from "./placeCard";
import { PANEL_GAP, PANEL_WIDTH, SPRITE_HEIGHT, type DialoguePlacement } from "./placeDialogue";
import { useTypewriter } from "./useTypewriter";
import type { HighlightRect } from "./useHighlightRect";

/** The prompt that stands in for a button when nothing needs deciding. */
const ADVANCE_HINT = "Click to continue…";

/** How long she pulls a face after being poked, in milliseconds. */
const POKE_MS = 500;

/** The faces a poke can produce. None of them means anything; that is the joke. */
const POKE_FACES: readonly MioMood[] = ["curious", "angry", "success"];

/**
 * Poke the character and she reacts for half a second.
 *
 * Presentation state and nothing else — it never reaches the session, never
 * changes what the step says, and is forgotten the moment the timer runs out.
 * The authored expression (FR-011f) is what she goes back to.
 *
 * The cost, stated because it is real: the standing sprite used to be
 * `pointer-events: none`, so the product underneath stayed clickable through
 * every pixel of her. Reacting to a click means catching it, and the canvas
 * behind her is no longer reachable where she stands.
 */
function usePoke(): { face: MioMood | null; poke: () => void } {
  const [face, setFace] = useState<MioMood | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
    },
    [],
  );

  const poke = () => {
    if (timer.current !== null) clearTimeout(timer.current);
    setFace(POKE_FACES[Math.floor(Math.random() * POKE_FACES.length)] ?? null);
    timer.current = setTimeout(() => {
      setFace(null);
      timer.current = null;
    }, POKE_MS);
  };

  return { face, poke };
}

/**
 * One beat, drawn as far as it has been typed.
 *
 * The untyped tail is rendered transparent rather than left out, so the line
 * wraps once and stays wrapped — see `useTypewriter` for why that matters in a
 * box of fixed height. It is still in the accessibility tree, which is the
 * behavior worth having: a screen reader announces the sentence, not a
 * sentence being spelled.
 */
function BeatLine({ segments, shown }: { segments: BeatSegment[]; shown: number }) {
  let start = 0;

  return (
    <>
      {segments.map((segment, index) => {
        const visible = Math.max(0, Math.min(segment.text.length, shown - start));
        start += segment.text.length;
        const tail = segment.text.slice(visible);
        const body = (
          <>
            {segment.text.slice(0, visible)}
            {tail ? <span className="opacity-0">{tail}</span> : null}
          </>
        );

        return segment.strong ? (
          <strong className="font-semibold" key={index}>
            {body}
          </strong>
        ) : (
          <span key={index}>{body}</span>
        );
      })}
    </>
  );
}

export interface DialogueSurfaceProps {
  placement: DialoguePlacement;
  /**
   * FR-011e — deliver this step as a chat line rather than as a scene.
   *
   * The step's own declaration, passed straight through. Nothing here decides
   * it: which form suits a step depends on what the step is asking the reader
   * to look at, and that is the author's to know.
   */
  compact: boolean;
  /**
   * The box the group is laid out in — the canvas, in viewport coordinates.
   *
   * Positioned rather than parented: the canvas is React Flow's, and mounting
   * into it would put a tutorial inside a surface that pans, zooms and
   * re-renders its own children. `fixed` at measured coordinates follows it
   * without joining it.
   */
  stage: HighlightRect;
  /**
   * Where the compact form goes: beside the lit target, in viewport
   * coordinates, or docked when the step points at nothing.
   *
   * Ignored by the full form, which stands on the canvas. The two forms answer
   * FR-089 differently and each needs its own geometry.
   */
  card: CardPlacement;
  mood: MioMood;
  speaker: string;
  /** The beat currently being delivered. Empty renders the panel with no line. */
  line: string;
  /** How many beats remain after this one. Drives the advance affordance. */
  remaining: number;
  /**
   * What a click on the panel does, or null when a click does nothing.
   *
   * Deliberately not named for beats. On any beat but the last it is the next
   * beat; on the last beat of a step with nothing to ask, it is the step's own
   * continue. The surface does not need to know which, and keeping it ignorant
   * is what lets one click carry the whole reading with no buttons at all.
   */
  onAdvance: (() => void) | null;
  /**
   * The step's controls, or null when the step asks the reader for nothing.
   *
   * Null is the ordinary case and not an absence of function: it means the
   * panel itself is the control, and the hint below says so.
   */
  controls: React.ReactNode;
  /** The heading, which is also the way back into the catalogue. */
  heading: React.ReactNode;
  /** Shown instead of the line when the session or the last trigger failed. */
  problem?: string | null;
}

export function DialogueSurface({
  placement,
  compact,
  stage,
  card,
  mood,
  speaker,
  line,
  remaining,
  onAdvance,
  controls,
  heading,
  problem,
}: DialogueSurfaceProps) {
  const advanceable = onAdvance !== null;
  /*
   * The beat's emphasis is decided once per line, and the typewriter counts
   * in the characters the reader will actually see. A problem banner replaces
   * the line entirely, so there is nothing to type and nothing to wait for:
   * something has gone wrong and the reader should be reading about it now.
   */
  const segments = useMemo(() => beatSegments(line), [line]);
  /*
   * The beat's position rides along in the reset key, because the text alone
   * does not identify a beat: an author may write the same sentence twice in a
   * row, and keyed on the words the second one would arrive already typed. No
   * two beats of one step share a `remaining`.
   */
  const typed = useTypewriter(
    problem ? "" : `${remaining}\u0000${line}`,
    problem ? 0 : beatLength(segments),
  );
  const onRight = placement.side === "right";
  const { face, poke } = usePoke();
  // Her authored expression, unless she has just been poked.
  const shown = face ?? mood;
  /*
   * Her transparent side margin, in rendered pixels, so the gap the reader sees
   * is `PANEL_GAP` in every expression. The result is usually negative — the
   * band beside her is wider than the gap — which is a pull, not an overlap:
   * the pixels it pulls the panel across are empty ones.
   */
  const inset = Math.round((MIO_FACING_INSET[shown] * SPRITE_HEIGHT) / MIO_CANVAS.height);
  const offset = PANEL_GAP - inset;

  const panel = (
    <>
      <div className="flex items-center justify-between gap-3">
        <span
          className="rounded-md bg-ember px-2 py-0.5 text-[0.7rem] font-semibold tracking-wide text-white"
          data-testid="tutorial-dialogue-speaker"
        >
          {speaker}
        </span>
        {heading}
      </div>

      {/*
       * The line sits in a box of fixed height and scrolls inside it, so a long
       * beat costs a scroll rather than a panel that grows downward and shoves
       * the controls off the bottom of the canvas. Three lines is the height: it
       * holds every beat the six levels currently have without scrolling, and a
       * beat that needs more than three lines is one the author should have
       * split (`MAX_SAY_BEATS` is the same argument at the other end). The
       * compact form takes four, and needs them: its box is narrower, so the
       * same sentence wraps further, and the room that form saves is the
       * character it does not draw rather than the words it does.
       */}
      <div
        className={[
          compact ? "h-[6rem]" : "h-[4.5rem]",
          // `scrollbar-thin` for its transparent track: the browser default
          // paints a white gutter down the side of a panel that is not white.
          "shrink-0 overflow-y-auto scrollbar-thin text-[0.95rem] leading-6",
        ].join(" ")}
        data-testid="tutorial-dialogue-line"
      >
        {problem ? (
          <span className="text-red-700" data-testid="tutorial-dialogue-problem">
            {problem}
          </span>
        ) : (
          <BeatLine segments={segments} shown={typed.shown} />
        )}
      </div>

      <div className="flex h-6 shrink-0 items-center justify-between gap-3">
        {/*
         * The words on every beat a click would move, the chevron only while
         * there is more of this step behind it. The chevron alone was the
         * convention and not the instruction: a reader who had not met it did
         * not know a triangle meant "click anywhere", and mid-step is exactly
         * where they meet it first.
         *
         * Neither is a button. Pressing them is not how they are used — the
         * whole panel is the target — and marking them up as buttons would put
         * a second keyboard stop on the action the panel already carries.
         */}
        {/*
         * Both wait for the line to finish. The chevron is what says the beat
         * is over, and showing it beside a sentence still arriving would make
         * it mean nothing; the words beside it would be inviting a click that
         * only finishes the typing.
         */}
        <span className="flex items-center gap-1.5">
          {typed.done && remaining > 0 ? (
            <span
              aria-hidden="true"
              className="text-xs text-ink/35"
              data-testid="tutorial-dialogue-remaining"
            >
              ▼
            </span>
          ) : null}
          {typed.done && advanceable ? (
            <span className="text-xs italic text-ink/40" data-testid="tutorial-dialogue-hint">
              {ADVANCE_HINT}
            </span>
          ) : null}
        </span>
        {/*
         * The controls wait for the line, like the chevron and the prompt above.
         * A reader has not been told what a button does until the sentence that
         * says so has arrived, and one of them — the ending of FR-090b — closes
         * their project. Buttons that appear when the speaking stops is also the
         * convention the rest of this surface borrows.
         */}
        {typed.done && controls ? <div className="flex items-center gap-2">{controls}</div> : null}
      </div>
    </>
  );

  /*
   * The panel is the click target whenever a click would do something — with or
   * without controls in it. It could once afford to go inert while controls
   * were showing, because Continue was one of them; with Continue gone the
   * panel is the *only* way forward, and a step carrying a trigger would
   * otherwise have no way out at all. What keeps the two apart is `fromControl`
   * below: a press that landed on a button is that button's and nothing else's.
   */
  const clickable = advanceable || !typed.done;
  /*
   * One click, two meanings, in this order: finish the line, then move on.
   * A reader who clicks through at speed never waits, and never loses a
   * sentence to a click they made before it had arrived.
   */
  const advance = () => {
    if (!typed.done) {
      typed.reveal();
      return;
    }
    onAdvance?.();
  };
  /*
   * A click that landed on a control inside the panel belongs to that control,
   * not to the panel.
   *
   * The heading carries three of them — back, the catalogue link, and leave —
   * and every one of them sits inside the click target. Without this, pressing
   * back also advanced the reading, which on the last beat meant pressing back
   * moved the reader forward a whole step.
   */
  const fromControl = (target: EventTarget | null) =>
    target instanceof Element && target.closest("button, a, input, textarea, select") !== null;

  const panelProps = {
    ...(clickable
      ? {
          onClick: (event: React.MouseEvent) => {
            if (fromControl(event.target)) return;
            advance();
          },
          onKeyDown: (event: React.KeyboardEvent) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            if (fromControl(event.target)) return;
            event.preventDefault();
            advance();
          },
        }
      : {}),
    /*
     * The keyboard stop belongs to the step, not to the typing. A panel that
     * gained and lost `role="button"` as each line finished would move focus
     * out from under anyone tabbing through it.
     */
    ...(advanceable ? { role: "button" as const, tabIndex: 0 } : {}),
  };

  if (compact) {
    /*
     * Positioned against the window rather than the canvas, because what it is
     * pointing at need not be on the canvas at all — the palette entry it
     * follows lives in the left panel, the Restore button in the bottom one. A
     * docked card is anchored by its bottom edge and a placed one by its top,
     * so both cross and exactly one of them is a number.
     */
    return (
      <section
        aria-label="Tutorial dialogue"
        className="pointer-events-none fixed z-40"
        data-testid="tutorial-dialogue"
        data-tutorial-dialogue-side={placement.side}
        data-tutorial-dialogue-edge={placement.edge}
        data-tutorial-dialogue-anchor={card.side ?? "docked"}
        data-tutorial-dialogue-compact="true"
        style={{
          top: card.top ?? undefined,
          bottom: card.bottom ?? undefined,
          left: card.left,
          width: CARD_WIDTH,
        }}
      >
        <div
          className={[
            "pointer-events-auto flex items-start gap-3",
            "rounded-2xl border border-ink/10 bg-canvas px-3 py-2.5 text-ink",
            "shadow-[0_10px_36px_rgba(28,33,27,0.18)]",
            clickable ? "cursor-pointer" : "",
          ].join(" ")}
          {...panelProps}
        >
          <img
            alt=""
            aria-hidden="true"
            className="size-9 shrink-0 rounded-full bg-canvas ring-1 ring-ink/10"
            data-testid="tutorial-dialogue-avatar"
            data-mood="idle"
            src={MIO_COMPACT_AVATAR}
          />
          <div className="flex min-w-0 flex-1 flex-col gap-1.5">{panel}</div>
        </div>
      </section>
    );
  }

  return (
    <section
      aria-label="Tutorial dialogue"
      className="pointer-events-none fixed z-40"
      data-testid="tutorial-dialogue"
      data-tutorial-dialogue-side={placement.side}
      data-tutorial-dialogue-edge={placement.edge}
      style={{ top: stage.top, left: stage.left, width: stage.width, height: stage.height }}
    >
      {/*
       * Against the stage's floor with no gap, so the sprite's own crop line
       * lands on the boundary instead of hanging above it — she is a bust, and
       * a bust floating 24px above the floor reads as a sticker. That floor is
       * the top edge of the tab strip, so she stands on the tabs rather than
       * over them. The margin the group gives up is taken by the panel, so the
       * text keeps its clearance.
       */}
      <div
        className={[
          "absolute flex items-end",
          placement.edge === "bottom" ? "bottom-0" : "top-0",
          onRight ? "right-6 flex-row-reverse" : "left-6",
        ].join(" ")}
      >
        {/*
         * The sprite for the side she is standing on, so she faces her own
         * dialogue. Two baked sets rather than one flipped in CSS — see `mio.ts`
         * for why the mirror is a file.
         */}
        {/*
         * Poking her is the one thing here that is not about the tutorial. It
         * is also why she takes pointer events at all — see `usePoke` for what
         * that costs. Not a button: there is nothing to announce and nothing to
         * reach by keyboard, and a tab stop on a joke would be in the way of
         * every reader who cannot see it.
         */}
        <img
          alt=""
          aria-hidden="true"
          className="pointer-events-auto shrink-0 cursor-pointer select-none drop-shadow-[0_12px_28px_rgba(28,33,27,0.22)]"
          data-testid="tutorial-dialogue-sprite"
          data-mood={shown}
          data-side={placement.side}
          onClick={poke}
          src={face === "curious" ? MIO_POKE_CURIOUS : spriteFor(shown, placement.side)}
          style={{ height: SPRITE_HEIGHT }}
        />

        <div
          className={[
            "pointer-events-auto flex shrink-0 flex-col gap-1.5 rounded-2xl",
            "border border-ink/10 bg-canvas px-4 py-3 text-ink shadow-[0_10px_36px_rgba(28,33,27,0.18)]",
            clickable ? "cursor-pointer" : "",
            placement.edge === "bottom" ? "mb-6" : "mt-6",
          ].join(" ")}
          style={{
            width: PANEL_WIDTH,
            [onRight ? "marginRight" : "marginLeft"]: offset,
          }}
          {...panelProps}
        >
          {panel}
        </div>
      </div>
    </section>
  );
}
