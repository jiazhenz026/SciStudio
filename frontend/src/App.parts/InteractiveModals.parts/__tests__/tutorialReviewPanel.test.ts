/*
 * Core tutorial 2's Review Labels panel, actually mounted.
 *
 * `tests/tutorials/test_core_tutorial_what_is_a_type.py` already holds this
 * file to the panel contract, but it does so by reading the source: it can see
 * that the envelope, the token check and the `emit` are present and cannot see
 * whether running them works. A panel that threw on mount passed every one of
 * those assertions and reached a reader as "Couldn't load this interactive
 * panel: panel mount() threw: suspects is not iterable".
 *
 * So this runs the shipped document against a payload shaped like the one the
 * block builds — two slides, cells plus one speck — and drives the batch the
 * way a reader does. It reads the asset directly rather than a copy, because a
 * copy is the one thing that cannot catch a change to the original.
 *
 * ADR-054 spec 1 (#2229) rewrote what is driven here. The panel used to be an
 * ADR-051 ES module this file imported and called `mount(container, host)` on;
 * T-007 deleted the loader for that form and A-009 provides no shim, so the
 * asset is a panel directory now — `panel.json` plus a self-contained
 * `index.html`. What replaces the import is the frame handshake: the document's
 * own script is evaluated, handed an `init` envelope, and driven through the
 * DOM it renders. The two ex-loader types this file used to declare locally,
 * with a TODO(#2229) saying why, went with the form they described.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

const PANEL_MESSAGE_MARKER = 1;

/**
 * The shipped document, from the tutorial's assets — not a fixture of it.
 *
 * vitest runs with the frontend package as its working directory, so the
 * repository root is one level up.
 */
const DOCUMENT = readFileSync(
  join(
    process.cwd(),
    "..",
    "src/scistudio/tutorials/core/what-is-a-type/assets/panels/review_labels/index.html",
  ),
  "utf8",
);

/** Everything between `<body>` and the document's own `<script>`. */
const BODY_MARKUP = (/<body>([\s\S]*?)<script>/.exec(DOCUMENT) ?? [])[1] ?? "";
/** The document's script, which is the whole panel. */
const PANEL_SCRIPT = (/<script>([\s\S]*?)<\/script>/.exec(DOCUMENT) ?? [])[1] ?? "";

interface PanelMessage {
  readonly type: string;
  readonly payload: Record<string, unknown>;
}

interface PanelLabel {
  id: number;
  area: number;
}

function slide(cells: number[], specks: number[]) {
  const ids = [...cells, ...specks];
  return {
    grid: Array.from({ length: 8 }, (_, y) =>
      Array.from({ length: 8 }, (_, x) => ids[(y * 8 + x) % ids.length]),
    ),
    image: Array.from({ length: 8 }, () => Array.from({ length: 8 }, () => 120)),
    labels: [
      ...cells.map((id): PanelLabel => ({ id, area: 1500 })),
      ...specks.map((id): PanelLabel => ({ id, area: 40 })),
    ],
  };
}

/**
 * Evaluate the document's script, hand it `init`, and return what it sent.
 *
 * The frame's half of the D-011 handshake, done by hand: `window.parent` is a
 * recorder, and the panel's `message` listener is captured as it registers so
 * each test drives its own mount rather than every previously-evaluated copy.
 */
function mountPanel(
  payload: Record<string, unknown>,
  options: { capability?: string; restoredState?: unknown } = {},
) {
  const sent: PanelMessage[] = [];
  let listener: ((event: { data: unknown }) => void) | null = null;

  Object.defineProperty(window, "parent", {
    configurable: true,
    value: {
      postMessage: (message: { type: string; payload: Record<string, unknown> }) =>
        sent.push({ type: message.type, payload: message.payload }),
    },
  });

  document.body.innerHTML = BODY_MARKUP;

  const addEventListener = window.addEventListener.bind(window);
  window.addEventListener = ((type: string, handler: unknown) => {
    if (type === "message") listener = handler as (event: { data: unknown }) => void;
    else addEventListener(type, handler as EventListener);
  }) as typeof window.addEventListener;
  try {
    new Function(PANEL_SCRIPT)();
  } finally {
    window.addEventListener = addEventListener as typeof window.addEventListener;
  }
  if (listener === null) throw new Error("the panel document registered no message listener");
  const deliver = listener as (event: { data: unknown }) => void;

  const send = (type: string, messagePayload: Record<string, unknown>) =>
    deliver({
      data: {
        scistudio_panel: PANEL_MESSAGE_MARKER,
        token: "tok-1",
        type,
        payload: messagePayload,
      },
    });

  send("init", {
    api_version: "1",
    panel_id: "tutorial.review_labels",
    capability: options.capability ?? "producing",
    // What `InteractivePanelHost` actually passes: the block's window-sized
    // view, bound under `prompt` and repeated on `target`.
    target: payload,
    bindings: { prompt: { type: "interactive_prompt", snapshot: payload } },
    read_limits: { max_rows: 1000, max_bytes: 1_000_000 },
    asset_base_url: "/api/panels/assets/tutorial.review_labels/",
    restored_state: options.restoredState ?? null,
  });

  return { sent, send };
}

/** The code of the panel's most recent emission, or `null` if it has not emitted. */
function lastEmission(sent: PanelMessage[]): string | null {
  const emits = sent.filter((message) => message.type === "emit");
  if (emits.length === 0) return null;
  return String(emits[emits.length - 1].payload.code);
}

