/**
 * ADR-054 spec 1, T-005 and T-006 — the React host for a panel.
 *
 * `PanelHost` owns one mount: the sandboxed frame, the per-mount token, the
 * handshake, the version gate, the capability gate, the bounded windowed read,
 * the update channel, the error channel, and the optional state hook. It is the
 * only place in the frontend that knows a panel is a frame.
 *
 * **The version gate takes its version from the backend (D-010).** The
 * descriptor carries both the version the panel declares and the version the
 * backend accepts. No constant in this file, or anywhere else in the frontend,
 * spells a panel API version: exactly one such constant exists in the tree and
 * it is `PANEL_API_VERSION` in `scistudio.core.panels` (FR-004, SC-001). A
 * panel declaring a version the host does not accept is refused *before* it is
 * mounted, and the same check runs again against what the document declares in
 * its `ready` message.
 *
 * **Hot reload and the state hook (FR-030, FR-031).** Changing `remountToken`
 * tears the frame down and builds a new one from the document as it now is on
 * disk. The frame boundary is what makes that clean: discarding a frame leaves
 * no cached module behind, which is precisely what neither retired ES-module
 * loader could promise. Across that remount the host carries the panel's own
 * snapshot: it sends `state_request` before the teardown, waits a bounded time
 * for the answer, and hands whatever came back to the new mount as
 * `init.restored_state`. A panel that does not implement the hook never answers
 * and remounts clean; a snapshot that will not serialise is discarded by
 * `sanitizePanelState` and the panel remounts clean too. Neither is a failed
 * reload — losing an in-progress selection is recoverable, failing to reload
 * after a save is not.
 *
 * **The fallback is the caller's decision (FR-015, FR-036).** When a mount
 * fails, `PanelHost` renders its own error surface and hands the failure to
 * `renderFallback`. It does not choose a panel, and it holds no mapping from a
 * response's kind to one: the backend names the panel and the fallback panel in
 * the response the caller is already reading. Mounting that fallback is a
 * second `PanelHost` the caller renders.
 */

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { ReactNode } from "react";

import type { PanelDiagnostic } from "./PanelErrorSurface";
import { PanelDiagnosticsBanner, PanelErrorSurface } from "./PanelErrorSurface";
import type { PanelCapabilityDenial, PanelEmitConsumer } from "./panelCapability";
import { createPanelCapabilityGate } from "./panelCapability";
import type { PanelDescriptor } from "./panelDescriptor";
import { validatePanelDescriptor } from "./panelDescriptor";
import type {
  PanelFailure,
  PanelFrameConnection,
  PanelFrameFactory,
  PanelHostActionPerformer,
  PanelReadResolver,
  PanelResourceResolver,
} from "./panelFrame";
import { mountPanelFrame, panelFailure } from "./panelFrame";
import type {
  PanelBindingSnapshot,
  PanelStateSnapshot,
  PanelToHostMessage,
  PanelUpdatePayload,
} from "./panelMessages";
import { sanitizePanelState } from "./panelMessages";

export type PanelHostStatus = "mounting" | "ready" | "failed";

export interface PanelHostHandle {
  /**
   * Ask the mounted panel for its snapshot (FR-031). Resolves `kept: false`
   * when there is no mount, when the panel does not implement the hook, or
   * when the snapshot will not serialise — in every one of those cases the
   * panel remounts clean rather than the reload failing.
   */
  requestState(timeoutMs?: number): Promise<PanelStateSnapshot>;
  /** Push one update over the update channel (FR-010). */
  sendUpdate(payload: PanelUpdatePayload): boolean;
}

