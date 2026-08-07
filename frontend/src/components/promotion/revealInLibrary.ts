// FR-020 — land the user looking at `My Library`.
//
// Spec: docs/specs/adr-053-personal-tool-library.md §6 FR-020: "On success the
// UI MUST confirm inline and reveal the item in its new section in the
// palette. The action exists to teach that the container exists; a silent
// success wastes the teaching moment."
//
// Four things have to happen for that sentence to be true, and none of them is
// optional:
//
//   1. The catalogue is re-read, or the palette does not have the new item yet.
//   2. The palette panel is expanded — it starts collapsed by default, so a
//      promotion from the canvas or the editor would otherwise reveal nothing.
//   3. The left panel switches to the item's own tab (`Blocks` / `Data types`).
//   4. The palette narrows to the item, so `My Library` is the only section
//      showing it. Filtering is what makes this a *reveal* rather than a hint:
//      the promoted item and its new section are the only thing on screen.
//
// Steps 1, 2 and 4-for-blocks are store writes and happen here. Steps 3 and
// 4-for-types need a component that owns React state, so they are published
// through the subscription below and consumed by `ProjectWorkspace` (the tab)
// and `TypePalette` (its own search box). A module-level channel rather than a
// store slice: this is a transient, one-shot instruction, not application
// state, and putting it in the persisted store would resurrect a stale reveal
// on the next launch.

import { useSyncExternalStore } from "react";

import { useAppStore } from "../../store";
import { loadTypeCatalog } from "../../store/useTypeCatalog";

export interface LibraryReveal {
  /** Which left-panel tab holds the item's `My Library` section. */
  surface: "blocks" | "types";
  /** The promoted item's display name — also the search term that isolates it. */
  name: string;
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
export function revealInLibrary(surface: LibraryReveal["surface"], name: string): void {
  token += 1;
  const store = useAppStore.getState();
  if (surface === "blocks") {
    // The block catalogue is App-owned and refreshed off this counter; the
    // search term is store-held, so narrowing to the item needs no component.
    store.bumpBlockCatalogRefresh();
    store.setPaletteSearch(name);
  } else {
    void loadTypeCatalog({ force: true });
  }
  useAppStore.setState({ paletteCollapsed: false });
  publish({ surface, name, token });
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
