/**
 * ADR-053 spec 2 (#2001) — the correctness caveat (FR-037, FR-038).
 *
 * User Story 4: a user starting a session is told, before anything happens,
 * that the agent can be wrong and that reviewing the result is their job.
 *
 * This component is deliberately dull. There is no dismiss control, no
 * disclosure triangle, no `aria-hidden` collapse — FR-038 forbids collapsing
 * the statement into a dismissible notice, and every mechanism for tucking it
 * away is a mechanism for a user reaching the start action without having seen
 * it. It renders inline, always expanded, immediately above the start action.
 *
 * It is also rendered identically in no-codebase mode. Nothing was transcribed
 * there, but nothing was verified either — spec §4.5 records that the
 * no-codebase path has the WEAKER floor, since there is no original to run. A
 * caveat softened for that path would be softened in exactly the case that
 * needs it most.
 */
import { CAVEAT_BODY, CAVEAT_HEADING } from "./copy";

export function CorrectnessCaveat() {
  return (
    <section
      className="grid gap-1 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
      data-testid="work-import-caveat"
      aria-labelledby="work-import-caveat-heading"
    >
      <h3 className="font-medium" id="work-import-caveat-heading">
        {CAVEAT_HEADING}
      </h3>
      <p>{CAVEAT_BODY}</p>
    </section>
  );
}