export interface PanelHostProps {
  readonly descriptor: PanelDescriptor;
  /** What a displaying panel is showing: the opening snapshot. */
  readonly target?: unknown;
  /** What a producing panel is bound to; more than one is ordinary (FR-013). */
  readonly bindings?: Readonly<Record<string, PanelBindingSnapshot>> | null;
  /** A snapshot from a previous mount of this panel (FR-031). */
  readonly restoredState?: unknown;
  /** Posted to the panel whenever its identity changes, once ready (FR-010). */
  readonly update?: PanelUpdatePayload | null;
  /** Answers one bounded windowed read. Absent means the panel gets no reads. */
  readonly onRead?: PanelReadResolver;
  /**
   * Answers one `resource` — a bounded follow-up read addressed by id (D-017).
   * Composite slot navigation and collection item opening go through it.
   */
  readonly onResource?: PanelResourceResolver;
  /**
   * Performs one `host_action` — export, download, editor handoff (D-017).
   * Chrome the frame cannot draw for itself, because it is granted
   * `allow-scripts` and nothing else.
   */
  readonly onHostAction?: PanelHostActionPerformer;
  /** Where a producing panel's emitted code goes (FR-012). */
  readonly onEmit?: PanelEmitConsumer;
  /** Called once when the mount fails (FR-014). */
  readonly onFailure?: (failure: PanelFailure) => void;
  /** Called for every non-fatal report from the panel or about it. */
  readonly onDiagnostic?: (diagnostic: PanelDiagnostic) => void;
  /** Called when the panel volunteers a snapshot outside a state request. */
  readonly onState?: (snapshot: PanelStateSnapshot) => void;
  /**
   * Rendered beneath the error surface when the mount fails. The caller decides
   * whether that is the fallback panel the backend named (FR-015, FR-036).
   */
  readonly renderFallback?: (failure: PanelFailure) => ReactNode;
  /** Change this to force a remount of the same panel (hot reload, FR-030). */
  readonly remountToken?: string | number;
  /** The frame-creation seam. Production leaves it alone. */
  readonly frameFactory?: PanelFrameFactory;
  readonly loadTimeoutMs?: number;
  readonly handshakeTimeoutMs?: number;
  readonly readTimeoutMs?: number;
  readonly className?: string;
}

/** Everything the mount effect reads but must not remount for. */
interface LatestProps {
  descriptor: PanelDescriptor;
  target: unknown;
  bindings: Readonly<Record<string, PanelBindingSnapshot>> | null;
  restoredState: unknown;
  onRead?: PanelReadResolver;
  onResource?: PanelResourceResolver;
  onHostAction?: PanelHostActionPerformer;
  onEmit?: PanelEmitConsumer;
  onFailure?: (failure: PanelFailure) => void;
  onDiagnostic?: (diagnostic: PanelDiagnostic) => void;
  onState?: (snapshot: PanelStateSnapshot) => void;
}

/** The identity of a mount: change any of it and the frame is rebuilt. */
function mountIdentity(descriptor: PanelDescriptor, remountToken?: string | number): string {
  return [
    descriptor?.panel_id,
    descriptor?.document_url,
    descriptor?.api_version,
    descriptor?.accepted_api_version,
    descriptor?.capability,
    descriptor?.asset_base_url,
    remountToken ?? "",
  ].join("\u0000");
}

/** One line for anything thrown while asking for a snapshot. Never throws. */
function describeStateError(error: unknown): string {
  try {
    return error instanceof Error
      ? `the state request failed: ${error.message}`
      : `the state request failed: ${String(error)}`;
  } catch {
    return "the state request failed";
  }
}

