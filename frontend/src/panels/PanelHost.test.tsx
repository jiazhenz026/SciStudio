/**
 * ADR-054 spec 1, T-005 and T-006 — the React host, from the outside.
 *
 * ADR-054's `tests:` list names this path, so it is fixed.
 *
 * The three failure paths SC-006 requires are driven with genuinely broken
 * input rather than mocked failures: a descriptor naming a document that is not
 * a same-origin asset path, a panel declaring a version the backend does not
 * accept, and a panel that loads and then never answers the handshake. The
 * capability gate is exercised from the host's side: a displaying mount is
 * given an `onEmit`, a real `emit` message is posted from the real frame's own
 * window carrying the host's real token, and the assertion is that nothing
 * reached the consumer (SC-007).
 *
 * What is real and what is substituted is described in `__tests__/support.ts`:
 * the frame, its sandbox attribute, its `contentWindow` and every message that
 * crosses it are real; only the load observation is substituted, because jsdom
 * does not fetch an iframe's `src`.
 */

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps } from "react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RealFrameSeam } from "./__tests__/support";
import { createRealFrameSeam, flush, receivedOfType } from "./__tests__/support";
import { PanelHost } from "./PanelHost";
import type { PanelHostHandle } from "./PanelHost";
import type { PanelDescriptor } from "./panelDescriptor";
import { panelToHostMessage } from "./panelMessages";

afterEach(cleanup);

const DESCRIPTOR: PanelDescriptor = {
  panel_id: "core.table",
  display_name: "Table",
  api_version: "1",
  accepted_api_version: "1",
  capability: "displaying",
  document_url: "/api/panels/assets/core.table/index.html",
  asset_base_url: "/api/panels/assets/core.table/",
  read_limits: { max_rows: 500, max_bytes: 1_000_000 },
};

type HostProps = ComponentProps<typeof PanelHost>;

function descriptor(overrides: Partial<PanelDescriptor> = {}): PanelDescriptor {
  return { ...DESCRIPTOR, ...overrides };
}

/**
 * The host issues its own token; the tests read it back off the real `init`
 * envelope the frame received rather than pretending to know it.
 */
function tokenFrom(seam: RealFrameSeam): string {
  const init = receivedOfType(seam, "init")[0];
  expect(init).toBeDefined();
  return (init as unknown as { token: string }).token;
}

function renderHost(overrides: Partial<HostProps>, seam: RealFrameSeam) {
  return render(
    <PanelHost
      descriptor={descriptor()}
      frameFactory={seam.factory}
      loadTimeoutMs={250}
      handshakeTimeoutMs={250}
      readTimeoutMs={250}
      {...overrides}
    />,
  );
}

/** Render the host and drive its frame through a completed handshake. */
async function mountHost(overrides: Partial<HostProps> = {}, seam = createRealFrameSeam()) {
  const view = renderHost(overrides, seam);
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
  seam.clearReceived();
  return { seam, token, view };
}

describe("the version gate (FR-004, SC-006)", () => {
  it("refuses a panel built for another host before it frames anything", async () => {
    const seam = createRealFrameSeam();
    const onFailure = vi.fn();

    render(
      <PanelHost
        descriptor={descriptor({ api_version: "2" })}
        frameFactory={seam.factory}
        onFailure={onFailure}
      />,
    );

    const surface = await screen.findByTestId("panel-error-surface");
    expect(surface).toHaveAttribute("data-panel-failure", "version_mismatch");
    expect(surface.textContent).toContain("core.table");
    expect(surface.textContent).toContain('"2"');
    expect(seam.created()).toBe(false);
    expect(document.querySelector("iframe")).toBeNull();
    expect(onFailure).toHaveBeenCalledTimes(1);
  });

  it("takes the accepted version from the descriptor, not from a frontend constant", async () => {
    const seam = createRealFrameSeam();
    renderHost({ descriptor: descriptor({ api_version: "7", accepted_api_version: "7" }) }, seam);
    await act(async () => {
      seam.reportLoaded();
      await flush();
    });

    const init = receivedOfType(seam, "init")[0];
    expect((init.payload as { api_version: string }).api_version).toBe("7");

    await act(async () => {
      seam.fromPanel(tokenFrom(seam), "ready", { api_version: "7" });
      await flush();
    });
    await waitFor(() =>
      expect(screen.getByTestId("panel-host")).toHaveAttribute("data-panel-status", "ready"),
    );
    expect(screen.queryByTestId("panel-error-surface")).toBeNull();
  });

  it("refuses a document that answers ready with a version the backend rejects", async () => {
    const seam = createRealFrameSeam();
    renderHost({}, seam);
    await act(async () => {
      seam.reportLoaded();
      await flush();
    });
    await act(async () => {
      seam.fromPanel(tokenFrom(seam), "ready", { api_version: "4" });
      await flush();
    });

    const surface = await screen.findByTestId("panel-error-surface");
    expect(surface).toHaveAttribute("data-panel-failure", "version_mismatch");
  });
});

