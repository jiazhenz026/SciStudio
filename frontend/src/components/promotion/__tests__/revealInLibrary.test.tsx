// ADR-053 FR-020 — a success confirms inline AND reveals the item in its new
// palette section. A silent success wastes the teaching moment the whole
// feature exists for, so both halves are asserted.

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as CodeApi from "../../../lib/api/code";
import { useAppStore } from "../../../store";
import { resetTypeCatalogLoader } from "../../../store/useTypeCatalog";
import { resetAppStore } from "../../../testUtils";
import { resetDialogChannel, showPromotionResult } from "../dialogChannel";
import { promotableBlock } from "../promotable";
import type { PromotionOutcome } from "../promoteToUserLibrary";
import { resetLibraryReveal, revealInLibrary, useLibraryReveal } from "../revealInLibrary";
import { UserLibraryDialogs } from "../UserLibraryDialogs";
import { makeBlock } from "./fixtures";

const listTypes = vi.fn();
vi.mock("../../../lib/api/code", async (importOriginal) => {
  const actual = await importOriginal<typeof CodeApi>();
  return { codeApi: { ...actual.codeApi, listTypes: () => listTypes() } };
});

function Probe() {
  const reveal = useLibraryReveal();
  return <span data-testid="reveal">{reveal ? `${reveal.surface}:${reveal.name}` : "none"}</span>;
}

beforeEach(() => {
  resetAppStore();
  resetLibraryReveal();
  resetDialogChannel();
  resetTypeCatalogLoader();
  listTypes.mockResolvedValue({ types: [] });
});

afterEach(() => {
  cleanup();
});

describe("revealInLibrary — FR-020", () => {
  it("expands the palette, refreshes the catalogue, and narrows to the block", () => {
    useAppStore.setState({ paletteCollapsed: true });
    const before = useAppStore.getState().blockCatalogRefreshCounter;

    render(<Probe />);
    act(() => revealInLibrary("blocks", "Normalize"));

    const state = useAppStore.getState();
    expect(state.paletteCollapsed).toBe(false);
    // Without the refresh the palette would not yet contain the promoted item.
    expect(state.blockCatalogRefreshCounter).toBe(before + 1);
    // Narrowing to the name is what makes `My Library` the only section
    // showing it — the reveal, not merely a hint that it happened.
    expect(state.paletteSearch).toBe("Normalize");
    expect(screen.getByTestId("reveal")).toHaveTextContent("blocks:Normalize");
  });

  it("re-fires for a repeat promotion of the same item", () => {
    render(<Probe />);
    const tokens: number[] = [];
    act(() => revealInLibrary("blocks", "Normalize"));
    tokens.push(1);
    act(() => revealInLibrary("blocks", "Normalize"));
    tokens.push(2);
    // A consumer comparing the value alone would ignore the second promotion;
    // the token is what makes the effect run again.
    expect(screen.getByTestId("reveal")).toHaveTextContent("blocks:Normalize");
    expect(tokens).toEqual([1, 2]);
  });

  it("reloads the type catalogue when a type was promoted", () => {
    render(<Probe />);
    act(() => revealInLibrary("types", "Spectrum"));
    expect(listTypes).toHaveBeenCalled();
    expect(screen.getByTestId("reveal")).toHaveTextContent("types:Spectrum");
  });
});

describe("the inline confirmation — FR-020 / FR-023 / FR-024", () => {
  const item = promotableBlock(makeBlock({ type_name: "n", name: "Normalize", origin: "project" }));

  function outcome(overrides: Partial<PromotionOutcome> = {}): PromotionOutcome {
    return {
      status: "promoted",
      item,
      promoted: {
        kind: "block",
        label: "Normalize",
        filename: "normalize.py",
        path: "/home/dev/.scistudio/blocks/normalize.py",
        overwritten: false,
      },
      promotedDependencies: [],
      declinedDependencies: [],
      secondLevel: [],
      warnings: [],
      ...overrides,
    };
  }

  it("names the item and the section it now lives in", () => {
    render(<UserLibraryDialogs />);
    act(() => showPromotionResult(outcome()));

    const notice = screen.getByTestId("promotion-result");
    expect(notice).toHaveTextContent("Saved to My Library");
    expect(notice).toHaveTextContent("Normalize");
    // Non-modal, so it cannot cover the palette section it just revealed.
    expect(notice).not.toHaveAttribute("aria-modal");
  });

  it("shows every warning verbatim and does not auto-dismiss them", () => {
    vi.useFakeTimers();
    render(<UserLibraryDialogs />);
    act(() =>
      showPromotionResult(
        outcome({ warnings: ["Trace is still project-local.", "It will fail to load elsewhere."] }),
      ),
    );
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(screen.getAllByTestId("promotion-result-warning")).toHaveLength(2);
    vi.useRealTimers();
  });

  it("reports a failure rather than staying silent", () => {
    render(<UserLibraryDialogs />);
    act(() => showPromotionResult(outcome({ status: "failed", promoted: null, error: "boom" })));
    expect(screen.getByTestId("promotion-result")).toHaveTextContent("boom");
  });
});
