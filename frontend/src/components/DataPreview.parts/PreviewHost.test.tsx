/**
 * ADR-048 SPEC 1 — PreviewHost + core fallback + dynamic-loader tests.
 *
 * Covers the frontend Verification Plan (spec §4.4):
 *   - PreviewHost creates a session and mounts the core fallback viewer;
 *   - a dynamic manifest that fails same-origin validation falls back cleanly
 *     to the core viewer AND surfaces a diagnostic (US2.3 / FR-029);
 *   - collection outputs render a collection-level preview (US4);
 *   - DataFrame pagination/sort still works through the core viewer;
 *   - plot SVG is sandboxed and the export control renders (FR-018/FR-019);
 *   - the session-envelope cache key includes provider/session/query state
 *     (FR-021).
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PreviewEnvelope, PreviewTarget } from "../../types/api";

// Mock the api surface PreviewHost calls.
const createPreviewSession = vi.fn();
const patchPreviewSession = vi.fn();
const getPreviewResource = vi.fn();
const getPreviewSession = vi.fn();
const openNativeSaveDialog = vi.fn();
const savePreviewResource = vi.fn();
const fetchMock = vi.fn();
let anchorClickSpy: ReturnType<typeof vi.spyOn> | null = null;

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

import { PreviewHost } from "./PreviewHost";
import { buildPreviewCacheKey } from "../../store/previewSlice";
import { isSameOriginModuleUrl } from "./dynamicPreviewer";
import type { PreviewHostApi } from "./previewerHostApi";

function envelope(partial: Partial<PreviewEnvelope>): PreviewEnvelope {
  return {
    session_id: "pv-1",
    previewer_id: "core.base.fallback",
    target: { kind: "data_ref", ref: "data-1" },
    kind: "artifact",
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
    ...partial,
  };
}

const TARGET: PreviewTarget = { kind: "data_ref", ref: "data-1", recorded_type: "DataFrame" };

function okJson(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: vi.fn(async () => body),
  } as unknown as Response;
}

beforeEach(() => {
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

describe("PreviewHost — session creation + core fallback", () => {
  it("creates a session for the target and mounts the dataframe core viewer", async () => {
    createPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "core.dataframe.basic",
        kind: "dataframe",
        payload: {
          columns: ["A", "B"],
          rows: [{ A: 1, B: 2 }],
          total_rows: 1,
          page: 1,
          page_size: 50,
          total_pages: 1,
        },
      }),
    );

    render(<PreviewHost target={TARGET} />);

    await waitFor(() => expect(createPreviewSession).toHaveBeenCalledWith(TARGET, {}));
    expect(await screen.findByTestId("core-dataframe-viewer")).toBeInTheDocument();
    // table content + count
    expect(screen.getByText(/1 row × 2 columns/)).toBeInTheDocument();
  });

  it("renders the typed error viewer for an error envelope", async () => {
    createPreviewSession.mockResolvedValue(
      envelope({
        kind: "error",
        error: { code: "unknown_target", message: "no previewer matched" },
      }),
    );
    render(<PreviewHost target={TARGET} />);
    expect(await screen.findByTestId("core-error-viewer")).toBeInTheDocument();
    expect(screen.getByText(/no previewer matched/)).toBeInTheDocument();
    expect(screen.getByText(/unknown_target/)).toBeInTheDocument();
  });

  it("shows a request-error state when session creation rejects", async () => {
    createPreviewSession.mockRejectedValue(new Error("boom"));
    render(<PreviewHost target={TARGET} />);
    expect(await screen.findByTestId("preview-host-request-error")).toHaveTextContent("boom");
  });
});

describe("PreviewHost — dynamic manifest fallback (US2.3 / FR-022 / FR-029)", () => {
  it("rejects a remote module_url and falls back to the core viewer with a diagnostic", async () => {
    createPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "imaging.image.viewer",
        kind: "array",
        payload: {
          shape: [4, 4],
          dtype: "uint8",
          axes: ["y", "x"],
          ndim: 2,
          src: "data:image/png;base64,abc",
        },
        metadata: {
          complete: true,
          frontend_manifest: {
            previewer_id: "imaging.image.viewer",
            module_url: "https://evil.cdn.example/mod.js",
            export_name: "ImageViewer",
            api_version: "1",
          },
        },
      }),
    );

    render(<PreviewHost target={{ ...TARGET, recorded_type: "Image" }} />);

    // Falls back to the GENERIC core array viewer.
    expect(await screen.findByTestId("core-array-viewer")).toBeInTheDocument();
    // Diagnostic surfaced.
    await waitFor(() =>
      expect(screen.getByTestId("preview-diagnostics")).toHaveTextContent(/non-same-origin/i),
    );
  });

  it("falls back when the imported module is missing the named export", async () => {
    createPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "imaging.image.viewer",
        kind: "array",
        payload: { shape: [4, 4], dtype: "uint8", ndim: 2, src: "" },
        metadata: {
          complete: true,
          frontend_manifest: {
            previewer_id: "imaging.image.viewer",
            module_url: "/api/previews/assets/imaging.image.viewer/index.js",
            export_name: "ImageViewer",
            api_version: "1",
          },
        },
      }),
    );

    const fakeImporter = vi.fn(async () => ({ somethingElse: {} }));
    render(<PreviewHost target={{ ...TARGET, recorded_type: "Image" }} importer={fakeImporter} />);

    expect(await screen.findByTestId("core-array-viewer")).toBeInTheDocument();
    await waitFor(() => expect(fakeImporter).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByTestId("preview-diagnostics")).toHaveTextContent(
        /no export 'ImageViewer'/,
      ),
    );
  });

  it("mounts a valid same-origin previewer module via the injected importer", async () => {
    createPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "imaging.image.viewer",
        kind: "array",
        payload: { shape: [4, 4], dtype: "uint8", ndim: 2, src: "" },
        metadata: {
          complete: true,
          frontend_manifest: {
            previewer_id: "imaging.image.viewer",
            module_url: "/api/previews/assets/imaging.image.viewer/index.js",
            export_name: "ImageViewer",
            api_version: "1",
          },
        },
      }),
    );

    const mount = vi.fn((container: HTMLElement) => {
      container.textContent = "MOUNTED IMAGING VIEWER";
      return { unmount: vi.fn() };
    });
    const fakeImporter = vi.fn(async () => ({ ImageViewer: { apiVersion: "1", mount } }));

    render(<PreviewHost target={{ ...TARGET, recorded_type: "Image" }} importer={fakeImporter} />);

    await waitFor(() => expect(mount).toHaveBeenCalled());
    // Dynamic mount is used → no core fallback rendered.
    expect(screen.queryByTestId("core-array-viewer")).toBeNull();
    expect(screen.getByTestId("preview-host-dynamic-mount")).toHaveTextContent(
      "MOUNTED IMAGING VIEWER",
    );
  });

  it("mounts from the first-class envelope.frontend_manifest field (#1579)", async () => {
    // The session manager now stamps the manifest first-class on the envelope;
    // the host must read it from there (no metadata.frontend_manifest present).
    createPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "imaging.image.viewer",
        kind: "array",
        payload: { shape: [4, 4], dtype: "uint8", ndim: 2, src: "" },
        metadata: { complete: true },
        frontend_manifest: {
          previewer_id: "imaging.image.viewer",
          module_url: "/api/previews/assets/imaging.image.viewer/viewer.js",
          export_name: "ImageViewer",
          api_version: "1",
        },
      }),
    );

    const mount = vi.fn((container: HTMLElement) => {
      container.textContent = "MOUNTED FIRST-CLASS VIEWER";
      return { unmount: vi.fn() };
    });
    const fakeImporter = vi.fn(async () => ({ ImageViewer: { apiVersion: "1", mount } }));

    render(<PreviewHost target={{ ...TARGET, recorded_type: "Image" }} importer={fakeImporter} />);

    await waitFor(() => expect(mount).toHaveBeenCalled());
    expect(screen.queryByTestId("core-array-viewer")).toBeNull();
    expect(screen.getByTestId("preview-host-dynamic-mount")).toHaveTextContent(
      "MOUNTED FIRST-CLASS VIEWER",
    );
  });

  it("exposes saveArtifact through the native save dialog and session save endpoint", async () => {
    createPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "imaging.image.viewer",
        kind: "array",
        payload: { shape: [4, 4], dtype: "uint8", ndim: 2, src: "" },
        resources: [{ resource_id: "export", kind: "asset", params: { format: "svg" } }],
        metadata: { complete: true },
        frontend_manifest: {
          previewer_id: "imaging.image.viewer",
          module_url: "/api/previews/assets/imaging.image.viewer/viewer.js",
          export_name: "ImageViewer",
          api_version: "1",
        },
      }),
    );

    const capturedHost: { current: PreviewHostApi | null } = { current: null };
    const mount = vi.fn((_container: HTMLElement, host: PreviewHostApi) => {
      capturedHost.current = host;
      return { unmount: vi.fn() };
    });
    const fakeImporter = vi.fn(async () => ({ ImageViewer: { apiVersion: "1", mount } }));

    render(<PreviewHost target={{ ...TARGET, recorded_type: "Image" }} importer={fakeImporter} />);

    await waitFor(() => expect(mount).toHaveBeenCalled());
    if (!capturedHost.current) throw new Error("host API was not captured");
    await capturedHost.current.saveArtifact({ resourceId: "export", filename: "figure.svg" });

    expect(openNativeSaveDialog).toHaveBeenCalledWith({
      defaultFilename: "figure.svg",
      fileFilter: "SVG (*.svg)|*.svg|All files (*.*)|*.*",
    });
    expect(savePreviewResource).toHaveBeenCalledWith("pv-1", "export", {
      destination_path: "C:/Users/test/plot.svg",
      params: { format: "svg" },
    });
  });
});

describe("PreviewHost — collection + child routing (US4)", () => {
  it("renders the collection-level preview and drills into a sampled item", async () => {
    createPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "core.collection.basic",
        kind: "collection",
        payload: {
          count: 10,
          item_type: "Image",
          items: [
            { data_ref: "img-0", type_name: "Image" },
            { data_ref: "img-1", type_name: "Image" },
          ],
        },
        resources: [
          {
            resource_id: "item:0",
            kind: "child",
            params: { index: 0, item: { data_ref: "img-0", type_name: "Image" } },
          },
          {
            resource_id: "item:1",
            kind: "child",
            params: { index: 1, item: { data_ref: "img-1", type_name: "Image" } },
          },
        ],
      }),
    );
    fetchMock.mockResolvedValue(
      okJson({
        resource_id: "item:0",
        data: envelope({
          previewer_id: "core.array.basic",
          kind: "array",
          payload: { shape: [8, 8], dtype: "uint8", ndim: 2, src: "" },
        }) as unknown as Record<string, unknown>,
      }),
    );

    render(
      <PreviewHost target={{ ...TARGET, kind: "collection_ref", collection_item_type: "Image" }} />,
    );

    expect(await screen.findByTestId("core-collection-viewer")).toBeInTheDocument();
    expect(screen.getByTestId("collection-summary")).toHaveTextContent("10 Image (showing 2)");

    fireEvent.click(screen.getByTestId("collection-item-0"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/previews/sessions/pv-1/resources/item%3A0");
    expect(JSON.parse(url.searchParams.get("params") ?? "{}")).toEqual({
      index: 0,
      item: { data_ref: "img-0", type_name: "Image" },
    });
    // Child envelope is the generic array viewer; back button appears.
    expect(await screen.findByTestId("core-array-viewer")).toBeInTheDocument();
    expect(screen.getByTestId("preview-host-back")).toBeInTheDocument();
  });
});

describe("PreviewHost — plot viewer (FR-018 / FR-019)", () => {
  it("renders sandboxed SVG and an export control", async () => {
    createPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "core.plot.basic",
        kind: "plot",
        payload: { format: "svg", mime_type: "image/svg+xml", svg: "<svg></svg>", sandboxed: true },
        resources: [{ resource_id: "export", kind: "asset", params: { format: "svg" } }],
        diagnostics: ["sanitized SVG: removed script/handler/external-resource content"],
      }),
    );

    render(
      <PreviewHost target={{ ...TARGET, kind: "plot_artifact", recorded_type: "PlotArtifact" }} />,
    );

    const frame = (await screen.findByTestId("plot-svg-frame")) as HTMLIFrameElement;
    // Sandboxed iframe with an empty sandbox attr → no script execution.
    expect(frame.getAttribute("sandbox")).toBe("");
    expect(screen.getByTestId("plot-export-button")).toBeEnabled();
    expect(screen.getByTestId("preview-diagnostics")).toHaveTextContent(/sanitized SVG/);

    fireEvent.click(screen.getByTestId("plot-export-button"));
    await waitFor(() => expect(openNativeSaveDialog).toHaveBeenCalledTimes(1));
    expect(openNativeSaveDialog).toHaveBeenCalledWith({
      defaultFilename: "core.plot.basic.svg",
      fileFilter: "SVG (*.svg)|*.svg|All files (*.*)|*.*",
    });
    expect(savePreviewResource).toHaveBeenCalledWith("pv-1", "export", {
      destination_path: "C:/Users/test/plot.svg",
      params: { format: "svg" },
    });
  });

  it("renders a PDF artifact in a frame with an export control", async () => {
    createPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "core.plot.basic",
        kind: "plot",
        payload: {
          format: "pdf",
          mime_type: "application/pdf",
          src: "data:application/pdf;base64,JVBER",
        },
        resources: [{ resource_id: "export", kind: "asset", params: { format: "pdf" } }],
      }),
    );

    render(<PreviewHost target={{ ...TARGET, kind: "plot_artifact" }} />);
    expect(await screen.findByTestId("plot-pdf-frame")).toBeInTheDocument();
    expect(screen.getByTestId("plot-export-button")).toBeEnabled();
  });
});

describe("PreviewHost — DataFrame pagination/sort through the routed session (#1604)", () => {
  it("paginates and sorts through patchPreviewSession, never the legacy preview route", async () => {
    // #1604: the core DataFrameViewer reuses TableViewer, which now paginates
    // through the routed session PATCH (api.patchPreviewSession) — the same
    // path the ArrayViewer uses for slice selection — NOT the deleted legacy
    // deleted one-shot data-preview route. The patched envelope carries the
    // next page's payload, which flows back into the table.
    const page1 = Array.from({ length: 50 }, (_, i) => ({ A: i, B: i * 2 }));
    const page2 = Array.from({ length: 50 }, (_, i) => ({ A: 50 + i, B: (50 + i) * 2 }));
    createPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "core.dataframe.basic",
        kind: "dataframe",
        payload: {
          columns: ["A", "B"],
          rows: page1,
          total_rows: 523,
          page: 1,
          page_size: 50,
          total_pages: 11,
          sort_by: null,
          sort_dir: null,
        },
      }),
    );
    patchPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "core.dataframe.basic",
        kind: "dataframe",
        payload: {
          columns: ["A", "B"],
          rows: page2,
          total_rows: 523,
          page: 2,
          page_size: 50,
          total_pages: 11,
          sort_by: null,
          sort_dir: null,
        },
      }),
    );

    render(<PreviewHost target={TARGET} />);

    expect(await screen.findByTestId("core-dataframe-viewer")).toBeInTheDocument();
    expect(screen.getByText(/523 rows/)).toBeInTheDocument();
    expect(screen.getByLabelText("Next page")).toBeInTheDocument();

    // Next page → routed PATCH with page=2, never the legacy adapter.
    fireEvent.click(screen.getByLabelText("Next page"));
    await waitFor(() => expect(patchPreviewSession).toHaveBeenCalled());
    const [, patchQuery] = patchPreviewSession.mock.calls[0];
    expect(patchQuery).toMatchObject({ page: 2 });
    // The next page's rows land in the table from the patched envelope.
    expect(await screen.findByText("99")).toBeInTheDocument();

    // Sort by column A → routed PATCH carrying sort_by/sort_dir.
    fireEvent.click(screen.getByText("A"));
    await waitFor(() => expect(patchPreviewSession).toHaveBeenCalledTimes(2));
    const [, sortQuery] = patchPreviewSession.mock.calls[1];
    expect(sortQuery).toMatchObject({ page: 1, sort_by: "A", sort_dir: "asc" });
  });
});

describe("FR-021 cache key + FR-022 same-origin validation", () => {
  it("buildPreviewCacheKey includes ref, kind, previewer, session, query, version", () => {
    const key = buildPreviewCacheKey(
      { kind: "data_ref", ref: "data-1" },
      { slice_index: 3, page: 2, axis_indices: { "0": 1, "1": 4 }, _storage: { x: 1 } },
      { previewerId: "core.array.basic", sessionId: "pv-9", dataVersion: "v7" },
    );
    expect(key).toContain("data-1");
    expect(key).toContain("data_ref");
    expect(key).toContain("core.array.basic");
    expect(key).toContain("pv-9");
    expect(key).toContain("v7");
    expect(key).toContain("slice_index=3");
    expect(key).toContain("page=2");
    expect(key).toContain('axis_indices={"0":1,"1":4}');
    expect(key).not.toContain("[object Object]");
    // private enrichment keys never widen the key
    expect(key).not.toContain("_storage");
  });

  it("isSameOriginModuleUrl accepts site-relative paths and rejects remote/inline", () => {
    expect(isSameOriginModuleUrl("/api/previews/assets/p/index.js")).toBe(true);
    expect(isSameOriginModuleUrl("https://cdn.example/mod.js")).toBe(false);
    expect(isSameOriginModuleUrl("//cdn.example/mod.js")).toBe(false);
    expect(isSameOriginModuleUrl("data:text/javascript,alert(1)")).toBe(false);
    expect(isSameOriginModuleUrl("relative/path.js")).toBe(false);
    expect(isSameOriginModuleUrl("")).toBe(false);
  });
});

describe("PreviewHost — session-envelope cache (FR-021)", () => {
  it("does not reuse unresolved cache aliases before creating a session", async () => {
    const stale = envelope({
      session_id: "pv-stale",
      previewer_id: "core.text.basic",
      kind: "text",
      payload: { content: "stale body", truncated: false },
    });
    createPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "core.text.basic",
        kind: "text",
        payload: { content: "fresh body", truncated: false },
      }),
    );
    const getCachedEnvelope = vi.fn(() => stale);
    const cacheEnvelope = vi.fn();

    render(
      <PreviewHost
        target={TARGET}
        cacheEnvelope={cacheEnvelope}
        getCachedEnvelope={getCachedEnvelope}
        buildCacheKey={buildPreviewCacheKey}
      />,
    );

    expect(await screen.findByTestId("core-text-viewer")).toBeInTheDocument();
    expect(screen.getByText("fresh body")).toBeInTheDocument();
    expect(screen.queryByText("stale body")).toBeNull();
    expect(createPreviewSession).toHaveBeenCalledWith(TARGET, {});
    expect(getCachedEnvelope).not.toHaveBeenCalled();
    expect(cacheEnvelope).toHaveBeenCalledTimes(1);
    const [key] = cacheEnvelope.mock.calls[0];
    expect(String(key)).toContain("previewer=core.text.basic");
    expect(String(key)).toContain("session=pv-1");
  });

  it("caches patched array envelopes with resolved identity and axis_indices", async () => {
    const initialPayload = {
      shape: [4, 6, 2, 3],
      dtype: "float64",
      axes: ["t", "z", "y", "x"],
      ndim: 4,
      matrix: [
        [-1, 0, 2],
        [3, -4, 5],
      ],
      vmin: -4,
      vmax: 5,
      slice_axes: [
        { axis: 0, name: "t", size: 4, index: 1 },
        { axis: 1, name: "z", size: 6, index: 2 },
      ],
    };
    const patchedPayload = {
      ...initialPayload,
      slice_axes: [
        { axis: 0, name: "t", size: 4, index: 1 },
        { axis: 1, name: "z", size: 6, index: 4 },
      ],
    };
    createPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "core.array.basic",
        kind: "array",
        payload: initialPayload,
        metadata: { complete: true, data_version: "v7" },
      }),
    );
    patchPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "core.array.basic",
        kind: "array",
        payload: patchedPayload,
        metadata: { complete: true, data_version: "v7" },
      }),
    );
    const cacheEnvelope = vi.fn();

    render(
      <PreviewHost
        target={{ ...TARGET, recorded_type: "Array" }}
        cacheEnvelope={cacheEnvelope}
        buildCacheKey={buildPreviewCacheKey}
      />,
    );

    expect(await screen.findByTestId("core-array-viewer")).toBeInTheDocument();
    let keys = cacheEnvelope.mock.calls.map(([key]) => String(key));
    expect(keys).toHaveLength(1);
    expect(keys[0]).toContain("previewer=core.array.basic");
    expect(keys[0]).toContain("session=pv-1");
    expect(keys[0]).toContain("version=v7");
    expect(keys[0]).not.toBe(buildPreviewCacheKey({ ...TARGET, recorded_type: "Array" }, {}));
    cacheEnvelope.mockClear();

    fireEvent.change(screen.getByTestId("array-slice-slider-1"), { target: { value: "4" } });

    await waitFor(() => expect(patchPreviewSession).toHaveBeenCalledTimes(1));
    const [, patch] = patchPreviewSession.mock.calls[0];
    expect(patch).toMatchObject({ axis_indices: { "0": 1, "1": 4 } });
    await waitFor(() => expect(cacheEnvelope).toHaveBeenCalled());
    keys = cacheEnvelope.mock.calls.map(([key]) => String(key));
    expect(keys).toHaveLength(1);
    expect(
      keys.some(
        (key) =>
          key.includes("previewer=core.array.basic") &&
          key.includes("session=pv-1") &&
          key.includes("version=v7") &&
          key.includes('axis_indices={"0":1,"1":4}'),
      ),
    ).toBe(true);
    expect(keys.every((key) => !key.includes("_storage"))).toBe(true);
  });
});
