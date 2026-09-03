/**
 * ADR-054 spec 1, T-007 and T-008 — the routed preview surface, merged with the
 * panel host.
 *
 * This component owns the *session*: it creates one for the selected target,
 * patches its query, fetches its bounded resources, saves what it exports, and
 * keeps the drill-down stack of child envelopes. What it no longer owns is any
 * decision about what renders the data.
 *
 * **Three things went away here, and the reasons are different.**
 *
 * 1. *The ES-module loader.* A panel is now a document in a sandboxed frame
 *    (FR-007), mounted by the single `mountPanelFrame` in `frontend/src/panels/`.
 *    `dynamicPanel.ts` and its host API are deleted rather than wrapped
 *    (SC-002), and with them the second panel API version constant: the one
 *    definition lives in `scistudio.core.panels` and reaches the host as
 *    `accepted_api_version` on the descriptor (D-010, SC-001).
 * 2. *The kind-to-viewer dispatch.* `CoreFallbackRenderer` switched on
 *    `envelope.kind` to pick a compiled React viewer. The backend has already
 *    chosen a panel and named the fallback, so the host mounts what it was told
 *    (FR-015, FR-036, SC-010). The nine viewers are panel documents now.
 * 3. *The diagnostics banner and the error surface.* Not gone — moved. They are
 *    host chrome (FR-035) and live in `frontend/src/panels/PanelErrorSurface.tsx`,
 *    where they render as ordinary React markup with no frame and no message
 *    contract, so they still work when the frame mechanism itself does not.
 *
 * **What the host does across the boundary** (D-017). A panel speaks three
 * request types and this component answers all three, for displaying and
 * producing mounts alike — FR-011 withholds the *emission* path from a
 * displaying panel, not the bounded read FR-010 requires the host to supply:
 *
 *   - `read` — a patch of the panel's own query state, answered by patching the
 *     session and handing back the new envelope.
 *   - `resource` — a bounded follow-up read by id. A composite slot or a
 *     collection item resolves to a child envelope, and the host routes that
 *     child into its own panel through the drill-down stack rather than pushing
 *     a second object's payload into a panel that was never bound to it.
 *   - `host_action` — export, download, editor handoff: chrome the frame cannot
 *     perform for itself because it holds `allow-scripts` and nothing else.
 *
 * **The tutorial surface a frame cannot carry** (D-019). The shipped
 * `what-is-a-type` tutorial depends on the `preview_item_opened` UI event and
 * on two highlight targets that used to sit on components inside what is now an
 * opaque frame. Neither can survive the boundary, so the host keeps both: it
 * fires `preview_item_opened` when it services a collection item's `resource`,
 * and it carries the highlight targets on its own chrome around the frame. See
 * `PanelTutorialChrome` for why each one is attached where it is.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../lib/api";
import type {
  PanelDescriptor,
  PanelDiagnostic,
  PanelFailure,
  PanelFrameFactory,
  PanelHostActionOutcome,
} from "../../panels";
import { PanelDiagnosticsBanner, PanelErrorSurface, PanelHost } from "../../panels";
import { useAppStore } from "../../store";
import { usePanelReloadToken } from "../../store/usePanelReload";
import type {
  PanelDescriptorResponse,
  PreviewEnvelope,
  PreviewResource,
  PreviewResourceResponse,
  PreviewTarget,
} from "../../types/api";

import { COLLECTION_ITEM_PREFIX, PanelTutorialChrome } from "./PanelTutorialChrome";

export interface PreviewHostProps {
  /** The target to preview. A `null` target renders the empty state. */
  target: PreviewTarget | null;
  /** Optional initial query state (slice/page/sort). */
  initialQuery?: Record<string, unknown>;
  /**
   * #2113 — routing epoch. Bumped by the store whenever a per-type panel
   * choice changes (#2049); the session-creation effect re-runs, so an open
   * preview re-creates its session and the backend routes it through the new
   * choice instead of sitting on the envelope the old choice produced.
   */
  routingEpoch?: number;
  /**
   * Optional session-keyed cache hooks (ADR-048 FR-021). The host writes
   * rendered envelopes only after the backend has resolved panel identity, so
   * cache keys include target + panel + session + query + data version.
   */
  getCachedEnvelope?: (key: string) => PreviewEnvelope | undefined;
  cacheEnvelope?: (key: string, envelope: PreviewEnvelope) => void;
  buildCacheKey?: (
    target: PreviewTarget,
    query: Record<string, unknown>,
    opts?: PreviewCacheKeyOptions,
  ) => string;
  /** Test seam: the frame-creation seam `mountPanelFrame` builds through. */
  frameFactory?: PanelFrameFactory;
}

