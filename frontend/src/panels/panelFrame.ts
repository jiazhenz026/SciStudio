/**
 * ADR-054 spec 1, T-005 — the sandboxed frame: creation, the token, the
 * handshake, the bounded waits, and teardown.
 *
 * This is not an adaptation of either retired ES-module loader. Those imported
 * a module into the application's own realm; this creates a frame at an opaque
 * origin and speaks to it by `postMessage`. The one idea carried across is that
 * the document a panel is served from must be a same-origin path the backend
 * emitted, never a remote URL.
 *
 * **The sandbox is one permission** (FR-008, ADR-054 3.2). The frame is created
 * with `sandbox="allow-scripts"` and nothing else. Each permission withheld is
 * withheld for a stated reason:
 *
 * - `allow-same-origin`: with it the framed document shares the application's
 *   origin and can walk into the parent document, its storage, and the API with
 *   the person's credentials — the frame would be no boundary at all.
 * - `allow-forms`: a panel submits nothing.
 * - `allow-popups`, `allow-top-navigation`: a panel must not open or navigate
 *   anything outside itself.
 * - `allow-modals`: a panel must not block the application with a dialog.
 * - `allow-downloads`: saving a file is host chrome.
 *
 * Do not add one to make a test pass. The consequence of withholding
 * `allow-same-origin` is that the frame has an *opaque* origin: `event.origin`
 * is `"null"` and is useless as a check, and the host must address the frame
 * with `targetOrigin: "*"`. Two checks stand in for the origin check, and both
 * are applied to every inbound message: the per-mount token, and the identity
 * of `event.source` against the frame's own `contentWindow`.
 *
 * **The seam.** `PanelFrameFactory` is the single point at which the frame
 * element is created and its load is observed. jsdom does not fetch an iframe's
 * `src`, so under the test runner a real frame never fires `load`; a test
 * substitutes a factory that wraps the real element and reports it loaded. Only
 * the load observation is substituted — the element, its sandbox attribute, its
 * `contentWindow`, and every message that crosses it stay real.
 */

import type {
  HostToPanelPayloads,
  HostToPanelType,
  PanelBindingSnapshot,
  PanelCapability,
  PanelHostActionPayload,
  PanelReadLimits,
  PanelReadPayload,
  PanelResourcePayload,
  PanelStateSnapshot,
  PanelToHostMessage,
} from "./panelMessages";
import {
  describeError,
  hostToPanelMessage,
  isAcceptedApiVersion,
  parsePanelToHostMessage,
  sanitizePanelState,
} from "./panelMessages";

/**
 * The complete sandbox permission set a panel frame is granted (FR-008). One
 * permission. This exact string is asserted by the test suite.
 */
export const PANEL_FRAME_SANDBOX = "allow-scripts";

/** How long the entry document has to finish loading before the mount fails. */
export const PANEL_FRAME_LOAD_TIMEOUT_MS = 10_000;

/**
 * How long a loaded panel has to answer `init` with `ready` (FR-009). A wait
 * that elapses is a load failure, not a slow panel we keep waiting on: the
 * person is looking at an empty rectangle until we say otherwise.
 */
export const PANEL_HANDSHAKE_TIMEOUT_MS = 5_000;

/** How long one windowed read may stay in flight before the host gives up. */
export const PANEL_READ_TIMEOUT_MS = 15_000;

/** How long the optional state hook is waited on before the snapshot is lost. */
export const PANEL_STATE_REQUEST_TIMEOUT_MS = 1_000;

/* -------------------------------------------------------------------------- */
/* Failures                                                                    */
/* -------------------------------------------------------------------------- */

/** Why a panel is not mounted, or stopped being mounted (FR-014). */
export type PanelFailureReason =
  /** The descriptor is missing a field the host needs before it can mount. */
  | "invalid_descriptor"
  /** The entry document is not a same-origin path the backend emitted. */
  | "invalid_document_url"
  /** There is no frame mechanism here, or creating the frame threw (FR-035). */
  | "frame_unavailable"
  /** The entry document never finished loading. */
  | "load_timeout"
  /** The panel never answered `ready` inside the bounded wait (FR-009). */
  | "handshake_timeout"
  /** The panel declares a version the host does not accept (FR-004). */
  | "version_mismatch"
  /** The panel reported a fatal error of its own before it was mounted. */
  | "panel_error"
  /** The mount was torn down while something was still in flight. */
  | "torn_down";

