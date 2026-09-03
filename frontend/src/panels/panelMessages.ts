/**
 * ADR-054 spec 1, T-005 — the panel message contract.
 *
 * A panel is mounted in a frame granted `allow-scripts` and nothing else
 * (FR-007, FR-008), so it runs at an *opaque origin*: the host cannot check
 * `event.origin` and the panel cannot check the host's. The contract replaces
 * the origin check with two things that do work across an opaque boundary — a
 * per-mount token that every message in both directions carries, and (on the
 * host side, in `panelFrame.ts`) an identity check of `event.source` against
 * the frame's own `contentWindow`.
 *
 * Every message in both directions is the D-011 envelope:
 *
 * ```json
 * { "scistudio_panel": 1, "token": "<per-mount token>", "type": "init", "payload": {} }
 * ```
 *
 * This module owns the envelope, the two type unions, and *total* guards over
 * them. The guards take the mount's token and reject anything whose token does
 * not match it (FR-008). They never throw: every input they are given arrives
 * from a sandboxed document that may send anything at all, including values
 * with throwing accessors, so a guard that threw would turn hostile data into a
 * host-side crash.
 *
 * This module has no imports and no DOM contact, which is what lets the frame
 * module, the capability gate and the host component all depend on it.
 */

/** Envelope marker. A message without it is not part of this contract. */
export const PANEL_MESSAGE_MARKER = 1 as const;

/**
 * The two capabilities of the contract (FR-006). It lives here rather than in
 * `panelCapability.ts` because the granted capability travels on the wire in
 * `init`, and the wire contract is the module nothing else may depend upon.
 */
export type PanelCapability = "displaying" | "producing";

/** The D-011 envelope. */
export interface PanelEnvelope<TType extends string, TPayload> {
  readonly scistudio_panel: typeof PANEL_MESSAGE_MARKER;
  /** The per-mount token the host issued (FR-008). */
  readonly token: string;
  readonly type: TType;
  readonly payload: TPayload;
}

/* -------------------------------------------------------------------------- */
/* Host -> panel payloads                                                      */
/* -------------------------------------------------------------------------- */

/** The bounds a panel must respect when it asks for a window of data (FR-010). */
export interface PanelReadLimits {
  /** Maximum rows/elements one windowed read may return. */
  readonly max_rows: number;
  /** Maximum encoded size, in bytes, one windowed read may return. */
  readonly max_bytes: number;
}

/**
 * One variable a producing panel is bound to (FR-013). A panel may be bound to
 * more than one, because a panel that compares two objects is ordinary.
 */
export interface PanelBindingSnapshot {
  /** The bound value's type name, as the backend spells it. */
  readonly type: string;
  /** The opening snapshot of that value. */
  readonly snapshot: unknown;
}

/** `init` — sent once, after the frame's document has loaded (FR-009). */
export interface PanelInitPayload {
  /**
   * The API version the host accepts. D-010: this is the backend's
   * `PANEL_API_VERSION`, handed down in the descriptor. The frontend defines no
   * version of its own.
   */
  readonly api_version: string;
  readonly panel_id: string;
  /** The capability this mount was granted (FR-005). */
  readonly capability: PanelCapability;
  /** What a displaying panel is showing: the opening snapshot. */
  readonly target: unknown;
  /** What a producing panel is bound to, or `null` (FR-013). */
  readonly bindings: Readonly<Record<string, PanelBindingSnapshot>> | null;
  readonly read_limits: PanelReadLimits;
  /** Same-origin base the panel fetches its own bulk assets from (ADR-054 3.4). */
  readonly asset_base_url: string;
  /**
   * FR-031, the remount half of the optional state hook: the snapshot this
   * panel handed the host before its last teardown, or `null` when there is
   * none or the snapshot would not serialise. `init` is the only message a
   * mount receives before it is live, so the snapshot has nowhere else to ride.
   */
  readonly restored_state: unknown;
}

/** `update` — the update channel: a reason and what changed (FR-010). */
export interface PanelUpdatePayload {
  readonly reason: string;
  readonly changed: Readonly<Record<string, unknown>>;
}

/** `read_result` — the answer to one `read` (FR-010). */
export interface PanelReadResultPayload {
  readonly request_id: string;
  /** The window that was read. Shape is the provider's, not the host's. */
  readonly window: unknown;
}

/**
 * `error` — the host's error channel. `request_id` is set when the error ends a
 * specific `read`, which is what lets a panel fail one read without waiting out
 * its bounded timeout.
 */
export interface PanelHostErrorPayload {
  readonly code: string;
  readonly message: string;
  readonly request_id: string | null;
}

/** `state_request` and `teardown` carry no fields. */
export type PanelEmptyPayload = Readonly<Record<string, never>>;

