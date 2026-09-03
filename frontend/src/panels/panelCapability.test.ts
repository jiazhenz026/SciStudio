/**
 * ADR-054 spec 1, T-006 — the capability gate (FR-011, FR-012, SC-007).
 *
 * The gate is asserted from the outside: a displaying mount is *given* an emit
 * consumer, an `emit` is delivered to the gate, and the assertion is that the
 * consumer was never called. Testing the declaration — that the capability
 * field says "displaying" — would not show that, which is the distinction
 * SC-007 draws.
 */

import { describe, expect, it, vi } from "vitest";

import {
  PANEL_CAPABILITIES,
  PANEL_PRODUCING_TYPES,
  PANEL_PROTOCOL_TYPES,
  capabilitySatisfies,
  createPanelCapabilityGate,
  grantedOutboundTypes,
  isPanelCapability,
} from "./panelCapability";

describe("the capability set (FR-006)", () => {
  it("has exactly two members", () => {
    expect([...PANEL_CAPABILITIES]).toEqual(["displaying", "producing"]);
  });

  it("recognises nothing else", () => {
    expect(isPanelCapability("displaying")).toBe(true);
    expect(isPanelCapability("producing")).toBe(true);
    expect(isPanelCapability("previewing")).toBe(false);
    expect(isPanelCapability(undefined)).toBe(false);
    expect(isPanelCapability(null)).toBe(false);
    expect(isPanelCapability(0)).toBe(false);
  });

  it("lets a producing panel satisfy a displaying request, but not the reverse", () => {
    expect(capabilitySatisfies("producing", "displaying")).toBe(true);
    expect(capabilitySatisfies("displaying", "displaying")).toBe(true);
    expect(capabilitySatisfies("producing", "producing")).toBe(true);
    expect(capabilitySatisfies("displaying", "producing")).toBe(false);
  });
});

describe("grantedOutboundTypes", () => {
  it("grants a displaying mount the protocol types and no emit", () => {
    const granted = grantedOutboundTypes("displaying");
    for (const type of PANEL_PROTOCOL_TYPES) expect(granted.has(type)).toBe(true);
    for (const type of PANEL_PRODUCING_TYPES) expect(granted.has(type)).toBe(false);
    expect(granted.has("emit")).toBe(false);
  });

  it("grants a producing mount emit as well", () => {
    const granted = grantedOutboundTypes("producing");
    for (const type of PANEL_PROTOCOL_TYPES) expect(granted.has(type)).toBe(true);
    expect(granted.has("emit")).toBe(true);
  });
});

describe("the gate on a displaying mount (SC-007)", () => {
  it("never wires the emit path, even when one is offered", () => {
    const consumer = vi.fn();
    const denials: string[] = [];
    const gate = createPanelCapabilityGate("core.table", "displaying", {
      onEmit: consumer,
      onDenied: (denial) => denials.push(denial.code),
    });

    expect(gate.hasEmitPath).toBe(false);
    expect(gate.grants("emit")).toBe(false);

    const decision = gate.deliverEmit({ code: "df = df.drop(columns=['a'])" });

    expect(decision.granted).toBe(false);
    expect(consumer).not.toHaveBeenCalled();
    expect(denials).toEqual(["capability_denied"]);
    if (!decision.granted) {
      expect(decision.denial.message).toContain("core.table");
      expect(decision.denial.message).toContain("dropped");
    }
  });

  it("drops every emission, not only the first", () => {
    const consumer = vi.fn();
    const gate = createPanelCapabilityGate("core.table", "displaying", { onEmit: consumer });
    for (let index = 0; index < 5; index += 1) {
      expect(gate.deliverEmit({ code: `x = ${index}` }).granted).toBe(false);
    }
    expect(consumer).not.toHaveBeenCalled();
  });
});

describe("the gate on a producing mount", () => {
  it("hands the emitted code to the consumer verbatim", () => {
    const consumer = vi.fn();
    const gate = createPanelCapabilityGate("editor.table", "producing", { onEmit: consumer });

    expect(gate.hasEmitPath).toBe(true);
    expect(gate.grants("emit")).toBe(true);

    const decision = gate.deliverEmit({ code: "df = df.drop(columns=['a'])" });

    expect(decision).toEqual({ granted: true });
    expect(consumer).toHaveBeenCalledTimes(1);
    expect(consumer).toHaveBeenCalledWith("df = df.drop(columns=['a'])");
  });

  it("does not interpret what it is given (FR-012)", () => {
    const seen: string[] = [];
    const gate = createPanelCapabilityGate("editor.table", "producing", {
      onEmit: (code) => seen.push(code),
    });
    gate.deliverEmit({ code: "df.iloc[0] = 1  # the whitelist lives in the session, not here" });
    expect(seen).toEqual(["df.iloc[0] = 1  # the whitelist lives in the session, not here"]);
  });

  it("reports a producing mount that was given nowhere to send code", () => {
    const denials: string[] = [];
    const gate = createPanelCapabilityGate("editor.table", "producing", {
      onDenied: (denial) => denials.push(denial.code),
    });
    expect(gate.hasEmitPath).toBe(false);
    expect(gate.deliverEmit({ code: "x = 1" }).granted).toBe(false);
    expect(denials).toEqual(["emit_unavailable"]);
  });
});
