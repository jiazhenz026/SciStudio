/**
 * ADR-053 Learning Center — the reading window (#2084, closing TODO(#2057)).
 *
 * A reading tutorial does not guide the user around the product, so the
 * floating step card is the wrong furniture for it: there is nothing to point
 * at and nothing to avoid occluding. What it gets instead is a window — the
 * tutorial's summary as the top sentence, then one card per step in step
 * order. A card opens a paged reader; reading the last page returns to the
 * grid; the tutorial completes through the same continue/advance flow as
 * every other tutorial (FR-054a — Continue is in the footer, live exactly
 * when the backend says the current step is satisfied).
 *
 * Progress is never judged here. Fetching a page is what records it — the
 * backend notes `page_reached` on serve — and after each page this surface
 * asks the backend to re-evaluate, which is the same `evaluate` the step card
 * uses. Spec §4.1 holds: this file renders answers, it does not produce them.
 *
 * Built for any reading tutorial, not one: cards, pages, and counts all come
 * from the session and the catalogue entry. The wire carries only the current
 * step, so cards already walked past are remembered locally for display
 * (`readingCards.ts` explains why that memory is safe to lose).
 */

import { ArrowLeft, ArrowRight, BookOpen, Check, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  fetchTutorialPage,
  type TutorialCatalogueEntry,
  type TutorialSessionResponse,
} from "../../lib/api/learningCenter";
import { useAppStore } from "../../store";

import { PageMarkdown } from "./PageMarkdown";
import { cardOfStep, readingSlots, type ReadingCardInfo, type ReadingSlot } from "./readingCards";

interface ReadingSurfaceProps {
  /** The catalogue entry the session belongs to; carries the top sentence. */
  entry: TutorialCatalogueEntry;
  session: TutorialSessionResponse;
  /** Close the window. The session stays where it is (FR-090's little sister). */
  onClose: () => void;
}

interface OpenReader {
  card: ReadingCardInfo;
  pageIndex: number;
}

