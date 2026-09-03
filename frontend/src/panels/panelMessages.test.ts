/**
 * ADR-054 spec 1, T-005 — the message contract's envelope and its total guards.
 *
 * Every guard is fed input a hostile sandboxed document could really send: a
 * primitive, an array, an object whose property access throws, a cyclic object.
 * None of it is mocked; the assertions are that the guard answers `false` and
 * that it does not throw, because a guard that threw would turn a panel's
 * malformed message into a host-side crash.
 */

import { describe, expect, it } from "vitest";

import {
  HOST_TO_PANEL_TYPES,
  PANEL_MESSAGE_MARKER,
  PANEL_TO_HOST_TYPES,
  hostToPanelMessage,
  isAcceptedApiVersion,
  isHostToPanelMessage,
  isPanelEnvelope,
  isPanelToHostMessage,
  panelToHostMessage,
  parseHostToPanelMessage,
  parsePanelToHostMessage,
  sanitizePanelState,
} from "./panelMessages";

const TOKEN = "mount-token-1";

describe("the D-011 envelope", () => {
  it("is the same shape in both directions", () => {
    const outbound = hostToPanelMessage(TOKEN, "state_request", {});
    const inbound = panelToHostMessage(TOKEN, "ready", { api_version: "1" });

    expect(outbound).toEqual({
      scistudio_panel: 1,
      token: TOKEN,
      type: "state_request",
      payload: {},
    });
    expect(inbound).toEqual({
      scistudio_panel: 1,
      token: TOKEN,
      type: "ready",
      payload: { api_version: "1" },
    });
    expect(PANEL_MESSAGE_MARKER).toBe(1);
  });

  it("names six host-to-panel types and five panel-to-host types", () => {
    expect([...HOST_TO_PANEL_TYPES]).toEqual([
      "init",
      "update",
      "read_result",
      "error",
      "state_request",
      "teardown",
    ]);
    expect([...PANEL_TO_HOST_TYPES]).toEqual(["ready", "read", "emit", "error", "state"]);
  });
});

describe("isPanelEnvelope", () => {
  const wellFormed = panelToHostMessage(TOKEN, "ready", { api_version: "1" });

  it("accepts an envelope carrying this mount's token", () => {
    expect(isPanelEnvelope(wellFormed, TOKEN)).toBe(true);
  });

  it.each([
    ["a different token", { ...wellFormed, token: "some-other-mount" }],
    ["no token", { ...wellFormed, token: undefined }],
    ["a numeric token", { ...wellFormed, token: 1 }],
    ["a missing marker", { token: TOKEN, type: "ready", payload: {} }],
    ["a wrong marker", { ...wellFormed, scistudio_panel: 2 }],
    ["a non-string type", { ...wellFormed, type: 7 }],
    ["a non-object payload", { ...wellFormed, payload: "ready" }],
    ["no payload", { scistudio_panel: 1, token: TOKEN, type: "ready" }],
  ])("rejects an envelope with %s", (_label, value) => {
    expect(isPanelEnvelope(value, TOKEN)).toBe(false);
  });

  it.each([
    ["null", null],
    ["undefined", undefined],
    ["a string", "ready"],
    ["a number", 42],
    ["an array", [1, 2, 3]],
    ["a function", () => undefined],
  ])("rejects %s", (_label, value) => {
    expect(isPanelEnvelope(value, TOKEN)).toBe(false);
  });

  it("rejects everything when the mount has no token", () => {
    expect(isPanelEnvelope(wellFormed, "")).toBe(false);
  });

  it("does not throw when property access itself throws", () => {
    const hostile = {
      scistudio_panel: 1,
      token: TOKEN,
      type: "ready",
      get payload(): never {
        throw new Error("boom");
      },
    };
    expect(() => isPanelEnvelope(hostile, TOKEN)).not.toThrow();
    expect(isPanelEnvelope(hostile, TOKEN)).toBe(false);
    expect(() => isPanelToHostMessage(hostile, TOKEN)).not.toThrow();
    expect(isPanelToHostMessage(hostile, TOKEN)).toBe(false);
  });

  it("does not throw on a cyclic object", () => {
    const cyclic: Record<string, unknown> = { scistudio_panel: 1, token: TOKEN, type: "ready" };
    cyclic.payload = cyclic;
    expect(() => isPanelToHostMessage(cyclic, TOKEN)).not.toThrow();
    // The payload is an object, but it carries no `api_version`.
    expect(isPanelToHostMessage(cyclic, TOKEN)).toBe(false);
  });
});

