/*
 * Core tutorial 2's Review Labels panel, actually run.
 *
 * `tests/tutorials/test_core_tutorial_what_is_a_type.py` holds the panel folder
 * to the ADR-054 interactive context by reading its source: it can see the SDK
 * script and `api.writeBack` are present and cannot see whether the page works.
 * A panel that threw on start passed every one of those assertions and reached
 * a reader as a blank window.
 *
 * So this loads the shipped page into the document, runs its script against a
 * stubbed panel SDK carrying a view shaped like the one the block builds — two
 * slides, cells plus one speck — and drives the batch the way a reader does. It
 * reads the asset directly rather than a copy, because a copy is the one thing
 * that cannot catch a change to the original.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const PAGE = resolve(
  process.cwd(),
  "../src/scistudio/tutorials/core/what-is-a-type/assets/panels/review_labels/index.html",
);

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

/** Load the page's markup and run its inline script against a stub SDK. */
async function runPage(input: Record<string, unknown>) {
  const confirmed: Array<Record<string, unknown>> = [];
  const api = {
    context: "interactive",
    input,
    ready: () => Promise.resolve(api),
    writeBack: vi.fn((value: Record<string, unknown>) => {
      confirmed.push(value);
      return Promise.resolve(null);
    }),
    cancel: vi.fn(() => Promise.resolve(null)),
    reportError: vi.fn(() => Promise.resolve(null)),
  };
  (window as unknown as { scistudio: unknown }).scistudio = api;

  const parsed = new DOMParser().parseFromString(readFileSync(PAGE, "utf8"), "text/html");
  const inline = [...parsed.querySelectorAll("script")].filter((script) => !script.src);
  expect(inline, "the page carries its logic in one inline script").toHaveLength(1);
  parsed.querySelectorAll("script").forEach((script) => script.remove());
  document.body.innerHTML = parsed.body.innerHTML;

  new Function(inline[0].textContent ?? "")();
  // `ready()` resolves on a microtask, and the page starts on the next one.
  await Promise.resolve();
  await Promise.resolve();
  return { api, confirmed };
}

/** The panel's primary button — the one that ends or advances the review. */
function primaryButton(): HTMLButtonElement {
  const found = document.getElementById("confirm");
  if (!found) throw new Error("the panel rendered no Continue button");
  return found as HTMLButtonElement;
}

beforeEach(() => {
  // jsdom ships no canvas backend, and the panel draws on every refresh. A
  // context that accepts every call is enough: what is asserted here is the
  // panel's behaviour, not its pixels.
  (HTMLCanvasElement.prototype as unknown as Record<string, unknown>).getContext = () =>
    new Proxy({}, { get: () => () => {} });
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("core tutorial 2 — Review Labels panel", () => {
  it("starts against a two-slide batch and leaves Cancel to the host", async () => {
    const { api } = await runPage({ slides: [slide([1, 2], [3]), slide([1, 2], [])] });

    expect(document.querySelector("canvas")).not.toBeNull();
    expect(api.reportError).not.toHaveBeenCalled();
    const labels = [...document.querySelectorAll("button")].map((button) => button.textContent);
    expect(labels).not.toContain("Cancel");
  });

  it("walks every unseen slide before it ends the review", async () => {
    // Ending on the first click is the outcome this panel exists to prevent:
    // the reader would confirm a batch with a slide they never looked at.
    const { confirmed } = await runPage({ slides: [slide([1, 2], [3]), slide([1, 2], [])] });

    expect(primaryButton().textContent).toBe("Continue (1 image left)");

    primaryButton().click();
    expect(confirmed).toHaveLength(0);
    expect(primaryButton().textContent).toBe("Continue (keep all)");

    primaryButton().click();
    expect(confirmed).toEqual([{ removed: [[], []] }]);
  });

  it("writes back immediately when the batch is one slide", async () => {
    const { confirmed } = await runPage({ slides: [slide([1, 2], [3])] });

    expect(primaryButton().textContent).toBe("Continue (keep all)");
    primaryButton().click();

    expect(confirmed).toEqual([{ removed: [[]] }]);
  });

  it("sends the labels the reader struck out, per slide", async () => {
    const { confirmed } = await runPage({ slides: [slide([1, 2], [3]), slide([1, 2], [])] });

    // The label list carries one row per label; clicking a row marks it.
    const speckRow = [...document.querySelectorAll(".review-row")].find((row) =>
      (row.textContent ?? "").startsWith("label 3"),
    );
    expect(speckRow, "the speck must be listed for the reader to click").toBeTruthy();
    (speckRow as HTMLElement).click();

    expect(primaryButton().textContent).toBe("Continue (1 image left)");
    primaryButton().click();
    primaryButton().click();

    expect(confirmed).toEqual([{ removed: [[3], []] }]);
  });

  it("accepts a single-slide view written without the slides wrapper", async () => {
    // The shape a hand-written view takes, which the page documents as
    // supported — a block reviewing one image is an ordinary case.
    const { confirmed } = await runPage(slide([1, 2], [3]));

    primaryButton().click();
    expect(confirmed).toEqual([{ removed: [[]] }]);
  });
});