describe("a malformed panel document (SC-006)", () => {
  it("refuses a document that is not a same-origin asset path", async () => {
    const seam = createRealFrameSeam();
    renderHost(
      { descriptor: descriptor({ document_url: "https://cdn.example.com/panel.html" }) },
      seam,
    );

    const surface = await screen.findByTestId("panel-error-surface");
    expect(surface).toHaveAttribute("data-panel-failure", "invalid_document_url");
    expect(surface.textContent).toContain("core.table");
    expect(seam.created()).toBe(false);
  });

  it("refuses a descriptor the backend did not fill in", async () => {
    const seam = createRealFrameSeam();
    renderHost({ descriptor: { ...descriptor(), read_limits: undefined as never } }, seam);

    const surface = await screen.findByTestId("panel-error-surface");
    expect(surface).toHaveAttribute("data-panel-failure", "invalid_descriptor");
    expect(surface.textContent).toContain("read limits");
  });
});

describe("a panel that never answers the handshake (SC-006)", () => {
  it("renders the host's error surface and offers the caller its fallback", async () => {
    const seam = createRealFrameSeam();
    const onFailure = vi.fn();

    renderHost(
      {
        onFailure,
        renderFallback: (failure) => (
          <div data-testid="caller-fallback">{`fallback for ${failure.panelId}`}</div>
        ),
      },
      seam,
    );
    await act(async () => {
      seam.reportLoaded();
      await flush();
    });

    const surface = await screen.findByTestId("panel-error-surface");
    expect(surface).toHaveAttribute("data-panel-failure", "handshake_timeout");
    expect(surface.textContent).toContain("core.table");
    expect(screen.getByTestId("caller-fallback").textContent).toBe("fallback for core.table");
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("panel-frame-container")).toHaveAttribute("hidden");
  });

  it("makes no fallback decision of its own (FR-015, FR-036)", async () => {
    const seam = createRealFrameSeam();
    renderHost({}, seam);
    await act(async () => {
      seam.reportLoaded();
      await flush();
    });

    await screen.findByTestId("panel-error-surface");
    // Without a `renderFallback` the host shows its chrome and nothing else: it
    // holds no mapping from a response's kind to a panel.
    expect(screen.queryByTestId("caller-fallback")).toBeNull();
    expect(document.querySelectorAll("iframe")).toHaveLength(0);
  });
});

describe("the error surface is host chrome (FR-035)", () => {
  it("renders when the frame mechanism itself is unavailable", async () => {
    render(
      <PanelHost
        descriptor={descriptor()}
        frameFactory={() => {
          throw new Error("this environment has no frames");
        }}
      />,
    );

    const surface = await screen.findByTestId("panel-error-surface");
    expect(surface).toHaveAttribute("data-panel-failure", "frame_unavailable");
    expect(surface.textContent).toContain("this environment has no frames");
    expect(document.querySelector("iframe")).toBeNull();
  });
});

