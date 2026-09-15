/**
 * #2227 / #2381 — opening a collection item must survive a failed tutorial report.
 *
 * `CollectionViewer` reports `preview_item_opened` through a lazy
 * `import("../../store")` that nothing awaits. In CI that import was sometimes
 * still loading when the test environment was torn down; the module loader then
 * rejected it, and the unhandled rejection failed the whole `Frontend` job with
 * every test green (16 of the surveyed red Frontend runs).
 *
 * The load failure is reproduced here by making the store module throw while it
 * loads. The click must still open the item, and the rejection must be absorbed:
 * vitest fails the run on any unhandled rejection, so this file going red is the
 * regression signal.
 *
 * Its own file because the store mock replaces the module for every test in it.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { PreviewEnvelope } from "../../types/api";

vi.mock("../../store", () => {
  throw new Error("store module failed to load (simulated environment teardown)");
});

import { CollectionViewer } from "./coreViewers";

afterEach(cleanup);

const ENVELOPE = {
  session_id: "pv-collection",
  previewer_id: "core.collection.basic",
  target: { kind: "collection_ref", ref: "collection:images" },
  kind: "collection",
  payload: { count: 1, item_type: "Image", items: [{ data_ref: "img-0", type_name: "Image" }] },
  resources: [
    {
      resource_id: "item:0",
      kind: "child",
      params: { index: 0, item: { data_ref: "img-0", type_name: "Image" } },
    },
  ],
  metadata: { sampled: false, truncated: false, cached: false, derived: false, complete: true },
  diagnostics: [],
  error: null,
} as unknown as PreviewEnvelope;

it("opens the item and absorbs a store import that fails to load", async () => {
  const onOpenResource = vi.fn();
  render(<CollectionViewer envelope={ENVELOPE} onOpenResource={onOpenResource} />);

  fireEvent.click(screen.getByTestId("collection-item-0"));

  expect(onOpenResource).toHaveBeenCalledWith(ENVELOPE.resources[0]);
  // Let the lazy import settle inside this test, so a rejection it leaves
  // unhandled is attributed here rather than lost at teardown.
  await vi.dynamicImportSettled();
  await new Promise((resolve) => setTimeout(resolve, 0));
});
