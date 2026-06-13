/**
 * ADR-048 SPEC 1 — PreviewHost (FR-020 .. FR-023).
 *
 * The routed preview container. For a selected {@link PreviewTarget} it:
 *   1. Creates a session via `POST /api/previews/sessions` and reads the
 *      {@link PreviewEnvelope}.
 *   2. If the resolved previewer surfaces a `frontend_manifest` (first-class on
 *      `envelope.frontend_manifest`, with a legacy `envelope.metadata.frontend_manifest`
 *      fallback) → validates it (same-origin only,
 *      FR-022), dynamically `import()`s it, and mounts the named export with a
 *      constrained {@link PreviewHostApi} (FR-023). On ANY validation / import /
 *      mount failure → renders diagnostics AND the core fallback viewer for
 *      `envelope.kind` (FR-029, US2.3).
 *   3. Else → renders the core fallback viewer for `envelope.kind`.
 *
 * Child routing (composite slots, collection items, US4.3) re-uses the same
 * precedence by fetching the resource — which the backend renders as a freshly
 * routed child envelope — and pushing it onto a small drill-down stack.
 *
 * The host keeps only UI-level state (active envelope, drill-down stack); the
 * backend remains authoritative for routing, sessions, and data. Cache keying
 * lives in the Zustand preview slice (FR-021); this component reads/writes it
 * through the injected callbacks.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../lib/api";
import type {
  PreviewEnvelope,
  PreviewResource,
  PreviewResourceResponse,
  PreviewTarget,
  PreviewerManifest,
} from "../../types/api";

import { CoreFallbackRenderer, DiagnosticsBanner } from "./coreViewers";
import { type LoadResult, mountDynamicPreviewer } from "./dynamicPreviewer";
import {
  PREVIEWER_HOST_API_VERSION,
  type PreviewHostApi,
  type PreviewProviderIdentity,
  type PreviewerInstance,
} from "./previewerHostApi";

export interface PreviewHostProps {
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
  /** Test seam: inject a fake dynamic-module importer. */
  importer?: Parameters<typeof mountDynamicPreviewer>[3];
}

type Status = "idle" | "loading" | "ready" | "error";
type PreviewCacheKeyOptions = {
  previewerId?: string | null;
  sessionId?: string | null;
  dataVersion?: string | number | null;
};
const RESOURCE_PARAMS_MAX_CHARS = 8192;

