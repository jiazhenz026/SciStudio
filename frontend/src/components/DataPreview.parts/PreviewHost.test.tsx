/**
 * ADR-048 SPEC 1 / ADR-054 — PreviewHost tests.
 *
 * Every preview renders through a panel (#2493): the host creates a session,
 * mounts the routed panel for a `panel` envelope, shows the typed error for an
 * `error` envelope, re-creates the session with `core_only` when a panel fails,
 * re-routes only the previews a catalog change concerns, and writes the
 * session-envelope cache under the resolved identity (FR-021).
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PreviewEnvelope, PreviewTarget } from "../../types/api";

// Mock the api surface PreviewHost calls.
const createPreviewSession = vi.fn();
const patchPreviewSession = vi.fn();
const getPreviewSession = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    api: {
      ...(actual.api as Record<string, unknown>),
      createPreviewSession: (...a: unknown[]) => createPreviewSession(...a),
      patchPreviewSession: (...a: unknown[]) => patchPreviewSession(...a),
      getPreviewSession: (...a: unknown[]) => getPreviewSession(...a),
    },
  };
});

vi.mock("../../panels/PanelPreview", () => ({
  PanelPreview: ({ panelId, onFallback }: { panelId: string; onFallback: () => void }) => (
    <button data-testid={`panel-${panelId}`} onClick={onFallback}>
      Use core preview
    </button>
  ),
}));

import { PreviewHost } from "./PreviewHost";
import { requestPreviewReroute } from "../../panels/panelEvents";
import { buildPreviewCacheKey } from "../../store/previewSlice";

function envelope(partial: Partial<PreviewEnvelope>): PreviewEnvelope {
  return {
    session_id: "pv-1",
    previewer_id: "core.dataframe.basic",
    target: { kind: "data_ref", ref: "data-1" },
    kind: "panel",
    panel: { id: "core.dataframe.basic", api_version: "1.0" },
    payload: {},
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

beforeEach(() => {
  createPreviewSession.mockReset();
  patchPreviewSession.mockReset();
  getPreviewSession.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("PreviewHost — session creation", () => {
  it("creates a session for the target and mounts the routed panel", async () => {
    createPreviewSession.mockResolvedValue(envelope({}));

    render(<PreviewHost target={TARGET} />);

    await waitFor(() => expect(createPreviewSession).toHaveBeenCalledWith(TARGET, {}));
    expect(await screen.findByTestId("panel-core.dataframe.basic")).toBeInTheDocument();
  });

  it("passes a requested panel id to routing", async () => {
    createPreviewSession.mockResolvedValue(envelope({}));
    render(<PreviewHost target={TARGET} panelId="lab.table" />);
    await waitFor(() =>
      expect(createPreviewSession).toHaveBeenCalledWith(TARGET, { panel_id: "lab.table" }),
    );
  });

  it("renders the typed error viewer for an error envelope", async () => {
    createPreviewSession.mockResolvedValue(
      envelope({
        kind: "error",
        panel: null,
        previewer_id: "",
        error: { code: "unknown_target", message: "no panel matched" },
        diagnostics: ["routing diagnostic"],
      }),
    );
    render(<PreviewHost target={TARGET} />);
    expect(await screen.findByTestId("core-error-viewer")).toBeInTheDocument();
    expect(screen.getByText(/no panel matched/)).toBeInTheDocument();
    expect(screen.getByText(/unknown_target/)).toBeInTheDocument();
    expect(screen.getByTestId("preview-diagnostics")).toHaveTextContent("routing diagnostic");
  });

  it("shows a request-error state when session creation rejects", async () => {
    createPreviewSession.mockRejectedValue(new Error("boom"));
    render(<PreviewHost target={TARGET} />);
    expect(await screen.findByTestId("preview-host-request-error")).toHaveTextContent("boom");
  });

  it("resumes a child from its backend-resolved envelope without a new session", async () => {
    const child = envelope({
      session_id: "pv-child",
      panel: { id: "core.array.basic", api_version: "1.0" },
    });
    render(<PreviewHost target={child.target} initialEnvelope={child} />);
    expect(await screen.findByTestId("panel-core.array.basic")).toBeInTheDocument();
    expect(createPreviewSession).not.toHaveBeenCalled();
    expect(getPreviewSession).not.toHaveBeenCalled();
  });
});

describe("PreviewHost — core fallback", () => {
  it("re-creates the session with core_only when a panel fails", async () => {
    createPreviewSession
      .mockResolvedValueOnce(envelope({ panel: { id: "lab.table", api_version: "1.0" } }))
      .mockResolvedValueOnce(envelope({}));
    render(<PreviewHost target={TARGET} />);
    fireEvent.click(await screen.findByTestId("panel-lab.table"));
    await waitFor(() =>
      expect(createPreviewSession).toHaveBeenLastCalledWith(TARGET, { core_only: true }),
    );
    expect(await screen.findByTestId("panel-core.dataframe.basic")).toBeInTheDocument();
  });

  it("patches a resumed child session with core_only instead of routing again", async () => {
    const child = envelope({
      session_id: "pv-child",
      panel: { id: "lab.image", api_version: "1.0" },
    });
    patchPreviewSession.mockResolvedValue(
      envelope({ session_id: "pv-child", panel: { id: "core.array.basic", api_version: "1.0" } }),
    );
    render(<PreviewHost target={child.target} initialEnvelope={child} />);
    fireEvent.click(await screen.findByTestId("panel-lab.image"));
    await waitFor(() =>
      expect(patchPreviewSession).toHaveBeenCalledWith("pv-child", { core_only: true }),
    );
    expect(await screen.findByTestId("panel-core.array.basic")).toBeInTheDocument();
    expect(createPreviewSession).not.toHaveBeenCalled();
  });
});

describe("FR-021 cache key", () => {
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

  it("does not reuse unresolved cache aliases before creating a session", async () => {
    const stale = envelope({ session_id: "pv-stale", previewer_id: "core.text.basic" });
    createPreviewSession.mockResolvedValue(
      envelope({
        previewer_id: "core.text.basic",
        panel: { id: "core.text.basic", api_version: "1.0" },
        metadata: { complete: true, data_version: "v7" },
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

    expect(await screen.findByTestId("panel-core.text.basic")).toBeInTheDocument();
    expect(createPreviewSession).toHaveBeenCalledWith(TARGET, {});
    expect(getCachedEnvelope).not.toHaveBeenCalled();
    expect(cacheEnvelope).toHaveBeenCalledTimes(1);
    const [key] = cacheEnvelope.mock.calls[0];
    expect(String(key)).toContain("previewer=core.text.basic");
    expect(String(key)).toContain("session=pv-1");
    expect(String(key)).toContain("version=v7");
  });
});

describe("#2465 — only affected previews re-route", () => {
  it("re-creates the session for a matching type and leaves other previews mounted", async () => {
    const IMAGE_TARGET: PreviewTarget = { kind: "data_ref", ref: "img" };
    createPreviewSession.mockImplementation(async (target: PreviewTarget) =>
      target.ref === "img"
        ? envelope({
            session_id: `pv-img-${createPreviewSession.mock.calls.length}`,
            panel: { id: "lab.image", api_version: "1.0" },
            target: {
              kind: "data_ref",
              ref: "img",
              recorded_type: "Image",
              type_chain: ["DataObject", "Array", "Image"],
            },
          })
        : envelope({
            session_id: `pv-table-${createPreviewSession.mock.calls.length}`,
            target: {
              kind: "data_ref",
              ref: "data-1",
              recorded_type: "DataFrame",
              type_chain: ["DataObject", "DataFrame"],
            },
          }),
    );
    render(
      <>
        <PreviewHost target={IMAGE_TARGET} />
        <PreviewHost target={TARGET} />
      </>,
    );
    await waitFor(() => expect(createPreviewSession).toHaveBeenCalledTimes(2));

    requestPreviewReroute({ types: ["Array"] });
    await waitFor(() => expect(createPreviewSession).toHaveBeenCalledTimes(3));
    expect(createPreviewSession.mock.calls[2][0].ref).toBe("img");

    requestPreviewReroute({ types: ["Collection[Image]"] });
    requestPreviewReroute({ choiceType: "Spectrum" });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(createPreviewSession).toHaveBeenCalledTimes(3);

    // A choice for the table's most specific type re-routes only that preview.
    requestPreviewReroute({ choiceType: "DataFrame" });
    await waitFor(() => expect(createPreviewSession).toHaveBeenCalledTimes(4));
    expect(createPreviewSession.mock.calls[3][0].ref).toBe("data-1");
  });
});
