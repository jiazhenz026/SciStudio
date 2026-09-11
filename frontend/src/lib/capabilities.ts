/**
 * ADR-055 identity seam (`docs/specs/adr-055-identity-seam.md`, decision 2d) —
 * the enterprise capabilities the backend declares at boot, in the shape of
 * the shared capability contract (ADR-055 Spec 4,
 * `docs/specs/adr-055-enterprise-support.md`, issue #2322).
 *
 * An edition built on the open-source backend turns capabilities on through
 * `create_app(capabilities=...)`; the backend then injects the declaration into
 * the served `index.html` as `window.__SCISTUDIO_CAPABILITIES__`
 * (`src/scistudio/api/spa.py`). The open-source edition declares nothing, so
 * every capability reads as off and no gated UI appears. A page not served by
 * the backend (the vite dev server) reads as off too.
 *
 * The declaration is read once and cached: it comes from the document that
 * served the page and does not change for the page's lifetime. A malformed
 * declaration never throws; each malformed field reads as off, and a
 * capability this frontend does not know is ignored.
 *
 * Every URL a capability carries is a backend route path without the service
 * prefix. Resolve it with `apiUrl` (or pass it to `apiFetch`), exactly as API
 * calls are resolved, so it lands under a `/user/<name>/...` mount too. The
 * capability-gated components live in `frontend/src/components/Enterprise/`.
 */

declare global {
  interface Window {
    /** Injected by the backend when an edition turns a capability on. */
    __SCISTUDIO_CAPABILITIES__?: unknown;
  }
}

/** The `identity` capability: who is signed in, and where to sign out. */
export interface IdentityCapability {
  /** The signed-in user's display name. */
  readonly user: string;
  /**
   * The backend's own logout route, or `null` when the edition offers none
   * (the user name then renders without a Logout action). That route ends the
   * SciStudio session before any identity-provider logout and answers
   * `{location}`. Logout sends it a same-origin `POST`, resolved under the
   * service prefix, and then navigates to that location. A plain GET
   * navigation would let other sites force a logout.
   */
  readonly logoutUrl: string | null;
}

/** The `transfer` capability: laptop-to-server upload and download. */
export interface TransferCapability {
  /** Largest file the edition moves inline; the UI's upload is always staged. */
  readonly inlineMaxBytes: number;
  /** Download route with exactly one `{path}` marker. */
  readonly downloadUrlTemplate: string;
}

/** The `update` capability: where to poll for, and restart into, a new version. */
export interface UpdateCapability {
  /** `GET` answers `{running_version, installed_version, update_available, runs_active}`. */
  readonly statusUrl: string;
  /** `POST` answers `{location}`; the frontend then navigates there. */
  readonly restartUrl: string;
}

/** Every capability an edition can declare; all off in the open-source edition. */
export interface Capabilities {
  /** The declaration's shape version; `0` when nothing valid was declared. */
  readonly version: number;
  readonly identity: IdentityCapability | null;
  readonly transfer: TransferCapability | null;
  /** Hides the AI Chat surface; the backend refuses agent-kind PTY providers. */
  readonly aiChatDisabled: boolean;
  readonly update: UpdateCapability | null;
}

export type CapabilityName = "identity" | "transfer" | "aiChatDisabled" | "update";

const ALL_OFF: Capabilities = Object.freeze({
  version: 0,
  identity: null,
  transfer: null,
  aiChatDisabled: false,
  update: null,
});

const PATH_MARKER = "{path}";

/**
 * Same rule as the backend: a route path on this backend, nothing else — a
 * leading `/`, never `//`, and no whitespace, control characters or
 * backslashes (browsers read `/\host` as `//host`).
 */
export function isRoutePath(url: unknown): url is string {
  if (typeof url !== "string" || url === "") return false;
  for (const ch of url) {
    const code = ch.charCodeAt(0);
    if (code < 0x20 || code === 0x7f || ch === "\\" || /\s/u.test(ch)) return false;
  }
  return url.startsWith("/") && !url.startsWith("//");
}

function asRecord(raw: unknown): Record<string, unknown> | null {
  return typeof raw === "object" && raw !== null && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : null;
}

function readIdentity(raw: unknown): IdentityCapability | null {
  const record = asRecord(raw);
  if (record === null) return null;
  const { user, logoutUrl } = record;
  if (typeof user !== "string" || user.trim() === "") return null;
  if (logoutUrl === undefined || logoutUrl === null)
    return Object.freeze({ user, logoutUrl: null });
  // A logout URL that is present but unsafe drops the whole identity rather
  // than rendering a name whose Logout silently does nothing.
  if (!isRoutePath(logoutUrl)) return null;
  return Object.freeze({ user, logoutUrl });
}

function readTransfer(raw: unknown): TransferCapability | null {
  const record = asRecord(raw);
  if (record === null) return null;
  const { inlineMaxBytes, downloadUrlTemplate } = record;
  if (typeof inlineMaxBytes !== "number" || !Number.isSafeInteger(inlineMaxBytes)) return null;
  if (inlineMaxBytes < 0) return null;
  if (!isRoutePath(downloadUrlTemplate)) return null;
  if (downloadUrlTemplate.split(PATH_MARKER).length !== 2) return null;
  return Object.freeze({ inlineMaxBytes, downloadUrlTemplate });
}

function readUpdate(raw: unknown): UpdateCapability | null {
  const record = asRecord(raw);
  if (record === null) return null;
  const { statusUrl, restartUrl } = record;
  if (!isRoutePath(statusUrl) || !isRoutePath(restartUrl)) return null;
  return Object.freeze({ statusUrl, restartUrl });
}

function readVersion(raw: unknown): number {
  return typeof raw === "number" && Number.isSafeInteger(raw) && raw > 0 ? raw : 0;
}

function readCapabilities(raw: unknown): Capabilities {
  const record = asRecord(raw);
  if (record === null) return ALL_OFF;
  return Object.freeze({
    version: readVersion(record.version),
    identity: readIdentity(record.identity),
    transfer: readTransfer(record.transfer),
    aiChatDisabled: record.aiChatDisabled === true,
    update: readUpdate(record.update),
  });
}

let cachedCapabilities: Capabilities | null = null;

/** The capabilities this page was served with; every one off by default. */
export function getCapabilities(): Capabilities {
  if (cachedCapabilities === null) {
    cachedCapabilities = readCapabilities(
      typeof window !== "undefined" ? window.__SCISTUDIO_CAPABILITIES__ : undefined,
    );
  }
  return cachedCapabilities;
}

/** Whether one capability is on, for gating UI with a single check. */
export function isCapabilityEnabled(name: CapabilityName): boolean {
  const capabilities = getCapabilities();
  switch (name) {
    case "identity":
      return capabilities.identity !== null;
    case "transfer":
      return capabilities.transfer !== null;
    case "aiChatDisabled":
      return capabilities.aiChatDisabled;
    case "update":
      return capabilities.update !== null;
  }
}

/**
 * The download route for one project file: the template's `{path}` replaced by
 * the URL-encoded project-relative path. Still a route path; resolve it with
 * `apiUrl` before handing it to the browser.
 */
export function downloadRoutePath(transfer: TransferCapability, relativePath: string): string {
  return transfer.downloadUrlTemplate.split(PATH_MARKER).join(encodeURIComponent(relativePath));
}

/** Test-only hook: drop the cached declaration so a test can re-inject it. */
export function resetCapabilitiesCacheForTests(): void {
  cachedCapabilities = null;
}
