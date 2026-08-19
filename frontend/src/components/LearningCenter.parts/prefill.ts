/**
 * ADR-053 FR-011b — reading a step's `prefill`.
 *
 * A step says what a dialog should already be holding when the reader opens it,
 * so a tutorial that names a value does not then ask the reader to retype it.
 * This is the whole frontend side of that: a lookup by target name, returning
 * the values the step declared.
 *
 * Deliberately a plain function over the session rather than a store selector
 * or a piece of tutorial state of its own. A prefill is read at the instant a
 * dialog opens, by the code that opens it, and it is a *default* — nothing here
 * decides anything, and a reader who types something else has not fought the
 * tutorial, because the step's `done_when` judges the world rather than the
 * dialog.
 *
 * An unknown target name simply finds nothing. The closed set is core-owned
 * (`scistudio.tutorials.manifest.PREFILL_SPECS`) and validated when the
 * manifest loads, so an unresolvable target never reaches a running session.
 */

import type { TutorialSessionResponse } from "../../lib/api/learningCenter";

/** The values the current step seeds `target` with, or `null` when it seeds nothing. */
export function tutorialPrefillArgs(
  session: TutorialSessionResponse | null | undefined,
  target: string,
): Record<string, string> | null {
  const prefills = session?.step?.prefill;
  if (!Array.isArray(prefills)) return null;
  const match = prefills.find((entry) => entry.target === target);
  return match ? match.args : null;
}

/** One seeded value, or `undefined` when this step does not seed it. */
export function tutorialPrefillValue(
  session: TutorialSessionResponse | null | undefined,
  target: string,
  key: string,
): string | undefined {
  const value = tutorialPrefillArgs(session, target)?.[key];
  return value === undefined || value === "" ? undefined : value;
}
