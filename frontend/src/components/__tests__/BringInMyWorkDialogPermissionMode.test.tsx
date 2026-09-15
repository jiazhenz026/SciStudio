/**
 * #2379 (ADR-034 Addendum 1) — the shared permission picker inside Bring In My
 * Work: three buttons, Auto greyed out for a provider without an auto mode,
 * and Auto reaching the request in the backend's own spelling.
 */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../store";
import {
  CLAUDE,
  LAST_PAGE,
  provider,
  ready,
  renderDialog,
  sessionResponse,
  settled,
  SOURCE,
  walkTo,
  type PageAnswers,
  type StartSession,
} from "./BringInMyWorkDialog.harness";

function walkToStart(answers: PageAnswers = {}): void {
  walkTo(LAST_PAGE, answers);
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
    renderDialog(ready(CLAUDE));
    await settled();
    const group = screen.getByTestId("setup-permission-group");
    expect(group.textContent).toBe("Permission modeManualAutoYolo/Bypass");
    expect(screen.getByTestId("setup-permission-auto")).not.toBeDisabled();
  });

  it("greys Auto out for a provider whose CLI has no auto mode", async () => {
    renderDialog(
      ready(provider({ key: "no-auto-agent", label: "No Auto", supports_auto_mode: false })),
    );
    await settled();
    expect(screen.getByTestId("setup-permission-auto")).toBeDisabled();
    expect(screen.getByTestId("setup-permission-safe")).toBeChecked();
  });

  it("sends Auto to the backend in its own spelling", async () => {
    const startSession = vi.fn<StartSession>(async () =>
      sessionResponse({ provider: "claude-code", permission_mode: "auto" }),
    );
    renderDialog(ready(CLAUDE), { startSession });
    await settled();

    walkToStart({
      setup: () => {
        fireEvent.change(screen.getByTestId("work-import-source-input"), {
          target: { value: SOURCE },
        });
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
