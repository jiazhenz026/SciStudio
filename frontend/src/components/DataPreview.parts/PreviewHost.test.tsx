/**
 * ADR-054 spec 1, T-007 / T-008 / T-011 — the routed preview surface.
 *
 * What these defend is deliberately not what the ADR-048 suite defended. That
 * suite asserted rendered table cells, because the host rendered the table
 * itself; the table is a panel document at an opaque origin now, and a test
 * that reached into it would be asserting against something the host is not
 * allowed to see. So the properties here are the host's own:
 *
 *   - it mounts the panel the **backend** named, and carries no mapping from a
 *     response's kind to one (FR-036, SC-010);
 *   - a panel that fails leaves the data visible through the **backend-named**
 *     fallback, with a diagnostic naming the panel and the failure (FR-014,
 *     FR-015, SC-006);
 *   - it answers all three request types across the boundary — `read`,
 *     `resource`, `host_action` — for a displaying mount (D-017);
 *   - it keeps the tutorial surface the frame cannot carry: the
 *     `preview_item_opened` event and the two highlight targets (D-019);
 *   - saving a panel remounts it without the person reopening the view, and the
 *     panel's snapshot rides across that remount (FR-030, FR-031).
 *
 * The frame, its sandbox attribute, its `contentWindow` and every message in
 * both directions are real; only the load observation is substituted, because
 * jsdom does not fetch an iframe's `src`.
 */

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PanelDescriptorResponse, PreviewEnvelope, PreviewTarget } from "../../types/api";

// Mock the api surface PreviewHost calls.
const createPreviewSession = vi.fn();
const patchPreviewSession = vi.fn();
const getPreviewResource = vi.fn();
const getPreviewSession = vi.fn();
const openNativeSaveDialog = vi.fn();
const savePreviewResource = vi.fn();
const fetchMock = vi.fn();

vi.mock("../../lib/api", () => ({
  api: {
    createPreviewSession: (...a: unknown[]) => createPreviewSession(...a),
    patchPreviewSession: (...a: unknown[]) => patchPreviewSession(...a),
    getPreviewResource: (...a: unknown[]) => getPreviewResource(...a),
    getPreviewSession: (...a: unknown[]) => getPreviewSession(...a),
    openNativeSaveDialog: (...a: unknown[]) => openNativeSaveDialog(...a),
    savePreviewResource: (...a: unknown[]) => savePreviewResource(...a),
  },
}));

import type { PanelFrameFactory, PanelFrameHandle, PanelFrameSpec } from "../../panels";
import { createSandboxedPanelFrame, panelToHostMessage } from "../../panels";
import { buildPreviewCacheKey } from "../../store/previewSlice";
import { useAppStore } from "../../store";
import { resetAppStore } from "../../testUtils";
import { PreviewHost } from "./PreviewHost";

/* -------------------------------------------------------------------------- */
/* A frame seam that survives a remount                                        */
/* -------------------------------------------------------------------------- */

/**
 * The panel suite's seam holds one frame; this host mounts a *sequence* of
 * them — the chosen panel, then the fallback, then the reloaded document — so
 * this one keeps the newest and gives each its own load promise.
 */
interface Seam {
  readonly factory: PanelFrameFactory;
  specs(): readonly PanelFrameSpec[];
  loadLatest(): void;
  contentWindow(): Window;
  fromPanel(type: string, payload: Record<string, unknown>): void;
  received(): readonly Record<string, unknown>[];
  clearReceived(): void;
  token(): string;
}

function createSeam(): Seam {
  const specs: PanelFrameSpec[] = [];
  const received: Record<string, unknown>[] = [];
  let handle: PanelFrameHandle | null = null;
  let resolveLoaded: (() => void) | null = null;

  const factory: PanelFrameFactory = (spec) => {
    specs.push(spec);
    const real = createSandboxedPanelFrame(spec);
    const loaded = new Promise<void>((resolve) => {
      resolveLoaded = resolve;
    });
    real.contentWindow?.addEventListener("message", (event) => {
      received.push((event as MessageEvent).data as Record<string, unknown>);
    });
    handle = {
      element: real.element,
      get contentWindow() {
        return real.contentWindow;
      },
      whenLoaded: () => loaded,
      dispose: () => real.dispose(),
    };
    return handle;
  };

  const requireWindow = () => {
    const contentWindow = handle?.contentWindow;
    if (!contentWindow) throw new Error("no frame yet");
    return contentWindow;
  };

  return {
    factory,
    specs: () => specs,
    loadLatest: () => resolveLoaded?.(),
    contentWindow: requireWindow,
    token() {
      const init = received.find((entry) => entry?.type === "init");
      if (!init) throw new Error("no init was posted");
      return init.token as string;
    },
    fromPanel(type, payload) {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: panelToHostMessage(
            this.token(),
            type as "ready",
            payload as unknown as { api_version: string },
          ),
          source: requireWindow(),
        }),
      );
    },
    received: () => received,
    clearReceived: () => {
      received.length = 0;
    },
  };
}

