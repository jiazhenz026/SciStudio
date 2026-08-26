/**
 * ADR-053 FR-061a (#2083) — TerminalView's `paced` wiring.
 *
 * The pacing arithmetic is proved in scriptedPacing.test.ts. What is proved
 * here is the part only the component can decide: which tab is paced at all,
 * that a live tab is never slowed down, and that a click finishes the line.
 *
 * `vitest.setup.ts` answers "reduce" to `prefers-reduced-motion`, so a paced
 * tab in the default test environment writes straight through — which is the
 * first assertion below, because it is what keeps every other terminal suite
 * reading finished output. The tests that need real pacing say so by replacing
 * `matchMedia` for their own duration.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TerminalView } from "../TerminalView";
import {
  FakeFitAddon,
  FakeTerm,
  FakeWebSocket,
  installHarnessLifecycle,
  xtermState,
} from "./terminalViewHarness";

vi.mock("@xterm/xterm", () => ({ Terminal: FakeTerm }));
vi.mock("@xterm/addon-fit", () => ({ FitAddon: FakeFitAddon }));
vi.mock("@xterm/addon-search", () => ({ SearchAddon: class {} }));
vi.mock("@xterm/addon-web-links", () => ({ WebLinksAddon: class {} }));

installHarnessLifecycle();

const REDUCED = window.matchMedia;

/** Answer "no preference", so the pacing is live for the rest of the test. */
function allowMotion(): void {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

afterEach(() => {
  window.matchMedia = REDUCED;
});

/** The banner + question that opens every replay transcript, coloured. */
const SEGMENT = `\x1b[1m\x1b[36m> What is SciStudio?\x1b[0m\nA workflow runtime.\n`;

async function mount(paced: boolean) {
  render(
    <TerminalView
      tabId="replay-tab"
      projectDir="/proj"
      provider="user-terminal"
      dangerous={false}
      onExit={vi.fn()}
      onError={vi.fn()}
      paced={paced}
    />,
  );
  await waitFor(() => expect(xtermState.lastInstance).not.toBeNull());
  await waitFor(() => expect(FakeWebSocket.instances.length).toBeGreaterThan(0));
  const ws = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
  ws.open();
  return ws;
}

const written = () => xtermState.written.join("");

describe("TerminalView paced output (#2083)", () => {
  it("writes straight through when the reader has asked for reduced motion", async () => {
    const ws = await mount(true);
    ws.message(JSON.stringify({ type: "stdout", data: SEGMENT }));
    expect(written()).toBe(SEGMENT);
  });

  it("does not pace a live agent's tab", async () => {
    allowMotion();
    const ws = await mount(false);
    ws.message(JSON.stringify({ type: "stdout", data: SEGMENT }));
    // A live process's output is the process talking now; delaying it would
    // misreport when things happened.
    expect(written()).toBe(SEGMENT);
  });

  it("holds back a scripted reply and reveals it over time", async () => {
    allowMotion();
    const ws = await mount(true);
    ws.message(JSON.stringify({ type: "stdout", data: SEGMENT }));

    expect(written().length).toBeLessThan(SEGMENT.length);
    await waitFor(() => expect(written()).toBe(SEGMENT), { timeout: 5000 });
  });

  it("finishes the scripted reply when the reader clicks the terminal", async () => {
    allowMotion();
    const ws = await mount(true);
    ws.message(JSON.stringify({ type: "stdout", data: SEGMENT }));
    expect(written().length).toBeLessThan(SEGMENT.length);

    fireEvent.mouseDown(screen.getByTestId("terminal-view-replay-tab"));
    expect(written()).toBe(SEGMENT);
  });
});
