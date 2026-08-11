/**
 * ADR-053 Learning Center (#2057) — the selected tutorial, middle column.
 *
 * Shows what FR-085 requires — title, summary, cover if declared, state, and
 * the reason when a tutorial cannot be run — and carries the one action that
 * starts it.
 *
 * FR-087's restart confirmation lives here rather than over the list, and
 * names the directory it will delete (FR-066, FR-067). That is FR-088's
 * reasoning applied to a second action: "start again" describes the user's
 * intent while its effect is deleting a folder, and the two must not be
 * allowed to diverge silently.
 */

import { AlertTriangle, CheckCircle2, CircleDashed } from "lucide-react";
import { useEffect, useState } from "react";

import type { TutorialCatalogueEntry } from "../../lib/api/learningCenter";
import { tutorialEntryKey } from "../../store/learningCenterSlice";

const STATE_LABELS: Record<TutorialCatalogueEntry["state"], string> = {
  not_started: "Not started",
  in_progress: "In progress",
  complete: "Complete",
  unavailable: "Unavailable",
};

const ACTION_LABELS: Record<TutorialCatalogueEntry["state"], string | null> = {
  not_started: "Start tutorial",
  in_progress: "Resume tutorial",
  complete: "Start it again",
  unavailable: null,
};

function StateBadge({ state }: { state: TutorialCatalogueEntry["state"] }) {
  const label = STATE_LABELS[state];
  if (state === "complete") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-pine">
        <CheckCircle2 aria-hidden="true" className="size-3.5" />
        {label}
      </span>
    );
  }
  if (state === "in_progress") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-ember">
        <CircleDashed aria-hidden="true" className="size-3.5" />
        {label}
      </span>
    );
  }
  if (state === "unavailable") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-stone-500">
        <AlertTriangle aria-hidden="true" className="size-3.5" />
        {label}
      </span>
    );
  }
  return <span className="text-xs font-medium text-stone-500">{label}</span>;
}

export function TutorialDetail({
  entry,
  onStart,
}: {
  entry: TutorialCatalogueEntry | null;
  onStart: (entry: TutorialCatalogueEntry, restart: boolean) => void;
}) {
  /* FR-087 — a completed tutorial is never silently re-run. */
  const [confirmingRestart, setConfirmingRestart] = useState(false);
  const selectedKey = entry ? tutorialEntryKey(entry) : null;

  // Selecting a different tutorial withdraws a confirmation left standing, so
  // an accepted confirmation can never delete a project the user is no longer
  // looking at.
  useEffect(() => setConfirmingRestart(false), [selectedKey]);

  if (!entry) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <p className="max-w-xs text-center text-sm leading-6 text-stone-500">
          Choose a tutorial on the left to see what it covers.
        </p>
      </div>
    );
  }

  const actionLabel = ACTION_LABELS[entry.state];

  return (
    <div className="flex h-full flex-col gap-4 p-6" data-testid="tutorial-detail">
      {/* FR-085 — the cover is shown only when the tutorial declared one. */}
      {entry.cover_url ? (
        <img alt="" className="h-32 w-full rounded-xl object-cover" src={entry.cover_url} />
      ) : null}

      <div>
        <StateBadge state={entry.state} />
        <h3 className="mt-1 font-display text-xl leading-7 text-ink">{entry.title}</h3>
      </div>

      <p className="text-sm leading-6 text-stone-600">{entry.summary}</p>

      {/* FR-085 — unavailable always says why, or the user cannot act on it. */}
      {entry.state === "unavailable" && entry.unavailable_reason ? (
        <p className="rounded-xl bg-stone-50 px-3 py-2 text-xs leading-5 text-stone-600">
          {entry.unavailable_reason}
        </p>
      ) : null}

      <div className="mt-auto">
        {confirmingRestart ? (
          <div
            className="rounded-xl border border-stone-300 bg-stone-50 p-3"
            data-testid="learning-center-restart-confirm"
          >
            <p className="text-sm leading-6 text-ink">
              Start “{entry.title}” again? This deletes its tutorial project and creates a new one
              in its place.
            </p>
            {entry.project_directory ? (
              <p className="mt-2 break-all rounded-lg bg-white px-2 py-1 font-mono text-xs text-stone-600">
                {entry.project_directory}
              </p>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                className="rounded-full bg-ink px-3 py-1.5 text-xs font-medium text-white transition hover:bg-pine"
                onClick={() => {
                  setConfirmingRestart(false);
                  onStart(entry, true);
                }}
                type="button"
              >
                Delete it and start over
              </button>
              <button
                className="rounded-full border border-stone-300 px-3 py-1.5 text-xs font-medium text-stone-600 transition hover:border-pine hover:text-pine"
                onClick={() => setConfirmingRestart(false)}
                type="button"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : actionLabel ? (
          <button
            className="rounded-full bg-ink px-4 py-2 text-sm font-medium text-white transition hover:bg-pine"
            data-testid="tutorial-detail-start"
            onClick={() => {
              if (entry.state === "complete") {
                setConfirmingRestart(true);
                return;
              }
              onStart(entry, false);
            }}
            type="button"
          >
            {actionLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
