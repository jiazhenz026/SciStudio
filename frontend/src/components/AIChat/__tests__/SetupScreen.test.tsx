/**
 * Tests for SetupScreen — ADR-034 FR-021 status-driven provider select,
 * FR-021c/FR-021d zero-install notice, FR-021e/FR-021f permission relabel,
 * FR-021g/FR-021h pinned opaque action bar.
 *
 * These assertions exist because none of this fails loudly on its own: agent
 * provider keys are opaque strings (FR-020a), so a regression back to a
 * hardcoded two-provider picker would still typecheck.
 *
 * Honesty note on FR-021g: jsdom performs no layout, so nothing here proves the
 * action bar is actually on screen. `pins the action bar …` is a structural
 * regression guard only. The real proof is the Playwright check that owns the
 * host-chain half of T-011c.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import { SetupScreen, _resetSetupStatusCache } from "../SetupScreen";

import type { ProviderStatus } from "../SetupScreen.parts/types";
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

/**
 * A realistic payload: every supported agent in registry order, mixing all three
 * per-provider states (installed + logged in, installed + logged out, absent).
 */
const ALL_PROVIDERS: ProviderStatus[] = [
  { name: "claude-code", available: true, version: "2.1.0", logged_in: true, label: "Claude Code" },
  { name: "codex", available: false, version: null, logged_in: false, label: "Codex" },
  { name: "kimi-code", available: true, version: "0.33.0", logged_in: false, label: "Kimi Code" },
  { name: "qoder", available: false, version: null, logged_in: false, label: "Qoder" },
  { name: "qoder-cn", available: true, version: "1.4.2", logged_in: true, label: "Qoder (China)" },
];

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

/** Status request that never settles — the in-flight branch of FR-021d. */
function mockStatusPending() {
  const fetchMock = vi.fn().mockReturnValue(new Promise(() => {}));
  (global as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

/** Status request that fails — the errored branch of FR-021d. */
function mockStatusFailure() {
  const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) });
  (global as unknown as { fetch: typeof fetch }).fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

function selectProvider(name: string) {
  act(() => {
    fireEvent.change(screen.getByTestId("setup-provider-select"), { target: { value: name } });
  });
}

