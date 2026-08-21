/**
 * ADR-053 Learning Center — the reading window's card model (#2084).
 *
 * The grid is derived, never judged: these tests pin the derivation — slot
 * states, the lenient `pages` read (the field arrives with the #2061
 * vocabulary batch and is read structurally until the widened type lands),
 * and the catalogue-entry lookup the window's visibility hangs on.
 */

import { describe, expect, it } from "vitest";

import type {
  TutorialCatalogueResponse,
  TutorialSessionResponse,
  TutorialStepOutline,
  TutorialStepView,
} from "../../../lib/api/learningCenter";
import { findSessionEntry, readingSlots, stepPages, type ReadingCardInfo } from "../readingCards";

function stepView(over: Partial<TutorialStepView> & { pages?: string[] } = {}): TutorialStepView {
  return {
    id: "workflow-card",
    index: 0,
    total: 8,
    title: "Workflow",
    say: "The graph you build.",
    highlight: null,
    route_to: null,
    prefill: [],
    awaiting_continue: false,
    satisfied: false,
    ...over,
  } as TutorialStepView;
}

function session(
  step: TutorialStepView | null,
  steps?: TutorialStepOutline[],
): TutorialSessionResponse {
  return {
    source_kind: "core",
    source_id: "",
    tutorial_id: "scistudio-at-a-glance",
    title: "SciStudio at a Glance",
    project_id: null,
    project_path: null,
    step,
    satisfied_step_ids: [],
    status: "active",
    error: null,
    replay: null,
    ...(steps === undefined ? {} : { steps }),
  };
}

const CARD_TITLES = [
  "Workflow",
  "Block",
  "Data type",
  "Previewer",
  "Plot card",
  "History",
  "My library",
  "Others",
];

function outline(): TutorialStepOutline[] {
  return CARD_TITLES.map((title, index) => ({
    index,
    id: `${title.toLowerCase().replace(/ /g, "-")}-card`,
    title,
    say: `${title} in one line.`,
    pages: [`${title.toLowerCase().replace(/ /g, "-")}-page`],
  }));
}

describe("stepPages", () => {
  it("reads the pages field the #2061 batch adds", () => {
    expect(stepPages(stepView({ pages: ["a", "b"] }))).toEqual(["a", "b"]);
  });

  it("answers an empty list before the field exists", () => {
    expect(stepPages(stepView())).toEqual([]);
  });

  it("drops non-string entries rather than passing them to a URL", () => {
    const step = stepView();
    (step as unknown as { pages: unknown }).pages = ["a", 7, "", null, "b"];
    expect(stepPages(step)).toEqual(["a", "b"]);
  });
});

describe("readingSlots with the session's step outline", () => {
  it("names every card up front, in step order", () => {
    const slots = readingSlots(session(stepView({ index: 0 }), outline()), new Map());
    expect(slots.map((slot) => slot.card?.title)).toEqual(CARD_TITLES);
    expect(slots.map((slot) => slot.state)).toEqual([
      "current",
      "unread",
      "unread",
      "unread",
      "unread",
      "unread",
      "unread",
      "unread",
    ]);
    expect(slots[3].card?.say).toBe("Previewer in one line.");
    expect(slots[7].card?.pages).toEqual(["others-page"]);
  });

  it("renders the current slot from the live step, not the outline", () => {
    const slots = readingSlots(
      session(stepView({ index: 2, title: "Fresh title", pages: ["fresh"] }), outline()),
      new Map(),
    );
    expect(slots[2]).toMatchObject({
      state: "current",
      card: { title: "Fresh title", pages: ["fresh"] },
    });
    expect(slots.map((slot) => slot.state).slice(0, 4)).toEqual([
      "read",
      "read",
      "current",
      "unread",
    ]);
  });
});

describe("readingSlots without an outline (older fixtures)", () => {
  it("builds one slot per step: passed read, this one current, the rest unread", () => {
    const slots = readingSlots(session(stepView({ index: 2, pages: ["p1"] })), new Map());
    expect(slots).toHaveLength(8);
    expect(slots.map((slot) => slot.state)).toEqual([
      "read",
      "read",
      "current",
      "unread",
      "unread",
      "unread",
      "unread",
      "unread",
    ]);
  });

  it("renders the current slot from the live step, never from memory", () => {
    const remembered = new Map<number, ReadingCardInfo>([
      [0, { id: "stale", title: "Stale", say: null, pages: [] }],
    ]);
    const slots = readingSlots(session(stepView({ index: 0, title: "Fresh" })), remembered);
    expect(slots[0].card?.title).toBe("Fresh");
  });

  it("fills a passed slot from memory so the card keeps its name", () => {
    const remembered = new Map<number, ReadingCardInfo>([
      [0, { id: "workflow-card", title: "Workflow", say: "The graph.", pages: ["p1"] }],
    ]);
    const slots = readingSlots(
      session(stepView({ id: "block-card", index: 1, title: "Block" })),
      remembered,
    );
    expect(slots[0]).toMatchObject({ state: "read", card: { title: "Workflow" } });
  });

  it("leaves an unseen passed slot a placeholder rather than inventing a card", () => {
    const slots = readingSlots(session(stepView({ index: 3 })), new Map());
    expect(slots[1]).toEqual({ index: 1, state: "read", card: null });
  });

  it("answers nothing for a session without a step", () => {
    expect(readingSlots(session(null), new Map())).toEqual([]);
  });
});

describe("findSessionEntry", () => {
  const entry = {
    source_kind: "core" as const,
    source_id: "",
    id: "scistudio-at-a-glance",
    title: "SciStudio at a Glance",
    summary: "One sentence.",
    cover_url: null,
    order: 5,
    state: "in_progress" as const,
    unavailable_reason: null,
    project_directory: null,
    reading: true,
  };
  const catalogue: TutorialCatalogueResponse = {
    groups: [
      {
        source_kind: "core",
        source_id: "",
        label: "Core",
        completed: 0,
        total: 1,
        tutorials: [entry],
      },
    ],
    active: null,
    diagnostics: [],
  };

  it("finds the session's own entry by its triple", () => {
    expect(findSessionEntry(catalogue, session(stepView()))).toBe(entry);
  });

  it("answers null for a session the catalogue does not list", () => {
    const other = { ...session(stepView()), tutorial_id: "someone-else" };
    expect(findSessionEntry(catalogue, other)).toBeNull();
  });

  it("answers null while the catalogue has not arrived", () => {
    expect(findSessionEntry(null, session(stepView()))).toBeNull();
  });
});
