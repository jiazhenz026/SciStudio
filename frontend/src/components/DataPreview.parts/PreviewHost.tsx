/**
 * ADR-048 SPEC 1 / ADR-054 — PreviewHost (FR-020 .. FR-023).
 *
 * The routed preview container. For a selected {@link PreviewTarget} it creates
 * a session via `POST /api/previews/sessions` and reads the
 * {@link PreviewEnvelope}. A `panel` envelope mounts the routed panel in its
 * sandboxed frame ({@link PanelPreview}); anything else is an `error` envelope,
 * shown with its typed error. Every preview renders through a panel: the legacy
 * previewer module loader and the compiled per-kind viewers were removed
 * (ADR-054 §8, #2493).
 *
 * A panel that fails to load offers the core panel for the type: the host
 * re-creates the session with `core_only`. Child previews (a composite slot, a
 * collection item) are opened by the panel host and rendered through a nested
 * `PreviewHost` with the backend-resolved child envelope.
 *
 * The host keeps only UI-level state (active envelope, routing epoch); the
 * backend remains authoritative for routing, sessions, and data. Cache keying
 * lives in the Zustand preview slice (FR-021); this component writes it through
 * the injected callbacks.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../lib/api";
import { PanelPreview } from "../../panels/PanelPreview";
import { previewIsAffected, subscribePreviewReroute } from "../../panels/panelEvents";
import type { PanelSnapshot } from "../../panels/types";
import type { PreviewEnvelope, PreviewTarget } from "../../types/api";

import { ErrorViewer } from "./PreviewError";

export interface PreviewHostProps {
  /** Backend-resolved child; never reconstructed from an untrusted child ref. */
  initialEnvelope?: PreviewEnvelope;
  /** Resume a frozen session, including composite-local targets, on maximize. */
  previewSessionId?: string;
  panelId?: string;
  initialViewState?: unknown;
  onPanelSnapshot?: (snapshot: PanelSnapshot | null) => void;
  /** The target to preview. A `null` target renders the empty state. */
  target: PreviewTarget | null;
  /** Optional initial query state (slice/page/sort). */
  initialQuery?: Record<string, unknown>;
  /**
   * Optional session-keyed cache hooks (FR-021). The host writes rendered
   * envelopes only after the backend has resolved preview identity, so cache
   * keys include target + previewer + session + query + data version.
   */
  getCachedEnvelope?: (key: string) => PreviewEnvelope | undefined;
  cacheEnvelope?: (key: string, envelope: PreviewEnvelope) => void;
  buildCacheKey?: (
    target: PreviewTarget,
    query: Record<string, unknown>,
    opts?: PreviewCacheKeyOptions,
  ) => string;
}

type Status = "idle" | "loading" | "ready" | "error";
type PreviewCacheKeyOptions = {
  previewerId?: string | null;
  sessionId?: string | null;
  dataVersion?: string | number | null;
};

function cacheDataVersionFromEnvelope(envelope: PreviewEnvelope): string | number | null {
  const candidates = [
    envelope.metadata?.data_version,
    envelope.metadata?.dataVersion,
    envelope.payload?.data_version,
    envelope.payload?.dataVersion,
  ];
  const value = candidates.find(
    (candidate) => typeof candidate === "string" || typeof candidate === "number",
  );
  return typeof value === "string" || typeof value === "number" ? value : null;
}

function cacheIdentityFromEnvelope(envelope: PreviewEnvelope): PreviewCacheKeyOptions {
  return {
    previewerId: envelope.previewer_id,
    sessionId: envelope.session_id,
    dataVersion: cacheDataVersionFromEnvelope(envelope),
  };
}

function cacheEnvelopeForQuery(
  cacheEnvelope: PreviewHostProps["cacheEnvelope"],
  buildCacheKey: PreviewHostProps["buildCacheKey"],
  target: PreviewTarget,
  query: Record<string, unknown>,
  envelope: PreviewEnvelope,
) {
  if (!cacheEnvelope || !buildCacheKey) return;
  cacheEnvelope(buildCacheKey(target, query, cacheIdentityFromEnvelope(envelope)), envelope);
}

