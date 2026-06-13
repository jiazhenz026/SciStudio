/**
 * ADR-048 SPEC 1 — Previewer host-module API contract (FR-023).
 *
 * This module defines the *stable, versioned* contract between the core
 * frontend {@link PreviewHost} and a dynamically loaded, package- or
 * project-owned previewer ESM module. The imaging package
 * (`scistudio-blocks-imaging`) and any future package/project previewer
 * implements {@link PreviewerModule}; the host implements
 * {@link PreviewHostApi} and hands one instance to the module on mount.
 *
 * Why a hard contract:
 *   - Dynamic modules are loaded from backend-validated, same-origin URLs only
 *     (FR-022). The host validates the manifest before importing.
 *   - The module receives a *constrained* host API. It MUST NOT receive — and
 *     this contract deliberately does not expose — any workflow-mutation,
 *     runtime-state, lineage, or project-file primitives (FR-023 / ADR-048 §4).
 *     The only side effects a previewer can cause are bounded preview reads
 *     through the session API and user-initiated export/save of the data it is
 *     already displaying.
 *
 * Versioning:
 *   - {@link PREVIEWER_HOST_API_VERSION} is the host's current contract version
 *     and rides on every {@link PreviewHostApi}. A module declares the API
 *     version it was built against in its {@link PreviewerManifest.api_version}.
 *     The host refuses to mount (and falls back to the core viewer) when the
 *     versions are incompatible, surfacing a diagnostic instead.
 *
 * Mount flow (see {@link mountDynamicPreviewer} in `dynamicPreviewer.ts`):
 *   1. PreviewHost reads the first-class `envelope.frontend_manifest` (stamped
 *      by the session manager from the resolved PreviewerSpec, #1579; a legacy
 *      `envelope.metadata.frontend_manifest` fallback remains for un-migrated
 *      providers).
 *   2. It validates `module_url` is same-origin (rejects http/https/`//`/data:).
 *   3. It `import(module_url)` and reads `module[manifest.export_name]`.
 *   4. That export is a {@link PreviewerModule}; the host calls
 *      `module.mount(container, hostApi)` and keeps the returned
 *      {@link PreviewerInstance} for `update`/`unmount`.
 *   4a. Any failure in 2–4 → render diagnostics + the core fallback viewer.
 *
 * Example (a package previewer module, conceptually owned by the imaging
 * package — NOT implemented here):
 *
 * ```ts
 * import type { PreviewerModule } from "scistudio/previewerHostApi";
 *
 * export const ImageViewer: PreviewerModule = {
 *   apiVersion: "1",
 *   mount(container, host) {
 *     const root = createRoot(container);
 *     const render = (e) => root.render(<ImageView host={host} envelope={e} />);
 *     render(host.envelope);
 *     return {
 *       update: render,
 *       unmount: () => root.unmount(),
 *     };
 *   },
 * };
 * ```
 */

import type {
  EnvelopeKind,
  PreviewEnvelope,
  PreviewResource,
  PreviewSource,
  PreviewerManifest,
} from "../../types/api";

/**
 * Current host-module contract version. Bump this only on a breaking change to
 * {@link PreviewHostApi} / {@link PreviewerModule}. A loaded module whose
 * declared `api_version` is incompatible is not mounted (FR-006/FR-023).
 */
export const PREVIEWER_HOST_API_VERSION = "1" as const;

/** Identity of the block output / data target currently being previewed.
 *  Display-only — carries no workflow truth (FR-028). */
export interface PreviewProviderIdentity {
  /** Selected previewer id, e.g. `imaging.image.viewer`. */
  previewerId: string;
  /** The previewer's declared capabilities (`slice`, `lut`, `export`, ...),
   *  echoed from the manifest/spec when known. */
  capabilities: readonly string[];
  /** Optional workflow/node/output identity for labelling, mirrored from the
   *  envelope target's `source`. */
  source: PreviewSource | null;
}

/** Bounded export of the artifact the previewer is currently displaying.
 *  The host fulfils this via the session resource API or a same-origin asset
 *  URL — the module never reaches storage directly. */
export interface PreviewExportRequest {
  /** Resource id to export (e.g. `export` for plots, `tile` for arrays). */
  resourceId?: string;
  /** Resource params to merge with the advertised descriptor params. */
  params?: Record<string, unknown>;
  /** Suggested download filename. */
  filename?: string;
  /** Declared format hint (`png`, `svg`, `pdf`, `csv`, ...). */
  format?: string;
}

/**
 * The constrained API a dynamic previewer module receives on mount (FR-023).
 *
 * Every helper is read-only with respect to workflow/runtime/lineage state.
 * The session helpers proxy the same-origin session API; `exportArtifact` and
 * `saveArtifact` only move bytes the previewer is already authorised to show.
 */