async function flush(rounds = 6) {
  for (let round = 0; round < rounds; round += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

function ofType(seam: Seam, type: string): Record<string, unknown>[] {
  return seam.received().filter((entry) => entry?.type === type);
}

/* -------------------------------------------------------------------------- */
/* Fixtures                                                                    */
/* -------------------------------------------------------------------------- */

function descriptor(overrides: Partial<PanelDescriptorResponse> = {}): PanelDescriptorResponse {
  return {
    panel_id: "core.dataframe.basic",
    display_name: "Table",
    api_version: "1",
    accepted_api_version: "1",
    capability: "displaying",
    document_url: "/api/panels/assets/core.dataframe.basic/index.html",
    asset_base_url: "/api/panels/assets/core.dataframe.basic/",
    read_limits: { max_rows: 500, max_bytes: 1_000_000 },
    ...overrides,
  };
}

function envelope(partial: Partial<PreviewEnvelope> = {}): PreviewEnvelope {
  return {
    session_id: "pv-1",
    previewer_id: "core.dataframe.basic",
    target: { kind: "data_ref", ref: "data-1" },
    kind: "dataframe",
    payload: {},
    resources: [],
    metadata: {
      sampled: false,
      truncated: false,
      cached: false,
      derived: false,
      complete: true,
      failed: false,
    },
    diagnostics: [],
    error: null,
    panel: descriptor(),
    fallback_panel_id: "core.base.fallback",
    fallback_panel: descriptor({
      panel_id: "core.base.fallback",
      display_name: "Fallback",
      document_url: "/api/panels/assets/core.base.fallback/index.html",
      asset_base_url: "/api/panels/assets/core.base.fallback/",
    }),
    ...partial,
  };
}

const TARGET: PreviewTarget = { kind: "data_ref", ref: "data-1", recorded_type: "DataFrame" };

function okJson(body: unknown): Response {
  return { ok: true, status: 200, json: vi.fn(async () => body) } as unknown as Response;
}

/** Render the host and drive the mounted panel through its handshake. */
async function mount(env: PreviewEnvelope = envelope(), seam = createSeam()) {
  createPreviewSession.mockResolvedValue(env);
  const view = render(<PreviewHost target={TARGET} frameFactory={seam.factory} />);
  await screen.findByTestId("preview-host");
  await act(async () => {
    seam.loadLatest();
    await flush();
  });
  await act(async () => {
    seam.fromPanel("ready", { api_version: "1" });
    await flush();
  });
  await waitFor(() =>
    expect(screen.getByTestId("panel-host")).toHaveAttribute("data-panel-status", "ready"),
  );
  return { seam, view };
}

let anchorClickSpy: ReturnType<typeof vi.spyOn> | null = null;

beforeEach(() => {
  resetAppStore();
  createPreviewSession.mockReset();
  patchPreviewSession.mockReset();
  getPreviewResource.mockReset();
  getPreviewSession.mockReset();
  openNativeSaveDialog.mockReset();
  openNativeSaveDialog.mockResolvedValue({ paths: ["C:/Users/test/plot.svg"] });
  savePreviewResource.mockReset();
  savePreviewResource.mockResolvedValue({
    path: "C:/Users/test/plot.svg",
    filename: "plot.svg",
    size_bytes: 7,
    mime_type: "image/svg+xml",
  });
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  anchorClickSpy = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  anchorClickSpy?.mockRestore();
  anchorClickSpy = null;
  vi.unstubAllGlobals();
});

/* -------------------------------------------------------------------------- */

describe("the backend names the panel (FR-015, FR-036, SC-010)", () => {
  it("mounts the descriptor the response carried", async () => {
    const { seam } = await mount();

    expect(screen.getByTestId("panel-host")).toHaveAttribute(
      "data-panel-id",
      "core.dataframe.basic",
    );
    expect(seam.specs()[0].documentUrl).toBe(
      "/api/panels/assets/core.dataframe.basic/index.html",
    );
  });

  it("mounts whatever the response named, whatever the envelope's kind says", async () => {
    // The measurable form of SC-010: `kind` says dataframe and the named panel
    // is a project one. A host holding a kind-to-panel table would mount the
    // table viewer here; this one mounts what it was told.
    await mount(
      envelope({
        kind: "dataframe",
        previewer_id: "myproj.custom",
        panel: descriptor({
          panel_id: "myproj.custom",
          document_url: "/api/panels/assets/myproj.custom/index.html",
        }),
      }),
    );

    expect(screen.getByTestId("panel-host")).toHaveAttribute("data-panel-id", "myproj.custom");
  });

  it("says so plainly when the response named no panel at all", async () => {
    createPreviewSession.mockResolvedValue(envelope({ panel: null }));
    render(<PreviewHost target={TARGET} frameFactory={createSeam().factory} />);

    const surface = await screen.findByTestId("panel-error-surface");
    expect(surface.textContent).toContain("named no panel");
    // And nothing was framed: the host does not guess at a document URL.
    expect(document.querySelector("iframe")).toBeNull();
  });
});

describe("a failed panel still shows the data (FR-014, SC-006)", () => {
  it("mounts the backend-named fallback and reports a diagnostic naming the panel", async () => {
    // A version the backend does not accept fails before a frame is created,
    // which is the earliest of the three SC-006 failure paths.
    const seam = createSeam();
    createPreviewSession.mockResolvedValue(
      envelope({ panel: descriptor({ api_version: "9" }) }),
    );
    render(<PreviewHost target={TARGET} frameFactory={seam.factory} />);

    await waitFor(() =>
      expect(screen.getByTestId("panel-host")).toHaveAttribute(
        "data-panel-id",
        "core.base.fallback",
      ),
    );
    const banner = screen.getByTestId("panel-diagnostics");
    expect(banner.textContent).toContain("core.dataframe.basic");
    expect(banner.textContent).toContain("version_mismatch");
  });

  it("names the fallback it could not reach when only its id was sent", async () => {
    createPreviewSession.mockResolvedValue(
      envelope({ panel: descriptor({ api_version: "9" }), fallback_panel: null }),
    );
    render(<PreviewHost target={TARGET} frameFactory={createSeam().factory} />);

    const surface = await screen.findByTestId("panel-error-surface");
    expect(surface.textContent).toContain("core.base.fallback");
  });
});

describe("the three request types the host answers (D-017)", () => {
  it("answers `read` by patching the session and posting `read_result`", async () => {
    const { seam } = await mount();
    const next = envelope({ payload: { page: 2 } });
    patchPreviewSession.mockResolvedValue(next);
    seam.clearReceived();

    await act(async () => {
      seam.fromPanel("read", { request_id: "r1", query: { page: 2 } });
      await flush();
    });

    expect(patchPreviewSession).toHaveBeenCalledWith("pv-1", { page: 2 });
    const answers = ofType(seam, "read_result");
    expect(answers).toHaveLength(1);
    expect((answers[0].payload as { request_id: string }).request_id).toBe("r1");
  });

  it("answers `resource` for a collection item by routing the child into its own panel", async () => {
    const { seam } = await mount(
      envelope({
        kind: "collection",
        resources: [{ resource_id: "item:0", kind: "child", params: { index: 0 } }],
      }),
    );
    fetchMock.mockResolvedValue(
      okJson({
        resource_id: "item:0",
        data: envelope({ session_id: "pv-child", kind: "artifact", previewer_id: "core.artifact.basic" }),
      }),
    );
    seam.clearReceived();

    await act(async () => {
      seam.fromPanel("resource", { request_id: "r2", resource_id: "item:0", params: null });
      await flush();
    });

    // The child is on the drill-down stack, so the Back control appears.
    await waitFor(() => expect(screen.getByTestId("preview-host-back")).toBeInTheDocument());
    // And the answer is the acknowledgement, not the child's payload.
    const answers = ofType(seam, "resource_result");
    expect(answers).toHaveLength(1);
    expect(answers[0].payload).toMatchObject({
      request_id: "r2",
      resource: { routed: true, resource_id: "item:0" },
    });
  });

  it("hands a bounded tile back whole, because it is the panel's own data", async () => {
    const { seam } = await mount(
      envelope({
        kind: "array",
        resources: [{ resource_id: "tile:0", kind: "tile", params: {} }],
      }),
    );
    fetchMock.mockResolvedValue(okJson({ resource_id: "tile:0", data: { values: [1, 2, 3] } }));
    seam.clearReceived();

    await act(async () => {
      seam.fromPanel("resource", { request_id: "r3", resource_id: "tile:0", params: null });
      await flush();
    });

    const answers = ofType(seam, "resource_result");
    expect((answers[0].payload as { resource: unknown }).resource).toEqual({ values: [1, 2, 3] });
    expect(screen.queryByTestId("preview-host-back")).toBeNull();
  });

  it("answers a cancelled export with ok:true, because a decision is not a failure", async () => {
    // The native dialog ran and came back with no path: the person cancelled.
    openNativeSaveDialog.mockResolvedValue({ paths: [], available: true });
    const { seam } = await mount(
      envelope({
        kind: "plot",
        target: { kind: "plot_artifact", ref: "plot://x" },
        resources: [{ resource_id: "export", kind: "artifact", params: { format: "png" } }],
      }),
    );
    seam.clearReceived();

    await act(async () => {
      seam.fromPanel("host_action", {
        request_id: "r4",
        action: "export",
        params: { format: "png" },
      });
      await flush();
    });

    const answers = ofType(seam, "host_action_result");
    expect(answers[0].payload).toMatchObject({
      request_id: "r4",
      ok: true,
      detail: { status: "declined" },
    });
    expect(savePreviewResource).not.toHaveBeenCalled();
  });

  it("answers an action it cannot perform with ok:false", async () => {
    const { seam } = await mount(envelope({ kind: "text", payload: {}, resources: [] }));
    seam.clearReceived();

    await act(async () => {
      seam.fromPanel("host_action", {
        request_id: "r5",
        action: "editor_handoff",
        params: { ref: "data-1" },
      });
      await flush();
    });

    const answers = ofType(seam, "host_action_result");
    expect(answers[0].payload).toMatchObject({ request_id: "r5", ok: false });
  });
});

describe("the tutorial surface a frame cannot carry (D-019)", () => {
  it("fires preview_item_opened when it services a collection item's resource", async () => {
    const reportTutorialUiEvent = vi.fn(async () => {});
    useAppStore.setState({ reportTutorialUiEvent });
    const { seam } = await mount(
      envelope({
        kind: "collection",
        resources: [{ resource_id: "item:0", kind: "child", params: { index: 0 } }],
      }),
    );
    fetchMock.mockResolvedValue(
      okJson({ resource_id: "item:0", data: envelope({ session_id: "pv-child" }) }),
    );

    await act(async () => {
      seam.fromPanel("resource", { request_id: "r6", resource_id: "item:0", params: null });
      await flush();
    });

    expect(reportTutorialUiEvent).toHaveBeenCalledWith("preview_item_opened");
  });

  it("does not fire it for a resource that is not a collection item", async () => {
    const reportTutorialUiEvent = vi.fn(async () => {});
    useAppStore.setState({ reportTutorialUiEvent });
    const { seam } = await mount(
      envelope({
        kind: "composite",
        resources: [{ resource_id: "slot:mask", kind: "child", params: { slot: "mask" } }],
      }),
    );
    fetchMock.mockResolvedValue(
      okJson({ resource_id: "slot:mask", data: envelope({ session_id: "pv-child" }) }),
    );

    await act(async () => {
      seam.fromPanel("resource", { request_id: "r7", resource_id: "slot:mask", params: null });
      await flush();
    });

    expect(reportTutorialUiEvent).not.toHaveBeenCalled();
  });

  it("fires plot_exported after the save resolves, for a plot artifact", async () => {
    const reportTutorialUiEvent = vi.fn(async () => {});
    useAppStore.setState({ reportTutorialUiEvent });
    const { seam } = await mount(
      envelope({
        kind: "plot",
        target: { kind: "plot_artifact", ref: "plot://x" },
        resources: [{ resource_id: "export", kind: "artifact", params: { format: "png" } }],
      }),
    );

    await act(async () => {
      seam.fromPanel("host_action", {
        request_id: "r8",
        action: "export",
        params: { format: "png" },
      });
      await flush();
    });

    expect(savePreviewResource).toHaveBeenCalled();
    expect(reportTutorialUiEvent).toHaveBeenCalledWith("plot_exported");
  });

  it("carries both highlight targets on the host's own chrome, outside the frame", async () => {
    await mount(
      envelope({
        kind: "collection",
        target: { kind: "plot_artifact", ref: "plot://x" },
        resources: [{ resource_id: "item:0", kind: "child", params: { index: 0 } }],
      }),
    );

    const chrome = screen.getByTestId("preview-host-panel");
    expect(chrome).toHaveAttribute("data-tutorial-target", "preview_item");
    expect(chrome).toHaveAttribute("data-tutorial-target-key", "0");
    expect(
      chrome.querySelector('[data-tutorial-target="plot_export_button"]'),
    ).toBeInTheDocument();
    // Both are the host's markup: neither is inside the frame.
    const frame = document.querySelector("iframe");
    expect(frame?.querySelector("[data-tutorial-target]")).toBeFalsy();
  });
});

describe("hot reload and the state hook (FR-030, FR-031)", () => {
  it("remounts every instance of a saved panel without the view being reopened", async () => {
    const { seam } = await mount();
    expect(seam.specs()).toHaveLength(1);

    // Exactly what the websocket dispatcher does when a panel file changes.
    await act(async () => {
      useAppStore.getState().notePanelDocumentChanged("core.dataframe.basic");
      await flush();
    });

    await waitFor(() => expect(seam.specs().length).toBeGreaterThan(1));
    expect(seam.specs()[1].panelId).toBe("core.dataframe.basic");
  });

  it("leaves a panel alone when a different panel was the one that changed", async () => {
    const { seam } = await mount();

    await act(async () => {
      useAppStore.getState().notePanelDocumentChanged("some.other.panel");
      await flush();
    });

    expect(seam.specs()).toHaveLength(1);
  });

  it("carries the panel's snapshot across the remount and hands it back in init", async () => {
    const { seam } = await mount();
    seam.clearReceived();

    await act(async () => {
      useAppStore.getState().notePanelDocumentChanged("core.dataframe.basic");
      await flush();
    });
    // The old mount is asked for its snapshot before it goes away.
    await waitFor(() => expect(ofType(seam, "state_request").length).toBe(1));
    await act(async () => {
      seam.fromPanel("state", { state: { page: 4 } });
      await flush();
      seam.loadLatest();
      await flush();
    });

    await waitFor(() => expect(ofType(seam, "init").length).toBeGreaterThan(0));
    const inits = ofType(seam, "init");
    const init = inits[inits.length - 1];
    expect((init?.payload as { restored_state: unknown }).restored_state).toEqual({ page: 4 });
  });

  it("remounts clean when the snapshot will not serialise, rather than failing the reload", async () => {
    const { seam } = await mount();
    seam.clearReceived();

    await act(async () => {
      useAppStore.getState().notePanelDocumentChanged("core.dataframe.basic");
      await flush();
    });
    await waitFor(() => expect(ofType(seam, "state_request").length).toBe(1));

    const cyclic: Record<string, unknown> = {};
    cyclic.self = cyclic;
    await act(async () => {
      seam.fromPanel("state", { state: cyclic });
      await flush();
      seam.loadLatest();
      await flush();
    });

    await waitFor(() => expect(seam.specs().length).toBeGreaterThan(1));
    const inits = ofType(seam, "init");
    const init = inits[inits.length - 1];
    expect((init?.payload as { restored_state: unknown }).restored_state).toBeUndefined();
  });
});

describe("the session-envelope cache key (ADR-048 FR-021)", () => {
  it("includes ref, kind, panel, session, query and version", () => {
    const key = buildPreviewCacheKey(
      { kind: "data_ref", ref: "data-1" },
      { page: 2, _storage: "ignored" },
      { panelId: "core.dataframe.basic", sessionId: "pv-1", dataVersion: 7 },
    );
    expect(key).toContain("ref=data-1");
    expect(key).toContain("kind=data_ref");
    expect(key).toContain("panel=core.dataframe.basic");
    expect(key).toContain("session=pv-1");
    expect(key).toContain("version=7");
    expect(key).toContain("page=2");
    expect(key).not.toContain("_storage");
  });
});