/** The strip button that walks to the next image. */
function nextButton(): HTMLButtonElement {
  const found = [...document.querySelectorAll("button")].find((button) =>
    (button.textContent ?? "").startsWith("Next image"),
  );
  if (!found) throw new Error("the panel rendered no next-image button");
  return found as HTMLButtonElement;
}

/** The strip button that walks back to the previous image. */
function previousButton(): HTMLButtonElement {
  const found = [...document.querySelectorAll("button")].find((button) =>
    (button.textContent ?? "").endsWith("Previous"),
  );
  if (!found) throw new Error("the panel rendered no previous-image button");
  return found as HTMLButtonElement;
}

function labelRow(id: number): HTMLElement {
  const found = document.querySelector(`[data-label-id="${id}"]`);
  if (!found) throw new Error(`the panel listed no row for label ${id}`);
  return found as HTMLElement;
}

beforeEach(() => {
  // jsdom ships no canvas backend, and the panel draws on every render. A
  // context that accepts every call is enough, and is better than the `null`
  // jsdom returns: what is wanted here is that the drawing code runs.
  (HTMLCanvasElement.prototype as unknown as Record<string, unknown>).getContext = () =>
    new Proxy({}, { get: () => () => {} });
});

describe("core tutorial 2 — Review Labels panel", () => {
  it("answers init with ready and renders the batch", () => {
    const { sent } = mountPanel({ slides: [slide([1, 2], [3]), slide([1, 2], [])] });

    expect(sent[0]).toEqual({ type: "ready", payload: { api_version: "1" } });
    expect(document.querySelector("canvas")).not.toBeNull();
    expect(document.querySelectorAll("[data-label-id]")).toHaveLength(3);
  });

  it("emits nothing while a slide has never been on screen", () => {
    // Ending the review on the first Confirm is the outcome this panel exists
    // to prevent: the reader would commit a batch with a slide they never
    // looked at. Confirm is host chrome now (D-018) and stays disabled until
    // the panel emits, so withholding the emission *is* the refusal.
    const { sent } = mountPanel({ slides: [slide([1, 2], [3]), slide([1, 2], [])] });

    expect(lastEmission(sent)).toBeNull();
    expect(document.body.textContent).toContain("Look at 1 more image before you confirm.");

    nextButton().click();

    expect(lastEmission(sent)).toBe("removed = [[], []]\nscistudio.output(removed=removed)");
    expect(document.body.textContent).toContain("Ready to confirm: keep all.");
  });

  it("emits on arrival when the batch is one slide", () => {
    const { sent } = mountPanel({ slides: [slide([1, 2], [3])] });

    expect(lastEmission(sent)).toBe("removed = [[]]\nscistudio.output(removed=removed)");
  });

  it("re-emits the whole decision, per slide, as the reader strikes labels out", () => {
    const { sent } = mountPanel({ slides: [slide([1, 2], [3]), slide([1, 2], [])] });

    // Struck out before the batch has been walked: still nothing to commit.
    labelRow(3).click();
    expect(lastEmission(sent)).toBeNull();

    nextButton().click();
    expect(lastEmission(sent)).toBe("removed = [[3], []]\nscistudio.output(removed=removed)");

    // D-018: every emission carries the whole decision, so the newest one is
    // simply the decision. Clicking the same row back off says so.
    previousButton().click();
    labelRow(3).click();
    expect(lastEmission(sent)).toBe("removed = [[], []]\nscistudio.output(removed=removed)");
  });

  it("accepts a single-slide payload written without the slides wrapper", () => {
    // The shape a hand-written payload takes, which the document supports — a
    // block reviewing one image is an ordinary case.
    const { sent } = mountPanel(slide([1, 2], [3]));

    expect(lastEmission(sent)).toBe("removed = [[]]\nscistudio.output(removed=removed)");
  });

  it("sends no emission from a displaying mount", () => {
    // FR-011 puts the enforcement in the host; the panel's own guard is honesty
    // about what this mount was granted, and it is worth having: a producing
    // document opened from the preview surface must not try to produce.
    const { sent } = mountPanel({ slides: [slide([1, 2], [3])] }, { capability: "displaying" });

    expect(sent.filter((message) => message.type === "emit")).toEqual([]);
    expect(sent[0].type).toBe("ready");
  });

  it("hands the host a state snapshot and takes one back", () => {
    const { sent, send } = mountPanel({ slides: [slide([1, 2], [3]), slide([1, 2], [])] });
    labelRow(3).click();
    nextButton().click();

    send("state_request", {});
    const state = sent[sent.length - 1];
    expect(state.type).toBe("state");
    expect((state.payload.state as { removed: number[][] }).removed).toEqual([[3], []]);

    const restored = mountPanel(
      { slides: [slide([1, 2], [3]), slide([1, 2], [])] },
      { restoredState: state.payload.state },
    );
    // Both slides came back seen, so the restored mount can commit at once.
    expect(lastEmission(restored.sent)).toBe(
      "removed = [[3], []]\nscistudio.output(removed=removed)",
    );
  });

  it("reports a mount it cannot draw rather than throwing", () => {
    const { sent } = mountPanel({});

    expect(sent[0].type).toBe("ready");
    expect(sent[1].type).toBe("error");
    expect(String(sent[1].payload.message)).toContain("without any label maps");
    expect(lastEmission(sent)).toBeNull();
  });
});
