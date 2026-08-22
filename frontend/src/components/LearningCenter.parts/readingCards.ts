/**
 * ADR-053 Learning Center — the reading window's card model (#2084).
 *
 * A reading tutorial renders as a grid of cards, one per step, in step order.
 * The grid draws from the session's read-only step outline
 * (`SessionResponse.steps`, the #2061 batch) — index, id, title, say, pages
 * per step — so every card is named up front, the summary level's whole point.
 * The current card still renders from the live step view, which additionally
 * carries `satisfied` and is never stale.
 *
 * A session without an outline (an older fixture or cached response) falls
 * back to the current step plus steps this surface has already seen this
 * session, remembered by index. Remembering is display memory, not judgment:
 * nothing here decides whether a step is done (spec §4.1 puts that on the
 * backend), and losing the memory on reload degrades a passed card's caption,
 * never the tutorial's actual progress.
 */

import type {
  TutorialCatalogueEntry,
  TutorialCatalogueResponse,
  TutorialSessionResponse,
  TutorialStepOutline,
  TutorialStepView,
} from "../../lib/api/learningCenter";

/** What the grid knows about one step it has seen. */
export interface ReadingCardInfo {
  id: string;
  title: string | null;
  say: string | null;
  pages: string[];
}

/** One grid slot: a position, a state, and a card when one is known. */
export interface ReadingSlot {
  index: number;
  /**
   * `read` — the session moved past this step (continue only follows a
   * satisfied step, so passed means read); `current` — the step the session
   * is on; `unread` — not reached yet.
   */
  state: "read" | "current" | "unread";
  card: ReadingCardInfo | null;
}

/**
 * A step's reading pages, in order. The field is optional on the wire type
 * (older fixtures), and entries are filtered structurally because a page name
 * becomes a URL segment.
 */
export function stepPages(step: TutorialStepView | TutorialStepOutline): string[] {
  const pages = step.pages;
  if (!Array.isArray(pages)) return [];
  return pages.filter((page): page is string => typeof page === "string" && page.length > 0);
}

/** The current step as a card, or null when the session carries no step. */
export function cardOfStep(step: TutorialStepView): ReadingCardInfo {
  return { id: step.id, title: step.title, say: step.say, pages: stepPages(step) };
}

/**
 * Build the grid: one slot per step, in step order.
 *
 * The session's step outline names every card up front; the current step
 * always renders from the live step view rather than from the outline or from
 * memory, so a step whose text the backend changed mid-session is never shown
 * stale. `remembered` (cards this surface has seen, by index) only matters for
 * a session without an outline.
 */
export function readingSlots(
  session: TutorialSessionResponse,
  remembered: ReadonlyMap<number, ReadingCardInfo>,
): ReadingSlot[] {
  const step = session.step;
  if (!step) return [];
  const outline = Array.isArray(session.steps) ? session.steps : [];
  const state = (index: number): ReadingSlot["state"] =>
    index === step.index ? "current" : index < step.index ? "read" : "unread";
  if (outline.length > 0) {
    return outline.map((row) => ({
      index: row.index,
      state: state(row.index),
      card:
        row.index === step.index
          ? cardOfStep(step)
          : { id: row.id, title: row.title, say: row.say, pages: stepPages(row) },
    }));
  }
  const slots: ReadingSlot[] = [];
  for (let index = 0; index < step.total; index++) {
    slots.push({
      index,
      state: state(index),
      card: index === step.index ? cardOfStep(step) : (remembered.get(index) ?? null),
    });
  }
  return slots;
}

/**
 * The catalogue entry the active session belongs to, or null.
 *
 * The entry is where `reading` lives — the backend's derived answer to "is
 * this tutorial reading-only" (`TutorialManifest.is_reading_only`) — and the
 * reading window only ever renders for an entry that says so. Matching is by
 * the session's own triple, the same key the catalogue lists entries under.
 */
export function findSessionEntry(
  catalogue: TutorialCatalogueResponse | null,
  session: TutorialSessionResponse | null,
): TutorialCatalogueEntry | null {
  if (!catalogue || !session || !Array.isArray(catalogue.groups)) return null;
  for (const group of catalogue.groups) {
    if (!Array.isArray(group.tutorials)) continue;
    for (const entry of group.tutorials) {
      if (
        entry.source_kind === session.source_kind &&
        entry.source_id === session.source_id &&
        entry.id === session.tutorial_id
      ) {
        return entry;
      }
    }
  }
  return null;
}
