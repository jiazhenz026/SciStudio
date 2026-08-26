/**
 * ADR-053 FR-079 (#2057) — the one product behavior progress drives.
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
 *
 * **The offer opens with the provider introduction** (#2083). The milestone
 * is core tutorial 4 — a scripted agent session that ends promising "the real
 * agents are one configuration away" — so the first page of this surface is
 * `ProviderIntro`: the five real agent CLIs, what each is, and what setting
 * one up takes. Continue leads to the import question; closing at either page
 * is the same once-only skip.
 */

import { FolderInput, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useAppStore } from "../../store";
import { BringInMyWorkDialog } from "../BringInMyWorkDialog";
import { ENTRY_LABEL } from "../BringInMyWorkDialog.parts/copy";
import { ProviderIntro } from "./ProviderIntro";

export const OFFER_TITLE = "Bring your own work across?";

export const OFFER_BODY =
  "You have seen how SciStudio builds a workflow. The same thing can be done with the " +
  "analysis you already have — point it at your existing work and an agent will turn it " +
  "into blocks you can run here.";

export const OFFER_ACCEPT_LABEL = "Bring my work across";

export const OFFER_SKIP_LABEL = "Not now";

/**
 * What happens after "Yes" (#2083).
 *
 * Said before the click rather than discovered after it: the offer arrives
 * with no project open, on purpose, so the first thing it does is ask for one.
 * A reader who expected an importer and got a New Project dialog would think
 * they had mis-clicked.
 */
export const OFFER_PROJECT_NOTE =
  "You will be asked to make a project for it first — name it and put it wherever you like.";

/** FR-081 / User Story 5 acceptance 2 — where the feature lives afterwards. */
export const OFFER_SKIPPED_MESSAGE =
  `No problem. “${ENTRY_LABEL}” stays in the toolbar permanently — it is always there ` +
  `when you want it, whether or not you finish any tutorials.`;

export function WorkImportOffer() {
  const owed = useAppStore((state) => state.learningCenterWorkImportOffer);
  const dismissWorkImportOffer = useAppStore((state) => state.dismissWorkImportOffer);
  /*
   * #2083 — the offer waits for a closed project, and that is about where the
   * imported work would land rather than about tidiness. "Bring in my work"
   * imports into the *open* project; asked the moment the AI tutorial ends,
   * with the tutorial's own project still open, it would file the reader's
   * real codebase inside a throwaway called "What AI Can Do".
   *
   * It also leaves the reader alone if they chose "Keep exploring": they said
   * they wanted to keep poking at what they built, and a modal over it is the
   * opposite of that. The offer is owed until it is shown, so closing the
   * project later is when they get asked — nothing is lost by waiting.
   */
  const projectOpen = useAppStore((state) => state.currentProject !== null);
  /*
   * Started, and therefore no longer subject to the gate: step 2 of the flow
   * is "make yourself a project", which opens one. A gate that kept looking
   * would close the dialog at exactly the moment it succeeded.
   */
  const [started, setStarted] = useState(false);
  const pending = owed && (started || !projectOpen);
  useEffect(() => {
    if (owed && !projectOpen) setStarted(true);
    if (!owed) setStarted(false);
  }, [owed, projectOpen]);

  const [skipped, setSkipped] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  /*
   * #2083 — the provider introduction opens the offer. The milestone tutorial
   * ends promising "the real agents are one configuration away", and this is
   * where the promise is kept: first who the agents are, then the question of
   * what they could do with the reader's own work. Continue moves on; closing
   * the card at either page is the same skip, recorded the same once.
   */
  const [introSeen, setIntroSeen] = useState(false);
  useEffect(() => {
    if (pending) setIntroSeen(false);
  }, [pending]);

  /*
   * #2083 — a project of their own, before the import.
   *
   * "Bring in my work" imports into the open project, and at this point in the
   * flow there is none: the offer waited for the tutorial's to be closed
   * precisely so the reader's real codebase would not be filed inside it. So
   * the middle page is where they make the project it *should* go into, with
   * the ordinary New Project dialog — the name and the location are theirs to
   * choose, not something this flow should decide for them.
   */
  const openProjectDialog = useAppStore((state) => state.openProjectDialog);
  const requestUserGuidePage = useAppStore((state) => state.requestUserGuidePage);
  const [wantsProject, setWantsProject] = useState(false);
  useEffect(() => {
    if (wantsProject && projectOpen) {
      setWantsProject(false);
      setDialogOpen(true);
    }
  }, [wantsProject, projectOpen]);

  /*
   * The dialog is rendered here, beside the offer, rather than by reaching into
   * the toolbar's copy of it. The toolbar mounts its own only while open so the
   * availability probe fires when a user asks for the feature; sharing one
   * instance would mean lifting that state and changing the permanent entry's
   * behavior, which FR-081 says to leave exactly as it is.
   */
  if (dialogOpen) {
    return <BringInMyWorkDialog onClose={() => setDialogOpen(false)} />;
  }

  if (!pending && !skipped) return null;

  return (
    <div
      // z-[60], above the Learning Center's own z-50 overlay. Both are
      // full-screen and the Learning Center mounts second, so at equal
      // stacking it covered this one — and this is the offer that fires once
      // when a reader finishes the AI level, so a covered one is a lost one:
      // reloading does not bring it back. Found by the level-4 end-to-end
      // session, which hit-tested the center of this dialog and got the
      // catalogue behind it.
      className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/30 p-6 backdrop-blur-sm"
      data-testid="work-import-offer"
    >
      <div className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-[2rem] border border-stone-200 bg-white p-6 shadow-panel">
        {pending && !skipped && !introSeen ? (
          <>
            <div className="flex items-start justify-between gap-4">
              <ProviderIntro
                onContinue={() => setIntroSeen(true)}
                onOpenInstallGuide={() => {
                  /*
                   * Deliberately NOT a dismissal. Sending someone away to
                   * install a provider and calling the once-only offer spent
                   * would mean they never see it again — the one case where it
                   * is most certainly still owed.
                   */
                  setStarted(false);
                  requestUserGuidePage("ai-assistant.md");
                }}
              />
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
          </>
        ) : skipped ? (
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
            <p className="mt-2 text-xs leading-5 text-stone-500">{OFFER_PROJECT_NOTE}</p>

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
                data-testid="work-import-offer-accept"
                onClick={() => {
                  // Taking it up answers the offer just as skipping does, so it
                  // is recorded the same way and will not be volunteered again.
                  void dismissWorkImportOffer();
                  if (projectOpen) {
                    setDialogOpen(true);
                    return;
                  }
                  /*
                   * Nothing is open — by design, this offer waited for that —
                   * and the importer imports into the open project. So the
                   * next thing is a project to import into, named and placed
                   * by the reader. The effect above opens the importer once
                   * one exists.
                   */
                  setWantsProject(true);
                  openProjectDialog("new");
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
