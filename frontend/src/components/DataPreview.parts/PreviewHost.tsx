/**
 * ADR-048 SPEC 1 — PreviewHost (FR-020 .. FR-023).
 *
 * The routed preview container. For a selected {@link PreviewTarget} it:
 *   1. Creates a session via `POST /api/previews/sessions` and reads the
 *      {@link PreviewEnvelope}.
 *   2. If the resolved previewer surfaces a `frontend_manifest` (in
 *      `envelope.metadata.frontend_manifest`) → validates it (same-origin only,
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
   * Optional session-keyed cache hooks (FR-021). When provided, the host reads
   * a cached envelope before creating a session and writes the rendered
   * envelope back. The cache key already encodes target + previewer + query +
   * data version (see `previewSlice`); the host passes the rendered envelope.
   */
  getCachedEnvelope?: (key: string) => PreviewEnvelope | undefined;
  cacheEnvelope?: (key: string, envelope: PreviewEnvelope) => void;
  buildCacheKey?: (target: PreviewTarget, query: Record<string, unknown>) => string;
  /** Test seam: inject a fake dynamic-module importer. */
  importer?: Parameters<typeof mountDynamicPreviewer>[3];
}

type Status = "idle" | "loading" | "ready" | "error";

function readManifest(envelope: PreviewEnvelope | null): PreviewerManifest | undefined {
  if (!envelope) return undefined;
  const manifest = envelope.metadata?.frontend_manifest;
  if (manifest && typeof manifest === "object" && typeof manifest.module_url === "string") {
    return manifest;
  }
  return undefined;
}

export function PreviewHost({
  target,
  initialQuery,
  getCachedEnvelope,
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

    const cacheKey = buildCacheKey?.(target, query);
    const cached = cacheKey ? getCachedEnvelope?.(cacheKey) : undefined;
    if (cached) {
      setEnvelope(cached);
      setStatus("ready");
      return;
    }

    setStatus("loading");
    setRequestError(null);
    api
      .createPreviewSession(target, query)
      .then((env) => {
        if (cancelled) return;
        setEnvelope(env);
        setStatus("ready");
        if (cacheKey && cacheEnvelope) cacheEnvelope(cacheKey, env);
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
      if (buildCacheKey && cacheEnvelope && target) {
        cacheEnvelope(buildCacheKey(target, queryRef.current), next);
      }
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
        const result = await api.getPreviewResource(active.session_id, resource.resource_id);
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
          await api.getPreviewResource(active.session_id, resource.resource_id);
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
        patchQuery: async (q) =>
          activeEnvelope.session_id
            ? api.patchPreviewSession(activeEnvelope.session_id, q)
            : activeEnvelope,
        getResource: async (resourceId) =>
          activeEnvelope.session_id
            ? (await api.getPreviewResource(activeEnvelope.session_id, resourceId)).data
            : null,
        resources: activeEnvelope.resources,
      },
      assetUrl: (assetPath: string) =>
        `/api/previews/assets/${encodeURIComponent(activeEnvelope.previewer_id)}/${assetPath.replace(/^\/+/, "")}`,
      exportArtifact: async () => {
        const src = activeEnvelope.payload?.src;
        if (typeof src === "string" && src.startsWith("data:")) {
          triggerDownload(src, `${activeEnvelope.previewer_id}.bin`);
        }
      },
      saveArtifact: async () => {
        // No host-mediated save target wired in SPEC 1; modules must tolerate
        // a rejection. TODO(#1574): wire explicit backend save flow when the
        // plot-job save API lands (adr-048-ai-plot-tools).
        return Promise.reject(new Error("save not available"));
      },
      reportError: (message: string) => {
        setHostDiagnostics((d) => [...d, message]);
      },
    };
  }, [activeEnvelope, manifest]);

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
