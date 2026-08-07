// Shared palette section model — the group → ordered-take → remainder-A→Z
// skeleton and the generic text filter, used by BOTH left-panel palettes (the
// Blocks tab and the Data types tab) so the two surfaces cannot drift apart.
//
// Spec: docs/specs/adr-053-personal-tool-library.md
//   §10.1 shared helpers (FR-047 — this must fit both surfaces with no
//   per-surface special-casing), §9.1 (FR-036 ordering, FR-037 empty states).
//
// Nothing here knows what a block or a type is. Everything surface-specific —
// how an item is grouped, how it is sorted, what its haystack looks like —
// arrives as a callback, and §10.2 keeps `derivePackage`, the io-source/sink
// predicates, `CATEGORY_KEYS` and `portSignature` on the block side.

/** One rendered palette section. */
export interface Section<T> {
  /** Stable key for React and for per-section collapse state. */
  id: string;
  /** Header label shown to the user. */
  title: string;
  items: T[];
  /** Pinned sections always render and never collapse. */
  pinned: boolean;
  /**
   * One line stating what the section is for, rendered in place of the grid
   * when the section is empty (FR-037). A slot without a hint keeps the
   * ordinary omit-when-empty behaviour.
   */
  emptyHint?: string;
}

/**
 * A declared slot in the ordered head of the section list.
 *
 * The head is explicit and surface-owned (Data I/O → Built-in → My Library →
 * This Project for blocks; core → My Library → This Project for types); every
 * group key that is not claimed by a slot falls into the A→Z remainder.
 */
export interface SectionSlot {
  /** Group key produced by the surface's `groupOf`. */
  id: string;
  /** Header label. Remainder sections use their group key as their title. */
  title: string;
  /** Pinned sections always render and never collapse. */
  pinned?: boolean;
  /** Present ⇒ the section renders even when empty, showing this line. */
  emptyHint?: string;
}

/**
 * Filter `items` by a case-insensitive substring of their haystack text.
 *
 * An empty or whitespace-only `search` matches everything. Chip/facet filters
 * compose on top of this by the caller (search AND facet), which keeps the
 * facet vocabulary — block base categories, type parents — surface-owned.
 */
export function filterItems<T>(
  items: readonly T[],
  search: string,
  toHaystack: (item: T) => string,
): T[] {
  const needle = search.trim().toLowerCase();
  if (!needle) {
    return [...items];
  }
  return items.filter((item) => toHaystack(item).toLowerCase().includes(needle));
}

/**
 * Group `items` by `groupOf`, emit the declared slots in order, then every
 * remaining group A→Z by its key.
 *
 * A slot with no items is emitted only when it declares an `emptyHint`
 * (FR-037); remainder groups are never emitted empty because they exist only
 * when something landed in them. `compare` orders items inside every section.
 */
export function buildSections<T>(
  items: readonly T[],
  groupOf: (item: T) => string,
  pinnedOrder: readonly SectionSlot[],
  compare?: (a: T, b: T) => number,
): Section<T>[] {
  const grouped = new Map<string, T[]>();
  for (const item of items) {
    const key = groupOf(item);
    const bucket = grouped.get(key);
    if (bucket) {
      bucket.push(item);
    } else {
      grouped.set(key, [item]);
    }
  }

  const take = (key: string): T[] => {
    const bucket = grouped.get(key) ?? [];
    grouped.delete(key);
    return compare ? [...bucket].sort(compare) : [...bucket];
  };

  const sections: Section<T>[] = [];

  for (const slot of pinnedOrder) {
    const slotItems = take(slot.id);
    if (slotItems.length === 0 && slot.emptyHint === undefined) {
      continue;
    }
    const section: Section<T> = {
      id: slot.id,
      title: slot.title,
      items: slotItems,
      pinned: slot.pinned === true,
    };
    if (slot.emptyHint !== undefined) {
      section.emptyHint = slot.emptyHint;
    }
    sections.push(section);
  }

  for (const key of [...grouped.keys()].sort((a, b) => a.localeCompare(b))) {
    sections.push({ id: key, title: key, items: take(key), pinned: false });
  }

  return sections;
}

/**
 * Strip the teaching empty states from `slots`.
 *
 * Used while a search or facet filter is active: "No blocks of your own yet"
 * is a statement about the library, not about the current query, and printing
 * it under an active filter would assert something false about a section whose
 * contents were merely filtered away. Under a filter every section behaves
 * like every other one and is omitted when empty.
 */
export function withoutEmptyHints(slots: readonly SectionSlot[]): SectionSlot[] {
  return slots.map(({ emptyHint: _emptyHint, ...slot }) => slot);
}
