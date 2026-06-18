import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PreviewEnvelope, PreviewTarget } from "../../types/api";

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

import { PreviewHost } from "./PreviewHost";
import type { PreviewHostApi } from "./previewerHostApi";

const TARGET: PreviewTarget = { kind: "data_ref", ref: "data-1", recorded_type: "DataFrame" };

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
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
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

    expect(await screen.findByTestId("core-array-viewer")).toBeInTheDocument();
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
    expect(screen.queryByTestId("core-array-viewer")).toBeNull();
    expect(screen.getByTestId("preview-host-dynamic-mount")).toHaveTextContent(
      "MOUNTED IMAGING VIEWER",
    );
  });

  it("mounts from the first-class envelope.frontend_manifest field (#1579)", async () => {
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

  it("updates a dynamic child preview through host session.patchQuery", async () => {
    const childManifest = {
      previewer_id: "imaging.image.viewer",
      module_url: "/api/previews/assets/imaging.image.viewer/viewer.js",
      export_name: "ImageViewer",
      api_version: "1",
    };
    createPreviewSession.mockResolvedValue(
      envelope({
        session_id: "pv-root",
        previewer_id: "core.collection.basic",
        kind: "collection",
        payload: {
          count: 1,
          item_type: "Image",
          items: [{ data_ref: "img-0", type_name: "Image" }],
        },
        resources: [
          {
            resource_id: "item:0",
            kind: "child",
            params: { index: 0, item: { data_ref: "img-0", type_name: "Image" } },
          },
        ],
      }),
    );
    fetchMock.mockResolvedValue(
      okJson({
        resource_id: "item:0",
        data: envelope({
          session_id: "pv-child",
          previewer_id: "imaging.image.viewer",
          kind: "array",
          payload: { marker: "before" },
          frontend_manifest: childManifest,
        }) as unknown as Record<string, unknown>,
      }),
    );
    patchPreviewSession.mockResolvedValue(
      envelope({
        session_id: "pv-child",
        previewer_id: "imaging.image.viewer",
        kind: "array",
        payload: { marker: "after" },
        frontend_manifest: childManifest,
      }),
    );

    const capturedHosts: PreviewHostApi[] = [];
    const update = vi.fn((next: PreviewEnvelope) => {
      screen.getByTestId("preview-host-dynamic-mount").textContent = String(next.payload.marker);
    });
    const mount = vi.fn((container: HTMLElement, host: PreviewHostApi) => {
      capturedHosts.push(host);
      container.textContent = String(host.envelope.payload.marker);
      return { update, unmount: vi.fn() };
    });
    const fakeImporter = vi.fn(async () => ({ ImageViewer: { apiVersion: "1", mount } }));

    render(
      <PreviewHost
        target={{ ...TARGET, kind: "collection_ref", collection_item_type: "Image" }}
        importer={fakeImporter}
      />,
    );

    expect(await screen.findByTestId("core-collection-viewer")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("collection-item-0"));

    await waitFor(() => expect(mount).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("preview-host-dynamic-mount")).toHaveTextContent("before");

    const host = capturedHosts[capturedHosts.length - 1];
    if (!host) throw new Error("host API was not captured");
    await host.session.patchQuery({ axis_indices: { "0": 2 } });

    await waitFor(() =>
      expect(patchPreviewSession).toHaveBeenCalledWith("pv-child", {
        axis_indices: { "0": 2 },
      }),
    );
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(mount).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("preview-host-dynamic-mount")).toHaveTextContent("after");
  });
});
