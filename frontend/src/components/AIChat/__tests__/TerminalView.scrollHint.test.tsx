/**
 * Tests for the #1994 scrolled-up hint in TerminalView.
 *
 * Some CLIs intermittently fail to paint their bottom input box; pressing ↓
 * fixes it, but the user has no way to know that. This suite covers the hint
 * that surfaces the recovery — and, just as importantly, pins the fact that ↓
 * itself is NOT intercepted. xterm already scrolls to the bottom on user input
 * AND still delivers the key to the PTY, and that delivery is what repaints the
 * CLI; the upstream behaviour we rely on is pinned separately in
 * xtermScrollContract.test.ts against the real xterm build.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TerminalView } from "../TerminalView";
import {
  FakeFitAddon,
  FakeTerm,
  fireRender,
  fireScroll,
  installClipboard,
  installHarnessLifecycle,
  keyEvent,
  xtermState,
} from "./terminalViewHarness";

vi.mock("@xterm/xterm", () => ({ Terminal: FakeTerm }));
vi.mock("@xterm/addon-fit", () => ({ FitAddon: FakeFitAddon }));
vi.mock("@xterm/addon-search", () => ({ SearchAddon: class {} }));
vi.mock("@xterm/addon-web-links", () => ({ WebLinksAddon: class {} }));

installHarnessLifecycle();

// --- scrolled-up hint (#1994) ---------------------------------------------
// Some CLIs intermittently fail to paint their input box; pressing ↓ fixes
// it, but the user cannot know that. The hint surfaces the recovery. The ↓
// key itself is deliberately NOT intercepted — xterm already scrolls to the
// bottom on user input AND delivers the key to the PTY, and that delivery is
// what repaints the CLI. See __tests__/xtermScrollContract.test.ts.
describe("scrolled-up hint", () => {
  const HINT = "terminal-scroll-hint-t1";

  async function mountTerminal() {
    render(
      <TerminalView
        tabId="t1"
        projectDir="/p"
        provider="claude-code"
        dangerous={false}
        onExit={vi.fn()}
        onError={vi.fn()}
      />,
    );
    await waitFor(() => expect(xtermState.lastInstance).not.toBeNull());
    await waitFor(() => expect(xtermState.onRenderCbs.length).toBeGreaterThan(0));
    return xtermState.lastInstance!;
  }

  it("stays hidden while the viewport is at the bottom", async () => {
    const term = await mountTerminal();
    expect(screen.queryByTestId(HINT)).toBeNull();

    // Output arrives while the user is at the bottom: xterm keeps the
    // viewport pinned, so there is nothing to tell the user about.
    term.baseY = 40;
    term.viewportY = 40;
    fireRender();

    expect(screen.queryByTestId(HINT)).toBeNull();
  });

  it("appears when the user scrolls up into history", async () => {
    const term = await mountTerminal();
    term.scrollUp(30);
    fireScroll(0);

    await waitFor(() => expect(screen.getByTestId(HINT)).toBeInTheDocument());
    expect(screen.getByTestId(HINT)).toHaveTextContent("Press ↓ to jump to the latest output");
  });

  it("disappears once the viewport is back at the bottom", async () => {
    const term = await mountTerminal();
    term.scrollUp(30);
    fireScroll(0);
    await waitFor(() => expect(screen.getByTestId(HINT)).toBeInTheDocument());

    term.scrollToBottom();
    fireScroll(30);

    await waitFor(() => expect(screen.queryByTestId(HINT)).toBeNull());
  });

  it("appears when output arrives while the user is scrolled up", async () => {
    // baseY moves out from under a viewport that is standing still. No scroll
    // event fires for that, which is why the hook also listens to onRender.
    const term = await mountTerminal();
    term.viewportY = 0;
    term.baseY = 12;
    fireRender();

    await waitFor(() => expect(screen.getByTestId(HINT)).toBeInTheDocument());
  });

  it("never covers the terminal — the hint is not clickable", async () => {
    const term = await mountTerminal();
    term.scrollUp(30);
    fireScroll(0);
    await waitFor(() => expect(screen.getByTestId(HINT)).toBeInTheDocument());

    expect(screen.getByTestId(HINT).className).toContain("pointer-events-none");
  });

  it("passes ArrowDown through to xterm untouched", async () => {
    // THE load-bearing assertion for the decision not to claim ↓. If a future
    // edit starts swallowing it to "scroll to bottom", the key stops reaching
    // the PTY and the CLI never repaints — removing the very recovery the
    // hint advertises. Keep this passing.
    installClipboard({ writeText: vi.fn(), readText: vi.fn() });
    const term = await mountTerminal();
    term.scrollUp(30);
    fireScroll(0);
    await waitFor(() => expect(screen.getByTestId(HINT)).toBeInTheDocument());
    await waitFor(() => expect(xtermState.keyHandler).not.toBeNull());

    for (const modifiers of [
      { ctrlKey: false },
      { ctrlKey: true },
      { ctrlKey: false, shiftKey: true },
    ]) {
      const { ev, preventDefault } = keyEvent("ArrowDown", modifiers);
      expect(xtermState.keyHandler!(ev)).toBe(true);
      expect(preventDefault).not.toHaveBeenCalled();
    }
    // ArrowUp likewise — nothing in the scroll feature touches the arrows.
    const up = keyEvent("ArrowUp", { ctrlKey: false });
    expect(xtermState.keyHandler!(up.ev)).toBe(true);
    expect(up.preventDefault).not.toHaveBeenCalled();
  });

  it("stops tracking when the view unmounts", async () => {
    const { unmount } = render(
      <TerminalView
        tabId="t1"
        projectDir="/p"
        provider="claude-code"
        dangerous={false}
        onExit={vi.fn()}
        onError={vi.fn()}
      />,
    );
    await waitFor(() => expect(xtermState.onRenderCbs.length).toBeGreaterThan(0));

    unmount();

    // The hook's disposer ran, so nothing is left subscribed to the disposed
    // terminal (which would otherwise setState on an unmounted component).
    expect(xtermState.onRenderCbs.length).toBe(0);
  });
});