export const PanelHost = forwardRef<PanelHostHandle, PanelHostProps>(
  function PanelHost(props, ref) {
    const {
      descriptor,
      renderFallback,
      frameFactory,
      loadTimeoutMs,
      handshakeTimeoutMs,
      readTimeoutMs,
      remountToken,
      update,
      className,
    } = props;

    const containerRef = useRef<HTMLDivElement | null>(null);
    const connectionRef = useRef<PanelFrameConnection | null>(null);
    const diagnosticSeq = useRef(0);
    /**
     * The snapshot in transit across one remount (FR-031). Written by the mount
     * effect's cleanup when it can tell the mount is being *replaced* rather
     * than unmounted, read once by the mount that replaces it. Carries the
     * panel id so a snapshot can never be handed to a different panel.
     */
    const carriedState = useRef<{
      readonly panelId: string;
      readonly snapshot: Promise<PanelStateSnapshot>;
    } | null>(null);
    const latest = useRef<LatestProps>({
      descriptor,
      target: props.target,
      bindings: props.bindings ?? null,
      restoredState: props.restoredState,
    });

    const [status, setStatus] = useState<PanelHostStatus>("mounting");
    const [failure, setFailure] = useState<PanelFailure | null>(null);
    const [diagnostics, setDiagnostics] = useState<readonly PanelDiagnostic[]>([]);

    // Declared first so it runs before the mount effect on every commit: the
    // mount effect reads these through the ref and must never see a stale set.
    useEffect(() => {
      latest.current = {
        descriptor: props.descriptor,
        target: props.target,
        bindings: props.bindings ?? null,
        restoredState: props.restoredState,
        onRead: props.onRead,
        onResource: props.onResource,
        onHostAction: props.onHostAction,
        onEmit: props.onEmit,
        onFailure: props.onFailure,
        onDiagnostic: props.onDiagnostic,
        onState: props.onState,
      };
    });

    const record = useCallback((panelId: string, code: string, message: string) => {
      diagnosticSeq.current += 1;
      const diagnostic: PanelDiagnostic = {
        id: `${panelId}:${diagnosticSeq.current}`,
        panelId,
        code,
        message,
      };
      setDiagnostics((current) => [...current, diagnostic]);
      latest.current.onDiagnostic?.(diagnostic);
    }, []);

    const identity = mountIdentity(descriptor, remountToken);

    /*
     * Is the next cleanup a *replacement* or an unmount?
     *
     * Only a replacement is worth a `state_request`: on an unmount there is
     * nothing to restore into, and waiting on an answer would hold a dead frame
     * in the document for the length of the bounded wait. React renders before
     * it runs the old effect's cleanup, so comparing the identity here — in the
     * render pass — is what lets the cleanup tell the two apart. Assigning to a
     * ref during render is idempotent and survives a double render.
     */
    const lastIdentity = useRef(identity);
    const replacing = useRef(false);
    if (lastIdentity.current !== identity) {
      lastIdentity.current = identity;
      replacing.current = true;
    }

    useEffect(() => {
      const container = containerRef.current;
      let live: PanelFrameConnection | null = null;
      let cancelled = false;

      setStatus("mounting");
      setFailure(null);
      setDiagnostics([]);

      const current = latest.current.descriptor;
      const fail = (reported: PanelFailure) => {
        if (cancelled) return;
        setFailure(reported);
        setStatus("failed");
        latest.current.onFailure?.(reported);
      };

      const invalid = validatePanelDescriptor(current);
      if (invalid) {
        fail(invalid);
        return;
      }
      if (!container) {
        fail(
          panelFailure(current.panel_id, "frame_unavailable", "has no host container to mount in"),
        );
        return;
      }

      const panelId = current.panel_id;
      const capability = current.capability;

      const reportDenial = (denial: PanelCapabilityDenial) => {
        record(denial.panelId, denial.code, denial.message);
        connectionRef.current?.send("error", {
          code: denial.code,
          message: denial.message,
          request_id: null,
        });
      };

      // T-006, SC-007. The emit path is wired only for a producing mount: for a
      // displaying mount no consumer is passed in at all, so there is nothing
      // behind the gate for an `emit` to reach.
      const gate = createPanelCapabilityGate(panelId, capability, {
        onEmit:
          capability === "producing" ? (code: string) => latest.current.onEmit?.(code) : undefined,
        onDenied: reportDenial,
      });

      const handleMessage = (message: PanelToHostMessage, connection: PanelFrameConnection) => {
        switch (message.type) {
          case "read": {
            const resolver = latest.current.onRead;
            void connection.answerRead(
              message.payload,
              resolver ??
                (() => Promise.reject(new Error("this mount was given no way to read data"))),
            );
            return;
          }
          case "resource": {
            const resolver = latest.current.onResource;
            void connection.answerResource(
              message.payload,
              resolver ??
                (() => Promise.reject(new Error("this mount was given no way to open a resource"))),
            );
            return;
          }
          case "host_action": {
            const perform = latest.current.onHostAction;
            void connection.answerHostAction(
              message.payload,
              perform ??
                (() =>
                  Promise.reject(
                    new Error(`this host does not perform "${message.payload.action}"`),
                  )),
            );
            return;
          }
          case "emit": {
            gate.deliverEmit(message.payload);
            return;
          }
          case "error": {
            record(panelId, "panel_error", message.payload.message);
            return;
          }
          case "state": {
            latest.current.onState?.(sanitizePanelState(message.payload.state));
            return;
          }
          default:
            // `ready` after the handshake is complete carries nothing new.
            return;
        }
      };

      /*
       * FR-031's remount half. A snapshot the previous mount handed back wins
       * over the `restoredState` prop, because it is this panel's own more
       * recent state; the prop is the opening value a caller supplies for a
       * first mount. `carriedState` is consumed here whether or not it is used,
       * so a stale snapshot can never reach a third mount.
       */
      const carried = carriedState.current;
      carriedState.current = null;

      void (async () => {
        let restoredState = latest.current.restoredState;
        if (carried && carried.panelId === panelId) {
          const snapshot = await carried.snapshot;
          if (snapshot.kept) {
            restoredState = snapshot.state;
          } else {
            // Not a failure: the panel implements no hook, or its snapshot
            // would not serialise. Either way it remounts clean (FR-031).
            restoredState = latest.current.restoredState;
          }
        }
        if (cancelled) return;

        const result = await mountPanelFrame({
          container,
          panelId,
          documentUrl: current.document_url,
          acceptedApiVersion: current.accepted_api_version,
          title: current.display_name ?? panelId,
          init: {
            capability,
            target: latest.current.target,
            bindings: latest.current.bindings,
            readLimits: current.read_limits,
            assetBaseUrl: current.asset_base_url,
            restoredState,
          },
          frameFactory,
          loadTimeoutMs,
          handshakeTimeoutMs,
          readTimeoutMs,
          onMessage: handleMessage,
        });
        if (!result.ok) {
          fail(result.failure);
          return;
        }
        if (cancelled) {
          result.connection.teardown();
          return;
        }
        live = result.connection;
        connectionRef.current = result.connection;
        setStatus("ready");
      })();

      return () => {
        cancelled = true;
        const going = live;
        const isReplacement = replacing.current;
        replacing.current = false;
        if (going && isReplacement) {
          // FR-030 + FR-031: ask for the snapshot, then tear down whatever the
          // answer was. The teardown is chained rather than raced so the frame
          // is still there to answer, and the next mount awaits this same
          // promise, so it never appends into a container the old frame is
          // still leaving.
          carriedState.current = {
            panelId: going.panelId,
            snapshot: going
              .requestState()
              .catch(
                (error: unknown) =>
                  ({ kept: false, reason: describeStateError(error) }) as PanelStateSnapshot,
              )
              .then((snapshot) => {
                going.teardown();
                return snapshot;
              }),
          };
        } else {
          going?.teardown();
        }
        if (connectionRef.current === going) connectionRef.current = null;
      };
    }, [identity, frameFactory, loadTimeoutMs, handshakeTimeoutMs, readTimeoutMs, record]);

    // The update channel (FR-010): a new update object is pushed to a live panel.
    useEffect(() => {
      if (status !== "ready" || !update) return;
      connectionRef.current?.send("update", update);
    }, [status, update]);

    useImperativeHandle(
      ref,
      () => ({
        requestState: async (timeoutMs?: number) => {
          const connection = connectionRef.current;
          if (!connection) return { kept: false as const, reason: "no panel is mounted" };
          return connection.requestState(timeoutMs);
        },
        sendUpdate: (payload: PanelUpdatePayload) =>
          connectionRef.current?.send("update", payload) ?? false,
      }),
      [],
    );

    return (
      <div
        className={className}
        data-testid="panel-host"
        data-panel-id={descriptor?.panel_id}
        data-panel-status={status}
      >
        <PanelDiagnosticsBanner diagnostics={diagnostics} />
        {failure ? (
          <>
            <PanelErrorSurface failure={failure} panelName={descriptor?.display_name} />
            {renderFallback ? renderFallback(failure) : null}
          </>
        ) : null}
        <div
          ref={containerRef}
          data-testid="panel-frame-container"
          className="h-full w-full"
          hidden={failure !== null}
        />
      </div>
    );
  },
);
