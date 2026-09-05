/**
 * ADR-054 spec 1 D-018 — Confirm commits the panel's most recent emission.
 *
 * A producing panel's only outbound path is `emit` (FR-012), so it owns no
 * Confirm button: the host draws one, and pressing it sends the newest emission
 * back to the block. This suite drives that from the frame side with the real
 * message plumbing the preview host uses — a real `iframe`, its real
 * `contentWindow`, a real `emit` envelope carrying the host's own token — and
 * asserts the payload `onConfirm` receives.
 *
 * The payload shape is load-bearing across the wire. `{ code: <snippet> }` is
 * exactly what `settle_interactive_response` in
 * `src/scistudio/blocks/base/interactive.py` reads as an emission, and the
 * snippet used below is the one the shipped
 * `core.interactive.data_router` document emits. The Python side pins the same
 * string in `tests/blocks/test_interactive_emission.py`; if the two ever
 * disagree, a person presses Confirm and the block errors.
 *
 * The #2195 no-exit property is guarded by `InteractiveModals.test.tsx` and is
 * not re-asserted here.
 */

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RealFrameSeam } from "../../../panels/__tests__/support";
import { createRealFrameSeam, flush, receivedOfType } from "../../../panels/__tests__/support";
import type { PanelDescriptorResponse } from "../../../types/api";
import { InteractivePanelHost } from "../InteractivePanelHost";

afterEach(cleanup);

/** The descriptor the backend now puts on the `interactive_prompt` event. */
const DESCRIPTOR: PanelDescriptorResponse = {
  panel_id: "core.interactive.data_router",
  display_name: "core.interactive.data_router",
  api_version: "1",
  accepted_api_version: "1",
  capability: "producing",
  document_url: "/api/panels/assets/core.interactive.data_router/index.html",
  asset_base_url: "/api/panels/assets/core.interactive.data_router/",
  read_limits: { max_rows: 500, max_bytes: 1_000_000 },
};

/** Verbatim from `src/scistudio/panels/builtin/core.interactive.data_router`. */
const ROUTING_DECISION =
  'assignments = {"port_1": ["input_1:0"], "port_2": []}\n' +
  "scistudio.output(assignments=assignments)";

/** A second decision, to prove the newest emission is the one committed. */
const REVISED_DECISION =
  'assignments = {"port_1": [], "port_2": ["input_1:0"]}\n' +
  "scistudio.output(assignments=assignments)";

function tokenFrom(seam: RealFrameSeam): string {
  const init = receivedOfType(seam, "init")[0];
  expect(init).toBeDefined();
  return (init as unknown as { token: string }).token;
}

/** Mount the host and drive its frame through the handshake. */
async function mount(overrides: Partial<Parameters<typeof InteractivePanelHost>[0]> = {}) {
  const seam = createRealFrameSeam();
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <InteractivePanelHost
      descriptor={DESCRIPTOR}
      blockId="node-1"
      blockName="Data Router"
      panelPayload={{ input_ports: ["input_1"], output_ports: ["port_1", "port_2"] }}
      onConfirm={onConfirm}
      onCancel={onCancel}
      frameFactory={seam.factory}
      {...overrides}
    />,
  );
  await act(async () => {
    seam.reportLoaded();
    await flush();
  });
  const token = tokenFrom(seam);
  await act(async () => {
    seam.fromPanel(token, "ready", { api_version: "1" });
    await flush();
  });
  await waitFor(() =>
    expect(screen.getByTestId("panel-host")).toHaveAttribute("data-panel-status", "ready"),
  );
  return { seam, token, onConfirm, onCancel };
}

async function emit(seam: RealFrameSeam, token: string, code: string) {
  await act(async () => {
    seam.fromPanel(token, "emit", { code });
    await flush();
  });
}

describe("Confirm commits the panel's emission (D-018)", () => {
  it("is disabled until the panel has emitted, then sends that emission", async () => {
    const { seam, token, onConfirm } = await mount();

    // Nothing emitted yet: there is no decision to commit.
    expect(screen.getByTestId("interactive-panel-confirm")).toBeDisabled();

    await emit(seam, token, ROUTING_DECISION);

    const confirm = screen.getByTestId("interactive-panel-confirm");
    expect(confirm).toBeEnabled();
    confirm.click();

    // The exact shape `settle_interactive_response` reads as an emission: one
    // key, `code`, holding the snippet verbatim — not parsed, not rewritten.
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith({ code: ROUTING_DECISION });
  });

  it("commits the newest emission, because each one is the whole decision", async () => {
    // Both built-in producing documents re-emit their whole decision on every
    // change and say so in a header comment; that is what makes "most recent"
    // mean "current", and it is the property the host relies on.
    const { seam, token, onConfirm } = await mount();

    await emit(seam, token, ROUTING_DECISION);
    await emit(seam, token, REVISED_DECISION);

    screen.getByTestId("interactive-panel-confirm").click();

    expect(onConfirm).toHaveBeenCalledWith({ code: REVISED_DECISION });
  });

  it("cancels rather than confirming when the person closes the window", async () => {
    const { seam, token, onConfirm, onCancel } = await mount();
    await emit(seam, token, ROUTING_DECISION);

    screen.getByTestId("interactive-panel-close").click();

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