describe("the capability gate, from the host's side (T-006, SC-007)", () => {
  it("lets nothing reach the consumer when a displaying mount emits", async () => {
    const onEmit = vi.fn();
    const onDiagnostic = vi.fn();
    const { seam, token } = await mountHost({ onEmit, onDiagnostic });

    await act(async () => {
      seam.fromPanel(token, "emit", { code: "df = df.drop(columns=['a'])" });
      await flush();
    });

    expect(onEmit).not.toHaveBeenCalled();
    expect(onDiagnostic).toHaveBeenCalledTimes(1);
    expect(onDiagnostic.mock.calls[0][0]).toMatchObject({
      panelId: "core.table",
      code: "capability_denied",
    });

    // The denial is reported back to the panel over the error channel.
    const errors = receivedOfType(seam, "error");
    expect(errors).toHaveLength(1);
    expect(errors[0].payload).toMatchObject({ code: "capability_denied", request_id: null });

    const banner = await screen.findByTestId("panel-diagnostics");
    expect(banner.textContent).toContain("capability_denied");
  });

  it("drops every emission from a displaying mount, not only the first", async () => {
    const onEmit = vi.fn();
    const { seam, token } = await mountHost({ onEmit });

    await act(async () => {
      for (let index = 0; index < 4; index += 1) {
        seam.fromPanel(token, "emit", { code: `x = ${index}` });
      }
      await flush();
    });

    expect(onEmit).not.toHaveBeenCalled();
    expect(receivedOfType(seam, "error")).toHaveLength(4);
  });

  it("wires the emit path for a producing mount", async () => {
    const onEmit = vi.fn();
    const { seam, token } = await mountHost({
      descriptor: descriptor({ panel_id: "editor.table", capability: "producing" }),
      onEmit,
    });

    await act(async () => {
      seam.fromPanel(token, "emit", { code: "df = df.head(3)" });
      await flush();
    });

    expect(onEmit).toHaveBeenCalledTimes(1);
    expect(onEmit).toHaveBeenCalledWith("df = df.head(3)");
  });

  it("refuses an emit that carries the wrong token or comes from another window", async () => {
    const onEmit = vi.fn();
    const { seam, token } = await mountHost({
      descriptor: descriptor({ panel_id: "editor.table", capability: "producing" }),
      onEmit,
    });

    await act(async () => {
      // Right window, a previous mount's token.
      seam.raw(panelToHostMessage("a-previous-mount", "emit", { code: "x = 1" }));
      // Right token, another window entirely.
      seam.raw(panelToHostMessage(token, "emit", { code: "x = 2" }), seam.otherWindow());
      // Right token, no window at all.
      seam.raw(panelToHostMessage(token, "emit", { code: "x = 3" }), null);
      await flush();
    });

    expect(onEmit).not.toHaveBeenCalled();
  });
});

describe("the bounded windowed read (FR-010)", () => {
  it("routes a panel's read to the caller and answers it", async () => {
    const onRead = vi.fn(async (query: Readonly<Record<string, unknown>>) => ({
      rows: [{ a: 1 }],
      query,
    }));
    const { seam, token } = await mountHost({ onRead });

    await act(async () => {
      seam.fromPanel(token, "read", { request_id: "r1", query: { offset: 10 } });
      await flush();
    });

    expect(onRead).toHaveBeenCalledWith({ offset: 10 });
    expect(receivedOfType(seam, "read_result")[0].payload).toEqual({
      request_id: "r1",
      window: { rows: [{ a: 1 }], query: { offset: 10 } },
    });
  });

  it("tells the panel when this mount was given no way to read", async () => {
    const { seam, token } = await mountHost();

    await act(async () => {
      seam.fromPanel(token, "read", { request_id: "r9", query: {} });
      await flush();
    });

    expect(receivedOfType(seam, "read_result")).toHaveLength(0);
    expect(receivedOfType(seam, "error")[0].payload).toMatchObject({
      code: "read_failed",
      request_id: "r9",
    });
  });
});

