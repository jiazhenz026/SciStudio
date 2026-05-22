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

  it.skip("handle_block_pty_opened_creates_tab — I35c implements", () => {
    /*
     * Test plan:
     *   1. Reset store; spy on `addAiBlockTerminalTab` action.
     *   2. Call handleBlockPtyOpened({tab_id, title, block_run_id, permission_mode}).
     *   3. Expect addAiBlockTerminalTab called once with shaped payload.
     */
  });

  it.skip("handle_block_pty_opened_sets_active — I35c implements", () => {
    // After dispatch, active tab id === payload.tab_id.
  });

  it.skip("handle_block_pty_opened_skips_setup_screen — I35c implements", () => {
    // Tab.state should be "running" not "setup".
  });

  it.skip("handle_block_pty_closed_updates_status — I35c implements", () => {
    /*
     * Test plan:
     *   1. Pre-populate store with a tab from handleBlockPtyOpened.
     *   2. Call handleBlockPtyClosed({tab_id, result: "completed"}).
     *   3. Expect tab.aiBlockStatus === "done".
     */
  });

  it.skip("handle_block_pty_closed_keeps_tab_open — I35c implements", () => {
    // Per ADR-035 §3.9 — tab survives DONE/ERROR.
  });

  it.skip("handle_block_pty_closed_unknown_tab_id_is_noop — I35c implements", () => {
    // Should log warning, not throw.
  });
});

describe("ADR-035 §3.5 / §3.9 — AI-Block tab UI elements (skeleton)", () => {
  it("AiBlockStatusBadge component exports", () => {
    expect(typeof AiBlockStatusBadge).toBe("function");
  });

  it("MarkDoneButton component exports", () => {
    expect(typeof MarkDoneButton).toBe("function");
  });

  it.skip("AiBlockStatusBadge renders ✓ for done — I35c implements", () => {
    // Render with tab.aiBlockStatus="done"; expect ✓ glyph.
  });

  it.skip("AiBlockStatusBadge renders ✗ for error — I35c implements", () => {
    // Render with tab.aiBlockStatus="error"; expect ✗ glyph.
  });

  it.skip("AiBlockStatusBadge renders spinner for paused — I35c implements", () => {
    // Render with tab.aiBlockStatus="paused"; expect spinner.
  });

  it.skip("AiBlockStatusBadge returns null when source != ai-block — I35c implements", () => {
    // Render with tab.source="user-launched"; expect null.
  });

  it.skip("MarkDoneButton visible when ai-block paused — I35c implements", () => {
    // Render w/ source=ai-block + aiBlockStatus=paused; expect button.
  });

  it.skip("MarkDoneButton hidden when not ai-block tab — I35c implements", () => {
    // Render w/ source=user-launched; expect null.
  });

  it.skip("MarkDoneButton click calls mark_done API — I35c implements", () => {
    // Mock fetch; click; expect POST to /api/blocks/ai/<id>/mark_done.
  });
});