beforeEach(() => {
  _resetSetupStatusCache();
  setProject(fakeProject);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SetupScreen provider select (FR-021)", () => {
  it("renders one select listing every agent provider and no per-provider radio", async () => {
    mockStatusOnce({ providers: ALL_PROVIDERS });
    const { container } = render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);

    const select = await screen.findByTestId("setup-provider-select");
    expect(select.tagName).toBe("SELECT");
    expect(container.querySelectorAll("select")).toHaveLength(1);

    await waitFor(() =>
      expect(within(select).getAllByRole("option")).toHaveLength(ALL_PROVIDERS.length + 1),
    );
    for (const p of ALL_PROVIDERS) {
      expect(screen.getByTestId(`setup-provider-option-${p.name}`)).toBeInTheDocument();
    }

    // FR-021: the radio list is gone, not merely hidden.
    expect(container.querySelectorAll('input[type="radio"][name^="setup-provider"]')).toHaveLength(
      0,
    );
    expect(screen.queryByTestId("setup-provider-claude-code")).not.toBeInTheDocument();
    expect(screen.queryByTestId("setup-provider-codex")).not.toBeInTheDocument();

    expect(screen.getByTestId("setup-working-dir").textContent).toContain("/abs/path/to/project");
  });

  it("lists an uninstalled provider, disabled and annotated (FR-021a)", async () => {
    mockStatusOnce({ providers: ALL_PROVIDERS });
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);

    const codex = await screen.findByTestId("setup-provider-option-codex");
    expect(codex).toBeDisabled();
    expect(codex.textContent).toMatch(/not installed/i);
    expect(codex.textContent).toContain("Codex");
  });

  it("keeps an installed-but-logged-out provider selectable (FR-021a)", async () => {
    mockStatusOnce({ providers: ALL_PROVIDERS });
    const onLaunch = vi.fn();
    render(<SetupScreen tabId="t1" onLaunch={onLaunch} onCancel={vi.fn()} />);

    const kimi = await screen.findByTestId("setup-provider-option-kimi-code");
    expect(kimi).not.toBeDisabled();
    expect(kimi.textContent).toMatch(/not logged in/i);

    // The CLI runs its own login inside the PTY, so launching must be allowed.
    selectProvider("kimi-code");
    act(() => fireEvent.click(screen.getByTestId("setup-permission-safe")));
    await waitFor(() => expect(screen.getByTestId("setup-launch")).not.toBeDisabled());
  });

  it("orders every available provider above every unavailable one (FR-021b)", async () => {
    mockStatusOnce({ providers: ALL_PROVIDERS });
    const select = await (async () => {
      render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);
      return screen.findByTestId("setup-provider-select");
    })();

    await waitFor(() => expect(within(select).getAllByRole("option").length).toBeGreaterThan(1));
    const values = within(select)
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value)
      .filter((v) => v !== "");

    // Available first, registry order preserved inside each group.
    expect(values).toEqual(["claude-code", "kimi-code", "qoder-cn", "codex", "qoder"]);

    const firstUnavailable = values.indexOf("codex");
    const lastAvailable = values.indexOf("qoder-cn");
    expect(lastAvailable).toBeLessThan(firstUnavailable);
  });

  it("preselects nothing and keeps Launch disabled until a provider is chosen (FR-021i)", async () => {
    mockStatusOnce({ providers: ALL_PROVIDERS });
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);

    const select = (await screen.findByTestId("setup-provider-select")) as HTMLSelectElement;
    const placeholder = screen.getByTestId("setup-provider-placeholder") as HTMLOptionElement;

    expect(placeholder.textContent).toBe("Choose provider…");
    expect(placeholder).toBeDisabled();
    expect(select.value).toBe("");

    const launch = screen.getByTestId("setup-launch");
    expect(launch).toBeDisabled();

    // Permission alone is not enough.
    act(() => fireEvent.click(screen.getByTestId("setup-permission-safe")));
    expect(launch).toBeDisabled();

    // Provider + permission enables Launch.
    selectProvider("claude-code");
    await waitFor(() => expect(launch).not.toBeDisabled());
  });

  it("takes labels from the payload rather than a frontend map (FR-020b)", async () => {
    // A provider key this file has never heard of must render with its
    // backend-supplied label and be launchable, which is only possible if no
    // hand-maintained key or label list survives in the frontend.
    mockStatusOnce({
      providers: [
        {
          name: "future-agent",
          available: true,
          version: "9.9.9",
          logged_in: true,
          label: "Future Agent",
        },
      ],
    });
    const onLaunch = vi.fn();
    render(<SetupScreen tabId="t1" onLaunch={onLaunch} onCancel={vi.fn()} />);

    const option = await screen.findByTestId("setup-provider-option-future-agent");
    expect(option.textContent).toContain("Future Agent");

    selectProvider("future-agent");
    act(() => fireEvent.click(screen.getByTestId("setup-permission-safe")));
    act(() => fireEvent.click(screen.getByTestId("setup-launch")));
    expect(onLaunch).toHaveBeenCalledWith({ provider: "future-agent", dangerous: false });
  });

  it("invokes onLaunch with the chosen provider + dangerous flag (FR-021f)", async () => {
    mockStatusOnce({ providers: ALL_PROVIDERS });
    const onLaunch = vi.fn();
    render(<SetupScreen tabId="t1" onLaunch={onLaunch} onCancel={vi.fn()} />);
    await screen.findByTestId("setup-provider-select");

    selectProvider("qoder-cn");
    act(() => fireEvent.click(screen.getByTestId("setup-permission-dangerous")));
    act(() => fireEvent.click(screen.getByTestId("setup-launch")));

    expect(onLaunch).toHaveBeenCalledWith({ provider: "qoder-cn", dangerous: true });
  });

  it("invokes onCancel when Cancel is clicked", async () => {
    mockStatusOnce({ providers: ALL_PROVIDERS });
    const onCancel = vi.fn();
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={onCancel} />);
    await screen.findByTestId("setup-cancel");
    act(() => fireEvent.click(screen.getByTestId("setup-cancel")));
    expect(onCancel).toHaveBeenCalled();
  });

  it("shows the Codex trust-hooks note only when Codex is selected (#1859)", async () => {
    mockStatusOnce({
      providers: [
        ALL_PROVIDERS[0],
        { ...ALL_PROVIDERS[1], available: true, version: "0.118.0", logged_in: true },
      ],
    });
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);
    await screen.findByTestId("setup-provider-select");

    expect(screen.queryByTestId("setup-codex-trust-note")).not.toBeInTheDocument();

    selectProvider("claude-code");
    expect(screen.queryByTestId("setup-codex-trust-note")).not.toBeInTheDocument();

    selectProvider("codex");
    const note = screen.getByTestId("setup-codex-trust-note");
    expect(note.textContent).toMatch(/trust/i);
    expect(note.textContent).toMatch(/data\//);
  });
});