/** A load failure, carrying a diagnostic that names the panel (FR-014). */
export interface PanelFailure {
  readonly panelId: string;
  readonly reason: PanelFailureReason;
  /** Human-readable, names the panel and what went wrong. */
  readonly message: string;
}

export function panelFailure(
  panelId: string,
  reason: PanelFailureReason,
  detail: string,
): PanelFailure {
  return { panelId, reason, message: `panel "${panelId}" ${detail}` };
}

/* -------------------------------------------------------------------------- */
/* The frame seam                                                              */
/* -------------------------------------------------------------------------- */

export interface PanelFrameSpec {
  readonly panelId: string;
  /** Same-origin path of the panel's entry document on the asset route. */
  readonly documentUrl: string;
  /** Accessible name for the frame element. */
  readonly title: string;
}

/**
 * A created frame. `contentWindow` is read every time rather than captured,
 * because a frame that has not navigated yet does not have its final one.
 */
export interface PanelFrameHandle {
  readonly element: HTMLElement;
  readonly contentWindow: Window | null;
  /** Resolves when the entry document has loaded; rejects if it cannot. */
  whenLoaded(): Promise<void>;
  /** Remove the frame from the document. Must be safe to call twice. */
  dispose(): void;
}

export type PanelFrameFactory = (spec: PanelFrameSpec) => PanelFrameHandle;

/**
 * The production factory: one `iframe`, one sandbox permission, one source.
 *
 * The load listener is attached before the element is inserted by the caller,
 * so no load event can be missed between creation and insertion.
 */
export const createSandboxedPanelFrame: PanelFrameFactory = (spec) => {
  const element = document.createElement("iframe");
  element.setAttribute("sandbox", PANEL_FRAME_SANDBOX);
  element.setAttribute("title", spec.title);
  element.setAttribute("referrerpolicy", "no-referrer");
  element.dataset.panelId = spec.panelId;
  element.style.width = "100%";
  element.style.height = "100%";
  element.style.border = "0";
  element.style.display = "block";

  const loaded = new Promise<void>((resolve, reject) => {
    element.addEventListener("load", () => resolve(), { once: true });
    element.addEventListener(
      "error",
      () => reject(new Error("the entry document failed to load")),
      { once: true },
    );
  });

  element.setAttribute("src", spec.documentUrl);

  return {
    element,
    get contentWindow() {
      return element.contentWindow;
    },
    whenLoaded: () => loaded,
    dispose: () => element.remove(),
  };
};

/* -------------------------------------------------------------------------- */
/* The document URL                                                            */
/* -------------------------------------------------------------------------- */

/**
 * Is `url` a same-origin path the backend's asset route emitted?
 *
 * A panel document always arrives as a site-relative absolute path
 * (`/api/panels/assets/<panel_id>/<file>`). A remote URL, a protocol-relative
 * URL, and every inline scheme (`data:`, `blob:`, `javascript:`) are refused:
 * the frame's contents must come from the one route the application serves and
 * confines, never from something a manifest talked the host into fetching.
 */
export function isPanelDocumentUrl(url: unknown): url is string {
  if (typeof url !== "string") return false;
  const candidate = url.trim();
  if (candidate === "") return false;
  if (candidate.startsWith("//")) return false;
  if (/^[a-z][a-z0-9+.-]*:/i.test(candidate)) return false;
  if (!candidate.startsWith("/")) return false;
  try {
    return new URL(candidate, window.location.origin).origin === window.location.origin;
  } catch {
    return false;
  }
}

/* -------------------------------------------------------------------------- */
/* The per-mount token                                                         */
/* -------------------------------------------------------------------------- */

/**
 * Issue the token this mount's messages carry (FR-008). It is issued per mount,
 * never per panel: a remount must not accept a message the previous mount's
 * document is still posting.
 */
