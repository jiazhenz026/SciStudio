/**
 * ADR-054 Phase D (#2354) — Convert to interactive block (FR-036).
 *
 * US8 acceptance 1: naming one `Mask` output starts an agent session for that
 * output. What the brief says — `prepare_prompt`, one decision, `run`, the
 * MiniApp directory — is the route's to compose and the backend suite's to
 * pin; what this dialog can get wrong is which outputs it asks the route for,
 * and whether it touches the MiniApp, which it must not.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentAvailabilityResponse } from "../lib/api/agentAvailability";
import { ApiError } from "../lib/api/core";
import { useAppStore } from "../store";
import { resetAppStore } from "../testUtils";

import { completeRows, ConvertToBlockDialog } from "./ConvertToBlockDialog";

const READY: AgentAvailabilityResponse = {
  state: "ready",
  providers: [
    {
      key: "claude-code",
      label: "Claude Code",
      state: "ready",
      cause: null,
      next_step: null,
      session_unsupported_reason: null,
    },
  ],
};

function renderDialog(options: { convert?: ReturnType<typeof vi.fn> } = {}) {
  const convert = options.convert ?? vi.fn(async () => ({ session_tab_id: "tab-9" }));
  const onStarted = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <ConvertToBlockDialog
      convert={convert as never}
      fetchAvailability={(async () => READY) as never}
      onOpenChange={onOpenChange}
      onStarted={onStarted}
      open
      panelId="threshold"
      panelName="Threshold explorer"
    />,
  );
  return { convert, onStarted, onOpenChange };
}

async function settled(): Promise<void> {
  await waitFor(() => expect(screen.queryByTestId("miniapp-convert-probing")).toBeNull());
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({
    types: [{ name: "Mask" }, { name: "Value" }] as never,
    typesLoaded: true,
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ConvertToBlockDialog (ADR-054 FR-036)", () => {
  it("closes from the icon-only header button without submitting", async () => {
    const harness = renderDialog();
    await settled();

    const close = screen.getByRole("button", { name: "Close" });
    expect(close.textContent).toBe("");
    fireEvent.click(close);

    expect(harness.onOpenChange).toHaveBeenCalledWith(false);
    expect(harness.convert).not.toHaveBeenCalled();
  });

  it("starts a session naming the one output the user asked for", async () => {
    // US8 acceptance 1, verbatim.
    const harness = renderDialog();
    await settled();

    fireEvent.change(screen.getByTestId("miniapp-convert-name-0"), {
      target: { value: "mask" },
    });
    fireEvent.change(screen.getByTestId("miniapp-convert-type-0"), {
      target: { value: "Mask" },
    });
    fireEvent.click(screen.getByTestId("miniapp-convert-submit"));

    await waitFor(() => expect(harness.convert).toHaveBeenCalledTimes(1));
    expect(harness.convert).toHaveBeenCalledWith("threshold", {
      outputs: [{ name: "mask", type: "Mask", port: "mask" }],
      note: null,
      provider: "claude-code",
      permission_mode: "safe",
    });
    expect(harness.onStarted).toHaveBeenCalledWith("tab-9");
    expect(useAppStore.getState().terminalTabs.some((tab) => tab.id === "tab-9")).toBe(true);
    expect(useAppStore.getState().activeBottomTab).toBe("ai");
    expect(harness.onOpenChange).toHaveBeenCalledWith(false);
  });

  it("carries the optional note and several outputs", async () => {
    const harness = renderDialog();
    await settled();

    fireEvent.change(screen.getByTestId("miniapp-convert-name-0"), { target: { value: "mask" } });
    fireEvent.change(screen.getByTestId("miniapp-convert-type-0"), { target: { value: "Mask" } });
    fireEvent.click(screen.getByTestId("miniapp-convert-add-output"));
    fireEvent.change(screen.getByTestId("miniapp-convert-name-1"), {
      target: { value: "threshold" },
    });
    fireEvent.change(screen.getByTestId("miniapp-convert-type-1"), {
      target: { value: "Value" },
    });
    fireEvent.change(screen.getByTestId("miniapp-convert-note"), {
      target: { value: "Default to what the MiniApp last showed." },
    });
    fireEvent.click(screen.getByTestId("miniapp-convert-submit"));

    await waitFor(() => expect(harness.convert).toHaveBeenCalledTimes(1));
    expect(harness.convert.mock.calls[0][1]).toMatchObject({
      outputs: [
        { name: "mask", type: "Mask", port: "mask" },
        { name: "threshold", type: "Value", port: "threshold" },
      ],
      note: "Default to what the MiniApp last showed.",
    });
  });

  it("will not start a session with no output named", async () => {
    renderDialog();
    await settled();
    expect(screen.getByTestId("miniapp-convert-submit")).toBeDisabled();

    // A name with no type is not an output the agent can write.
    fireEvent.change(screen.getByTestId("miniapp-convert-name-0"), { target: { value: "mask" } });
    expect(screen.getByTestId("miniapp-convert-submit")).toBeDisabled();
  });

  it("shows what the route said when the session cannot start", async () => {
    const reason = "No agent provider can start a session right now.";
    const harness = renderDialog({
      convert: vi.fn(async () => {
        throw new ApiError(reason, 409);
      }),
    });
    await settled();
    fireEvent.change(screen.getByTestId("miniapp-convert-name-0"), { target: { value: "mask" } });
    fireEvent.change(screen.getByTestId("miniapp-convert-type-0"), { target: { value: "Mask" } });
    fireEvent.click(screen.getByTestId("miniapp-convert-submit"));

    await waitFor(() =>
      expect(screen.getByTestId("miniapp-convert-error")).toHaveTextContent(reason),
    );
    expect(harness.onStarted).not.toHaveBeenCalled();
  });

  it("shows the source and simplified fields while retaining shared agent controls", async () => {
    renderDialog();
    await settled();
    expect(screen.getByRole("heading", { name: "Convert to interactive block" })).toBeTruthy();
    const displayName = screen.getByText("Threshold explorer");
    expect(displayName.tagName).toBe("STRONG");
    expect(displayName.parentElement).toHaveTextContent(
      "Use Threshold explorer as an interactive step in your workflow. Choose which results it should send to the next blocks.",
    );
    expect(screen.getByText("Your MiniApp will remain available.")).toBeTruthy();
    expect(screen.getByTestId("miniapp-convert-submit")).toHaveTextContent(/^Convert$/);
    expect(screen.queryByTestId("miniapp-convert-port-0")).toBeNull();
    expect(screen.getByTestId("miniapp-convert-note")).toHaveAttribute(
      "placeholder",
      "Use the current threshold as the default.",
    );
    expect(screen.getByTestId("setup-provider-select")).toBeTruthy();
    expect(screen.getByTestId("setup-permission-safe")).toBeTruthy();
    expect(screen.getByTestId("setup-permission-dangerous")).toBeTruthy();
  });

  it("rejects duplicate output names and incomplete rows", async () => {
    const harness = renderDialog();
    await settled();
    fireEvent.change(screen.getByTestId("miniapp-convert-name-0"), { target: { value: "Mask" } });
    fireEvent.change(screen.getByTestId("miniapp-convert-type-0"), { target: { value: "Mask" } });
    fireEvent.click(screen.getByTestId("miniapp-convert-add-output"));
    expect(screen.getByTestId("miniapp-convert-submit")).toBeDisabled();
    fireEvent.change(screen.getByTestId("miniapp-convert-name-1"), { target: { value: "mask" } });
    fireEvent.change(screen.getByTestId("miniapp-convert-type-1"), { target: { value: "Mask" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Give each output a different name.");
    expect(screen.getByTestId("miniapp-convert-submit")).toBeDisabled();
    expect(harness.convert).not.toHaveBeenCalled();
  });

  it("generates legal unique ports for punctuation, digits and non-Latin names", () => {
    const names = ["Cell mask", "Cell-mask", "3D view", "图像"];
    expect(
      completeRows(
        names.map((name, index) => ({ id: String(index), name, type: "Mask", port: "" })),
      ).map((row) => row.port),
    ).toEqual(["cell_mask", "cell_mask_2", "output_3d_view", "output"]);
  });
});