type Status = "idle" | "loading" | "ready" | "error";
type PreviewCacheKeyOptions = {
  panelId?: string | null;
  sessionId?: string | null;
  dataVersion?: string | number | null;
};
const RESOURCE_PARAMS_MAX_CHARS = 8192;

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
    panelId: envelope.previewer_id,
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

/**
 * The descriptor the backend named, or `null`.
 *
 * `null` is not a routing decision the host then makes for itself: it means the
 * response did not name a panel, which the error surface reports as such. There
 * is deliberately no local table to fall back to (FR-036, SC-010).
 */
function descriptorOf(
  descriptor: PanelDescriptorResponse | null | undefined,
): PanelDescriptor | null {
  if (!descriptor || typeof descriptor.panel_id !== "string") return null;
  return descriptor as PanelDescriptor;
}

export function PreviewHost({
  target,
  initialQuery,
  routingEpoch,
  cacheEnvelope,
  buildCacheKey,
  frameFactory,
}: PreviewHostProps) {
  const [status, setStatus] = useState<Status>("idle");
  const [envelope, setEnvelope] = useState<PreviewEnvelope | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  // Diagnostics raised by the host itself (a failed resource, a failed export).
  const [hostDiagnostics, setHostDiagnostics] = useState<PanelDiagnostic[]>([]);
  // Drill-down stack of child envelopes (composite slot / collection item).
  const [childStack, setChildStack] = useState<PreviewEnvelope[]>([]);
  /*
   * FR-014: the chosen panel failed, so the named fallback is what mounts.
   *
   * The failure is stored *with the mount it belongs to* rather than cleared by
   * an effect when the panel changes. An effect cannot do this correctly: a
   * child's effects run before its parent's in the same commit, so the mount
   * that fails during the commit where the envelope first arrives would have
   * its failure wiped by a reset effect running immediately afterwards — and
   * the reader would sit forever on a panel that had already given up. Keying
   * the record means a stale failure simply stops matching.
   */
  const [chosenFailure, setChosenFailure] = useState<{
    readonly key: string;
    readonly failure: PanelFailure;
  } | null>(null);

  const queryRef = useRef<Record<string, unknown>>(initialQuery ?? {});
  const diagnosticSeq = useRef(0);
  const initialQueryKey = useMemo(() => JSON.stringify(initialQuery ?? {}), [initialQuery]);

  const note = useCallback((panelId: string, code: string, message: string) => {
    diagnosticSeq.current += 1;
    const id = `${panelId}:${diagnosticSeq.current}`;
    setHostDiagnostics((current) => [...current, { id, panelId, code, message }]);
  }, []);

  // -- session creation ----------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    setChildStack([]);
    setHostDiagnostics([]);
    setChosenFailure(null);
    if (!target) {
      setStatus("idle");
      setEnvelope(null);
      return;
    }
    const query = { ...(initialQuery ?? {}) };
    queryRef.current = query;

    setStatus("loading");
    setRequestError(null);
    api
      .createPreviewSession(target, query)
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
    // initialQuery is captured intentionally on target change only; later query
    // updates arrive through the `read` channel. routingEpoch (#2113) is a
    // deliberate dep: a choice change must re-create the session so the new
    // routing applies to the preview already open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target?.ref, target?.kind, initialQueryKey, routingEpoch]);

  // The envelope currently in focus (top of the drill-down stack, else root).
  const activeEnvelope = childStack[childStack.length - 1] ?? envelope;
  const activeRef = useRef<PreviewEnvelope | null>(activeEnvelope);
  activeRef.current = activeEnvelope;
  const rootSessionId = envelope?.session_id ?? null;

  // -- `read`: patch the session's query and hand back the new envelope ----
  const patchQuery = useCallback(
    async (patch: Readonly<Record<string, unknown>>): Promise<PreviewEnvelope> => {
      const current = activeRef.current;
      if (!current?.session_id) {
        throw new Error("this preview has no session to read from");
      }
      const isRoot = current.session_id === rootSessionId;
      if (isRoot) queryRef.current = { ...queryRef.current, ...patch };
      const next = await api.patchPreviewSession(current.session_id, { ...patch });
      if (isRoot) {
        setEnvelope(next);
        if (target) {
          cacheEnvelopeForQuery(cacheEnvelope, buildCacheKey, target, queryRef.current, next);
        }
      } else {
        setChildStack((stack) => (stack.length > 0 ? [...stack.slice(0, -1), next] : stack));
      }
      return next;
    },
    [rootSessionId, buildCacheKey, cacheEnvelope, target],
  );

  // -- `resource`: a tile comes back whole, a child is routed into a panel --
  const openResource = useCallback(
    async (resourceId: string, params: Readonly<Record<string, unknown>> | null) => {
      const active = activeRef.current;
      if (!active?.session_id) {
        throw new Error("this preview has no session to read from");
      }
      const declared = active.resources.find((r) => r.resource_id === resourceId);
      const result = await fetchPreviewResource(
        active.session_id,
        resourceId,
        mergeResourceParams(declared, params ?? undefined),
      );
      const child = result.data as unknown as PreviewEnvelope;
      if (!child || typeof child.kind !== "string") {
        // A bounded slice of the same object (an array tile). It is the panel's
        // own data, so it crosses whole.
        return result.data;
      }
      setChildStack((stack) => [...stack, child]);
      if (resourceId.startsWith(COLLECTION_ITEM_PREFIX)) {
        /*
         * ADR-053 FR-052 / ADR-054 D-019 — `preview_item_opened`, one of the
         * closed `UI_EVENT_NAMES` set, which five steps of the shipped
         * `what-is-a-type` tutorial wait on. It used to be reported by the
         * collection viewer's own card; that card is inside a frame at an
         * opaque origin now and can reach neither the store nor this event, so
         * the host reports it at the one place it can still observe the act —
         * servicing the item's `resource`.
         */
        void useAppStore.getState().reportTutorialUiEvent("preview_item_opened");
      }
      /*
       * D-017: the child was routed into its own panel, so this answer is the
       * acknowledgement rather than the child's payload. Neither built-in panel
       * that sends `resource` reads it for content, and pushing a second
       * object's data into a panel that was never bound to it would widen what
       * FR-010 asks the host to supply.
       */
      return { routed: true, resource_id: resourceId, panel_id: child.previewer_id };
    },
    [],
  );

  const popChild = useCallback(() => setChildStack((stack) => stack.slice(0, -1)), []);

  // -- `host_action`: what the frame cannot do for itself ------------------
  const saveEnvelopeResource = useCallback(
    async (
      active: PreviewEnvelope,
      resourceId: string,
      params?: Record<string, unknown>,
      filename?: string,
    ): Promise<"saved" | "declined"> => {
      if (!active.session_id) {
        throw new Error("no preview session");
      }
      const defaultFilename = filename ?? defaultResourceFilename(active, params);
      const dialog = await api
        .openNativeSaveDialog({
          defaultFilename,
          fileFilter: fileFilterForFilename(defaultFilename),
        })
        .catch(() => ({ paths: [] as string[], available: false }));
      const destinationPath = dialog.paths[0];
      if (destinationPath) {
        await api.savePreviewResource(active.session_id, resourceId, {
          destination_path: destinationPath,
          params: params ?? {},
        });
        return "saved";
      }
      // No path returned. Only fall back to a browser download when the native
      // save dialog was unavailable (the route raised → `available === false`).
      // When the native dialog DID run, an empty result means the person
      // cancelled — respect that and do NOT open a second (browser) save
      // dialog. That cancel is a decision rather than a failure, which is why
      // it comes back as `declined` and reaches the panel as `ok: true`.
      if (dialog.available === false) {
        const result = await fetchPreviewResource(active.session_id, resourceId, params);
        downloadDataUri(result.data, defaultFilename);
        return "saved";
      }
      return "declined";
    },
    [],
  );

  const performHostAction = useCallback(
    async (
      action: "export" | "download" | "editor_handoff",
      params: Readonly<Record<string, unknown>> | null,
    ): Promise<PanelHostActionOutcome> => {
      const active = activeRef.current;
      if (!active) return { ok: false, detail: "there is nothing on screen to act on" };

      if (action === "editor_handoff") {
        const path = editorHandoffPath(active, params);
        if (!path) {
          return { ok: false, detail: "this preview does not name a file the editor can open" };
        }
        useAppStore.getState().openFileTab(path);
        return { ok: true, detail: { opened: path } };
      }

      const resourceId = exportResourceId(active, action);
      if (!resourceId) {
        return { ok: false, detail: `this preview declares nothing to ${action}` };
      }
      const declared = active.resources.find((r) => r.resource_id === resourceId);
      const merged = mergeResourceParams(declared, { ...(params ?? {}) });
      const outcome = await saveEnvelopeResource(
        active,
        resourceId,
        merged,
        defaultResourceFilename(active, merged),
      );
      if (outcome === "declined") {
        // D-017: a person who dismissed the dialog concluded the action. The
        // panel is told so, without being told it failed.
        return { ok: true, detail: { status: "declined" } };
      }
      /*
       * ADR-053 FR-052 — `plot_exported`, reported only after the save
       * resolved, so a step that asks the reader to keep the figure waits for
       * the file rather than for the dialog. Scoped to a plot's own artifact by
       * the predicate this has always used: other panels export too, and the
       * event is about the figure.
       */
      if (active.target.kind === "plot_artifact") {
        void useAppStore.getState().reportTutorialUiEvent("plot_exported");
      }
      return { ok: true, detail: { status: "saved" } };
    },
    [saveEnvelopeResource],
  );

  // -- the mount -----------------------------------------------------------
  const chosen = descriptorOf(activeEnvelope?.panel);
  const fallback = descriptorOf(activeEnvelope?.fallback_panel);
  const fallbackId = activeEnvelope?.fallback_panel_id ?? null;

  // Both reload tokens are read unconditionally: hooks cannot be called
  // conditionally, and reading the mounted panel's token would make the token
  // depend on the failure that depends on the token.
  const chosenReload = usePanelReloadToken(chosen?.panel_id ?? null);
  const fallbackReload = usePanelReloadToken(fallback?.panel_id ?? null);

  /*
   * What identifies "this attempt at the chosen panel". A new panel, a new
   * document, or a reloaded one is a fresh attempt: a panel that failed against
   * this object may be fine once it has been rewritten, which is the whole
   * point of FR-030.
   */
  const chosenKey = [chosen?.panel_id ?? "", chosen?.document_url ?? "", chosenReload].join(
    "\u0000",
  );
  const chosenFailed =
    chosenFailure !== null && chosenFailure.key === chosenKey ? chosenFailure.failure : null;

  const mounted = chosenFailed ? fallback : chosen;
  const reloadToken = chosenFailed ? fallbackReload : chosenReload;
  const update = useMemo(
    () => (activeEnvelope ? { reason: "envelope", changed: { target: activeEnvelope } } : null),
    [activeEnvelope],
  );

  const chosenKeyRef = useRef(chosenKey);
  chosenKeyRef.current = chosenKey;
  const onChosenFailure = useCallback(
    (failure: PanelFailure) => {
      // FR-014: one behaviour for every load failure — the host's own error
      // surface naming the panel and the failure, and the fallback the backend
      // named, so the data stays visible.
      note(failure.panelId, failure.reason, failure.message);
      setChosenFailure({ key: chosenKeyRef.current, failure });
    },
    [note],
  );

  const onDiagnostic = useCallback((diagnostic: PanelDiagnostic) => {
    setHostDiagnostics((current) => [...current, diagnostic]);
  }, []);

  // -- render --------------------------------------------------------------
  if (!target || status === "idle") {
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
  if (!activeEnvelope) return null;

  return (
    <div data-testid="preview-host">
      {childStack.length > 0 ? (
        <button
          type="button"
          data-testid="preview-host-back"
          onClick={popChild}
          className="mb-2 rounded-full border border-stone-300 bg-white px-3 py-0.5 text-xs text-stone-600 hover:bg-stone-50"
        >
          ← Back
        </button>
      ) : null}

      <PanelDiagnosticsBanner diagnostics={hostDiagnostics} />

      {/* D-019 — the host's own markup around the frame, carrying the two
          highlight targets a boundary at an opaque origin cannot. */}
      <PanelTutorialChrome envelope={activeEnvelope}>
        {mounted ? (
          <PanelHost
            key={chosenFailed ? "fallback" : "chosen"}
            descriptor={mounted}
            target={activeEnvelope}
            update={update}
            remountToken={reloadToken}
            onRead={(query) => patchQuery(query)}
            onResource={openResource}
            onHostAction={performHostAction}
            onFailure={chosenFailed ? undefined : onChosenFailure}
            onDiagnostic={onDiagnostic}
            frameFactory={frameFactory}
          />
        ) : (
          <PanelErrorSurface
            failure={{
              panelId: activeEnvelope.previewer_id || "(unnamed)",
              reason: "invalid_descriptor",
              message: describeMissingPanel(activeEnvelope, chosenFailed, fallbackId),
            }}
          />
        )}
      </PanelTutorialChrome>
    </div>
  );
}

/**
 * Why nothing is mounted, said in terms of what the *backend* did or did not
 * name — never in terms of a panel this host would have picked for itself.
 */
function describeMissingPanel(
  envelope: PreviewEnvelope,
  chosenFailed: PanelFailure | null,
  fallbackId: string | null,
): string {
  if (chosenFailed) {
    return fallbackId
      ? `the fallback panel "${fallbackId}" was named for this preview but its descriptor was ` +
          "not sent, so there is no document to mount"
      : "the chosen panel failed and this response named no fallback panel";
  }
  return `this response named no panel to mount for ${envelope.kind} data`;
}

/**
 * Which declared resource an `export` or a `download` saves.
 *
 * The panel names the action, not the resource: an artifact document asks to
 * download the thing it is showing and does not know what the provider called
 * it. Preferring the action's own name, then `export`, then the single declared
 * resource keeps that promise without the host guessing between several.
 */
function exportResourceId(envelope: PreviewEnvelope, action: string): string | null {
  const ids = envelope.resources.map((resource) => resource.resource_id);
  if (ids.includes(action)) return action;
  if (ids.includes("export")) return "export";
  return ids.length === 1 ? ids[0] : null;
}

/** A project-relative path the editor can open, from whatever names one. */
function editorHandoffPath(
  envelope: PreviewEnvelope,
  params: Readonly<Record<string, unknown>> | null,
): string | null {
  const handoff =
    envelope.payload?.editor_handoff && typeof envelope.payload.editor_handoff === "object"
      ? (envelope.payload.editor_handoff as Record<string, unknown>)
      : {};
  const candidates = [params?.path, handoff.path, envelope.payload?.path, envelope.metadata?.path];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate !== "") return candidate;
  }
  return null;
}

