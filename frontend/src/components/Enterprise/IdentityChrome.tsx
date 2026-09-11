/**
 * ADR-055 Spec 4 FR-004 — who is signed in, and Logout.
 *
 * Renders the `identity` capability's user name, plus a Logout action when the
 * edition named a logout route. Logout sends that route a same-origin `POST`
 * (resolved under the service prefix), which ends the SciStudio session and
 * answers `{location}`; the browser then goes there, typically the identity
 * provider's own logout. The open-source edition adds no login screen and no
 * account management: it only shows the identity it is given.
 */

import { LogOut, User } from "lucide-react";
import { useState } from "react";

import type { IdentityCapability } from "../../lib/capabilities";
import { browserNavigation, errorMessage, postForLocation } from "./enterpriseApi";

export function IdentityChrome({ identity }: { identity: IdentityCapability }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { logoutUrl } = identity;

  const logout = async (route: string) => {
    setBusy(true);
    setError(null);
    try {
      browserNavigation.assign(await postForLocation(route));
    } catch (failure) {
      setError(`Logout failed: ${errorMessage(failure)}`);
      setBusy(false);
    }
  };

  return (
    <div className="flex shrink-0 items-center gap-2" data-testid="enterprise-identity">
      <span
        className="inline-flex max-w-[12rem] items-center gap-1.5 rounded-full bg-stone-100 px-3 py-1 text-xs font-medium text-stone-700"
        title={`Signed in as ${identity.user}`}
      >
        <User aria-hidden="true" className="size-4 shrink-0" />
        <span className="truncate" data-testid="enterprise-identity-user">
          {identity.user}
        </span>
      </span>
      {logoutUrl !== null ? (
        <button
          className="inline-flex items-center gap-1.5 rounded-full border border-stone-300 px-3 py-1 text-xs font-medium text-stone-600 hover:bg-stone-100 disabled:opacity-50"
          data-testid="enterprise-logout"
          disabled={busy}
          onClick={() => void logout(logoutUrl)}
          type="button"
        >
          <LogOut aria-hidden="true" className="size-4" />
          {busy ? "Logging out…" : "Logout"}
        </button>
      ) : null}
      {error !== null ? (
        <span className="text-xs text-rose-600" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}
