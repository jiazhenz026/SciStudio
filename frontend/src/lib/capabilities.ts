/**
 * ADR-055 identity seam (`docs/specs/adr-055-identity-seam.md`, decision 2d) —
 * the enterprise capabilities the backend declares at boot.
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
 * declaration never throws; each malformed field reads as off.
 *
 * TODO(#2304): the capability-gated UI components read this accessor — the
 *   signed-in user name with a Logout button (`identity`), an
 *   upload-from-my-computer picker with transfer progress, and the
 *   download/save flow (`transfer`). They wait for the enterprise transfer and
 *   logout API contracts.
 *   Out of scope per the #2304 owner decision (enterprise UI placement,
 *   option A: the components are tracked separately).
 *   Followup: https://github.com/jiazhenz026/SciStudio/issues/2304
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
   * The backend's own logout endpoint, as an absolute path such as
   * `/api/session/logout`. That endpoint ends the SciStudio session before any
   * identity-provider logout. Logout sends it a same-origin `POST`, resolved
   * through `apiUrl` so it lands under the service prefix, and then follows the
   * location the response returns. A plain GET navigation would let other
   * sites force a logout.
   */
  readonly logoutUrl: string;
}

/** Every capability an edition can declare; all off in the open-source edition. */
export interface Capabilities {
  readonly identity: IdentityCapability | null;
  readonly transfer: boolean;
}

export type CapabilityName = keyof Capabilities;

const ALL_OFF: Capabilities = Object.freeze({ identity: null, transfer: false });

/** Same rule as the backend: an absolute same-origin path, nothing else. */
function isSafeLogoutUrl(url: string): boolean {
  if (url === "" || url !== url.trim()) return false;
  for (const ch of url) {
    if (ch.charCodeAt(0) < 0x20) return false;
  }
  return url.startsWith("/") && !url.startsWith("//");
}

function readIdentity(raw: unknown): IdentityCapability | null {
  if (typeof raw !== "object" || raw === null) return null;
  const { user, logoutUrl } = raw as Record<string, unknown>;
  if (typeof user !== "string" || user.trim() === "") return null;
  if (typeof logoutUrl !== "string" || !isSafeLogoutUrl(logoutUrl)) return null;
  return Object.freeze({ user, logoutUrl });
}

function readCapabilities(raw: unknown): Capabilities {
  if (typeof raw !== "object" || raw === null) return ALL_OFF;
  const record = raw as Record<string, unknown>;
  return Object.freeze({
    identity: readIdentity(record.identity),
    transfer: record.transfer === true,
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
  return name === "identity" ? capabilities.identity !== null : capabilities.transfer;
}

/** Test-only hook: drop the cached declaration so a test can re-inject it. */
export function resetCapabilitiesCacheForTests(): void {
  cachedCapabilities = null;
}