async function fetchPreviewResource(
  sessionId: string,
  resourceId: string,
  params?: Record<string, unknown>,
): Promise<PreviewResourceResponse> {
  const response = await fetch(buildPreviewResourceUrl(sessionId, resourceId, params));
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({ detail: response.statusText }))) as {
      detail?: string | { message?: string };
    };
    const detail = payload.detail;
    const message =
      typeof detail === "string"
        ? detail
        : typeof detail?.message === "string"
          ? detail.message
          : `Request failed with ${response.status}`;
    throw new Error(message);
  }
  return (await response.json()) as PreviewResourceResponse;
}

function buildPreviewResourceUrl(
  sessionId: string,
  resourceId: string,
  params?: Record<string, unknown>,
): string {
  const base = `/api/previews/sessions/${encodeURIComponent(sessionId)}/resources/${encodeURIComponent(
    resourceId,
  )}`;
  if (!params || Object.keys(params).length === 0) return base;
  const encodedParams = JSON.stringify(params);
  if (encodedParams.length > RESOURCE_PARAMS_MAX_CHARS) {
    throw new Error("resource params exceed the 8 KiB limit");
  }
  const search = new URLSearchParams({ params: encodedParams });
  return `${base}?${search.toString()}`;
}

function mergeResourceParams(
  resource: PreviewResource | undefined,
  params?: Record<string, unknown>,
): Record<string, unknown> | undefined {
  const merged = { ...(resource?.params ?? {}), ...(params ?? {}) };
  return Object.keys(merged).length > 0 ? merged : undefined;
}

