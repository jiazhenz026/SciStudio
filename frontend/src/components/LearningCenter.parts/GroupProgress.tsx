/**
 * ADR-053 Learning Center (#2057) — the right column: a count and a position.
 *
 * Two different questions, kept apart. The ring answers "how much of this
 * source have I finished", from that source's own counts and no others
 * (FR-076). Below it, "where am I right now" — which is about the one running
 * session, since FR-043 allows only one at a time.
 *
 * The running tutorial is reported even when the user is looking at a
 * different tab. It is the single thing in the product that is mid-flight, and
 * a panel that hid it while the user browsed would be the surface that made
 * them lose it.
 */

import type { TutorialCatalogueGroup, TutorialSessionResponse } from "../../lib/api/learningCenter";

import { ProgressRing } from "./ProgressRing";

export function GroupProgress({
  group,
  session,
  onLeave,
}: {
  group: TutorialCatalogueGroup | null;
  session: TutorialSessionResponse | null;
  onLeave: () => void;
}) {
  const step = session?.step ?? null;

  return (
    <div className="flex h-full flex-col gap-5 p-5" data-testid="learning-center-progress">
      {group ? (
        <ProgressRing
          completed={group.completed}
          label={`${group.label} tutorials complete`}
          total={group.total}
        />
      ) : (
        /*
         * The Reading tab spans sources, and FR-076 forbids a count across
         * them. Selecting a tutorial brings its own source's ring back.
         */
        <p className="text-center text-xs leading-5 text-stone-500">
          Select a tutorial to see its source’s progress.
        </p>
      )}

      <div className="border-t border-stone-200 pt-4">
        <p className="text-xs uppercase tracking-[0.2em] text-stone-500">Right now</p>
        {session ? (
          <div className="mt-2" data-testid="learning-center-current-position">
            <p className="text-sm font-medium leading-6 text-ink">{session.title}</p>
            {step ? (
              <>
                <p className="mt-0.5 text-xs text-stone-500">
                  Step {step.index} of {step.total}
                </p>
                {step.say ? (
                  <p className="mt-2 line-clamp-4 text-xs leading-5 text-stone-600">{step.say}</p>
                ) : null}
              </>
            ) : (
              <p className="mt-0.5 text-xs text-stone-500">
                {session.status === "complete" ? "Finished." : "Getting ready…"}
              </p>
            )}
            {/* FR-090 — leaving is possible at any step and keeps the session. */}
            <button
              className="mt-3 rounded-full border border-stone-300 px-3 py-1 text-xs font-medium text-stone-600 transition hover:border-pine hover:text-pine"
              onClick={onLeave}
              type="button"
            >
              Leave tutorial
            </button>
          </div>
        ) : (
          <p className="mt-2 text-xs leading-5 text-stone-500">No tutorial is running.</p>
        )}
      </div>
    </div>
  );
}
