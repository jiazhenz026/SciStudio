/**
 * Skeleton tests for ADR-035 §3.10 engine-initiated tab open/close handlers.
 *
 * Implementation phase (I35c) flips each `it.skip` to `it` once the
 * handler dispatches to a real Zustand action and the AI-Block tab
 * source is wired through `terminalTabsSlice`.
 */
import { describe, expect, it } from "vitest";

import { AiBlockStatusBadge, MarkDoneButton } from "../TerminalTab";
import { handleBlockPtyClosed, handleBlockPtyOpened } from "../TerminalTabs";

describe("ADR-035 §3.10 — engine-initiated PTY tab events (skeleton)", () => {
  it("exports handleBlockPtyOpened as a function", () => {
    expect(typeof handleBlockPtyOpened).toBe("function");
  });

  it("exports handleBlockPtyClosed as a function", () => {
    expect(typeof handleBlockPtyClosed).toBe("function");
  });
});

describe("ADR-035 §3.5 / §3.9 — AI-Block tab UI elements (skeleton)", () => {
  it("AiBlockStatusBadge component exports", () => {
    expect(typeof AiBlockStatusBadge).toBe("function");
  });

  it("MarkDoneButton component exports", () => {
    expect(typeof MarkDoneButton).toBe("function");
  });
});