// Map an export format to the file extension the default save filename uses.
// jpeg is conventionally saved as .jpg to match the on-disk artifact (#1918).
function extensionForFormat(format: string): string {
  return format === "jpeg" ? "jpg" : format;
}

function defaultResourceFilename(
  envelope: PreviewEnvelope,
  params?: Record<string, unknown>,
): string {
  // When the caller requested a specific export format (the plot Save-as menu,
  // #1918), the default filename must carry that format's extension so the
  // native dialog defaults to the right type instead of the preview's format.
  const requested =
    typeof params?.format === "string" && params.format ? extensionForFormat(params.format) : "";
  const payloadPath = envelope.payload?.path;
  if (typeof payloadPath === "string" && payloadPath) {
    const normalized = payloadPath.replace(/[\\/]+$/, "");
    const parts = normalized.split(/[\\/]/);
    const name = parts[parts.length - 1];
    if (name) {
      if (requested) {
        const base = name.replace(/\.[A-Za-z0-9]+$/, "");
        return `${base}.${requested}`;
      }
      return name;
    }
  }
  return `${envelope.previewer_id}.${requested || "bin"}`;
}

function fileFilterForFilename(filename: string): string {
  const match = /\.([A-Za-z0-9]+)$/.exec(filename);
  if (!match) return "All files (*.*)|*.*";
  const extension = match[1].toLowerCase();
  return `${extension.toUpperCase()} (*.${extension})|*.${extension}|All files (*.*)|*.*`;
}

function downloadDataUri(data: Record<string, unknown>, filename: string): void {
  const dataUri = data.data_uri;
  if (typeof dataUri !== "string" || !dataUri.startsWith("data:")) {
    throw new Error("resource did not provide downloadable data");
  }
  const link = document.createElement("a");
  link.href = dataUri;
  link.download = filename;
  link.rel = "noopener";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
}