describe("the update channel (FR-010)", () => {
  it("posts an update to a live panel", async () => {
    const seam = createRealFrameSeam();
    const { view } = await mountHost({}, seam);

    await act(async () => {
      view.rerender(
        <PanelHost
          descriptor={descriptor()}
          frameFactory={seam.factory}
          loadTimeoutMs={250}
          handshakeTimeoutMs={250}
          readTimeoutMs={250}
          update={{ reason: "session_advanced", changed: { rows: 12 } }}
        />,
      );
    });
    // The effect that posts the update runs when `act` flushes, so the frame's
    // window is given a turn of its own to receive it.
    await act(async () => {
      await flush();
    });

    expect(receivedOfType(seam, "update")[0].payload).toEqual({
      reason: "session_advanced",
      changed: { rows: 12 },
    });
  });
});

describe("the error channel", () => {
  it("shows a panel's own error as a diagnostic without tearing it down", async () => {
    const onDiagnostic = vi.fn();
    const { seam, token } = await mountHost({ onDiagnostic });

    await act(async () => {
      seam.fromPanel(token, "error", { message: "the trace would not render", detail: null });
      await flush();
    });

    const banner = await screen.findByTestId("panel-diagnostics");
    expect(banner.textContent).toContain("the trace would not render");
    expect(screen.getByTestId("panel-host")).toHaveAttribute("data-panel-status", "ready");
    expect(screen.queryByTestId("panel-error-surface")).toBeNull();
    expect(onDiagnostic).toHaveBeenCalledTimes(1);
  });
});

describe("the optional state hook (FR-031)", () => {
  it("hands back a serialisable snapshot through the host handle", async () => {
    const ref = createRef<PanelHostHandle>();
    const { seam, token } = await mountHost({ ref });

    let snapshot: unknown;
    await act(async () => {
      const pending = ref.current?.requestState(250);
      await flush();
      seam.fromPanel(token, "state", { state: { selection: [3, 4] } });
      snapshot = await pending;
    });

    expect(receivedOfType(seam, "state_request")).toHaveLength(1);
    expect(snapshot).toEqual({ kept: true, state: { selection: [3, 4] } });
  });

  it("discards an unserialisable snapshot rather than failing the reload", async () => {
    const ref = createRef<PanelHostHandle>();
    const { seam, token } = await mountHost({ ref });

    const cyclic: Record<string, unknown> = { name: "selection" };
    cyclic.self = cyclic;

    let snapshot: { kept: boolean } | undefined;
    await act(async () => {
      const pending = ref.current?.requestState(250);
      await flush();
      // Dispatched directly: a structured clone refuses to carry a cyclic value
      // across a real frame, but a panel document can still hand one back.
      seam.raw({ scistudio_panel: 1, token, type: "state", payload: { state: cyclic } });
      snapshot = await pending;
    });

    expect(snapshot?.kept).toBe(false);
    expect(screen.getByTestId("panel-host")).toHaveAttribute("data-panel-status", "ready");
  });

  it("answers `kept: false` when nothing is mounted", async () => {
    const ref = createRef<PanelHostHandle>();
    render(
      <PanelHost
        ref={ref}
        descriptor={descriptor({ api_version: "9" })}
        frameFactory={createRealFrameSeam().factory}
      />,
    );
    await screen.findByTestId("panel-error-surface");
    await expect(ref.current?.requestState()).resolves.toEqual({
      kept: false,
      reason: "no panel is mounted",
    });
  });
});

describe("teardown", () => {
  it("removes the frame and stops listening when the host unmounts", async () => {
    const onEmit = vi.fn();
    const onDiagnostic = vi.fn();
    const { seam, token, view } = await mountHost({
      descriptor: descriptor({ panel_id: "editor.table", capability: "producing" }),
      onEmit,
      onDiagnostic,
    });
    const element = seam.element();
    expect(element.isConnected).toBe(true);

    await act(async () => {
      view.unmount();
    });
    await flush();

    expect(element.isConnected).toBe(false);

    // React removes the container, so the panel's window is gone with it: the
    // `teardown` message is best effort and its delivery is not asserted here.
    // What is asserted is that the host no longer acts on anything: a message
    // posted after the unmount reaches nothing.
    expect(() => seam.raw(panelToHostMessage(token, "emit", { code: "x = 1" }))).not.toThrow();
    await flush();
    expect(onEmit).not.toHaveBeenCalled();
    expect(onDiagnostic).not.toHaveBeenCalled();
  });
});
