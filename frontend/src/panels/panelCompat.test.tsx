/**
 * ADR-054 spec 1, T-012 — SC-009, proved from the host's side.
 *
 * The shim lives in `src/scistudio/panels/compat.py`: it wraps a previewer
 * written against the ADR-048 module form into a panel directory the merged
 * asset route serves, so that the retired form mounts through *this* host with
 * no second loader anywhere (FR-042, SC-002). There is therefore no frontend
 * production code to test here — that absence is the point — and what is left
 * to prove is the half a Python test cannot reach: that the host, handed the
 * descriptor the shim generates, renders the previewer and grants it neither
 * variable bindings nor an outbound path (FR-043, SC-009).
 *
 * So this asserts against the *host*, not the declaration. The descriptor below
 * is the shape `scistudio.panels.descriptor.panel_descriptor` produces for a
 * shimmed previewer — `capability: "displaying"`, the merged route's URLs, the
 * shim's generated entry document — and the panel in the frame behaves the way
 * the generated document behaves: it answers `ready` once its wrapped module
 * has mounted, then asks for a read, a resource and an export, and then tries
 * to emit. What reaches the emit consumer is what SC-009 is about.
 *
 * Deleted with the shim; see the removal list in `compat.py`'s docstring.
 */

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RealFrameSeam } from "./__tests__/support";
import { createRealFrameSeam, flush, receivedOfType } from "./__tests__/support";
import { PanelHost } from "./PanelHost";
import type { PanelDescriptor } from "./panelDescriptor";

afterEach(cleanup);

/** The shim's own generated entry document name; `compat.py` owns the spelling. */
const COMPAT_ENTRY = "__panel_compat__.html";

/**
 * What the backend describes a wrapped ADR-048 previewer as. Every field is the
 * shim's: the id is the previewer's own, the capability is displaying whatever
 * the spec declared, and the two URLs are the merged asset route's.
 */
const SHIMMED: PanelDescriptor = {
  panel_id: "fixture.image.viewer",
  display_name: "fixture.image.viewer",
  api_version: "1",
  accepted_api_version: "1",
  capability: "displaying",
  document_url: `/api/panels/assets/fixture.image.viewer/${COMPAT_ENTRY}`,
  asset_base_url: "/api/panels/assets/fixture.image.viewer/",
  read_limits: { max_rows: 500, max_bytes: 1_000_000 },
  tier: "package",
  features: ["slice", "metadata", "adr048-compat-shim"],
};

/** The opening snapshot the preview surface hands a displaying mount. */
const ENVELOPE = {
  previewer_id: "fixture.image.viewer",
  kind: "array",
  payload: { shape: [4, 4], src: "" },
  resources: [],
};

function initEnvelope(seam: RealFrameSeam): Record<string, unknown> {
  const init = receivedOfType(seam, "init")[0];
  expect(init).toBeDefined();
  return init as unknown as Record<string, unknown>;
}

/**
 * Render the host over the shim's descriptor and drive the frame the way the
 * generated document does: report the entry document loaded, then answer
 * `ready` — which the generated document only sends once the wrapped ADR-048
 * module has mounted, so a completed handshake here *is* "it renders".
 */
async function mountShimmedPreviewer(
  overrides: Partial<React.ComponentProps<typeof PanelHost>> = {},
) {
  const seam = createRealFrameSeam();
  render(
    <PanelHost
      descriptor={SHIMMED}
      target={ENVELOPE}
      frameFactory={seam.factory}
      loadTimeoutMs={250}
      handshakeTimeoutMs={250}
      readTimeoutMs={250}
      {...overrides}
    />,
  );
  await act(async () => {
    seam.reportLoaded();
    await flush();
  });
  const init = initEnvelope(seam);
  const token = init.token as string;
  await act(async () => {
    seam.fromPanel(token, "ready", { api_version: "1" });
    await flush();
  });
  await waitFor(() =>
    expect(screen.getByTestId("panel-host")).toHaveAttribute("data-panel-status", "ready"),
  );
  return { seam, token, init };
}

