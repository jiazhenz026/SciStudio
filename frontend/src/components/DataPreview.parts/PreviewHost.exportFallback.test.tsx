import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PreviewEnvelope, PreviewTarget } from "../../types/api";

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
import type { PreviewHostApi } from "./previewerHostApi";

const TARGET: PreviewTarget = { kind: "data_ref", ref: "data-1", recorded_type: "Spectrum" };

function envelope(partial: Partial<PreviewEnvelope>): PreviewEnvelope {
  return {
    session_id: "pv-1",
    previewer_id: "spectroscopy.spectrum.viewer",
    target: TARGET,
    kind: "series",
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
  savePreviewResource.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  anchorClickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  anchorClickSpy?.mockRestore();
  anchorClickSpy = null;
  vi.unstubAllGlobals();
});

describe("PreviewHost export fallback", () => {
  it("falls back to browser download when the native save dialog returns no path", async () => {
    createPreviewSession.mockResolvedValue(
      envelope({
        payload: { points: [{ x: 400, y: 1 }], axes: { x: { label: "wavelength-nm" } } },
        resources: [
          {
            resource_id: "export_points_csv",
            kind: "asset",
            params: { format: "csv", target: "points" },
          },
        ],
        frontend_manifest: {
          previewer_id: "spectroscopy.spectrum.viewer",
          module_url: "/api/previews/assets/spectroscopy.spectrum.viewer/viewer.js",
          export_name: "SpectrumViewer",
          api_version: "1",
        },
      }),
    );
    openNativeSaveDialog.mockResolvedValueOnce({ paths: [] });
    fetchMock.mockResolvedValue(
      okJson({
        resource_id: "export_points_csv",
        data: {
          mime_type: "text/csv",
          data_uri: "data:text/csv;base64,bGFtYmRhLGludGVuc2l0eQo0MDAsMQo=",
        },
      }),
    );

    const capturedHost: { current: PreviewHostApi | null } = { current: null };
    const mount = vi.fn((_container: HTMLElement, host: PreviewHostApi) => {
      capturedHost.current = host;
      return { unmount: vi.fn() };
    });
    const fakeImporter = vi.fn(async () => ({ SpectrumViewer: { apiVersion: "1", mount } }));

    render(<PreviewHost target={TARGET} importer={fakeImporter} />);

    await waitFor(() => expect(mount).toHaveBeenCalled());
    if (!capturedHost.current) throw new Error("host API was not captured");
    await capturedHost.current.exportArtifact({
      resourceId: "export_points_csv",
      filename: "spectrum_points.csv",
      format: "csv",
    });

    expect(openNativeSaveDialog).toHaveBeenCalledWith({
      defaultFilename: "spectrum_points.csv",
      fileFilter: "CSV (*.csv)|*.csv|All files (*.*)|*.*",
    });
    expect(savePreviewResource).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
    expect(url.pathname).toBe("/api/previews/sessions/pv-1/resources/export_points_csv");
    expect(JSON.parse(url.searchParams.get("params") ?? "{}")).toEqual({
      format: "csv",
      target: "points",
    });
    expect(anchorClickSpy).toHaveBeenCalledTimes(1);
  });
});
