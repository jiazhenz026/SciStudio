/**
 * ADR-054 spec 1, T-006 — the capability gate (FR-011, FR-012, SC-007).
 *
 * A mount states the capability it was granted, and the capability was declared
 * statically in the panel's declaration and resolved before the panel loaded
 * (FR-005). There is no runtime negotiation: nothing a mounted panel says can
 * give it a capability it did not declare.
 *
 * **The gate is structural, not a check.** `createPanelCapabilityGate` captures
 * the emit consumer *only* for a producing mount. For a displaying mount the
 * consumer reference is dropped at construction and the gate holds `null`, so
 * there is no path from an inbound `emit` to the consumer for later code to
 * take by accident. An `emit` from a displaying mount is dropped and reported
 * through the error channel; a test that sends one observes that nothing
 * reached the consumer, which is what SC-007 asks for and what a test of the
 * declaration alone would not show.
 *
 * **Which types the gate governs.** FR-011 says a displaying panel is granted
 * no outbound message type and FR-012 says a producing panel's only outbound
 * path is the emission of code; D-011 settles what that means for the wire:
 * `emit` is granted only to a producing mount. The remaining panel-to-host
 * types — `ready`, `read`, `error`, `state` — are the host's own protocol
 * rather than an outbound path out of the panel: a displaying panel must
 * complete the handshake (FR-009), must be able to make a bounded windowed read
 * (FR-010), must be able to report an error, and may implement the optional
 * state hook (FR-031). None of them carries anything out of the panel into the
 * session; `emit` is the only type that does.
 */

import type { PanelCapability, PanelEmitPayload, PanelToHostType } from "./panelMessages";

/** The closed set of two (FR-006). */
export const PANEL_CAPABILITIES: readonly PanelCapability[] = ["displaying", "producing"];

/**
 * The panel-to-host types that are the host's own protocol and are therefore
 * available to any mount, whatever its capability.
 */
export const PANEL_PROTOCOL_TYPES: readonly PanelToHostType[] = ["ready", "read", "error", "state"];

/** The panel-to-host types that only a producing mount is granted (FR-012). */
export const PANEL_PRODUCING_TYPES: readonly PanelToHostType[] = ["emit"];

/** Is `value` one of the two capabilities? */
export function isPanelCapability(value: unknown): value is PanelCapability {
  return value === "displaying" || value === "producing";
}

/**
 * Does a mount with `capability` satisfy a request that requires `required`?
 * A producing panel satisfies a displaying request; the reverse is false
 * (FR-006, FR-048).
 */
export function capabilitySatisfies(
  capability: PanelCapability,
  required: PanelCapability,
): boolean {
  if (required === "displaying") return true;
  return capability === "producing";
}

/** The outbound message types the host wires for a mount with `capability`. */
export function grantedOutboundTypes(capability: PanelCapability): ReadonlySet<PanelToHostType> {
  const granted = new Set<PanelToHostType>(PANEL_PROTOCOL_TYPES);
  if (capability === "producing") {
    for (const type of PANEL_PRODUCING_TYPES) granted.add(type);
  }
  return granted;
}

/** What the host refused, and why — reported through the error channel. */
export interface PanelCapabilityDenial {
  readonly panelId: string;
  readonly capability: PanelCapability;
  readonly type: PanelToHostType;
  readonly code: string;
  readonly message: string;
}

export type PanelGateDecision =
  | { readonly granted: true }
  | { readonly granted: false; readonly denial: PanelCapabilityDenial };

/** What a producing mount's emissions are handed to. */
export type PanelEmitConsumer = (code: string) => void;

export interface PanelCapabilityGateOptions {
  /**
   * The consumer of emitted code. It is captured only when `capability` is
   * `"producing"`; for a displaying mount it is dropped here and never stored.
   */
  readonly onEmit?: PanelEmitConsumer | null;
  /** Called with every denial, so the host can report it. */
  readonly onDenied?: (denial: PanelCapabilityDenial) => void;
}

export interface PanelCapabilityGate {
  readonly panelId: string;
  readonly capability: PanelCapability;
  /** Is `type` wired for this mount? */
  grants(type: PanelToHostType): boolean;
  /** Is there a consumer on the other side of the emit path at all? */
  readonly hasEmitPath: boolean;
  /**
   * Deliver one emission. Granted only for a producing mount with a consumer;
   * otherwise the code is dropped and the denial is returned and reported.
   */
  deliverEmit(payload: PanelEmitPayload): PanelGateDecision;
}

/**
 * Build the gate for one mount. The capability is fixed for the life of the
 * mount: a panel that wants the other one is a different mount.
 */
export function createPanelCapabilityGate(
  panelId: string,
  capability: PanelCapability,
  options: PanelCapabilityGateOptions = {},
): PanelCapabilityGate {
  // The whole gate. For a displaying mount the consumer is not captured, so no
  // later code can reach it: there is nothing to reach (FR-011, SC-007).
  const emitConsumer: PanelEmitConsumer | null =
    capability === "producing" ? (options.onEmit ?? null) : null;
  const granted = grantedOutboundTypes(capability);
  const onDenied = options.onDenied;

  const deny = (type: PanelToHostType, code: string, message: string): PanelGateDecision => {
    const denial: PanelCapabilityDenial = { panelId, capability, type, code, message };
    onDenied?.(denial);
    return { granted: false, denial };
  };

  return {
    panelId,
    capability,
    get hasEmitPath() {
      return emitConsumer !== null;
    },
    grants(type) {
      return granted.has(type);
    },
    deliverEmit(payload) {
      if (!granted.has("emit")) {
        return deny(
          "emit",
          "capability_denied",
          `panel "${panelId}" is mounted for display and may not emit code; ` +
            "the emission was dropped",
        );
      }
      if (emitConsumer === null) {
        return deny(
          "emit",
          "emit_unavailable",
          `panel "${panelId}" emitted code but this mount has nowhere to send it`,
        );
      }
      emitConsumer(payload.code);
      return { granted: true };
    },
  };
}