export function issuePanelToken(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }
  if (cryptoApi && typeof cryptoApi.getRandomValues === "function") {
    const bytes = cryptoApi.getRandomValues(new Uint8Array(16));
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  return `panel-${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
}

/* -------------------------------------------------------------------------- */
/* The connection                                                              */
/* -------------------------------------------------------------------------- */

/** What the host answers a `read` with. Rejecting fails that one read. */
export type PanelReadResolver = (query: Readonly<Record<string, unknown>>) => Promise<unknown>;

/**
 * What the host answers a `resource` with (D-017). Rejecting fails that one
 * request; the panel is told through `error` carrying the request id.
 */
export type PanelResourceResolver = (
  resourceId: string,
  params: Readonly<Record<string, unknown>> | null,
) => Promise<unknown>;

/**
 * The result of performing one `host_action` (D-017).
 *
 * `ok: true` means the host carried the action to a conclusion the panel need
 * not act on — including a person who dismissed the save dialog, which is a
 * decision rather than a failure. `ok: false` is an action that was attempted
 * and went wrong. See `PanelHostActionResultPayload` for why `ok` is binary.
 */
export interface PanelHostActionOutcome {
  readonly ok: boolean;
  readonly detail?: string | Readonly<Record<string, unknown>> | null;
}

/** What the host does when a panel asks for chrome it cannot draw itself. */
export type PanelHostActionPerformer = (
  action: PanelHostActionPayload["action"],
  params: Readonly<Record<string, unknown>> | null,
) => Promise<PanelHostActionOutcome | void>;

/** How one bounded request round trip ended. */
export type PanelRequestOutcome =
  | { readonly status: "answered" }
  | { readonly status: "failed"; readonly message: string }
  | { readonly status: "timed_out" }
  | { readonly status: "cancelled" };

/** The name this outcome had when `read` was the only request type. */
export type PanelReadOutcome = PanelRequestOutcome;

/** A live mount. Every method is safe to call after teardown; none throws. */
export interface PanelFrameConnection {
  readonly panelId: string;
  /** The per-mount token every message in both directions carries. */
  readonly token: string;
  readonly element: HTMLElement;
  readonly capability: PanelCapability;
  readonly disposed: boolean;
  /** Post one host-to-panel message. `false` when the mount is gone. */
  send<K extends HostToPanelType>(type: K, payload: HostToPanelPayloads[K]): boolean;
  /**
   * Run one bounded read round trip: register the request as in flight, await
   * `resolve`, and post `read_result` — or, on failure or timeout, an `error`
   * carrying the request id so the panel need not wait its own timeout out. A
   * teardown while it is in flight resolves it `cancelled` and posts nothing.
   */
  answerRead(request: PanelReadPayload, resolve: PanelReadResolver): Promise<PanelRequestOutcome>;
  /**
   * The same round trip for `resource` (D-017), answered by `resource_result`.
   */
  answerResource(
    request: PanelResourcePayload,
    resolve: PanelResourceResolver,
  ): Promise<PanelRequestOutcome>;
  /**
   * The same round trip for `host_action` (D-017), answered by
   * `host_action_result`. A performer that resolves without an outcome is
   * read as `{ ok: true }`: it did the thing and has nothing to add.
   */
  answerHostAction(
    request: PanelHostActionPayload,
    perform: PanelHostActionPerformer,
  ): Promise<PanelRequestOutcome>;
  /**
   * Ask the panel for its snapshot (FR-031). A panel that does not implement
   * the hook simply never answers, so the wait is bounded and its elapsing is
   * an ordinary outcome rather than a failure.
   */
  requestState(timeoutMs?: number): Promise<PanelStateSnapshot>;
  /**
   * Tell the panel it is going away, then remove it. Idempotent.
   *
   * The `teardown` message is best effort: `postMessage` is delivered on a
   * later turn, so a caller that removes the frame's container in the same turn
   * (React unmounting the host, for instance) discards the panel's window
   * before the message lands. Everything the *host* relies on — the listener,
   * the in-flight reads — is released synchronously.
   */
  teardown(): void;
}

export type PanelMessageHandler = (
  message: PanelToHostMessage,
  connection: PanelFrameConnection,
) => void;

/** Everything `init` carries that the mount does not derive for itself. */
export interface PanelMountInit {
  readonly capability: PanelCapability;
  readonly target: unknown;
  readonly bindings: Readonly<Record<string, PanelBindingSnapshot>> | null;
  readonly readLimits: PanelReadLimits;
  readonly assetBaseUrl: string;
  readonly restoredState: unknown;
}

export interface PanelFrameMountOptions {
  /** Host-owned element the frame is inserted into. */
  readonly container: HTMLElement;
  readonly panelId: string;
  readonly documentUrl: string;
  /**
   * The version the backend accepts, taken from the descriptor (D-010). The
   * frontend never spells a version literal.
   */
  readonly acceptedApiVersion: string;
  readonly init: PanelMountInit;
  readonly title?: string;
  readonly frameFactory?: PanelFrameFactory;
  readonly loadTimeoutMs?: number;
  readonly handshakeTimeoutMs?: number;
  readonly readTimeoutMs?: number;
  readonly onMessage?: PanelMessageHandler;
  readonly issueToken?: () => string;
}

export type PanelMountResult =
  | { readonly ok: true; readonly connection: PanelFrameConnection }
  | { readonly ok: false; readonly failure: PanelFailure };

type Settled<T> =
  | { readonly status: "resolved"; readonly value: T }
  | { readonly status: "rejected"; readonly error: unknown }
  | { readonly status: "timeout" };

function settleWithin<T>(promise: Promise<T>, timeoutMs: number): Promise<Settled<T>> {
  return new Promise<Settled<T>>((resolve) => {
    let done = false;
    const timer = setTimeout(() => {
      if (done) return;
      done = true;
      resolve({ status: "timeout" });
    }, timeoutMs);
    const finish = (settled: Settled<T>) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve(settled);
    };
    promise.then(
      (value) => finish({ status: "resolved", value }),
      (error) => finish({ status: "rejected", error }),
    );
  });
}

interface PendingRequest {
  cancel(): void;
}

/** The internal race outcome; the public one does not carry the answer. */
type RequestRaceOutcome =
  | { readonly status: "answered"; readonly value: unknown }
  | { readonly status: "failed"; readonly message: string }
  | { readonly status: "timed_out" }
  | { readonly status: "cancelled" };

/**
 * Create the frame, complete the handshake, and hand back a live connection —
 * or the single {@link PanelFailure} that explains why not. Never throws.
 */
export async function mountPanelFrame(options: PanelFrameMountOptions): Promise<PanelMountResult> {
  const { container, panelId, documentUrl, acceptedApiVersion, init } = options;
  const loadTimeoutMs = options.loadTimeoutMs ?? PANEL_FRAME_LOAD_TIMEOUT_MS;
  const handshakeTimeoutMs = options.handshakeTimeoutMs ?? PANEL_HANDSHAKE_TIMEOUT_MS;
  const readTimeoutMs = options.readTimeoutMs ?? PANEL_READ_TIMEOUT_MS;

  if (!isPanelDocumentUrl(documentUrl)) {
    return {
      ok: false,
      failure: panelFailure(
        panelId,
        "invalid_document_url",
        `has no same-origin entry document: ${JSON.stringify(documentUrl)}`,
      ),
    };
  }
  if (typeof window === "undefined" || typeof document === "undefined") {
    return {
      ok: false,
      failure: panelFailure(panelId, "frame_unavailable", "cannot be framed in this environment"),
    };
  }

  const token = (options.issueToken ?? issuePanelToken)();

  let handle: PanelFrameHandle;
  try {
    handle = (options.frameFactory ?? createSandboxedPanelFrame)({
      panelId,
      documentUrl,
      title: options.title ?? panelId,
    });
  } catch (error) {
    return {
      ok: false,
      failure: panelFailure(
        panelId,
        "frame_unavailable",
        `could not be framed: ${describeError(error)}`,
      ),
    };
  }
  if (!handle || !handle.element) {
    return {
      ok: false,
      failure: panelFailure(panelId, "frame_unavailable", "was given no frame element"),
    };
  }

  let disposed = false;
  let handshakeDone = false;
  const pendingRequests = new Map<string, PendingRequest>();
  let pendingState: ((state: unknown) => void) | null = null;
  let resolveHandshake: ((message: PanelToHostMessage) => void) | null = null;

  const post = <K extends HostToPanelType>(type: K, payload: HostToPanelPayloads[K]): boolean => {
    if (disposed) return false;
    const target = handle.contentWindow;
    if (!target) return false;
    try {
      // `targetOrigin: "*"` is forced by FR-008: the frame's origin is opaque,
      // so no origin string could ever match it. The token and the
      // `event.source` identity check are what replace the origin check.
      target.postMessage(hostToPanelMessage(token, type, payload), "*");
      return true;
    } catch {
      return false;
    }
  };

  const listener = (event: MessageEvent) => {
    if (disposed) return;
    // Two checks, both required (FR-008): the message must come from this
    // frame's own window, and it must carry this mount's token.
    if (event.source !== handle.contentWindow) return;
    const message = parsePanelToHostMessage(event.data, token);
    if (message === null) return;
    if (!handshakeDone) {
      if (message.type === "ready" || message.type === "error") {
        resolveHandshake?.(message);
      }
      return;
    }
    if (message.type === "state" && pendingState) {
      const settle = pendingState;
      pendingState = null;
      settle(message.payload.state);
      return;
    }
    options.onMessage?.(message, connection);
  };

  const detachFrame = () => {
    try {
      handle.dispose();
    } catch {
      // The frame is being discarded; a failure to remove it is not actionable.
    }
  };

  /**
   * `deferDetach` exists for the one caller that has just spoken to the panel:
   * `postMessage` is delivered asynchronously, so removing the frame in the
   * same turn would drop the `teardown` the panel was owed. Everything the host
   * itself depends on — the listener, the in-flight reads — is released
   * immediately either way.
   */
  const dispose = (deferDetach = false) => {
    if (disposed) return;
    disposed = true;
    window.removeEventListener("message", listener);
    for (const pending of pendingRequests.values()) pending.cancel();
    pendingRequests.clear();
    const settleState = pendingState;
    pendingState = null;
    settleState?.(undefined);
    if (deferDetach) {
      setTimeout(detachFrame, 0);
    } else {
      detachFrame();
    }
  };

  /**
   * One bounded request round trip, shared by all three request types (D-017).
   *
   * Register the request as in flight, race the resolver against the read
   * timeout and against teardown, then either post the request's own result
   * type or post an `error` carrying the request id — which is what lets the
   * panel fail one request without waiting out its own timeout (D-016.2). A
   * teardown while it is in flight resolves it `cancelled` and posts nothing,
   * because the window it would post into is going away.
   */
  const answerRequest = async (
    kind: "read" | "resource" | "host_action",
    requestId: string,
    resolve: () => Promise<unknown>,
    deliver: (value: unknown) => void,
  ): Promise<PanelRequestOutcome> => {
    if (disposed) return { status: "cancelled" };
    const cancelled = new Promise<RequestRaceOutcome>((settle) => {
      pendingRequests.set(requestId, { cancel: () => settle({ status: "cancelled" }) });
    });
    const timedOut = new Promise<RequestRaceOutcome>((settle) => {
      setTimeout(() => settle({ status: "timed_out" }), readTimeoutMs);
    });
    const answered = (async (): Promise<RequestRaceOutcome> => {
      try {
        return { status: "answered", value: await resolve() };
      } catch (error) {
        return { status: "failed", message: describeError(error) };
      }
    })();

    const outcome = await Promise.race([cancelled, timedOut, answered]);
    pendingRequests.delete(requestId);
    if (outcome.status === "cancelled" || disposed) {
      return { status: "cancelled" };
    }
    if (outcome.status === "answered") {
      deliver(outcome.value);
      return { status: "answered" };
    }
    post("error", {
      code: outcome.status === "timed_out" ? `${kind}_timeout` : `${kind}_failed`,
      message:
        outcome.status === "timed_out"
          ? `the host did not answer ${kind} ${requestId} within ${readTimeoutMs}ms`
          : outcome.message,
      request_id: requestId,
    });
    return outcome;
  };

  const connection: PanelFrameConnection = {
    panelId,
    token,
    element: handle.element,
    capability: init.capability,
    get disposed() {
      return disposed;
    },
    send: post,
    answerRead(request, resolve) {
      return answerRequest("read", request.request_id, () => resolve(request.query), (value) =>
        post("read_result", { request_id: request.request_id, window: value }),
      );
    },
    answerResource(request, resolve) {
      return answerRequest(
        "resource",
        request.request_id,
        () => resolve(request.resource_id, request.params ?? null),
        (value) => post("resource_result", { request_id: request.request_id, resource: value }),
      );
    },
    answerHostAction(request, perform) {
      return answerRequest(
        "host_action",
        request.request_id,
        () => perform(request.action, request.params ?? null),
        (value) => {
          // A performer that resolves without an outcome did the thing and has
          // nothing to add; that is `ok: true` with no detail.
          const outcome = (value ?? { ok: true }) as PanelHostActionOutcome;
          post("host_action_result", {
            request_id: request.request_id,
            ok: outcome.ok !== false,
            detail: outcome.detail ?? null,
          });
        },
      );
    },
    async requestState(timeoutMs = PANEL_STATE_REQUEST_TIMEOUT_MS) {
      if (disposed) return { kept: false, reason: "the mount was torn down" };
      const answered = new Promise<unknown>((settle) => {
        pendingState = settle;
      });
      if (!post("state_request", {})) {
        pendingState = null;
        return { kept: false, reason: "the panel could not be reached" };
      }
      const settled = await settleWithin(answered, timeoutMs);
      pendingState = null;
      if (settled.status !== "resolved") {
        return { kept: false, reason: "the panel did not answer the state request" };
      }
      return sanitizePanelState(settled.value);
    },
    teardown() {
      if (disposed) return;
      post("teardown", {});
      dispose(true);
    },
  };

  window.addEventListener("message", listener);
  container.appendChild(handle.element);

  const loaded = await settleWithin(handle.whenLoaded(), loadTimeoutMs);
  if (disposed) {
    return {
      ok: false,
      failure: panelFailure(panelId, "torn_down", "was torn down while loading"),
    };
  }
  if (loaded.status === "timeout") {
    dispose();
    return {
      ok: false,
      failure: panelFailure(
        panelId,
        "load_timeout",
        `did not finish loading within ${loadTimeoutMs}ms`,
      ),
    };
  }
  if (loaded.status === "rejected") {
    dispose();
    return {
      ok: false,
      failure: panelFailure(
        panelId,
        "load_timeout",
        `failed to load its entry document: ${describeError(loaded.error)}`,
      ),
    };
  }

  const handshake = new Promise<PanelToHostMessage>((settle) => {
    resolveHandshake = settle;
  });

  if (
    !post("init", {
      api_version: acceptedApiVersion,
      panel_id: panelId,
      capability: init.capability,
      target: init.target,
      bindings: init.bindings,
      read_limits: init.readLimits,
      asset_base_url: init.assetBaseUrl,
      restored_state: init.restoredState,
    })
  ) {
    dispose();
    return {
      ok: false,
      failure: panelFailure(panelId, "frame_unavailable", "exposed no window to hand `init` to"),
    };
  }

  const answer = await settleWithin(handshake, handshakeTimeoutMs);
  resolveHandshake = null;
  if (disposed) {
    return {
      ok: false,
      failure: panelFailure(panelId, "torn_down", "was torn down during the handshake"),
    };
  }
  if (answer.status !== "resolved") {
    dispose();
    return {
      ok: false,
      failure: panelFailure(
        panelId,
        "handshake_timeout",
        `did not answer \`init\` with \`ready\` within ${handshakeTimeoutMs}ms`,
      ),
    };
  }
  const answered = answer.value;
  if (answered.type !== "ready") {
    dispose();
    const detail = answered.type === "error" ? `: ${answered.payload.message}` : "";
    return {
      ok: false,
      failure: panelFailure(
        panelId,
        "panel_error",
        `reported an error before it was mounted${detail}`,
      ),
    };
  }
  const declared = answered.payload.api_version;
  if (!isAcceptedApiVersion(declared, acceptedApiVersion)) {
    dispose();
    return {
      ok: false,
      failure: panelFailure(
        panelId,
        "version_mismatch",
        `declares panel API version ${JSON.stringify(declared)}, which this host does not accept ` +
          `(it accepts ${JSON.stringify(acceptedApiVersion)})`,
      ),
    };
  }

  handshakeDone = true;
  return { ok: true, connection };
}
