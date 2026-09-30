/**
 * ADR-055 identity seam and Spec 4 — capability accessor tests (#2304, #2322).
 *
 * The open-source edition injects no declaration, so the default must read as
 * every capability off; a declaration from an edition must come through typed;
 * a capability this frontend does not know is ignored; and a malformed or
 * unsafe field must read as off rather than throw.
 */

import { afterEach, describe, expect, it } from "vitest";

import {
  downloadRoutePath,
  getCapabilities,
  isCapabilityEnabled,
  isRoutePath,
  resetCapabilitiesCacheForTests,
} from "./capabilities";

const ALL_OFF = { version: 0, identity: null, transfer: null, aiChatDisabled: false, update: null };
const IDENTITY = { user: "alice", logoutUrl: "/api/test-edition/session/logout" };
const TRANSFER = {
  inlineMaxBytes: 8 * 1024 * 1024,
  downloadUrlTemplate: "/api/test-edition/transfer/download?path={path}",
};
const UPDATE = {
  statusUrl: "/api/test-edition/update/status",
  restartUrl: "/api/test-edition/update/restart",
};

/** Route paths the backend would never declare; the accessor must refuse them too. */
const NOT_ROUTE_PATHS = [
  "/api/test-edition/../x",
  "/api/./x",
  "/../api/x",
  "/api/test-edition/%2e%2e/x",
  "/api/test-edition/%2E/x",
  "/api/test-edition/.%2E/x",
  "/api/%252e%252e/x",
  "/\ufeffapi/test-edition/x",
  "/api/test-edition/x\u200b",
  "/api/test-edition/x\u00ad",
  "/api/test-edition/x\u3000",
  "/api/test-edition/x\u00a0",
  "/api/test-edition/x\u1680",
  "/api/test-edition/x\x85",
  "/api/test-edition/x\x80",
  "",
  "api/test-edition/x",
  "//evil.example/x",
  "https://hub.example.org/hub/logout",
  "javascript:alert(1)",
  " /api/test-edition/x",
  "/api/test-edition/x ",
  "/api/test edition/x",
  "/api/test-edition/\nx",
  "/api/test-edition/x",
  "/api/test-edition/ x",
  "/\\evil.example/x",
];

function declare(value: unknown): void {
  if (value === undefined) {
    delete window.__SCISTUDIO_CAPABILITIES__;
  } else {
    window.__SCISTUDIO_CAPABILITIES__ = value;
  }
  resetCapabilitiesCacheForTests();
}

afterEach(() => {
  declare(undefined);
});

