/*
 * Core tutorial 2's Review Labels panel, actually mounted.
 *
 * `tests/tutorials/test_core_tutorial_what_is_a_type.py` already holds this
 * file to the ADR-051 contract, but it does so by reading the source: it can
 * see that `export default` and `mount(container, host)` are present and
 * cannot see whether calling them works. A panel that threw on mount passed
 * every one of those assertions and reached a reader as "Couldn't load this
 * interactive panel: panel mount() threw: suspects is not iterable".
 *
 * So this mounts the shipped module against a payload shaped like the one the
 * block builds — two slides, cells plus one speck — and drives the batch the
 * way a reader does. It imports the asset directly rather than a copy, because
 * a copy is the one thing that cannot catch a change to the original.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

/*
 * The shipped panel, from the tutorial's assets — not a fixture of it.
 *
 * TODO(#2229): this asset is still written in the ADR-051 interactive-panel
 *   *module* form, and ADR-054 T-007 deleted the loader that mounted it. A-009
 *   says no shim is provided for that form because "its only consumers are in
 *   this repository", and this asset is the consumer it means: it must become
 *   a panel directory under the new contract. That lives in
 *   `src/scistudio/tutorials/**`, outside this change's scope, so the two
 *   ex-loader types are declared here to keep this coverage of a *shipped*
 *   tutorial panel running rather than deleting it.
 *   Followup: https://github.com/jiazhenz026/SciStudio/issues/2229
 */
interface PanelHostApi {
  apiVersion: string;
  blockId: string;
  panelPayload: Record<string, unknown>;
  confirm: (response: Record<string, unknown>) => void;
  cancel: () => void;
}

interface PanelInstance {
  unmount(): void;
  update?(payload: Record<string, unknown>): void;
}

const panel = (await import(
  // @ts-expect-error -- a .mjs asset outside src/ ships no declaration file
  "../../../../../src/scistudio/tutorials/core/what-is-a-type/assets/panels/review_labels/panel.mjs"
)) as {
  default: { apiVersion: string; mount(container: HTMLElement, host: PanelHostApi): PanelInstance };
};
const reviewPanel = panel.default;

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

function hostFor(payload: Record<string, unknown>) {
  const confirmed: Array<Record<string, unknown>> = [];
  return {
    host: {
      apiVersion: "1",
      blockId: "review-1",
      panelPayload: payload,
      confirm: (response: Record<string, unknown>) => confirmed.push(response),
      cancel: vi.fn(),
    },
    confirmed,
  };
}

/** The panel's primary button — the one that ends or advances the review. */
function primaryButton(container: HTMLElement): HTMLButtonElement {
  const found = [...container.querySelectorAll("button")].find((button) =>
    (button.textContent ?? "").startsWith("Continue"),
  );
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

describe("core tutorial 2 — Review Labels panel", () => {
  it("mounts against a two-slide batch", () => {
    const container = document.createElement("div");
    const { host } = hostFor({ slides: [slide([1, 2], [3]), slide([1, 2], [])] });

    const instance = reviewPanel.mount(container, host);

    expect(container.querySelector("canvas")).not.toBeNull();
    expect(typeof instance.unmount).toBe("function");
    instance.unmount();
  });

  it("walks every unseen slide before it ends the review", () => {
    // Ending on the first click is the outcome this panel exists to prevent:
    // the reader would confirm a batch with a slide they never looked at.
    const container = document.createElement("div");
    const { host, confirmed } = hostFor({ slides: [slide([1, 2], [3]), slide([1, 2], [])] });
    reviewPanel.mount(container, host);

    expect(primaryButton(container).textContent).toBe("Continue (1 image left)");

    primaryButton(container).click();
    expect(confirmed).toHaveLength(0);
    expect(primaryButton(container).textContent).toBe("Continue (keep all)");

    primaryButton(container).click();
    expect(confirmed).toEqual([{ removed: [[], []] }]);
  });

  it("confirms immediately when the batch is one slide", () => {
    const container = document.createElement("div");
    const { host, confirmed } = hostFor({ slides: [slide([1, 2], [3])] });
    reviewPanel.mount(container, host);

    expect(primaryButton(container).textContent).toBe("Continue (keep all)");
    primaryButton(container).click();

    expect(confirmed).toEqual([{ removed: [[]] }]);
  });

  it("sends the labels the reader struck out, per slide", () => {
    const container = document.createElement("div");
    const { host, confirmed } = hostFor({ slides: [slide([1, 2], [3]), slide([1, 2], [])] });
    reviewPanel.mount(container, host);

    // The label list carries one row per label; clicking a row marks it.
    const speckRow = [...container.querySelectorAll("div")].find((row) =>
      (row.textContent ?? "").startsWith("label 3"),
    );
    expect(speckRow, "the speck must be listed for the reader to click").toBeTruthy();
    (speckRow as HTMLElement).click();

    expect(primaryButton(container).textContent).toBe("Continue (1 image left)");
    primaryButton(container).click();
    primaryButton(container).click();

    expect(confirmed).toEqual([{ removed: [[3], []] }]);
  });

  it("accepts a single-slide payload written without the slides wrapper", () => {
    // The shape a hand-written payload takes, which the module documents as
    // supported — a block reviewing one image is an ordinary case.
    const container = document.createElement("div");
    const { host, confirmed } = hostFor(slide([1, 2], [3]));
    reviewPanel.mount(container, host);

    primaryButton(container).click();
    expect(confirmed).toEqual([{ removed: [[]] }]);
  });
});
