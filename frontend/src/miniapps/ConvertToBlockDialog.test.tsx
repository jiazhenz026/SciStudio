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

import { ConvertToBlockDialog } from "./ConvertToBlockDialog";

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
    />,
  );
  return { convert, onStarted, onOpenChange };
}

async function settled(): Promise<void> {
  await waitFor(() => expect(screen.queryByTestId("miniapp-convert-probing")).toBeNull());
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ types: [], typesLoaded: true });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ConvertToBlockDialog (ADR-054 FR-036)", () => {
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
    fireEvent.change(screen.getByTestId("miniapp-convert-port-1"), {
      target: { value: "t" },
    });
    fireEvent.change(screen.getByTestId("miniapp-convert-note"), {
      target: { value: "Default to what the MiniApp last showed." },
    });
    fireEvent.click(screen.getByTestId("miniapp-convert-submit"));

    await waitFor(() => expect(harness.convert).toHaveBeenCalledTimes(1));
    expect(harness.convert.mock.calls[0][1]).toMatchObject({
      outputs: [
        { name: "mask", type: "Mask", port: "mask" },
        { name: "threshold", type: "Value", port: "t" },
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

  it("says the MiniApp is left alone", async () => {
    // FR-036 — "The MiniApp MUST be left unchanged". The dialog writes nothing
    // itself, and it tells the user that before they commit.
    renderDialog();
    await settled();
    expect(screen.getByTestId("miniapp-convert-dialog")).toHaveTextContent(
      /left exactly as it is/i,
    );
  });
});
