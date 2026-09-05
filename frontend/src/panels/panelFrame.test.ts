/**
 * ADR-054 spec 1, T-005 — the sandboxed frame, the token, the handshake, the
 * bounded waits, and teardown.
 *
 * What is real here: the `iframe` production code creates, its `sandbox`
 * attribute, its `contentWindow`, the `init` envelope the host posts into that
 * window, and every `MessageEvent` the "panel" posts back carrying that real
 * window as `event.source`. What is substituted: the load observation only —
 * jsdom never fetches an iframe's `src`, so a real frame never fires `load`.
 * See `__tests__/support.ts`.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { createRealFrameSeam, flush, receivedOfType } from "./__tests__/support";
import {
  PANEL_FRAME_LOAD_TIMEOUT_MS,
  PANEL_FRAME_SANDBOX,
  PANEL_HANDSHAKE_TIMEOUT_MS,
  PANEL_READ_TIMEOUT_MS,
  PANEL_STATE_REQUEST_TIMEOUT_MS,
  createSandboxedPanelFrame,
  isPanelDocumentUrl,
  issuePanelToken,
  mountPanelFrame,
} from "./panelFrame";
import type { PanelFrameConnection, PanelFrameMountOptions } from "./panelFrame";
import { panelToHostMessage } from "./panelMessages";

const DOCUMENT_URL = "/api/panels/assets/core.table/index.html";
const TOKEN = "mount-token-under-test";

function container(): HTMLDivElement {
  const element = document.createElement("div");
  document.body.appendChild(element);
  return element;
}

function mountOptions(
  overrides: Partial<PanelFrameMountOptions> & Pick<PanelFrameMountOptions, "container">,
): PanelFrameMountOptions {
  return {
    panelId: "core.table",
    documentUrl: DOCUMENT_URL,
    acceptedApiVersion: "1",
    issueToken: () => TOKEN,
    loadTimeoutMs: 250,
    handshakeTimeoutMs: 250,
    readTimeoutMs: 250,
    init: {
      capability: "displaying",
      target: { rows: [{ a: 1 }] },
      bindings: null,
      readLimits: { max_rows: 500, max_bytes: 1_000_000 },
      assetBaseUrl: "/api/panels/assets/core.table/",
      restoredState: null,
    },
    ...overrides,
  };
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("the sandbox is one permission (FR-008)", () => {
  it("sets exactly `allow-scripts` on the real frame", () => {
    const handle = createSandboxedPanelFrame({
      panelId: "core.table",
      documentUrl: DOCUMENT_URL,
      title: "Table",
    });
    const element = handle.element as HTMLIFrameElement;

    expect(PANEL_FRAME_SANDBOX).toBe("allow-scripts");
    expect(element.getAttribute("sandbox")).toBe("allow-scripts");
    expect(element.tagName).toBe("IFRAME");

    // The attribute is read as a token list rather than a substring, so a
    // future `allow-scripts allow-same-origin` could not pass this.
    const granted = (element.getAttribute("sandbox") ?? "").split(/\s+/).filter(Boolean);
    expect(granted).toEqual(["allow-scripts"]);

    for (const withheld of [
      "allow-same-origin",
      "allow-forms",
      "allow-popups",
      "allow-modals",
      "allow-downloads",
      "allow-top-navigation",
      "allow-top-navigation-by-user-activation",
      "allow-pointer-lock",
      "allow-presentation",
      "allow-popups-to-escape-sandbox",
      "allow-storage-access-by-user-activation",
    ]) {
      expect(granted).not.toContain(withheld);
    }

    expect(element.getAttribute("src")).toBe(DOCUMENT_URL);
    expect(element.getAttribute("title")).toBe("Table");
    handle.dispose();
  });

  it("mounts the frame the host actually created into the host's container", async () => {
    const seam = createRealFrameSeam();
    const host = container();
    const mounting = mountPanelFrame(mountOptions({ container: host, frameFactory: seam.factory }));

    const frame = host.querySelector("iframe");
    expect(frame).not.toBeNull();
    expect(frame?.getAttribute("sandbox")).toBe("allow-scripts");

    seam.reportLoaded();
    await flush();
    seam.fromPanel(TOKEN, "ready", { api_version: "1" });
    const result = await mounting;
    expect(result.ok).toBe(true);
    if (result.ok) result.connection.teardown();
  });
});

describe("the entry document URL", () => {
  it.each([
    "/api/panels/assets/core.table/index.html",
    "/api/previews/assets/core.table/index.html",
    "/api/panels/assets/pkg.viewer/nested/index.html",
  ])("accepts the same-origin path %s", (url) => {
    expect(isPanelDocumentUrl(url)).toBe(true);
  });

  it.each([
    ["a remote document", "https://cdn.example.com/panel.html"],
    ["a protocol-relative document", "//cdn.example.com/panel.html"],
    ["an inline document", "data:text/html,<h1>hi</h1>"],
    ["a blob document", "blob:http://localhost/1234"],
    ["a javascript URL", "javascript:alert(1)"],
    ["a relative path", "panels/core.table/index.html"],
    ["an empty string", ""],
    ["whitespace", "   "],
    ["a non-string", 7],
  ])("refuses %s", (_label, url) => {
    expect(isPanelDocumentUrl(url)).toBe(false);
  });
});

describe("the per-mount token", () => {
  it("issues a different token every time", () => {
    const tokens = new Set(Array.from({ length: 50 }, () => issuePanelToken()));
    expect(tokens.size).toBe(50);
    for (const token of tokens) expect(token.length).toBeGreaterThan(8);
  });
});

describe("the bounded waits are named constants", () => {
  it("are all finite and ordered sensibly", () => {
    expect(PANEL_FRAME_LOAD_TIMEOUT_MS).toBeGreaterThan(0);
    expect(PANEL_HANDSHAKE_TIMEOUT_MS).toBeGreaterThan(0);
    expect(PANEL_READ_TIMEOUT_MS).toBeGreaterThan(PANEL_HANDSHAKE_TIMEOUT_MS);
    expect(PANEL_STATE_REQUEST_TIMEOUT_MS).toBeLessThan(PANEL_HANDSHAKE_TIMEOUT_MS);
  });
});

describe("the handshake (FR-009)", () => {
  it("posts init once the document has loaded, and not before", async () => {
    const seam = createRealFrameSeam();
    const host = container();
    const mounting = mountPanelFrame(
      mountOptions({
        container: host,
        frameFactory: seam.factory,
        init: {
          capability: "producing",
          target: null,
          bindings: {
            frame: { type: "DataFrame", snapshot: { rows: 3 } },
            spectrum: { type: "Spectrum", snapshot: { points: 9 } },
          },
          readLimits: { max_rows: 200, max_bytes: 4096 },
          assetBaseUrl: "/api/panels/assets/editor.table/",
          restoredState: { selection: [4] },
        },
      }),
    );

    seam.observe();
    await flush();
    expect(seam.received()).toHaveLength(0);

    seam.reportLoaded();
    await flush();

    const inits = receivedOfType(seam, "init");
    expect(inits).toHaveLength(1);
    expect(inits[0]).toEqual({
      scistudio_panel: 1,
      token: TOKEN,
      type: "init",
      payload: {
        api_version: "1",
        panel_id: "core.table",
        capability: "producing",
        target: null,
        bindings: {
          frame: { type: "DataFrame", snapshot: { rows: 3 } },
          spectrum: { type: "Spectrum", snapshot: { points: 9 } },
        },
        read_limits: { max_rows: 200, max_bytes: 4096 },
        asset_base_url: "/api/panels/assets/editor.table/",
        restored_state: { selection: [4] },
      },
    });

    seam.fromPanel(TOKEN, "ready", { api_version: "1" });
    const result = await mounting;
    expect(result.ok).toBe(true);
    if (result.ok) result.connection.teardown();
  });

  it("treats a panel that never answers as a load failure", async () => {
    const seam = createRealFrameSeam();
    const result = await (async () => {
      const mounting = mountPanelFrame(
        mountOptions({ container: container(), frameFactory: seam.factory }),
      );
      seam.reportLoaded();
      return mounting;
    })();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.failure.reason).toBe("handshake_timeout");
      expect(result.failure.panelId).toBe("core.table");
      expect(result.failure.message).toContain("core.table");
      expect(result.failure.message).toContain("ready");
    }
  });

  it("ignores a `ready` carrying another mount's token", async () => {
    const seam = createRealFrameSeam();
    const mounting = mountPanelFrame(
      mountOptions({ container: container(), frameFactory: seam.factory }),
    );
    seam.reportLoaded();
    await flush();

    seam.raw(panelToHostMessage("a-different-mount", "ready", { api_version: "1" }));
    const result = await mounting;

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.failure.reason).toBe("handshake_timeout");
  });

  it("ignores a correctly tokened `ready` from a window that is not the frame", async () => {
    const seam = createRealFrameSeam();
    const mounting = mountPanelFrame(
      mountOptions({ container: container(), frameFactory: seam.factory }),
    );
    seam.reportLoaded();
    await flush();

    seam.raw(panelToHostMessage(TOKEN, "ready", { api_version: "1" }), seam.otherWindow());
    seam.raw(panelToHostMessage(TOKEN, "ready", { api_version: "1" }), null);
    const result = await mounting;

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.failure.reason).toBe("handshake_timeout");
  });

  it("ignores malformed traffic from the frame and still times out", async () => {
    const seam = createRealFrameSeam();
    const mounting = mountPanelFrame(
      mountOptions({ container: container(), frameFactory: seam.factory }),
    );
    seam.reportLoaded();
    await flush();

    seam.raw("ready");
    seam.raw({ type: "ready" });
    seam.raw({ scistudio_panel: 1, token: TOKEN, type: "ready" });
    seam.raw({ scistudio_panel: 1, token: TOKEN, type: "ready", payload: {} });
    const result = await mounting;

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.failure.reason).toBe("handshake_timeout");
  });

  it("fails the mount when the panel reports an error instead of ready", async () => {
    const seam = createRealFrameSeam();
    const mounting = mountPanelFrame(
      mountOptions({ container: container(), frameFactory: seam.factory }),
    );
    seam.reportLoaded();
    await flush();
    seam.fromPanel(TOKEN, "error", { message: "its own script threw", detail: null });

    const result = await mounting;
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.failure.reason).toBe("panel_error");
      expect(result.failure.message).toContain("its own script threw");
    }
  });
});

describe("the version gate at the handshake (FR-004)", () => {
  it("refuses a panel declaring a version the host does not accept", async () => {
    const seam = createRealFrameSeam();
    const mounting = mountPanelFrame(
      mountOptions({ container: container(), frameFactory: seam.factory }),
    );
    seam.reportLoaded();
    await flush();
    seam.fromPanel(TOKEN, "ready", { api_version: "2" });

    const result = await mounting;
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.failure.reason).toBe("version_mismatch");
      expect(result.failure.message).toContain("core.table");
      expect(result.failure.message).toContain('"2"');
      expect(result.failure.message).toContain('"1"');
    }
  });
});

describe("the load wait", () => {
  it("fails the mount when the document never finishes loading", async () => {
    const seam = createRealFrameSeam();
    const host = container();
    const result = await mountPanelFrame(
      mountOptions({ container: host, frameFactory: seam.factory }),
    );

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.failure.reason).toBe("load_timeout");
      expect(result.failure.message).toContain("core.table");
    }
    expect(host.querySelector("iframe")).toBeNull();
  });

  it("fails the mount when the document reports a load error", async () => {
    const seam = createRealFrameSeam();
    const mounting = mountPanelFrame(
      mountOptions({ container: container(), frameFactory: seam.factory }),
    );
    seam.reportLoadFailure("404 from the asset route");

    const result = await mounting;
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.failure.reason).toBe("load_timeout");
      expect(result.failure.message).toContain("404 from the asset route");
    }
  });
});

describe("refusals that happen before a frame exists", () => {
  it("refuses a document that is not a same-origin asset path", async () => {
    const seam = createRealFrameSeam();
    const host = container();
    const result = await mountPanelFrame(
      mountOptions({
        container: host,
        frameFactory: seam.factory,
        documentUrl: "https://cdn.example.com/panel.html",
      }),
    );

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.failure.reason).toBe("invalid_document_url");
      expect(result.failure.message).toContain("core.table");
    }
    expect(seam.created()).toBe(false);
    expect(host.querySelector("iframe")).toBeNull();
  });

  it("reports the frame mechanism being unavailable rather than throwing", async () => {
    const host = container();
    const result = await mountPanelFrame(
      mountOptions({
        container: host,
        frameFactory: () => {
          throw new Error("frames are not available here");
        },
      }),
    );

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.failure.reason).toBe("frame_unavailable");
      expect(result.failure.message).toContain("frames are not available here");
    }
  });
});

async function mountReady(
  overrides: Partial<PanelFrameMountOptions> = {},
): Promise<{ connection: PanelFrameConnection; seam: ReturnType<typeof createRealFrameSeam> }> {
  const seam = createRealFrameSeam();
  const mounting = mountPanelFrame(
    mountOptions({ container: container(), frameFactory: seam.factory, ...overrides }),
  );
  seam.reportLoaded();
  await flush();
  seam.fromPanel(TOKEN, "ready", { api_version: "1" });
  const result = await mounting;
  if (!result.ok) throw new Error(`mount failed: ${result.failure.message}`);
  seam.clearReceived();
  return { connection: result.connection, seam };
}

describe("the bounded windowed read (FR-010)", () => {
  it("answers a read with `read_result` carrying the request id", async () => {
    const { connection, seam } = await mountReady();
    const outcome = await connection.answerRead(
      { request_id: "r1", query: { offset: 0 } },
      async (query) => ({
        rows: [{ a: 1 }],
        echoed: query,
      }),
    );
    await flush();

    expect(outcome).toEqual({ status: "answered" });
    expect(receivedOfType(seam, "read_result")).toEqual([
      {
        scistudio_panel: 1,
        token: TOKEN,
        type: "read_result",
        payload: {
          request_id: "r1",
          window: { rows: [{ a: 1 }], echoed: { offset: 0 } },
        },
      },
    ]);
    connection.teardown();
  });

  it("fails one read through the error channel, tied to its request id", async () => {
    const { connection, seam } = await mountReady();
    const outcome = await connection.answerRead({ request_id: "r2", query: {} }, async () => {
      throw new Error("the provider refused");
    });
    await flush();

    expect(outcome).toEqual({ status: "failed", message: "the provider refused" });
    const errors = receivedOfType(seam, "error");
    expect(errors).toHaveLength(1);
    expect(errors[0].payload).toEqual({
      code: "read_failed",
      message: "the provider refused",
      request_id: "r2",
    });
    connection.teardown();
  });

  it("gives up on a read that never answers", async () => {
    const { connection, seam } = await mountReady();
    const outcome = await connection.answerRead(
      { request_id: "r3", query: {} },
      () => new Promise<unknown>(() => undefined),
    );
    await flush();

    expect(outcome).toEqual({ status: "timed_out" });
    expect(receivedOfType(seam, "error")[0].payload).toMatchObject({
      code: "read_timeout",
      request_id: "r3",
    });
    connection.teardown();
  });

  it("resolves an in-flight read as cancelled when the mount is torn down", async () => {
    const { connection, seam } = await mountReady();
    const pending = connection.answerRead(
      { request_id: "r4", query: {} },
      () => new Promise<unknown>(() => undefined),
    );

    connection.teardown();
    const outcome = await pending;
    await flush();

    expect(outcome).toEqual({ status: "cancelled" });
    expect(receivedOfType(seam, "read_result")).toHaveLength(0);
    expect(receivedOfType(seam, "error")).toHaveLength(0);
  });
});

describe("teardown", () => {
  it("tells the panel, removes the frame, and stops listening", async () => {
    const { connection, seam } = await mountReady();
    const element = seam.element();
    expect(element.isConnected).toBe(true);

    connection.teardown();
    await flush();

    expect(receivedOfType(seam, "teardown")).toHaveLength(1);
    expect(element.isConnected).toBe(false);
    expect(connection.disposed).toBe(true);

    // The listener is gone: nothing the dead frame posts is acted on.
    seam.clearReceived();
    seam.raw(panelToHostMessage(TOKEN, "emit", { code: "x = 1" }));
    expect(connection.send("update", { reason: "late", changed: {} })).toBe(false);
  });

  it("is idempotent", async () => {
    const { connection } = await mountReady();
    connection.teardown();
    expect(() => connection.teardown()).not.toThrow();
    expect(connection.disposed).toBe(true);
  });
});

describe("the optional state hook (FR-031)", () => {
  it("keeps a serialisable snapshot the panel hands back", async () => {
    const { connection, seam } = await mountReady();
    const pending = connection.requestState(250);
    await flush();

    expect(receivedOfType(seam, "state_request")).toHaveLength(1);
    seam.fromPanel(TOKEN, "state", { state: { selection: [2, 3] } });

    await expect(pending).resolves.toEqual({ kept: true, state: { selection: [2, 3] } });
    connection.teardown();
  });

  it("discards a snapshot that will not serialise rather than failing", async () => {
    const { connection, seam } = await mountReady();
    const pending = connection.requestState(250);
    await flush();

    const cyclic: Record<string, unknown> = { name: "selection" };
    cyclic.self = cyclic;
    // Dispatched directly, because a structured clone would refuse to carry it
    // across a real frame boundary — this is the snapshot a same-realm panel
    // document can still hand back.
    seam.raw({
      scistudio_panel: 1,
      token: TOKEN,
      type: "state",
      payload: { state: cyclic },
    });

    const snapshot = await pending;
    expect(snapshot.kept).toBe(false);
    connection.teardown();
  });

  it("treats a panel that does not implement the hook as having no state", async () => {
    const { connection } = await mountReady();
    await expect(connection.requestState(250)).resolves.toEqual({
      kept: false,
      reason: "the panel did not answer the state request",
    });
    connection.teardown();
  });
});

describe("messages after the handshake", () => {
  it("routes only well-formed, correctly tokened messages from this frame", async () => {
    const seen: string[] = [];
    const { connection, seam } = await mountReady({
      onMessage: (message) => seen.push(message.type),
    });

    seam.fromPanel(TOKEN, "emit", { code: "x = 1" });
    seam.raw(panelToHostMessage("another-mount", "emit", { code: "x = 2" }));
    seam.raw(panelToHostMessage(TOKEN, "emit", { code: "x = 3" }), seam.otherWindow());
    seam.raw({ nonsense: true });
    seam.fromPanel(TOKEN, "error", { message: "non-fatal", detail: null });

    expect(seen).toEqual(["emit", "error"]);
    connection.teardown();
  });

  it("does not throw when the panel posts something with a hostile getter", async () => {
    const onMessage = vi.fn();
    const { connection, seam } = await mountReady({ onMessage });
    expect(() =>
      seam.raw({
        scistudio_panel: 1,
        token: TOKEN,
        type: "emit",
        get payload(): never {
          throw new Error("boom");
        },
      }),
    ).not.toThrow();
    expect(onMessage).not.toHaveBeenCalled();
    connection.teardown();
  });
});