export function PreviewHost({
  initialEnvelope,
  previewSessionId,
  target,
  initialQuery,
  cacheEnvelope,
  buildCacheKey,
  panelId,
  initialViewState,
  onPanelSnapshot,
}: PreviewHostProps) {
  /*
   * #2465 — this preview's routing epoch. The panel service names what changed
   * (type claims whose candidates moved, or one type whose choice moved) and
   * only a preview it concerns bumps its epoch; the session-creation effect
   * then re-creates the session through the new routing. Every other open
   * preview stays mounted untouched.
   */
  const [routingEpoch, setRoutingEpoch] = useState(0);
  const fallbackTargetKey = `${target?.kind}:${target?.ref}:${routingEpoch}`;
  const [coreOnlyTarget, setCoreOnlyTarget] = useState<string | null>(null);
  const coreOnly = coreOnlyTarget === fallbackTargetKey;
  const [status, setStatus] = useState<Status>("idle");
  const [envelope, setEnvelope] = useState<PreviewEnvelope | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  const routedEnvelope = useRef<PreviewEnvelope | null>(null);
  routedEnvelope.current = envelope;
  useEffect(
    () =>
      subscribePreviewReroute((signal) => {
        const current = routedEnvelope.current;
        if (current && previewIsAffected(current, signal)) setRoutingEpoch((value) => value + 1);
      }),
    [],
  );
  const initialQueryKey = useMemo(() => JSON.stringify(initialQuery ?? {}), [initialQuery]);

  // -- session creation ----------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    if (!target) {
      setStatus("idle");
      setEnvelope(null);
      return;
    }
    const query = {
      ...(initialQuery ?? {}),
      ...(coreOnly ? { core_only: true } : panelId ? { panel_id: panelId } : {}),
    };

    setStatus("loading");
    setRequestError(null);
    const sessionId = initialEnvelope?.session_id ?? previewSessionId;
    const resolved = sessionId
      ? coreOnly
        ? api.patchPreviewSession(sessionId, { core_only: true })
        : initialEnvelope
          ? Promise.resolve(initialEnvelope)
          : routingEpoch > 0
            ? // #2465 Q5-b — a re-route can find the frozen session gone (its
              // panel was removed); the preview recreates one instead of erroring.
              api.getPreviewSession(sessionId).catch(() => api.createPreviewSession(target, query))
            : api.getPreviewSession(sessionId)
      : api.createPreviewSession(target, query);
    resolved
      .then((env) => {
        if (cancelled) return;
        setEnvelope(env);
        setStatus("ready");
        cacheEnvelopeForQuery(cacheEnvelope, buildCacheKey, target, query, env);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setRequestError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
    // initialQuery is captured intentionally on target change only. routingEpoch
    // (#2113, #2465) is a deliberate dep: a routing change that concerns this
    // preview must re-create the session so the new routing applies to it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    target?.ref,
    target?.kind,
    initialQueryKey,
    routingEpoch,
    coreOnly,
    panelId,
    initialEnvelope?.session_id,
    previewSessionId,
  ]);

  useEffect(() => {
    if (envelope && !envelope.panel) {
      onPanelSnapshot?.({
        target: envelope.target,
        ...(envelope.session_id ? { previewSessionId: envelope.session_id } : {}),
      });
    }
  }, [envelope, onPanelSnapshot]);

  // -- render --------------------------------------------------------------
  if (!target || status !== "ready")
    return <PreviewStatus status={target ? status : "idle"} requestError={requestError} />;
  if (!envelope) return null;

  if (envelope.panel) {
    return (
      <MountedPanel
        envelope={envelope}
        panelId={envelope.panel.id}
        initialViewState={initialViewState}
        onPanelSnapshot={onPanelSnapshot}
        onFallback={() => {
          onPanelSnapshot?.(null);
          setCoreOnlyTarget(fallbackTargetKey);
        }}
      />
    );
  }

  return (
    <div data-testid="preview-host">
      <ErrorViewer envelope={envelope} />
    </div>
  );
}

/**
 * A panel-backed envelope: the frame.
 *
 * Extracted from `PreviewHost` rather than inlined because every wrapper
 * between the stage and the iframe has to be a flex column that can shrink, or
 * the frame falls back to its own minimum height and a figure takes a third of
 * a focused tab. Keeping that chain in one readable place is the point.
 */
function MountedPanel({
  envelope,
  panelId,
  initialViewState,
  onPanelSnapshot,
  onFallback,
}: {
  envelope: PreviewEnvelope;
  panelId: string;
  initialViewState?: PreviewHostProps["initialViewState"];
  onPanelSnapshot?: PreviewHostProps["onPanelSnapshot"];
  onFallback: () => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="preview-host">
      <PanelPreview
        key={`${envelope.session_id}:${panelId}`}
        target={envelope.target}
        panelId={panelId}
        previewSessionId={envelope.session_id}
        initialViewState={initialViewState}
        onSnapshot={onPanelSnapshot}
        renderChild={(child, onSnapshot) => (
          <PreviewHost target={child.target} initialEnvelope={child} onPanelSnapshot={onSnapshot} />
        )}
        onFallback={onFallback}
      />
    </div>
  );
}

function PreviewStatus({ status, requestError }: { status: Status; requestError: string | null }) {
  if (status === "idle") {
    return (
      <div className="rounded-[1.6rem] border border-dashed border-stone-300 px-4 py-6 text-sm text-stone-500">
        Nothing to preview yet
      </div>
    );
  }
  if (status === "loading") {
    return (
      <div
        className="rounded-[1.6rem] border border-stone-200 bg-white p-4 text-sm text-stone-500"
        data-testid="preview-host-loading"
      >
        Loading preview…
      </div>
    );
  }
  if (status === "error") {
    return (
      <div
        className="rounded-[1.6rem] border border-red-300 bg-red-50 p-4 text-sm text-red-800"
        data-testid="preview-host-request-error"
        role="alert"
      >
        Could not create a preview session: {requestError}
      </div>
    );
  }
  return null;
}