/** The payload each host-to-panel type carries. */
export interface HostToPanelPayloads {
  init: PanelInitPayload;
  update: PanelUpdatePayload;
  read_result: PanelReadResultPayload;
  error: PanelHostErrorPayload;
  state_request: PanelEmptyPayload;
  teardown: PanelEmptyPayload;
}

export type HostToPanelType = keyof HostToPanelPayloads;

export type HostToPanelMessage = {
  [K in HostToPanelType]: PanelEnvelope<K, HostToPanelPayloads[K]>;
}[HostToPanelType];

/* -------------------------------------------------------------------------- */
/* Panel -> host payloads                                                      */
/* -------------------------------------------------------------------------- */

/** `ready` — completes the handshake and declares the panel's API version. */
export interface PanelReadyPayload {
  readonly api_version: string;
}

/** `read` — one bounded windowed read (FR-010). */
export interface PanelReadPayload {
  readonly request_id: string;
  readonly query: Readonly<Record<string, unknown>>;
}

/**
 * `emit` — the code a producing panel emits (FR-012). The host does not
 * interpret it; the AST whitelist of ADR-054 3.6 sits where an emission is
 * queued, which is the explore session, not here.
 */
export interface PanelEmitPayload {
  readonly code: string;
}

/** `error` — the panel's error channel. */
export interface PanelErrorPayload {
  readonly message: string;
  readonly detail: Readonly<Record<string, unknown>> | null;
}

/** `state` — the optional serialisable snapshot (FR-031). */
export interface PanelStatePayload {
  readonly state: unknown;
}

/** The payload each panel-to-host type carries. */
export interface PanelToHostPayloads {
  ready: PanelReadyPayload;
  read: PanelReadPayload;
  emit: PanelEmitPayload;
  error: PanelErrorPayload;
  state: PanelStatePayload;
}

export type PanelToHostType = keyof PanelToHostPayloads;

export type PanelToHostMessage = {
  [K in PanelToHostType]: PanelEnvelope<K, PanelToHostPayloads[K]>;
}[PanelToHostType];

/** Every type name in each direction, for exhaustive checks and diagnostics. */
export const HOST_TO_PANEL_TYPES: readonly HostToPanelType[] = [
  "init",
  "update",
  "read_result",
  "error",
  "state_request",
  "teardown",
];

export const PANEL_TO_HOST_TYPES: readonly PanelToHostType[] = [
  "ready",
  "read",
  "emit",
  "error",
  "state",
];

/* -------------------------------------------------------------------------- */
/* Construction                                                                */
/* -------------------------------------------------------------------------- */

/** Build one host-to-panel envelope. */
export function hostToPanelMessage<K extends HostToPanelType>(
  token: string,
  type: K,
  payload: HostToPanelPayloads[K],
): PanelEnvelope<K, HostToPanelPayloads[K]> {
  return { scistudio_panel: PANEL_MESSAGE_MARKER, token, type, payload };
}

/**
 * Build one panel-to-host envelope. Production never sends in this direction —
 * the panel does — but panel documents and tests need the same builder, and one
 * builder is how the two directions stay the same envelope.
 */
export function panelToHostMessage<K extends PanelToHostType>(
  token: string,
  type: K,
  payload: PanelToHostPayloads[K],
): PanelEnvelope<K, PanelToHostPayloads[K]> {
  return { scistudio_panel: PANEL_MESSAGE_MARKER, token, type, payload };
}

/* -------------------------------------------------------------------------- */
/* Guards                                                                      */
/* -------------------------------------------------------------------------- */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringField(source: Record<string, unknown>, key: string): string | null {
  const value = source[key];
  return typeof value === "string" ? value : null;
}

/**
 * Does `value` look like an envelope addressed to this mount?
 *
 * Rejects, in order: a non-object; a missing or wrong marker; a token that is
 * not a string or does not match the mount's token (FR-008); a non-string type;
 * a payload that is not a plain object.
 */
export function isPanelEnvelope(
  value: unknown,
  token: string,
): value is PanelEnvelope<string, Record<string, unknown>> {
  try {
    if (typeof token !== "string" || token === "") return false;
    if (!isRecord(value)) return false;
    if (value.scistudio_panel !== PANEL_MESSAGE_MARKER) return false;
    if (typeof value.token !== "string" || value.token !== token) return false;
    if (typeof value.type !== "string") return false;
    return isRecord(value.payload);
  } catch {
    // A hostile document can hand us an object whose property access throws.
    return false;
  }
}

function isPanelToHostPayload(type: string, payload: Record<string, unknown>): boolean {
  switch (type) {
    case "ready":
      return stringField(payload, "api_version") !== null;
    case "read":
      return stringField(payload, "request_id") !== null && isRecord(payload.query);
    case "emit":
      return stringField(payload, "code") !== null;
    case "error":
      return (
        stringField(payload, "message") !== null &&
        (payload.detail === null || payload.detail === undefined || isRecord(payload.detail))
      );
    case "state":
      return "state" in payload;
    default:
      return false;
  }
}

