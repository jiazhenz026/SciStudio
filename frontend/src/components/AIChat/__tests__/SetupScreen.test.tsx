/**
 * Tests for SetupScreen — radio interactions, disabled-Launch logic,
 * provider status hints from /api/ai/status.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import { SetupScreen, _resetSetupStatusCache } from "../SetupScreen";

import type { ProjectResponse } from "../../../types/api";

const fakeProject: ProjectResponse = {
  id: "proj",
  name: "Project",
  description: "",
  path: "/abs/path/to/project",
  current_workflow_id: null,
  workflows: [],
  workflow_count: 0,
};

function setProject(p: ProjectResponse | null) {
  useAppStore.setState({ currentProject: p });
}

function mockStatusOnce(payload: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => payload,
  });
  (global as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

beforeEach(() => {
  _resetSetupStatusCache();
  setProject(fakeProject);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SetupScreen", () => {
  it("renders provider and permission radios with the working dir", async () => {
    mockStatusOnce({
      providers: [
        { name: "claude-code", available: true, version: "2.1.0", logged_in: true },
        { name: "codex", available: true, version: "0.118.0", logged_in: true },
      ],
    });
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByTestId("setup-provider-claude-code")).not.toBeDisabled(),
    );
    expect(screen.getByTestId("setup-working-dir").textContent).toContain("/abs/path/to/project");
    expect(screen.getByTestId("setup-provider-claude-code")).toBeInTheDocument();
    expect(screen.getByTestId("setup-provider-codex")).toBeInTheDocument();
    expect(screen.getByTestId("setup-permission-safe")).toBeInTheDocument();
    expect(screen.getByTestId("setup-permission-dangerous")).toBeInTheDocument();
  });

  it("keeps Cancel and Launch outside the scrollable setup body", async () => {
    mockStatusOnce({
      providers: [
        { name: "claude-code", available: true, version: "2.1.0", logged_in: true },
        { name: "codex", available: true, version: "0.118.0", logged_in: true },
      ],
    });
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);

    const launch = await screen.findByTestId("setup-launch");
    const root = screen.getByTestId("setup-screen-t1");
    const scrollBody = screen.getByTestId("setup-scroll-body");
    const actions = screen.getByTestId("setup-actions");

    expect(root.className).toContain("overflow-hidden");
    expect(scrollBody.className).toContain("overflow-y-auto");
    expect(actions.className).toContain("shrink-0");
    expect(actions.className).not.toContain("bg-white");
    expect(scrollBody.contains(actions)).toBe(false);
    expect(actions.contains(screen.getByTestId("setup-cancel"))).toBe(true);
    expect(actions.contains(launch)).toBe(true);
  });

  it("disables the Launch button until provider AND permission are chosen", async () => {
    mockStatusOnce({
      providers: [
        { name: "claude-code", available: true, version: "2.1.0", logged_in: true },
        { name: "codex", available: true, version: "0.118.0", logged_in: true },
      ],
    });
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);
    const launch = await screen.findByTestId("setup-launch");
    expect(launch).toBeDisabled();
    act(() => fireEvent.click(screen.getByTestId("setup-provider-claude-code")));
    expect(launch).toBeDisabled();
    act(() => fireEvent.click(screen.getByTestId("setup-permission-safe")));
    await waitFor(() => expect(launch).not.toBeDisabled());
  });

  it("disables a provider when /api/ai/status says it's not installed", async () => {
    mockStatusOnce({
      providers: [
        { name: "claude-code", available: true, version: "2.1.0", logged_in: true },
        { name: "codex", available: false, version: null, logged_in: false },
      ],
    });
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);
    const codex = await screen.findByTestId("setup-provider-codex");
    expect(codex).toBeDisabled();
    expect(screen.getByTestId("setup-provider-codex-hint").textContent).toMatch(/not installed/i);
  });

  it("shows '(not logged in)' when the provider is available but unauthenticated", async () => {
    mockStatusOnce({
      providers: [
        {
          name: "claude-code",
          available: true,
          version: "2.1.0",
          logged_in: false,
        },
        { name: "codex", available: true, version: "0.118.0", logged_in: true },
      ],
    });
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);
    const hint = await screen.findByTestId("setup-provider-claude-code-hint");
    expect(hint.textContent).toMatch(/not logged in/i);
  });

  it("invokes onLaunch with the chosen provider + dangerous flag", async () => {
    mockStatusOnce({
      providers: [{ name: "claude-code", available: true, version: "2.1.0", logged_in: true }],
    });
    const onLaunch = vi.fn();
    render(<SetupScreen tabId="t1" onLaunch={onLaunch} onCancel={vi.fn()} />);
    await screen.findByTestId("setup-launch");
    act(() => fireEvent.click(screen.getByTestId("setup-provider-claude-code")));
    act(() => fireEvent.click(screen.getByTestId("setup-permission-dangerous")));
    act(() => fireEvent.click(screen.getByTestId("setup-launch")));
    expect(onLaunch).toHaveBeenCalledWith({
      provider: "claude-code",
      dangerous: true,
    });
  });

  it("invokes onCancel when Cancel is clicked", async () => {
    mockStatusOnce({ providers: [] });
    const onCancel = vi.fn();
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={onCancel} />);
    await screen.findByTestId("setup-cancel");
    act(() => fireEvent.click(screen.getByTestId("setup-cancel")));
    expect(onCancel).toHaveBeenCalled();
  });
});
