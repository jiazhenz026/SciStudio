/**
 * ADR-053 FR-079 (#2057) — the one product behaviour progress drives.
 *
 * Everything else about progress is display: counts per group, a state on each
 * catalogue entry, a dot on the toolbar. This is the single place where having
 * finished a tutorial makes the product *do* something — it offers to carry the
 * user's existing analysis across. Without it the whole progress subsystem
 * drives nothing at all, which is what the no-context audit found.
 *
 * **Once, and the backend decides when.** FR-079 says the offer is presented
 * once. The backend's `mark_completed` returns true only on the first record
 * and `work_import_offer_pending` is derived from it, so this component asks
 * `GET /unlock` and records the answer with `POST /unlock/dismiss`. It keeps no
 * "have I shown this" flag of its own — a second record of the same fact is how
 * an offer that must appear once appears twice, and the two copies would
 * disagree the first time a user reloaded mid-offer.
 *
 * **Skipping says where it went.** FR-081 and User Story 5: the capability is
 * permanent and nothing gates it. A user who skips without being told where the
 * feature lives has lost it, so the skip path names the toolbar entry — and
 * names it by importing the entry's own label, so the two cannot drift into
 * pointing at different words.
 *
 * **This gates nothing.** The toolbar entry is available regardless of
 * progress. The unlock decides only when the product volunteers the offer,
 * never whether the capability can be reached.
 */

import { FolderInput, X } from "lucide-react";
import { useState } from "react";

import { useAppStore } from "../../store";
import { BringInMyWorkDialog } from "../BringInMyWorkDialog";
import { ENTRY_LABEL } from "../BringInMyWorkDialog.parts/copy";

export const OFFER_TITLE = "Bring your own work across?";

export const OFFER_BODY =
  "You have seen how SciStudio builds a workflow. The same thing can be done with the " +
  "analysis you already have — point it at your existing work and an agent will turn it " +
  "into blocks you can run here.";

export const OFFER_ACCEPT_LABEL = "Bring my work across";

export const OFFER_SKIP_LABEL = "Not now";

/** FR-081 / User Story 5 acceptance 2 — where the feature lives afterwards. */
export const OFFER_SKIPPED_MESSAGE =
  `No problem. “${ENTRY_LABEL}” stays in the toolbar permanently — it is always there ` +
  `when you want it, whether or not you finish any tutorials.`;

export function WorkImportOffer() {
  const pending = useAppStore((state) => state.learningCenterWorkImportOffer);
  const dismissWorkImportOffer = useAppStore((state) => state.dismissWorkImportOffer);

  const [skipped, setSkipped] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  /*
   * The dialog is rendered here, beside the offer, rather than by reaching into
   * the toolbar's copy of it. The toolbar mounts its own only while open so the
   * availability probe fires when a user asks for the feature; sharing one
   * instance would mean lifting that state and changing the permanent entry's
   * behaviour, which FR-081 says to leave exactly as it is.
   */
  if (dialogOpen) {
    return <BringInMyWorkDialog onClose={() => setDialogOpen(false)} />;
  }

  if (!pending && !skipped) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-6 backdrop-blur-sm"
      data-testid="work-import-offer"
    >
      <div className="w-full max-w-lg rounded-[2rem] border border-stone-200 bg-white p-6 shadow-panel">
        {skipped ? (
          <>
            <p className="text-sm leading-6 text-stone-700" data-testid="work-import-offer-skipped">
              {OFFER_SKIPPED_MESSAGE}
            </p>
            <div className="mt-5 flex justify-end">
              <button
                className="rounded-full bg-ink px-4 py-2 text-xs font-medium text-white transition hover:bg-pine"
                onClick={() => setSkipped(false)}
                type="button"
              >
                Got it
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-start justify-between gap-4">
              <h2 className="inline-flex items-center gap-2 font-display text-xl text-ink">
                <FolderInput aria-hidden="true" className="size-5 text-ember" />
                {OFFER_TITLE}
              </h2>
              <button
                aria-label="Close"
                className="inline-flex size-8 shrink-0 items-center justify-center rounded-full text-stone-400 transition hover:bg-stone-100 hover:text-ink"
                onClick={() => {
                  setSkipped(true);
                  void dismissWorkImportOffer();
                }}
                type="button"
              >
                <X aria-hidden="true" className="size-4" />
              </button>
            </div>

            <p className="mt-3 text-sm leading-6 text-stone-600">{OFFER_BODY}</p>

            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button
                className="rounded-full border border-stone-300 px-4 py-2 text-xs font-medium text-stone-600 transition hover:border-pine hover:text-pine"
                onClick={() => {
                  setSkipped(true);
                  void dismissWorkImportOffer();
                }}
                type="button"
              >
                {OFFER_SKIP_LABEL}
              </button>
              <button
                className="rounded-full bg-ink px-4 py-2 text-xs font-medium text-white transition hover:bg-pine"
                onClick={() => {
                  // Taking it up answers the offer just as skipping does, so it
                  // is recorded the same way and will not be volunteered again.
                  void dismissWorkImportOffer();
                  setDialogOpen(true);
                }}
                type="button"
              >
                {OFFER_ACCEPT_LABEL}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
