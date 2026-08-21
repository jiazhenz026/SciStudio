/**
 * ADR-053 Learning Center — the reading window's card model (#2084).
 *
 * A reading tutorial renders as a grid of cards, one per step, in step order.
 * The wire contract only ever carries the *current* step (`SessionResponse.step`,
 * FR-041's closed step view), so the grid is built from three sources:
 *
 * - the current step, which is fully known;
 * - steps this surface has already seen this session, remembered by index so a
 *   walked-past card keeps its name and stays reopenable;
 * - the step count (`step.total`), which sizes the grid so unvisited cards
 *   render as placeholders rather than not at all.
 *
 * Remembering is display memory, not judgment: nothing here decides whether a
 * step is done (spec §4.1 puts that on the backend), and losing the memory on
 * reload degrades a read card's caption, never the tutorial's actual progress.
 */

import type {
  TutorialCatalogueEntry,
  TutorialCatalogueResponse,
  TutorialSessionResponse,
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
 * The `pages` field the #2061 vocabulary batch adds to the step view, read
 * leniently: this surface was built alongside that batch, and reading the
 * field structurally keeps the two mergeable in either order. Once the widened
 * `TutorialStepView` type lands, this narrows to a plain property read.
 */
export function stepPages(step: TutorialStepView): string[] {
  const pages = (step as { pages?: unknown }).pages;
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
 * `remembered` maps step index to the card seen there. The current step always
 * renders from the live session rather than from memory, so a step whose text
 * the backend changed mid-session is never shown stale.
 */
export function readingSlots(
  session: TutorialSessionResponse,
  remembered: ReadonlyMap<number, ReadingCardInfo>,
): ReadingSlot[] {
  const step = session.step;
  if (!step) return [];
  const slots: ReadingSlot[] = [];
  for (let index = 0; index < step.total; index++) {
    if (index === step.index) {
      slots.push({ index, state: "current", card: cardOfStep(step) });
    } else {
      slots.push({
        index,
        state: index < step.index ? "read" : "unread",
        card: remembered.get(index) ?? null,
      });
    }
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
