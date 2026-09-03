// ADR-053 FR-020 — what the app does with each promotion outcome.
//
// `runPromotion` is the only call into the action, so the decision "which
// outcomes get an inline confirmation" lives here and nowhere else. An
// external review of PR #2036 found the one outcome that decision got wrong: a
// cancel taken *after* the cascade had written dependency files was reported
// as `cancelled` and therefore silently, while My Library had changed.

import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as DialogChannel from "../dialogChannel";
import { promotableBlock, type PromotableItem } from "../promotable";
import type * as PromoteModule from "../promoteToUserLibrary";
import type { PromotionOutcome } from "../promoteToUserLibrary";
import type * as RevealModule from "../revealInLibrary";
import { makeBlock } from "./fixtures";

const promote = vi.fn();
vi.mock("../promoteToUserLibrary", async (importOriginal) => {
  const actual = await importOriginal<typeof PromoteModule>();
  return { ...actual, promoteToUserLibrary: () => promote() };
});

vi.mock("../promotionIo", () => ({ createPromotionIo: () => ({}) }));

const showPromotionResult = vi.fn();
vi.mock("../dialogChannel", async (importOriginal) => {
  const actual = await importOriginal<typeof DialogChannel>();
  return {
    ...actual,
    showPromotionResult: (outcome: PromotionOutcome) => showPromotionResult(outcome),
  };
});

const revealInLibrary = vi.fn();
vi.mock("../revealInLibrary", async (importOriginal) => {
  const actual = await importOriginal<typeof RevealModule>();
  return { ...actual, revealInLibrary: (...args: unknown[]) => revealInLibrary(...args) };
});

const item: PromotableItem = promotableBlock(
  makeBlock({ type_name: "normalize", name: "Normalize", origin: "project" }),
)!;

function outcome(status: PromotionOutcome["status"]): PromotionOutcome {
  return {
    status,
    item,
    promoted: null,
    promotedDependencies: [],
    declinedDependencies: [],
    secondLevel: [],
    warnings: [],
  };
}

beforeEach(() => {
  promote.mockReset();
  showPromotionResult.mockReset();
  revealInLibrary.mockReset();
});

describe("runPromotion — which outcomes the user is told about", () => {
  it("says nothing about a cancellation the user made before anything was written", async () => {
    const { runPromotion } = await import("../runPromotion");
    promote.mockResolvedValue(outcome("cancelled"));

    await runPromotion(item);

    expect(showPromotionResult).not.toHaveBeenCalled();
  });

  it.each(["promoted", "partial", "failed"] as const)("reports a %s outcome", async (status) => {
    const { runPromotion } = await import("../runPromotion");
    promote.mockResolvedValue(outcome(status));

    await runPromotion(item);

    expect(showPromotionResult).toHaveBeenCalledTimes(1);
    expect(showPromotionResult.mock.calls[0][0].status).toBe(status);
  });

  it("reveals only a completed promotion", async () => {
    const { runPromotion } = await import("../runPromotion");
    promote.mockResolvedValue(outcome("partial"));

    await runPromotion(item);

    // The item is not in the library, so there is nothing to reveal — the
    // notice is what names the dependency files that stayed.
    expect(revealInLibrary).not.toHaveBeenCalled();
  });

  it("reveals a promoted block in its palette section", async () => {
    const { runPromotion } = await import("../runPromotion");
    promote.mockResolvedValue(outcome("promoted"));

    await runPromotion(item);

    expect(revealInLibrary).toHaveBeenCalledWith("blocks");
  });

  it("confirms a promoted panel without a reveal — it has no palette tab", async () => {
    // Learning Center #2086: panels have no left-panel section, and
    // switching to the Blocks tab would teach the wrong location. The inline
    // confirmation still runs.
    const { runPromotion } = await import("../runPromotion");
    const panelItem: PromotableItem = {
      target: "previewers",
      kind: "previewer",
      label: "image_viewer",
      origin: "project",
      source: { from: "projectFile", path: "previewers/image_viewer.py" },
    };
    promote.mockResolvedValue({ ...outcome("promoted"), item: panelItem });

    await runPromotion(panelItem);

    expect(revealInLibrary).not.toHaveBeenCalled();
    expect(showPromotionResult).toHaveBeenCalledTimes(1);
  });
});