describe("a previewer in the retired form renders through the shim (FR-042, SC-009)", () => {
  it("mounts through the one loader, in the one sandboxed frame", async () => {
    const { seam } = await mountShimmedPreviewer();

    const frame = document.querySelector("iframe");
    expect(frame).not.toBeNull();
    expect(frame?.getAttribute("sandbox")).toBe("allow-scripts");
    expect(frame?.getAttribute("src")).toBe(SHIMMED.document_url);
    expect(seam.spec().panelId).toBe("fixture.image.viewer");
  });

  it("is handed the opening snapshot, the read limits and its own asset base", async () => {
    const { init } = await mountShimmedPreviewer();
    const payload = init.payload as Record<string, unknown>;

    expect(payload.capability).toBe("displaying");
    expect(payload.target).toEqual(ENVELOPE);
    expect(payload.read_limits).toEqual(SHIMMED.read_limits);
    expect(payload.asset_base_url).toBe(SHIMMED.asset_base_url);
  });
});

describe("the shim grants nothing new (FR-043, SC-009)", () => {
  it("hands a wrapped previewer no variable bindings", async () => {
    const { init } = await mountShimmedPreviewer();
    const payload = init.payload as Record<string, unknown>;

    // Not "no bindings were used" — the field the contract carries them on is
    // null, so there is nothing for a wrapped module to find (FR-013, FR-043).
    expect(payload.bindings).toBeNull();
  });

  it("gives it no outbound path: an emit reaches no consumer", async () => {
    const onEmit = vi.fn();
    const onDiagnostic = vi.fn();
    const { seam, token } = await mountShimmedPreviewer({ onEmit, onDiagnostic });

    await act(async () => {
      seam.fromPanel(token, "emit", { code: "x = 1" });
      await flush();
    });

    // The consumer was supplied and still received nothing: the gate is
    // structural, so a displaying mount has no path to it at all (FR-011).
    expect(onEmit).not.toHaveBeenCalled();
    expect(onDiagnostic).toHaveBeenCalled();
    const reported = onDiagnostic.mock.calls.map(([entry]) => JSON.stringify(entry)).join(" ");
    expect(reported).toContain("emit");
  });

  it("still answers the bounded reads the retired host API promised (D-017)", async () => {
    const onRead = vi.fn(async () => ({ rows: [{ a: 1 }] }));
    const onResource = vi.fn(async () => ({ ok: true }));
    const onHostAction = vi.fn(async () => ({ ok: true, detail: null }));
    const { seam, token } = await mountShimmedPreviewer({ onRead, onResource, onHostAction });

    await act(async () => {
      // `session.patchQuery`, `session.getResource` and `exportArtifact` as the
      // generated document sends them: three named types, not one overloaded
      // `read` with an `action` key.
      seam.fromPanel(token, "read", { request_id: "r1", query: { page: 2 } });
      seam.fromPanel(token, "resource", { request_id: "r2", resource_id: "tile", params: null });
      seam.fromPanel(token, "host_action", { request_id: "r3", action: "export", params: null });
      await flush();
    });

    expect(onRead).toHaveBeenCalledWith({ page: 2 });
    expect(onResource).toHaveBeenCalledWith("tile", null);
    expect(onHostAction).toHaveBeenCalledWith("export", null);
    expect(receivedOfType(seam, "read_result")).toHaveLength(1);
    expect(receivedOfType(seam, "resource_result")).toHaveLength(1);
    expect(receivedOfType(seam, "host_action_result")).toHaveLength(1);
  });
});

describe("a wrapped previewer that cannot mount is the one load failure (FR-014)", () => {
  it("draws the host's error surface and offers the backend-named fallback", async () => {
    const seam = createRealFrameSeam();
    const onFailure = vi.fn();
    render(
      <PanelHost
        descriptor={SHIMMED}
        target={ENVELOPE}
        frameFactory={seam.factory}
        handshakeTimeoutMs={250}
        onFailure={onFailure}
        renderFallback={() => <div data-testid="fallback-panel">the fallback</div>}
      />,
    );
    await act(async () => {
      seam.reportLoaded();
      await flush();
    });
    const token = (initEnvelope(seam).token as string) ?? "";

    // The generated document reports and stays silent when the wrapped module
    // throws on mount, so the handshake never completes — one behaviour, the
    // same one every other panel failure produces.
    await act(async () => {
      seam.fromPanel(token, "error", {
        message: "the previewer module could not be mounted: boom",
        detail: null,
      });
      await flush();
    });

    const surface = await screen.findByTestId("panel-error-surface");
    expect(surface.textContent).toContain("fixture.image.viewer");
    expect(surface.textContent).toContain("could not be mounted");
    expect(screen.getByTestId("fallback-panel")).toBeInTheDocument();
    expect(onFailure).toHaveBeenCalledTimes(1);
  });
});