function readManifest(envelope: PreviewEnvelope | null): PreviewerManifest | undefined {
  if (!envelope) return undefined;
  // Prefer the first-class field the session manager stamps (#1579); fall back
  // to the legacy flattened `metadata.frontend_manifest` for un-migrated providers.
  const manifest = envelope.frontend_manifest ?? envelope.metadata?.frontend_manifest;
  if (manifest && typeof manifest === "object" && typeof manifest.module_url === "string") {
    return manifest;
  }
  return undefined;
}

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
  target,
  initialQuery,
  cacheEnvelope,
  buildCacheKey,
  importer,
}: PreviewHostProps) {
  const [status, setStatus] = useState<Status>("idle");
  const [envelope, setEnvelope] = useState<PreviewEnvelope | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  // Diagnostics raised by the host itself (dynamic-load failures etc).
  const [hostDiagnostics, setHostDiagnostics] = useState<string[]>([]);
  // Drill-down stack of child envelopes (composite slot / collection item).
  const [childStack, setChildStack] = useState<PreviewEnvelope[]>([]);

  const queryRef = useRef<Record<string, unknown>>(initialQuery ?? {});

  // -- session creation ----------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    setChildStack([]);
    setHostDiagnostics([]);
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
    // initialQuery is captured intentionally on target change only; later
    // query updates go through patchQuery below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target?.ref, target?.kind]);

  // -- patch query (slice/page/sort/slot) ----------------------------------
  const patchQuery = useCallback(
    async (patch: Record<string, unknown>): Promise<PreviewEnvelope> => {
      const current = envelope;
      if (!current?.session_id) {
        return current ?? Promise.reject(new Error("no session"));
      }
      queryRef.current = { ...queryRef.current, ...patch };
      const next = await api.patchPreviewSession(current.session_id, patch);
      setEnvelope(next);
      if (target)
        cacheEnvelopeForQuery(cacheEnvelope, buildCacheKey, target, queryRef.current, next);
      return next;
    },
    [envelope, buildCacheKey, cacheEnvelope, target],
  );

  // -- child routing (composite slot / collection item) --------------------
  const openResource = useCallback(
    async (resource: PreviewResource) => {
      const active = childStack[childStack.length - 1] ?? envelope;
      if (!active?.session_id) return;
      try {
        const result = await fetchPreviewResource(
          active.session_id,
          resource.resource_id,
          resource.params,
        );
        // A child resource resolves to a full child envelope.
        const childEnvelope = result.data as unknown as PreviewEnvelope;
        if (childEnvelope && typeof childEnvelope.kind === "string") {
          setChildStack((stack) => [...stack, childEnvelope]);
        }
      } catch (err) {
        setHostDiagnostics((d) => [
          ...d,
          `failed to open ${resource.resource_id}: ${err instanceof Error ? err.message : String(err)}`,
        ]);
      }
    },
    [childStack, envelope],
  );

  const popChild = useCallback(() => setChildStack((stack) => stack.slice(0, -1)), []);

  // -- export / save -------------------------------------------------------
  const exportResource = useCallback(
    async (resource: PreviewResource) => {
      const active = childStack[childStack.length - 1] ?? envelope;
      if (!active) return;
      // Plot export: a same-origin asset download for the displayed artifact.
      const src = active.payload?.src;
      if (typeof src === "string" && src.startsWith("data:")) {
        triggerDownload(src, `${active.previewer_id}.${resource.params?.format ?? "bin"}`);
        return;
      }
      if (active.session_id) {
        try {
          const result = await fetchPreviewResource(
            active.session_id,
            resource.resource_id,
            resource.params,
          );
          triggerResourceDownload(
            result.data,
            `${active.previewer_id}.${resource.params?.format ?? "bin"}`,
          );
        } catch (err) {
          setHostDiagnostics((d) => [
            ...d,
            `export failed: ${err instanceof Error ? err.message : String(err)}`,
          ]);
        }
      }
    },
    [childStack, envelope],
  );

  // The envelope currently in focus (top of the drill-down stack, else root).
  const activeEnvelope = childStack[childStack.length - 1] ?? envelope;
  const manifest = useMemo(() => readManifest(activeEnvelope), [activeEnvelope]);

  // -- dynamic previewer mount ---------------------------------------------
  const mountRef = useRef<HTMLDivElement | null>(null);
  const instanceRef = useRef<PreviewerInstance | null>(null);
  const [dynamicFailed, setDynamicFailed] = useState(false);

  const hostApi: PreviewHostApi | null = useMemo(() => {
    if (!activeEnvelope || !manifest) return null;
    const provider: PreviewProviderIdentity = {
      previewerId: activeEnvelope.previewer_id,
      capabilities: [],
      source: activeEnvelope.target.source ?? null,
    };
    return {
      apiVersion: PREVIEWER_HOST_API_VERSION,
      previewSessionId: activeEnvelope.session_id,
      envelope: activeEnvelope,
      kind: activeEnvelope.kind,
      provider,
      session: {
        refresh: async () =>
          activeEnvelope.session_id ? api.getPreviewSession(activeEnvelope.session_id) : null,
        patchQuery: async (q) => {
          if (!activeEnvelope.session_id) return activeEnvelope;
          if (activeEnvelope.session_id === envelope?.session_id) return patchQuery(q);
          return api.patchPreviewSession(activeEnvelope.session_id, q);
        },
        getResource: async (resourceId, params) => {
          if (!activeEnvelope.session_id) return null;
          const resource = activeEnvelope.resources.find((r) => r.resource_id === resourceId);
          return (
            await fetchPreviewResource(
              activeEnvelope.session_id,
              resourceId,
              mergeResourceParams(resource, params),
            )
          ).data;
        },
        resources: activeEnvelope.resources,
      },
      assetUrl: (assetPath: string) =>
        `/api/previews/assets/${encodeURIComponent(activeEnvelope.previewer_id)}/${assetPath.replace(/^\/+/, "")}`,
      exportArtifact: async (request) => {
        const src = activeEnvelope.payload?.src;
        if (typeof src === "string" && src.startsWith("data:")) {
          triggerDownload(src, request?.filename ?? `${activeEnvelope.previewer_id}.bin`);
          return;
        }
        if (!activeEnvelope.session_id) return;
        const resourceId = request?.resourceId ?? "export";
        const resource = activeEnvelope.resources.find((r) => r.resource_id === resourceId);
        const params = mergeResourceParams(resource, {
          ...(request?.params ?? {}),
          ...(request?.format ? { format: request.format } : {}),
        });
        const result = await fetchPreviewResource(activeEnvelope.session_id, resourceId, params);
        triggerResourceDownload(
          result.data,
          request?.filename ?? `${activeEnvelope.previewer_id}.${request?.format ?? "bin"}`,
        );
      },
      saveArtifact: async () => {
        // No host-mediated save target wired yet; modules must tolerate a
        // rejection. The plot-job run + routed preview path is wired (#1606,
        // api.runPlotJob -> plotTargetFromRunResponse -> PreviewHost); the
        // explicit save-to-project flow is a separate destination contract.
        // TODO(#1626): wire saveArtifact to the backend plot-artifact save flow.
        //   Out of scope per #1606 (preview wiring only); follow-up: issue #1626.
        return Promise.reject(new Error("save not available"));
      },
      reportError: (message: string) => {
        setHostDiagnostics((d) => [...d, message]);
      },
    };
  }, [activeEnvelope, envelope?.session_id, manifest, patchQuery]);

  useEffect(() => {
    // Tear down any prior instance whenever the focus changes.
    if (instanceRef.current) {
      try {
        instanceRef.current.unmount();
      } catch {
        /* ignore unmount errors */
      }
      instanceRef.current = null;
    }
    setDynamicFailed(false);

    if (!manifest || !hostApi || !mountRef.current) return;
    let disposed = false;
    const container = mountRef.current;
    void mountDynamicPreviewer(manifest, container, hostApi, importer).then(
      (result: LoadResult) => {
        if (disposed) return;
        if (result.ok) {
          instanceRef.current = result.instance;
        } else {
          // FR-029 / US2.3 — diagnostics + clean fallback to the core viewer.
          setDynamicFailed(true);
          setHostDiagnostics((d) => [...d, result.message]);
        }
      },
    );
    return () => {
      disposed = true;
      if (instanceRef.current) {
        try {
          instanceRef.current.unmount();
        } catch {
          /* ignore */
        }
        instanceRef.current = null;
      }
    };
  }, [manifest, hostApi, importer]);

  // Push new envelopes into a live dynamic instance.
  useEffect(() => {
    if (instanceRef.current?.update && activeEnvelope) {
      instanceRef.current.update(activeEnvelope);
    }
  }, [activeEnvelope]);

  // -- render --------------------------------------------------------------
  if (!target || status === "idle") {
    return (
      <div className="rounded-[1.6rem] border border-dashed border-stone-300 px-4 py-6 text-sm text-stone-500">
        Nothing to preview.
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

  const useDynamic = !!manifest && !dynamicFailed;

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

      <DiagnosticsBanner diagnostics={hostDiagnostics} />

      {/* Mount point for the dynamic previewer. Always present in the DOM so the
          mount effect has a stable container; hidden when we fall back. */}
      <div
        ref={mountRef}
        data-testid="preview-host-dynamic-mount"
        style={{ display: useDynamic ? "block" : "none" }}
      />

      {/* Core fallback path: no manifest, or the dynamic previewer failed. */}
      {!useDynamic ? (
        <CoreFallbackRenderer
          envelope={activeEnvelope}
          onPatchQuery={(q) => void patchQuery(q)}
          onOpenResource={(r) => void openResource(r)}
          onExport={(r) => void exportResource(r)}
        />
      ) : null}
    </div>
  );
}

function triggerDownload(href: string, filename: string): void {
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
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

function triggerResourceDownload(data: Record<string, unknown>, fallbackFilename: string): void {
  const href =
    typeof data.data_uri === "string"
      ? data.data_uri
      : typeof data.src === "string" && data.src.startsWith("data:")
        ? data.src
        : null;
  if (!href) return;
  triggerDownload(href, typeof data.filename === "string" ? data.filename : fallbackFilename);
}
