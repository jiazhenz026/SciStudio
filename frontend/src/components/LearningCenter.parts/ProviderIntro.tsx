/**
 * ADR-053 / #2083 — the provider introduction that opens the work-import offer.
 *
 * Core tutorial 4 ends on a promise: "the real agents are one configuration
 * away". This card keeps it. When the milestone completion fires the offer,
 * the reader first meets the real agent CLIs SciStudio can drive — which ones
 * exist, what state each is in on this machine, and what setting one up takes
 * — and only then the import question, which is the thing those agents would
 * be doing.
 *
 * Everything provider-shaped here is backend truth. ADR-034 FR-020a/FR-020b
 * (held in place by `tests/architecture/test_adr_034_provider_single_source.py`)
 * forbid the frontend hand-maintaining provider keys, labels, or per-provider
 * copy: a sixth provider is a registry-only change, and a list written here
 * would be the copy that misses it. So the rows come whole from
 * `GET /api/ai/availability` — key, label, graded state, and the
 * backend-composed `next_step` that says precisely how to configure each one
 * (which binary, where SciStudio looked, which command signs in).
 *
 * Greyed, never hidden. The same rule the Bring In My Work provider dropdown
 * follows, for the same reason: a provider the user has not set up is an
 * option they have not taken, not one that does not exist. The scenarios doc
 * calls this out — a user who configured one CLI usually has no idea the
 * others are supported.
 *
 * The probe never blocks (FR-035's rule, inherited): the card renders
 * immediately with its prose and a checking note, and the rows fill in when
 * the report resolves. The probe is the same memoised report the Bring In My
 * Work dialog reads moments later if the reader accepts, so asking here warms
 * exactly the cache that dialog needs.
 */

import { Bot } from "lucide-react";
import { useEffect, useState } from "react";

import {
  fetchAgentAvailability,
  type AgentAvailabilityResponse,
  type ProviderAvailability,
} from "../../lib/api/agentAvailability";

export const PROVIDER_INTRO_TITLE = "Meet the real agents";

export const PROVIDER_INTRO_BODY =
  "The agent in the tutorial was a recording. These are the real ones — coding-agent " +
  "CLIs from their vendors, and SciStudio drives any of them in the same terminal you " +
  "just used, with the same tools. Set up one and everything you watched works live, " +
  "on your own data.";

export const PROVIDER_INTRO_CHECKING = "Checking this machine for the supported agent CLIs…";

export const PROVIDER_INTRO_UNAVAILABLE =
  "The provider check did not answer. The full list — with per-provider setup guidance — " +
  "is always available from the AI Chat tab's setup screen and the Bring in my work dialog.";

export const PROVIDER_INTRO_FOOTNOTE =
  "Nothing here is hidden behind progress: providers you have not set up stay listed and " +
  "greyed, and every SciStudio surface that starts an agent offers all of them.";

export const PROVIDER_INTRO_READY_NOTE = "Set up and working — nothing to do.";

export const PROVIDER_INTRO_CONTINUE_LABEL = "Continue";

const STATE_LABELS: Record<ProviderAvailability["state"], string> = {
  ready: "ready",
  not_authenticated: "installed — needs sign-in",
  not_installed: "not installed",
  call_failed: "signed in — last call failed",
};

const STATE_CHIP_CLASSES: Record<ProviderAvailability["state"], string> = {
  ready: "bg-emerald-100 text-emerald-700",
  not_authenticated: "bg-amber-100 text-amber-700",
  not_installed: "bg-stone-100 text-stone-500",
  call_failed: "bg-rose-100 text-rose-700",
};

/** The configure line for one provider — the backend's words wherever it has any. */
function configureLine(provider: ProviderAvailability): string {
  if (provider.state === "ready") return PROVIDER_INTRO_READY_NOTE;
  if (provider.next_step) return provider.next_step;
  if (provider.state === "call_failed" && provider.cause) return provider.cause;
  return STATE_LABELS[provider.state];
}

export interface ProviderIntroProps {
  onContinue: () => void;
}

export function ProviderIntro({ onContinue }: ProviderIntroProps) {
  const [availability, setAvailability] = useState<AgentAvailabilityResponse | null>(null);
  const [probeFailed, setProbeFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchAgentAvailability()
      .then((report) => {
        if (!cancelled) setAvailability(report);
      })
      .catch(() => {
        // The card still works: prose plus a pointer at the surfaces that
        // carry the list permanently, rather than an error about a report
        // nobody asked for.
        if (!cancelled) setProbeFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div data-testid="provider-intro">
      <h2 className="inline-flex items-center gap-2 font-display text-xl text-ink">
        <Bot aria-hidden="true" className="size-5 text-ember" />
        {PROVIDER_INTRO_TITLE}
      </h2>

      <p className="mt-3 text-sm leading-6 text-stone-600">{PROVIDER_INTRO_BODY}</p>

      {availability === null ? (
        <p className="mt-4 text-xs leading-5 text-stone-500" data-testid="provider-intro-checking">
          {probeFailed ? PROVIDER_INTRO_UNAVAILABLE : PROVIDER_INTRO_CHECKING}
        </p>
      ) : (
        <ul className="mt-4 space-y-2">
          {availability.providers.map((provider) => {
            const usable = provider.state === "ready";
            return (
              <li
                className={`rounded-2xl border border-stone-200 p-3 ${usable ? "" : "opacity-60"}`}
                data-testid={`provider-intro-${provider.key}`}
                key={provider.key}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-ink">{provider.label}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATE_CHIP_CLASSES[provider.state]}`}
                  >
                    {STATE_LABELS[provider.state]}
                  </span>
                </div>
                <p className="mt-1 text-xs leading-5 text-stone-600">{configureLine(provider)}</p>
                {provider.session_unsupported_reason ? (
                  <p className="mt-0.5 text-xs leading-5 text-stone-400">
                    {provider.session_unsupported_reason}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      <p className="mt-3 text-xs leading-5 text-stone-500">{PROVIDER_INTRO_FOOTNOTE}</p>

      <div className="mt-5 flex justify-end">
        <button
          className="rounded-full bg-ink px-4 py-2 text-xs font-medium text-white transition hover:bg-pine"
          data-testid="provider-intro-continue"
          onClick={onContinue}
          type="button"
        >
          {PROVIDER_INTRO_CONTINUE_LABEL}
        </button>
      </div>
    </div>
  );
}