function isHostToPanelPayload(type: string, payload: Record<string, unknown>): boolean {
  switch (type) {
    case "init":
      return (
        stringField(payload, "api_version") !== null &&
        stringField(payload, "panel_id") !== null &&
        isPanelCapabilityName(payload.capability) &&
        stringField(payload, "asset_base_url") !== null &&
        (payload.bindings === null || isRecord(payload.bindings)) &&
        isRecord(payload.read_limits)
      );
    case "update":
      return stringField(payload, "reason") !== null && isRecord(payload.changed);
    case "read_result":
      return stringField(payload, "request_id") !== null;
    case "error":
      return (
        stringField(payload, "code") !== null &&
        stringField(payload, "message") !== null &&
        (payload.request_id === null || typeof payload.request_id === "string")
      );
    case "state_request":
    case "teardown":
      return true;
    default:
      return false;
  }
}

/** Is `value` the name of one of the two capabilities (FR-006)? */
export function isPanelCapabilityName(value: unknown): value is PanelCapability {
  return value === "displaying" || value === "producing";
}

/** Total guard for the panel-to-host direction. Never throws. */
export function isPanelToHostMessage(value: unknown, token: string): value is PanelToHostMessage {
  try {
    if (!isPanelEnvelope(value, token)) return false;
    return isPanelToHostPayload(value.type, value.payload);
  } catch {
    return false;
  }
}

/** Total guard for the host-to-panel direction. Never throws. */
export function isHostToPanelMessage(value: unknown, token: string): value is HostToPanelMessage {
  try {
    if (!isPanelEnvelope(value, token)) return false;
    return isHostToPanelPayload(value.type, value.payload);
  } catch {
    return false;
  }
}

/**
 * Narrow `value` to a panel-to-host message, or `null`. This is the form the
 * frame's message listener uses: one call answers "is this mine, and is it
 * well formed", and anything else is ignored in silence, because a sandboxed
 * document can post whatever it likes into its parent.
 */
export function parsePanelToHostMessage(value: unknown, token: string): PanelToHostMessage | null {
  return isPanelToHostMessage(value, token) ? value : null;
}

/** The mirror of {@link parsePanelToHostMessage}, for panel documents and tests. */
export function parseHostToPanelMessage(value: unknown, token: string): HostToPanelMessage | null {
  return isHostToPanelMessage(value, token) ? value : null;
}

/* -------------------------------------------------------------------------- */
/* The version gate                                                            */
/* -------------------------------------------------------------------------- */

function majorOf(version: string): string {
  return version.trim().split(".")[0];
}

/**
 * FR-004 / D-010 — does the host accept a panel declaring `declared`?
 *
 * `accepted` is the backend's `PANEL_API_VERSION`, carried in the descriptor.
 * Nothing in the frontend spells a version literal. The comparison is on the
 * major component: a host advances minor and patch additively, and a panel
 * built against `1.0` still runs on `1.3`.
 */
export function isAcceptedApiVersion(declared: unknown, accepted: unknown): boolean {
  if (typeof declared !== "string" || typeof accepted !== "string") return false;
  const declaredVersion = declared.trim();
  const acceptedVersion = accepted.trim();
  if (declaredVersion === "" || acceptedVersion === "") return false;
  return majorOf(declaredVersion) === majorOf(acceptedVersion);
}

/* -------------------------------------------------------------------------- */
/* The optional state hook                                                     */
/* -------------------------------------------------------------------------- */

/** What became of a snapshot a panel handed back (FR-031). */
export type PanelStateSnapshot =
  | { readonly kept: true; readonly state: unknown }
  | { readonly kept: false; readonly reason: string };

/**
 * FR-031 — a snapshot that cannot be serialised is *discarded*, not raised. The
 * panel then remounts clean, which is the whole point: a reload that fails
 * because a panel handed back a cyclic object would be a worse outcome than a
 * lost selection.
 */
export function sanitizePanelState(state: unknown): PanelStateSnapshot {
  if (state === undefined || state === null) {
    return { kept: false, reason: "the panel handed back no state" };
  }
  try {
    const encoded = JSON.stringify(state);
    if (typeof encoded !== "string") {
      return { kept: false, reason: "the snapshot did not serialise to JSON" };
    }
    return { kept: true, state: JSON.parse(encoded) };
  } catch (error) {
    return {
      kept: false,
      reason: `the snapshot did not serialise to JSON: ${describeError(error)}`,
    };
  }
}

/** One-line description of anything thrown, for diagnostics. Never throws. */
export function describeError(error: unknown): string {
  try {
    if (error instanceof Error) return error.message;
    return String(error);
  } catch {
    return "unknown error";
  }
}
