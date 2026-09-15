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
 * copy. The rows come from `useAgentStatus` — the AI Chat setup screen's own
 * `GET /api/ai/status` hook and cache (#2454), so this card, the chat, and the
 * session dialogs read one report and warm one cache.
 *
 * Grayed, never hidden. The same rule the Bring In My Work provider dropdown
 * follows, for the same reason: a provider the user has not set up is an
 * option they have not taken, not one that does not exist. The scenarios doc
 * calls this out — a user who configured one CLI usually has no idea the
 * others are supported.
 *
 * The status never blocks: the card renders immediately with its prose and a
 * checking note, and the rows fill in when the report resolves.
 */

import { Bot } from "lucide-react";

import { useAgentStatus } from "../AIChat/SetupScreen.parts/agentStatus";
import type { ProviderStatus } from "../AIChat/SetupScreen.parts/types";

export const PROVIDER_INTRO_TITLE = "Meet the real agents";

export const PROVIDER_INTRO_BODY =
  "SciStudio's workflows are AI heavy. These are the providers we support:";

export const PROVIDER_INTRO_CHECKING = "Checking this machine…";

export const PROVIDER_INTRO_UNAVAILABLE =
  "The provider check did not answer. The AI Chat tab's setup screen has the same list.";

export const PROVIDER_INTRO_FOOTNOTE = "Not installed yet?";

export const PROVIDER_INTRO_READY_NOTE = "Installed and signed in.";

export const PROVIDER_INTRO_CONTINUE_LABEL = "Continue";

type ProviderState = "ready" | "not_authenticated" | "not_installed";

function stateOf(row: ProviderStatus): ProviderState {
  if (!row.available) return "not_installed";
  return row.logged_in ? "ready" : "not_authenticated";
}

const STATE_LABELS: Record<ProviderState, string> = {
  ready: "ready",
  not_authenticated: "installed — needs sign-in",
  not_installed: "not installed",
};

const STATE_CHIP_CLASSES: Record<ProviderState, string> = {
  ready: "bg-emerald-100 text-emerald-700",
  not_authenticated: "bg-amber-100 text-amber-700",
  not_installed: "bg-stone-100 text-stone-500",
};

/** The configure line for one provider — the backend's words wherever it has any. */
/** Label for the link out to the installation guide. */
export const PROVIDER_INTRO_GUIDE_LABEL = "Read the installation guide.";

function configureLine(state: ProviderState): string {
  return state === "ready" ? PROVIDER_INTRO_READY_NOTE : STATE_LABELS[state];
}

export interface ProviderIntroProps {
  onContinue: () => void;
  /** Open the user guide's AI assistant page — how to install a provider. */
  onOpenInstallGuide: () => void;
}

export function ProviderIntro({ onContinue, onOpenInstallGuide }: ProviderIntroProps) {
  const { status, statusError } = useAgentStatus();
  const providers = status?.providers ?? null;
  const probeFailed = statusError !== null;

  return (
    <div data-testid="provider-intro">
      <h2 className="inline-flex items-center gap-2 font-display text-xl text-ink">
        <Bot aria-hidden="true" className="size-5 text-ember" />
        {PROVIDER_INTRO_TITLE}
      </h2>

      <p className="mt-3 text-sm leading-6 text-stone-600">{PROVIDER_INTRO_BODY}</p>

      {providers === null ? (
        <p className="mt-4 text-xs leading-5 text-stone-500" data-testid="provider-intro-checking">
          {probeFailed ? PROVIDER_INTRO_UNAVAILABLE : PROVIDER_INTRO_CHECKING}
        </p>
      ) : (
        <ul className="mt-4 space-y-2">
          {providers.map((provider) => {
            const state = stateOf(provider);
            return (
              <li
                className={`rounded-2xl border border-stone-200 p-3 ${state === "ready" ? "" : "opacity-60"}`}
                data-testid={`provider-intro-${provider.name}`}
                key={provider.name}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-ink">{provider.label}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATE_CHIP_CLASSES[state]}`}
                  >
                    {STATE_LABELS[state]}
                  </span>
                </div>
                <p className="mt-1 text-xs leading-5 text-stone-600">{configureLine(state)}</p>
              </li>
            );
          })}
        </ul>
      )}

      <p className="mt-3 text-xs leading-5 text-stone-500">
        {PROVIDER_INTRO_FOOTNOTE}{" "}
        {/*
         * #2083 — the list above says which providers are missing; this is the
         * page that says what to do about it. Without it the reader is told
         * "not installed" and left to search for the answer.
         */}
        <button
          className="font-medium text-pine underline decoration-pine/40 underline-offset-2 hover:decoration-pine"
          data-testid="provider-intro-install-guide"
          onClick={() => onOpenInstallGuide()}
          type="button"
        >
          {PROVIDER_INTRO_GUIDE_LABEL}
        </button>
      </p>

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