export function ReadingSurface({ entry, session, onClose }: ReadingSurfaceProps) {
  const continueStep = useAppStore((state) => state.continueActiveTutorialStep);
  const evaluateStep = useAppStore((state) => state.evaluateActiveTutorialStep);
  const leaveTutorial = useAppStore((state) => state.leaveActiveTutorial);

  /* Cards this window has seen, by step index — display memory only. */
  const [remembered, setRemembered] = useState<ReadonlyMap<number, ReadingCardInfo>>(new Map());
  const [reader, setReader] = useState<OpenReader | null>(null);
  const [pageText, setPageText] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);

  const step = session.step;

  /* Remember every step the session shows us, keyed by its position. */
  useEffect(() => {
    if (!step) return;
    setRemembered((current) => {
      const card = cardOfStep(step);
      const known = current.get(step.index);
      if (known && known.id === card.id && known.pages.length === card.pages.length) return current;
      const next = new Map(current);
      next.set(step.index, card);
      return next;
    });
  }, [step]);

  /*
   * Load the open page. Fetching is the progress report (the backend records
   * the page on serve), so a successful load is followed by an evaluate —
   * that is what moves `satisfied` and lights Continue without a reload.
   */
  const readerCardId = reader?.card.id ?? null;
  const readerPage = reader === null ? null : (reader.card.pages[reader.pageIndex] ?? null);
  useEffect(() => {
    if (readerPage === null) return;
    let stale = false;
    setPageText(null);
    setPageError(null);
    void (async () => {
      try {
        const text = await fetchTutorialPage(
          { source_kind: entry.source_kind, source_id: entry.source_id, id: entry.id },
          readerPage,
        );
        if (stale) return;
        setPageText(text);
        await evaluateStep();
      } catch (error) {
        if (stale) return;
        setPageError(error instanceof Error ? error.message : String(error));
      }
    })();
    return () => {
      stale = true;
    };
    // `readerCardId` stands in for the card object so paging within one card
    // refetches only the page, while switching cards refetches from its start.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readerCardId, readerPage, entry.source_kind, entry.source_id, entry.id]);

  const slots = readingSlots(session, remembered);
  const canContinue =
    session.status === "active" && step !== null && (step.satisfied || step.awaiting_continue);

  const openCard = (slot: ReadingSlot) => {
    if (!slot.card || slot.card.pages.length === 0) return;
    if (slot.state === "unread") return;
    setReader({ card: slot.card, pageIndex: 0 });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-6 backdrop-blur-sm"
      data-testid="reading-surface"
    >
      <div className="flex h-[min(42rem,88vh)] w-full max-w-4xl flex-col overflow-hidden rounded-[2rem] border border-stone-200 bg-white shadow-panel">
        <header className="flex items-start justify-between gap-4 px-8 pt-5">
          <h2 className="inline-flex min-w-0 items-center gap-2 font-display text-2xl text-ink">
            <BookOpen aria-hidden="true" className="size-5 text-ember" />
            {session.title}
          </h2>
          <button
            aria-label="Close reading window"
            className="inline-flex size-8 shrink-0 items-center justify-center rounded-full text-stone-400 transition hover:bg-stone-100 hover:text-ink"
            data-testid="reading-close"
            onClick={onClose}
            type="button"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        </header>

        {session.status === "error" ? (
          <p className="mx-8 mt-3 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">
            {session.error ?? "This tutorial stopped with an error."}
          </p>
        ) : null}

        {reader === null ? (
          <>
            {/* The window's top sentence — the tutorial's summary (owner copy). */}
            <p
              className="mx-8 mt-2 text-sm leading-6 text-stone-600"
              data-testid="reading-top-sentence"
            >
              {entry.summary}
            </p>

            {/* One card per step, in step order. */}
            <div className="min-h-0 flex-1 overflow-y-auto px-8 py-5">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {slots.map((slot) => {
                  const openable =
                    slot.card !== null && slot.card.pages.length > 0 && slot.state !== "unread";
                  return (
                    <button
                      className={`flex min-h-28 flex-col items-start gap-1.5 rounded-xl border p-3 text-left transition ${
                        slot.state === "current"
                          ? "border-ember bg-ember/5 hover:bg-ember/10"
                          : slot.state === "read"
                            ? "border-stone-200 bg-white hover:border-pine"
                            : "border-dashed border-stone-200 bg-stone-50"
                      } ${openable ? "cursor-pointer" : "cursor-default"}`}
                      data-reading-state={slot.state}
                      data-testid={`reading-card-${slot.index}`}
                      disabled={!openable}
                      key={slot.index}
                      onClick={() => openCard(slot)}
                      type="button"
                    >
                      <span className="inline-flex w-full items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-ink">
                          {slot.card?.title ?? `Card ${slot.index + 1}`}
                        </span>
                        {slot.state === "read" ? (
                          <Check aria-label="Read" className="size-4 shrink-0 text-pine" />
                        ) : null}
                      </span>
                      {slot.card?.say ? (
                        <span className="text-xs leading-5 text-stone-500">{slot.card.say}</span>
                      ) : slot.state === "unread" ? (
                        <span className="text-xs leading-5 text-stone-400">Not yet — read on.</span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </div>
          </>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col px-8 py-4" data-testid="reading-page">
            <div className="flex items-baseline justify-between gap-3 pb-2">
              <span className="text-sm font-semibold text-ink">{reader.card.title}</span>
              <span className="text-xs tabular-nums text-stone-500">
                Page {reader.pageIndex + 1} of {reader.card.pages.length}
              </span>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto rounded-xl border border-stone-100 bg-stone-50/50 p-5">
              {pageError !== null ? (
                <p className="text-sm text-red-700" data-testid="reading-page-error">
                  {pageError}
                </p>
              ) : pageText === null ? (
                <p className="inline-flex items-center gap-2 text-sm text-stone-500">
                  <Loader2 aria-hidden="true" className="size-4 animate-spin" />
                  Loading…
                </p>
              ) : (
                <PageMarkdown source={pageText} />
              )}
            </div>
            <div className="flex items-center justify-between pt-3">
              <button
                className="inline-flex items-center gap-1.5 rounded-full border border-stone-300 px-3 py-1.5 text-xs font-medium text-stone-600 transition hover:border-pine hover:text-pine disabled:cursor-not-allowed disabled:opacity-40"
                data-testid="reading-page-back"
                disabled={reader.pageIndex === 0}
                onClick={() =>
                  setReader((current) =>
                    current === null || current.pageIndex === 0
                      ? current
                      : { ...current, pageIndex: current.pageIndex - 1 },
                  )
                }
                type="button"
              >
                <ArrowLeft aria-hidden="true" className="size-3.5" />
                Back
              </button>
              {reader.pageIndex + 1 < reader.card.pages.length ? (
                <button
                  className="inline-flex items-center gap-1.5 rounded-full bg-ink px-4 py-1.5 text-xs font-medium text-white transition hover:bg-pine"
                  data-testid="reading-page-next"
                  onClick={() =>
                    setReader((current) =>
                      current === null ? current : { ...current, pageIndex: current.pageIndex + 1 },
                    )
                  }
                  type="button"
                >
                  Next
                  <ArrowRight aria-hidden="true" className="size-3.5" />
                </button>
              ) : (
                /* Reading the last page returns to the grid. */
                <button
                  className="inline-flex items-center gap-1.5 rounded-full bg-ink px-4 py-1.5 text-xs font-medium text-white transition hover:bg-pine"
                  data-testid="reading-page-done"
                  onClick={() => setReader(null)}
                  type="button"
                >
                  Back to the cards
                </button>
              )}
            </div>
          </div>
        )}

        <footer className="flex items-center justify-between gap-3 border-t border-stone-200 px-8 py-3">
          <span className="text-xs tabular-nums text-stone-500">
            {step ? `Card ${step.index + 1} of ${step.total}` : null}
          </span>
          <span className="inline-flex items-center gap-2">
            {/* FR-090 — leaving is possible at any step, and keeps the session. */}
            <button
              className="rounded-full border border-stone-300 px-3 py-1.5 text-xs font-medium text-stone-600 transition hover:border-pine hover:text-pine"
              data-testid="reading-leave"
              onClick={() => void leaveTutorial()}
              title="Leave this tutorial — your place is kept"
              type="button"
            >
              Leave tutorial
            </button>
            {/*
             * FR-054a — the one thing that moves the tutorial on. Live exactly
             * when the backend reports the current card's pages all read.
             */}
            <button
              className="rounded-full bg-ink px-4 py-1.5 text-xs font-medium text-white transition hover:bg-pine disabled:cursor-not-allowed disabled:bg-stone-300"
              data-testid="reading-continue"
              disabled={!canContinue}
              onClick={() => void continueStep()}
              title={
                canContinue
                  ? "Go to the next card"
                  : "This card is not finished — open it and read its pages"
              }
              type="button"
            >
              Continue
            </button>
          </span>
        </footer>
      </div>
    </div>
  );
}
