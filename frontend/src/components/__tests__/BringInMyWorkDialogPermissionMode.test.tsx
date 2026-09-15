/**
 * #2379 (ADR-034 Addendum 1) — the shared permission picker inside Bring In My
 * Work: three buttons, Auto greyed out for a provider without an auto mode,
 * and Auto reaching the request in the backend's own spelling.
 */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../store";
import {
  CLAUDE,
  LAST_PAGE,
  provider,
  renderDialog,
  sessionResponse,
  settled,
  SOURCE,
  walkTo,
  type StartSession,
} from "./BringInMyWorkDialog.harness";

function chooseProvider(name: string): void {
  fireEvent.change(screen.getByTestId("setup-provider-select"), { target: { value: name } });
  expect(screen.getByTestId("setup-provider-select")).toHaveValue(name);
}

beforeEach(() => {
  useAppStore.setState({
    currentProject: {
      id: "p1",
      name: "Demo",
      description: "",
      path: "/projects/demo",
      workflow_count: 0,
      workflows: [],
      current_workflow_id: "main",
    },
    terminalTabs: [],
    activeTerminalTabId: null,
    activeBottomTab: "config",
    bottomPanelCollapsed: true,
  });
});

afterEach(cleanup);

describe("#2379 — Manual / Auto / Yolo/Bypass in Bring In My Work", () => {
  it("renders the same three buttons with no descriptive text", async () => {
    renderDialog([CLAUDE]);
    await settled();
    chooseProvider("claude-code");
    const group = screen.getByTestId("setup-permission-group");
    expect(group.textContent).toBe("Permission modeManualAutoYolo/Bypass");
    expect(screen.getByTestId("setup-permission-auto")).not.toBeDisabled();
  });

  it("starts with no permission mode chosen", async () => {
    renderDialog([CLAUDE]);
    await settled();
    chooseProvider("claude-code");
    const group = screen.getByRole("radiogroup", { name: "Permission mode" });
    expect(within(group).queryAllByRole("radio", { checked: true })).toEqual([]);
  });

  it("greys Auto out for a provider whose CLI has no auto mode", async () => {
    renderDialog([
      CLAUDE,
      provider({ name: "codex", label: "No Auto", supports_auto_mode: false }),
    ]);
    await settled();
    chooseProvider("codex");
    expect(screen.getByTestId("setup-permission-auto")).toBeDisabled();
    expect(screen.getByTestId("setup-permission-safe")).not.toBeDisabled();
    expect(screen.getByTestId("setup-permission-dangerous")).not.toBeDisabled();
  });

  it("falls back to Manual when switching to a provider without Auto", async () => {
    renderDialog([
      CLAUDE,
      provider({ name: "codex", label: "No Auto", supports_auto_mode: false }),
    ]);
    await settled();
    chooseProvider("claude-code");
    fireEvent.click(screen.getByTestId("setup-permission-auto"));
    expect(screen.getByTestId("setup-permission-auto")).toHaveAttribute("aria-checked", "true");

    chooseProvider("codex");
    expect(screen.getByTestId("setup-permission-safe")).toHaveAttribute("aria-checked", "true");
  });

  it("sends Auto to the backend in its own spelling", async () => {
    const startSession = vi.fn<StartSession>(async () =>
      sessionResponse({ provider: "claude-code", permission_mode: "auto" }),
    );
    renderDialog([CLAUDE], { startSession });
    await settled();

    walkTo(LAST_PAGE, {
      setup: () => {
        fireEvent.change(screen.getByTestId("work-import-source-input"), {
          target: { value: SOURCE },
        });
        chooseProvider("claude-code");
        fireEvent.click(screen.getByTestId("setup-permission-auto"));
      },
    });
    fireEvent.click(screen.getByTestId("work-import-start"));

    await waitFor(() => expect(startSession).toHaveBeenCalledTimes(1));
    expect(startSession.mock.calls[0][0]).toMatchObject({
      provider: "claude-code",
      permission_mode: "auto",
    });
  });
});
