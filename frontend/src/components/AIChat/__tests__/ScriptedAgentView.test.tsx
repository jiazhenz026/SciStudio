/**
 * ADR-053 FR-061a (#2083) — the agent window around the scripted session.
 *
 * What is proved here is the split: the header and the prompt box exist, the
 * question is typed into the box rather than into the terminal, and the
 * terminal receives it only once it has been sent. The pacing arithmetic
 * belongs to scriptedPacing.test.ts.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AGENT_MARK } from "../scriptedAgentBanner";
import { ScriptedAgentView } from "../ScriptedAgentView";
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

const ESC = String.fromCharCode(27);
const SEGMENT = `${ESC}[1m${ESC}[36m> What is SciStudio?${ESC}[0m\nA workflow runtime.\n`;

async function mount() {
  render(
    <ScriptedAgentView
      tabId="replay-tab"
      projectDir="/proj"
      provider="user-terminal"
      onExit={vi.fn()}
      onError={vi.fn()}
    />,
  );
  await waitFor(() => expect(xtermState.lastInstance).not.toBeNull());
  await waitFor(() => expect(FakeWebSocket.instances.length).toBeGreaterThan(0));
  const ws = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
  ws.open();
  // The banner is already in the buffer by now, so the conversation assertions
  // below measure from after it rather than trying to match around it.
  await waitFor(() => expect(written()).toContain("recorded session"));
  const bannerEnd = written().length;
  return { ws, conversation: () => written().slice(bannerEnd) };
}

const written = () => xtermState.written.join("");
const box = () => screen.getByTestId("scripted-agent-prompt-replay-tab").textContent ?? "";

describe("ScriptedAgentView (#2083)", () => {
  it("prints its name into the buffer, so the banner can scroll away", async () => {
    await mount();
    // Into the terminal rather than into chrome above it: that is what lets it
    // leave once the conversation is long enough to push it off.
    await waitFor(() => expect(written()).toContain("recorded session"));
    expect(written()).toContain(AGENT_MARK[0]);
  });

  it("keeps a prompt box on screen from the start", async () => {
    await mount();
    // The box is furniture: present before anything has been asked.
    expect(screen.getByTestId("scripted-agent-prompt-replay-tab")).toBeTruthy();
  });

  it("types the question into the box, not into the terminal", async () => {
    allowMotion();
    const { ws, conversation } = await mount();
    ws.message(JSON.stringify({ type: "stdout", data: SEGMENT }));

    await waitFor(() => expect(box()).toContain("What"));
    // The question is still being typed, so nothing has joined the banner yet.
    expect(conversation()).toBe("");
  });

  it("sends the question, then lets the reply arrive in the terminal", async () => {
    allowMotion();
    const { ws, conversation } = await mount();
    ws.message(JSON.stringify({ type: "stdout", data: SEGMENT }));

    // The whole exchange: the box empties and the terminal ends up holding the
    // recorded transcript, colour codes and all.
    await waitFor(() => expect(conversation()).toBe(SEGMENT), { timeout: 8000 });
    expect(box()).not.toContain("What is SciStudio?");
  });

  it("renders the transcript unpaced when the reader has asked for reduced motion", async () => {
    const { ws, conversation } = await mount();
    ws.message(JSON.stringify({ type: "stdout", data: SEGMENT }));
    expect(conversation()).toBe(SEGMENT);
  });
});
