// FR-020 — land the user looking at `My Library`.
//
// Spec: docs/specs/adr-053-personal-tool-library.md §6 FR-020: "On success the
// UI MUST confirm inline and bring the item's new section into view."
//
// Three things have to happen for that sentence to be true, and none of them is
// optional:
//
//   1. The catalogue is re-read, or the palette does not have the new item yet.
//   2. The palette panel is expanded — it starts collapsed by default, so a
//      promotion from the canvas or the editor would otherwise reveal nothing.
//   3. The left panel switches to the item's own tab (`Blocks` / `Data types`).
//
// A fourth step used to type the item's name into the palette search box, so
// `My Library` was the only section left showing anything. FR-020 now forbids
// it: the user did not type that, so from their side the palette had simply
// lost every other block, and a confirmation that reads as a malfunction
// teaches the opposite of what this feature exists to teach. The item is in
// `My Library` on the tab they are now looking at, and the inline notice names
// it — that is the reveal.
//
// This is also why the channel carries no name: with nothing to filter, nothing
// downstream needs one, and a field that says "the search term that isolates
// it" would be describing behaviour that no longer exists.
//
// Steps 1 and 2 are store writes and happen here. Step 3 needs a component that
// owns React state, so it is published through the subscription below and
// consumed by `ProjectWorkspace`. A module-level channel rather than a store
// slice: this is a transient, one-shot instruction, not application state, and
// putting it in the persisted store would resurrect a stale reveal on the next
// launch.

import { useSyncExternalStore } from "react";

import { useAppStore } from "../../store";
import { loadTypeCatalog } from "../../store/useTypeCatalog";

export interface LibraryReveal {
  /** Which left-panel tab holds the item's `My Library` section. */
  surface: "blocks" | "types";
  /**
   * Bumped on every reveal so promoting the same item twice re-fires. A
   * consumer comparing values alone would ignore the second promotion.
   */
  token: number;
}

let current: LibraryReveal | null = null;
let token = 0;
const listeners = new Set<() => void>();

function publish(next: LibraryReveal | null): void {
  current = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Reveal a freshly promoted item in its new palette section.
 *
 * Safe to call from a non-React context: everything it touches is either the
 * zustand store's imperative API or this module's own channel.
 */
export function revealInLibrary(surface: LibraryReveal["surface"]): void {
  token += 1;
  if (surface === "blocks") {
    // The block catalogue is App-owned and refreshed off this counter.
    useAppStore.getState().bumpBlockCatalogRefresh();
  } else {
    void loadTypeCatalog({ force: true });
  }
  useAppStore.setState({ paletteCollapsed: false });
  publish({ surface, token });
}

/** The pending reveal, or `null`. Re-renders the caller on every new one. */
export function useLibraryReveal(): LibraryReveal | null {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => null,
  );
}

/** Test seam — drop any pending reveal so each test starts clean. */
export function resetLibraryReveal(): void {
  token = 0;
  publish(null);
}