describe("isPanelToHostMessage", () => {
  it.each([
    ["ready", { api_version: "1" }],
    ["read", { request_id: "r1", query: { offset: 0 } }],
    ["emit", { code: "df = df.head()" }],
    ["error", { message: "the panel gave up", detail: null }],
    ["state", { state: { selection: [1, 2] } }],
  ] as const)("accepts a well-formed %s", (type, payload) => {
    const message = panelToHostMessage(TOKEN, type as any, payload as any);
    expect(isPanelToHostMessage(message, TOKEN)).toBe(true);
    expect(parsePanelToHostMessage(message, TOKEN)).toBe(message);
  });

  it.each([
    ["an unknown type", { scistudio_panel: 1, token: TOKEN, type: "escape", payload: {} }],
    ["a host-to-panel type", { scistudio_panel: 1, token: TOKEN, type: "init", payload: {} }],
    ["ready without a version", { scistudio_panel: 1, token: TOKEN, type: "ready", payload: {} }],
    [
      "read without a request id",
      { scistudio_panel: 1, token: TOKEN, type: "read", payload: { query: {} } },
    ],
    [
      "read without a query",
      { scistudio_panel: 1, token: TOKEN, type: "read", payload: { request_id: "r1" } },
    ],
    [
      "emit with non-string code",
      { scistudio_panel: 1, token: TOKEN, type: "emit", payload: { code: { drop: true } } },
    ],
    ["state with no state field", { scistudio_panel: 1, token: TOKEN, type: "state", payload: {} }],
  ])("rejects %s", (_label, value) => {
    expect(isPanelToHostMessage(value, TOKEN)).toBe(false);
    expect(parsePanelToHostMessage(value, TOKEN)).toBeNull();
  });

  it("rejects a well-formed message carrying another mount's token", () => {
    const message = panelToHostMessage("a-previous-mount", "emit", { code: "x = 1" });
    expect(isPanelToHostMessage(message, TOKEN)).toBe(false);
  });
});

describe("isHostToPanelMessage", () => {
  const init = hostToPanelMessage(TOKEN, "init", {
    api_version: "1",
    panel_id: "core.table",
    capability: "displaying",
    target: { rows: [] },
    bindings: null,
    read_limits: { max_rows: 500, max_bytes: 1_000_000 },
    asset_base_url: "/api/panels/assets/core.table/",
    restored_state: null,
  });

  it("accepts a well-formed init", () => {
    expect(isHostToPanelMessage(init, TOKEN)).toBe(true);
    expect(parseHostToPanelMessage(init, TOKEN)).toBe(init);
  });

  it("rejects an init declaring a capability that is not one of the two", () => {
    const bogus = { ...init, payload: { ...init.payload, capability: "administrating" } };
    expect(isHostToPanelMessage(bogus, TOKEN)).toBe(false);
  });

  it("rejects an init carrying another mount's token", () => {
    expect(isHostToPanelMessage({ ...init, token: "elsewhere" }, TOKEN)).toBe(false);
  });

  it("accepts the empty-payload types", () => {
    expect(isHostToPanelMessage(hostToPanelMessage(TOKEN, "teardown", {}), TOKEN)).toBe(true);
    expect(isHostToPanelMessage(hostToPanelMessage(TOKEN, "state_request", {}), TOKEN)).toBe(true);
  });

  it("rejects an error without a code", () => {
    const bogus = {
      scistudio_panel: 1,
      token: TOKEN,
      type: "error",
      payload: { message: "nope", request_id: null },
    };
    expect(isHostToPanelMessage(bogus, TOKEN)).toBe(false);
  });
});

describe("isAcceptedApiVersion (FR-004, D-010)", () => {
  it("accepts a panel whose major version is the accepted one", () => {
    expect(isAcceptedApiVersion("1", "1")).toBe(true);
    expect(isAcceptedApiVersion("1.0", "1.4")).toBe(true);
    expect(isAcceptedApiVersion("1.9.3", "1")).toBe(true);
  });

  it("refuses a panel built for a different major version", () => {
    expect(isAcceptedApiVersion("2", "1")).toBe(false);
    expect(isAcceptedApiVersion("1", "2")).toBe(false);
    expect(isAcceptedApiVersion("0.9", "1.0")).toBe(false);
  });

  it("refuses anything that is not a version", () => {
    expect(isAcceptedApiVersion(undefined, "1")).toBe(false);
    expect(isAcceptedApiVersion("1", undefined)).toBe(false);
    expect(isAcceptedApiVersion("", "1")).toBe(false);
    expect(isAcceptedApiVersion("1", "  ")).toBe(false);
    expect(isAcceptedApiVersion(1, 1)).toBe(false);
  });
});

describe("sanitizePanelState (FR-031)", () => {
  it("keeps a serialisable snapshot, detached from the panel's object", () => {
    const original = { selection: [1, 2], label: "peak" };
    const result = sanitizePanelState(original);
    expect(result).toEqual({ kept: true, state: { selection: [1, 2], label: "peak" } });
    if (result.kept) expect(result.state).not.toBe(original);
  });

  it("discards a cyclic snapshot rather than failing", () => {
    const cyclic: Record<string, unknown> = { name: "selection" };
    cyclic.self = cyclic;
    const result = sanitizePanelState(cyclic);
    expect(result.kept).toBe(false);
    if (!result.kept) expect(result.reason).toContain("serialise");
  });

  it("discards a snapshot JSON cannot encode", () => {
    expect(sanitizePanelState({ size: 1n }).kept).toBe(false);
    expect(sanitizePanelState(undefined).kept).toBe(false);
    expect(sanitizePanelState(null).kept).toBe(false);
  });
});