describe("getCapabilities", () => {
  it("reads every capability as off when nothing was declared", () => {
    declare(undefined);
    expect(getCapabilities()).toEqual(ALL_OFF);
  });

  it("reads a full declaration from the backend", () => {
    declare({
      version: 1,
      identity: IDENTITY,
      transfer: TRANSFER,
      aiChatDisabled: true,
      update: UPDATE,
    });
    expect(getCapabilities()).toEqual({
      version: 1,
      identity: IDENTITY,
      transfer: TRANSFER,
      aiChatDisabled: true,
      update: UPDATE,
    });
  });

  it.each([
    ["identity", { identity: IDENTITY }, { identity: IDENTITY }],
    ["transfer", { transfer: TRANSFER }, { transfer: TRANSFER }],
    ["aiChatDisabled", { aiChatDisabled: true }, { aiChatDisabled: true }],
    ["update", { update: UPDATE }, { update: UPDATE }],
  ])("reads %s on its own, every other capability off", (_name, declared, expected) => {
    declare({ version: 1, ...declared });
    expect(getCapabilities()).toEqual({ ...ALL_OFF, version: 1, ...expected });
  });

  it.each([
    ["a missing", { user: "alice" }],
    ["a null", { user: "alice", logoutUrl: null }],
  ])("reads an identity with %s logout URL as a name without Logout", (_label, identity) => {
    declare({ version: 1, identity });
    expect(getCapabilities().identity).toEqual({ user: "alice", logoutUrl: null });
  });

  it("ignores a capability it does not know", () => {
    declare({ version: 1, somethingNewer: { url: "/api/x" }, transfer: TRANSFER });
    expect(getCapabilities()).toEqual({ ...ALL_OFF, version: 1, transfer: TRANSFER });
  });

  it.each([
    ["a string", "identity"],
    ["a number", 1],
    ["null", null],
    ["an array", []],
    ["the old boolean transfer", { version: 1, transfer: true }],
    ["a negative inline limit", { transfer: { ...TRANSFER, inlineMaxBytes: -1 } }],
    ["a fractional inline limit", { transfer: { ...TRANSFER, inlineMaxBytes: 1.5 } }],
    ["a string inline limit", { transfer: { ...TRANSFER, inlineMaxBytes: "8" } }],
    [
      "a template without the {path} marker",
      { transfer: { ...TRANSFER, downloadUrlTemplate: "/api/test-edition/download" } },
    ],
    [
      "a template with two {path} markers",
      { transfer: { ...TRANSFER, downloadUrlTemplate: "/api/x?a={path}&b={path}" } },
    ],
    ["a truthy non-boolean aiChatDisabled", { aiChatDisabled: "true" }],
    ["aiChatDisabled 1", { aiChatDisabled: 1 }],
    ["an update without a restart URL", { update: { statusUrl: UPDATE.statusUrl } }],
    ["an update without a status URL", { update: { restartUrl: UPDATE.restartUrl } }],
    ["an identity without a user", { identity: { logoutUrl: IDENTITY.logoutUrl } }],
    ["an identity with a blank user", { identity: { user: "  ", logoutUrl: IDENTITY.logoutUrl } }],
  ])("reads %s as off", (_label, value) => {
    declare(value);
    const capabilities = getCapabilities();
    expect(capabilities.identity).toBeNull();
    expect(capabilities.transfer).toBeNull();
    expect(capabilities.aiChatDisabled).toBe(false);
    expect(capabilities.update).toBeNull();
  });

  it.each(NOT_ROUTE_PATHS)("drops an identity whose logout URL is not a route path: %j", (url) => {
    declare({ version: 1, identity: { user: "alice", logoutUrl: url }, transfer: TRANSFER });
    expect(getCapabilities()).toEqual({ ...ALL_OFF, version: 1, transfer: TRANSFER });
  });

  it.each(NOT_ROUTE_PATHS)("drops transfer and update carrying %j", (url) => {
    declare({
      version: 1,
      transfer: { ...TRANSFER, downloadUrlTemplate: `${url}{path}` },
      update: { ...UPDATE, restartUrl: url },
      aiChatDisabled: true,
    });
    expect(getCapabilities()).toEqual({ ...ALL_OFF, version: 1, aiChatDisabled: true });
  });

  it.each([
    ["missing", undefined, 0],
    ["negative", -1, 0],
    ["fractional", 1.5, 0],
    ["a string", "1", 0],
    ["a later version", 2, 2],
  ])("reads a %s version and still reads the fields", (_label, version, expected) => {
    declare({ version, aiChatDisabled: true });
    expect(getCapabilities().version).toBe(expected);
    expect(getCapabilities().aiChatDisabled).toBe(true);
  });

  it("reads the declaration once and caches it until reset", () => {
    declare({ version: 1, transfer: TRANSFER });
    expect(getCapabilities().transfer).toEqual(TRANSFER);
    window.__SCISTUDIO_CAPABILITIES__ = { version: 1 };
    expect(getCapabilities().transfer).toEqual(TRANSFER);
    resetCapabilitiesCacheForTests();
    expect(getCapabilities().transfer).toBeNull();
  });

  it("returns frozen objects", () => {
    declare({ version: 1, identity: IDENTITY, transfer: TRANSFER, update: UPDATE });
    const capabilities = getCapabilities();
    expect(Object.isFrozen(capabilities)).toBe(true);
    expect(Object.isFrozen(capabilities.identity)).toBe(true);
    expect(Object.isFrozen(capabilities.transfer)).toBe(true);
    expect(Object.isFrozen(capabilities.update)).toBe(true);
  });
});

describe("isCapabilityEnabled", () => {
  it("is off for every capability by default", () => {
    declare(undefined);
    for (const name of ["identity", "transfer", "aiChatDisabled", "update"] as const) {
      expect(isCapabilityEnabled(name)).toBe(false);
    }
  });

  it("follows the declaration", () => {
    declare({ version: 1, identity: IDENTITY, aiChatDisabled: true });
    expect(isCapabilityEnabled("identity")).toBe(true);
    expect(isCapabilityEnabled("transfer")).toBe(false);
    expect(isCapabilityEnabled("aiChatDisabled")).toBe(true);
    expect(isCapabilityEnabled("update")).toBe(false);
  });
});

describe("isRoutePath", () => {
  it.each(["/api/test-edition/x", "/api/x?path={path}", "/hub/logout"])("accepts %j", (url) => {
    expect(isRoutePath(url)).toBe(true);
  });

  it.each([...NOT_ROUTE_PATHS, null, 1, {}])("refuses %j", (url) => {
    expect(isRoutePath(url)).toBe(false);
  });
});

describe("downloadRoutePath", () => {
  it("replaces the {path} marker with the URL-encoded project-relative path", () => {
    expect(downloadRoutePath(TRANSFER, "data/raw/scan 1 & 2.tif")).toBe(
      "/api/test-edition/transfer/download?path=data%2Fraw%2Fscan%201%20%26%202.tif",
    );
  });

  it("works with the {path} marker in the route itself", () => {
    const transfer = { inlineMaxBytes: 0, downloadUrlTemplate: "/api/test-edition/files/{path}" };
    expect(downloadRoutePath(transfer, "results/a?b.csv")).toBe(
      "/api/test-edition/files/results%2Fa%3Fb.csv",
    );
  });
});
