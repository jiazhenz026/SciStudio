/**
 * ADR-055 identity seam — capability accessor tests (decision 2d).
 *
 * The open-source edition injects no declaration, so the default must read as
 * every capability off; a declaration from an edition must come through typed;
 * and a malformed or unsafe declaration must read as off rather than throw.
 */

import { afterEach, describe, expect, it } from "vitest";

import {
  getCapabilities,
  isCapabilityEnabled,
  resetCapabilitiesCacheForTests,
} from "./capabilities";

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
    expect(getCapabilities()).toEqual({ identity: null, transfer: false });
  });

  it("reads a full declaration from the backend", () => {
    declare({ identity: { user: "alice", logoutUrl: "/api/session/logout" }, transfer: true });
    expect(getCapabilities()).toEqual({
      identity: { user: "alice", logoutUrl: "/api/session/logout" },
      transfer: true,
    });
  });

  it("reads transfer on its own", () => {
    declare({ identity: null, transfer: true });
    expect(getCapabilities()).toEqual({ identity: null, transfer: true });
  });

  it("accepts a logout path that already carries the service prefix", () => {
    declare({
      identity: { user: "alice", logoutUrl: "/user/alice/scistudio/api/session/logout" },
      transfer: false,
    });
    expect(getCapabilities().identity).toEqual({
      user: "alice",
      logoutUrl: "/user/alice/scistudio/api/session/logout",
    });
  });

  it.each([
    ["a string", "identity"],
    ["a number", 1],
    ["null", null],
    ["an array", []],
    ["a truthy non-boolean transfer", { transfer: "yes" }],
    ["an identity without a user", { identity: { logoutUrl: "/api/session/logout" } }],
    [
      "an identity with a blank user",
      { identity: { user: "  ", logoutUrl: "/api/session/logout" } },
    ],
    ["an identity without a logout URL", { identity: { user: "alice" } }],
  ])("reads %s as off", (_label, value) => {
    declare(value);
    expect(getCapabilities()).toEqual({ identity: null, transfer: false });
  });

  it.each([
    "javascript:alert(1)",
    "//evil.example/logout",
    "https://hub.example.org/hub/logout",
    "api/session/logout",
    " /api/session/logout",
    "/api/session/\nlogout",
    "ftp://hub.example.org/logout",
  ])("drops an identity whose logout URL is not a same-origin path: %j", (logoutUrl) => {
    declare({ identity: { user: "alice", logoutUrl }, transfer: true });
    expect(getCapabilities()).toEqual({ identity: null, transfer: true });
  });

  it("reads the declaration once and caches it until reset", () => {
    declare({ identity: null, transfer: true });
    expect(getCapabilities().transfer).toBe(true);
    window.__SCISTUDIO_CAPABILITIES__ = { identity: null, transfer: false };
    expect(getCapabilities().transfer).toBe(true);
    resetCapabilitiesCacheForTests();
    expect(getCapabilities().transfer).toBe(false);
  });

  it("returns frozen objects", () => {
    declare({ identity: { user: "alice", logoutUrl: "/hub/logout" }, transfer: true });
    const capabilities = getCapabilities();
    expect(Object.isFrozen(capabilities)).toBe(true);
    expect(Object.isFrozen(capabilities.identity)).toBe(true);
  });
});

describe("isCapabilityEnabled", () => {
  it("is off for every capability by default", () => {
    declare(undefined);
    expect(isCapabilityEnabled("identity")).toBe(false);
    expect(isCapabilityEnabled("transfer")).toBe(false);
  });

  it("follows the declaration", () => {
    declare({ identity: { user: "alice", logoutUrl: "/hub/logout" }, transfer: false });
    expect(isCapabilityEnabled("identity")).toBe(true);
    expect(isCapabilityEnabled("transfer")).toBe(false);
  });
});