describe("SetupScreen zero-install notice (FR-021c / FR-021d)", () => {
  it("renders the notice only when status loaded and nothing is available", async () => {
    mockStatusOnce({ providers: ALL_PROVIDERS.map((p) => ({ ...p, available: false })) });
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);

    const notice = await screen.findByTestId("setup-no-providers-notice");
    // FR-021c: it replaces the picker rather than sitting beside a dead one.
    expect(screen.queryByTestId("setup-provider-select")).not.toBeInTheDocument();
    expect(notice.textContent).toMatch(/install/i);

    // Names every supported agent by product name, taken from the payload.
    const listed = within(screen.getByTestId("setup-no-providers-list"))
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    expect(listed).toEqual(["Claude Code", "Codex", "Kimi Code", "Qoder", "Qoder (China)"]);
    // Product names, not provider keys.
    expect(notice.textContent).not.toContain("claude-code");
    expect(notice.textContent).not.toContain("qoder-cn");
    // Deliberately no per-provider install commands.
    expect(notice.textContent).not.toMatch(/npm |pip |brew |curl |install -g/i);
  });

  it("does not render the notice while status is in flight (FR-021d)", async () => {
    mockStatusPending();
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);

    // Existing loading treatment stays: the picker, not the notice.
    expect(await screen.findByTestId("setup-provider-loading")).toBeInTheDocument();
    expect(screen.getByTestId("setup-provider-select")).toBeInTheDocument();
    expect(screen.queryByTestId("setup-no-providers-notice")).not.toBeInTheDocument();
    expect(screen.getByTestId("setup-launch")).toBeDisabled();
  });

  it("does not render the notice when the status request failed (FR-021d)", async () => {
    mockStatusFailure();
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);

    // Existing error treatment stays; unknown availability is not absence.
    expect(await screen.findByTestId("setup-status-error")).toBeInTheDocument();
    expect(screen.queryByTestId("setup-no-providers-notice")).not.toBeInTheDocument();
    expect(screen.getByTestId("setup-provider-select")).toBeInTheDocument();
    expect(screen.getByTestId("setup-launch")).toBeDisabled();
  });
});

describe("SetupScreen permission picker (FR-021e / FR-021f)", () => {
  it("uses the plain-language labels and leaks no CLI flag name", async () => {
    mockStatusOnce({ providers: ALL_PROVIDERS });
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);

    const group = await screen.findByTestId("setup-permission-group");
    expect(group.textContent).toContain("Manual Approve");
    expect(group.textContent).toContain("Bypass Permission");

    // FR-021e: a `--` substring is the cheapest proof no flag name survived,
    // and it blocks a future edit from reintroducing one.
    expect(group.textContent ?? "").not.toContain("--");
    expect(group.textContent ?? "").not.toMatch(/dangerously|skip-permissions|sandbox mode/i);

    // Plain-language caution stays on the bypass option.
    expect(group.textContent).toMatch(/sandbox/i);
  });

  it("keeps the stored safe / dangerous values unchanged (FR-021f)", async () => {
    mockStatusOnce({ providers: ALL_PROVIDERS });
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);

    const safe = (await screen.findByTestId("setup-permission-safe")) as HTMLInputElement;
    const dangerous = screen.getByTestId("setup-permission-dangerous") as HTMLInputElement;
    expect(safe.value).toBe("safe");
    expect(dangerous.value).toBe("dangerous");
  });
});

describe("SetupScreen action bar (FR-021g / FR-021h)", () => {
  it("pins the action bar outside the scrollable body on an opaque background", async () => {
    mockStatusOnce({ providers: ALL_PROVIDERS });
    render(<SetupScreen tabId="t1" onLaunch={vi.fn()} onCancel={vi.fn()} />);

    const launch = await screen.findByTestId("setup-launch");
    const root = screen.getByTestId("setup-screen-t1");
    const scrollBody = screen.getByTestId("setup-scroll-body");
    const actions = screen.getByTestId("setup-actions");

    expect(root.className).toContain("overflow-hidden");
    expect(scrollBody.className).toContain("overflow-y-auto");
    expect(actions.className).toContain("shrink-0");
    expect(scrollBody.contains(actions)).toBe(false);
    expect(actions.contains(screen.getByTestId("setup-cancel"))).toBe(true);
    expect(actions.contains(launch)).toBe(true);

    // FR-021g: sticky guard so the bar survives an ancestor scroll context.
    expect(actions.className).toContain("sticky");
    expect(actions.className).toContain("bottom-0");
    // FR-021h: content passes behind the bar, so the background MUST be opaque.
    // This replaces the pre-ADR-034 assertion that the bar had no `bg-white`,
    // which now contradicts the spec.
    expect(actions.className).toContain("bg-white");
    expect(actions.className).not.toMatch(/bg-white\/\d/);
  });
});