export interface PreviewHostApi {
  /** Host contract version. Modules may assert compatibility against this. */
  readonly apiVersion: string;

  /** The owning preview session id, or `null` for a one-shot preview. */
  readonly previewSessionId: string | null;

  /** The current envelope the module is asked to render. */
  readonly envelope: PreviewEnvelope;

  /** The canonical fallback kind of the current envelope. */
  readonly kind: EnvelopeKind;

  /** Provider metadata (id, capabilities, display source). */
  readonly provider: PreviewProviderIdentity;

  /** Bounded session-data helpers. These are the ONLY data-access primitives
   *  a module is given; all reads are server-bounded and side-effect free. */
  readonly session: {
    /**
     * Re-fetch the current envelope for the session (no query change).
     * Resolves with `null` for a one-shot preview that has no session.
     */
    refresh: () => Promise<PreviewEnvelope | null>;
    /**
     * Merge new query state (slice/page/sort/slot/item/colormap range/...) and
     * re-render the envelope. No-op resolving with the current envelope when
     * there is no live session.
     */
    patchQuery: (query: Record<string, unknown>) => Promise<PreviewEnvelope>;
    /**
     * Fetch a bounded provider resource (array tile, child preview, ...) by id.
     * Descriptor params are supplied automatically when the id matches an
     * advertised resource; callers may pass explicit params for provider-owned
     * resources that are not listed in the current envelope.
     * Resolves with the raw resource data dict. Rejects (or resolves `null`)
     * when there is no session.
     */
    getResource: (
      resourceId: string,
      params?: Record<string, unknown>,
    ) => Promise<Record<string, unknown> | null>;
    /** Resource descriptors advertised by the current envelope. */
    readonly resources: readonly PreviewResource[];
  };

  /**
   * Build a same-origin asset URL served by the validated previewer bundle
   * (`/api/previews/assets/{previewerId}/{path}`). Used for static module-owned
   * assets (icons, worker scripts, CSS). Remote URLs are never produced.
   */
  assetUrl: (assetPath: string) => string;

  /**
   * Trigger a user-facing export/download of the displayed artifact. The host
   * performs the bounded fetch and the browser download; the module supplies
   * only the descriptor.
   */
  exportArtifact: (request?: PreviewExportRequest) => Promise<void>;

  /**
   * Persist the displayed artifact back through an explicit, host-mediated
   * backend save flow (no direct project-file writes). Optional — the host may
   * expose this only where a save target exists; modules must tolerate a
   * rejected promise.
   */
  saveArtifact: (request?: PreviewExportRequest) => Promise<void>;

  /** Report a non-fatal previewer-side error to the host so it can surface a
   *  diagnostic (and, if rendering is impossible, fall back to the core view).
   *  This is the module's only error channel — it must not throw across the
   *  mount boundary for routine failures. */
  reportError: (message: string, detail?: Record<string, unknown>) => void;
}

/** Handle returned by {@link PreviewerModule.mount} so the host can push new
 *  envelopes into a mounted module and tear it down. */
export interface PreviewerInstance {
  /** Called by the host when the session envelope changes (e.g. after a
   *  patchQuery the host initiated). Optional. */
  update?: (envelope: PreviewEnvelope) => void;
  /** Tear down the module (unmount React root, remove listeners, revoke object
   *  URLs). Called when the host swaps previewers or unmounts. */
  unmount: () => void;
}

/**
 * The shape a dynamic previewer module must export under
 * {@link PreviewerManifest.export_name}. This is the contract package/project
 * authors implement.
 */
export interface PreviewerModule {
  /** API version this module was built against; compared to
   *  {@link PREVIEWER_HOST_API_VERSION} before mounting. */
  apiVersion: string;
  /**
   * Mount the previewer into a host-owned DOM container with a constrained
   * host API. Returns a {@link PreviewerInstance} for later update/unmount.
   * MUST NOT throw for routine failures — call `host.reportError` instead.
   */
  mount: (container: HTMLElement, host: PreviewHostApi) => PreviewerInstance;
}

/** Re-export the wire manifest type so module authors import a single contract
 *  surface. */
export type { PreviewerManifest };

/** Narrow runtime guard: is `value` a usable {@link PreviewerModule}? */
export function isPreviewerModule(value: unknown): value is PreviewerModule {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<PreviewerModule>;
  return typeof candidate.mount === "function" && typeof candidate.apiVersion === "string";
}

/** Are the host and module API versions compatible? Major version (the part
 *  before the first `.`) must match; the host advances minor/patch additively. */
export function isApiVersionCompatible(
  moduleApiVersion: string | undefined,
  hostApiVersion: string = PREVIEWER_HOST_API_VERSION,
): boolean {
  if (!moduleApiVersion) return false;
  const major = (v: string) => v.split(".")[0];
  return major(moduleApiVersion) === major(hostApiVersion);
}
