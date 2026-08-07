// The Data types tab — the left panel's third tab (ADR-053 §9.2).
//
// Specs:
//   docs/specs/adr-053-personal-tool-library.md §9.2 (FR-039 – FR-043),
//     §7.1 FR-051 (colour precedence), §10.1 (shared helpers, FR-047),
//     §9.3 (FR-044 – FR-046 interactive popover).
//   docs/specs/frontend-block-palette.md §11.
//
// Everything structural here is B3's shared palette machinery — `filterItems`
// and `buildSections<T>` (via `TypePalette.parts/typeModel`), `PaletteTile`,
// `FilterChips`, `useHoverPopover`, and `DetailPopover` (via
// `TypePalette.parts/TypeDetailPopover`). FR-047 requires that skeleton to fit
// both surfaces with no per-surface special-casing, and it does: this file
// supplies four callbacks (group, sort, haystack, facet) and no exceptions.
//
// FR-027 is why the tab reads the type catalogue directly rather than taking
// blocks as props: refreshing types must not mean refreshing the palette, and
// drawing types must not require a blocks request.

import { useEffect, useMemo, useRef, useState } from "react";

import { resolveRingColor, resolveTypeColor } from "../config/typeColorMap";
import { useReloadFlash } from "../hooks/useReloadFlash";
import { useTypeCatalog } from "../store/useTypeCatalog";
import type { TypeSummary } from "../types/api";

import { paletteColumns } from "./BlockPalette";
import { FilterChips, type FilterChip } from "./palette/FilterChips";
import { useHoverPopover } from "./palette/hoverPopover";
import { TypeDetailPopover } from "./TypePalette.parts/TypeDetailPopover";
import { TypeTile } from "./TypePalette.parts/TypeTile";
import {
  buildTypeSections,
  isFilteringTypes,
  typeFamilies,
  typeHierarchyFrom,
  type TypeSection,
} from "./TypePalette.parts/typeModel";

interface SectionViewProps {
  section: TypeSection;
  forceOpen: boolean;
  columns: number;
  /** Fill + ring for one type, resolved through the FR-051 precedence. */
  swatchFor: (type: TypeSummary) => { fill: string; ring?: string };
  onEnter: (type: TypeSummary, rect: DOMRect) => void;
  onLeave: () => void;
}

function SectionView({
  section,
  forceOpen,
  columns,
  swatchFor,
  onEnter,
  onLeave,
}: SectionViewProps) {
  const [collapsed, setCollapsed] = useState(false);
  const open = section.pinned || forceOpen || !collapsed;

  return (
    <section>
      {section.pinned ? (
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.3em] text-stone-700">
          {section.title}
        </p>
      ) : (
        <button
          className="mb-2 flex w-full items-center gap-1 text-left"
          onClick={() => setCollapsed((prev) => !prev)}
          type="button"
        >
          <span className="text-[11px] text-stone-600">{open ? "▼" : "▶"}</span>
          <span className="text-[11px] font-semibold uppercase tracking-[0.3em] text-stone-700">
            {section.title}
          </span>
        </button>
      )}
      {open && section.items.length === 0 ? (
        // FR-037 (via FR-040): `My Library` and `This Project` render even when
        // empty, each carrying one line stating what the section is for.
        <p
          className="px-1 text-[11px] leading-snug text-stone-500"
          data-testid="palette-section-empty"
        >
          {section.emptyHint}
        </p>
      ) : null}
      {open && section.items.length > 0 ? (
        <div
          className="grid gap-1"
          style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
        >
          {section.items.map((type) => {
            const swatch = swatchFor(type);
            return (
              <TypeTile
                fill={swatch.fill}
                key={type.name}
                onEnter={onEnter}
                onLeave={onLeave}
                ring={swatch.ring}
                type={type}
              />
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

/**
 * Family filter chips (FR-040).
 *
 * The chip vocabulary stays surface-owned (§10.1): the Blocks tab supplies its
 * base categories, and a type's analogue is the core base family it descends
 * from. Each chip is tinted with that family's own resolved colour, so the
 * chip row is also a legend for the tile swatches beside it.
 */
function familyChips(
  families: readonly string[],
  swatchFor: (name: string) => { fill: string; ring?: string },
): FilterChip[] {
  return families.map((family) => {
    const swatch = swatchFor(family);
    return {
      key: family,
      label: family,
      background: `${swatch.fill}22`,
      border: swatch.ring ?? swatch.fill,
      color: swatch.fill,
    };
  });
}

export function TypePalette() {
  const { types, loaded, declared, reload } = useTypeCatalog();
  const [search, setSearch] = useState("");
  const [activeFamilies, setActiveFamilies] = useState<string[]>([]);
  // FR-044/FR-046: B3's shared hover state machine, the same one the Blocks
  // tab drives. Spreading `popoverProps` onto the card below is what makes it
  // interactive and keeps it open across the tile→card gap.
  const hover = useHoverPopover<TypeSummary>();
  // Same one-shot blink the Blocks tab and the project tree use, so all three
  // side panels confirm a completed reload identically.
  const { ref: contentRef, trigger: triggerFlash } = useReloadFlash<HTMLDivElement, TypeSummary[]>(
    types,
  );

  // Mirror the Blocks tab's responsive grid rather than restating it, so the
  // two tabs never disagree about how many tiles fit a dragged panel width.
  const gridScrollRef = useRef<HTMLDivElement | null>(null);
  const [gridWidth, setGridWidth] = useState(0);
  useEffect(() => {
    const node = gridScrollRef.current;
    if (!node || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(() => setGridWidth(node.clientWidth));
    observer.observe(node);
    setGridWidth(node.clientWidth);
    return () => observer.disconnect();
  }, []);
  const columns = paletteColumns(gridWidth);

  const hierarchy = useMemo(() => typeHierarchyFrom(types), [types]);
  // FR-041 + FR-051: one resolution, shared with the canvas port handles. The
  // declared colour (FR-050) wins, then `typeColorMap`, then the hash
  // fallback; `declared` is `undefined` until the listing lands (FR-067).
  const swatchFor = useMemo(() => {
    const forName = (name: string) => ({
      fill: resolveTypeColor([name], hierarchy, declared),
      ring: resolveRingColor([name], hierarchy, declared),
    });
    return {
      byName: forName,
      byType: (type: TypeSummary) => forName(type.name),
    };
  }, [hierarchy, declared]);

  const sections = buildTypeSections(types, search, activeFamilies);
  const forceOpen = isFilteringTypes(search, activeFamilies);
  const chips = familyChips(typeFamilies(types), swatchFor.byName);

  const toggleFamily = (key: string) => {
    setActiveFamilies((prev) =>
      prev.includes(key) ? prev.filter((entry) => entry !== key) : [...prev, key],
    );
  };

  const handleReload = () => {
    triggerFlash();
    void reload();
  };

  const hovered = hover.hovered;
  const hoveredSwatch = hovered ? swatchFor.byType(hovered.item) : null;

  return (
    <aside className="flex h-full flex-col overflow-hidden border-r border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))] p-4">
      <div className="flex items-center justify-between gap-2">
        {/* FR-039: the panel names itself after its tab, so `Blocks` and
            `Data types` read as peers. */}
        <p className="font-display text-xl text-ink">Data types</p>
        <button className="toolbar-button" onClick={handleReload} type="button">
          Reload
        </button>
      </div>

      <div
        className="flex min-h-0 flex-1 flex-col"
        data-testid="type-palette-content"
        ref={contentRef}
      >
        <input
          className="mt-4 w-full rounded-2xl border border-stone-300 bg-white px-4 py-3 text-sm outline-none transition focus:border-ember"
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search data types"
          value={search}
        />

        {chips.length > 0 ? (
          <FilterChips
            active={activeFamilies}
            chips={chips}
            onToggle={toggleFamily}
            testId="type-family-chips"
          />
        ) : null}

        <div
          className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto pb-6 scrollbar-thin"
          ref={gridScrollRef}
        >
          {sections.map((section) => (
            <SectionView
              columns={columns}
              forceOpen={forceOpen}
              key={section.id}
              onEnter={hover.openFor}
              onLeave={hover.scheduleClose}
              section={section}
              swatchFor={swatchFor.byType}
            />
          ))}
          {loaded && types.length === 0 ? (
            <p
              className="px-1 text-[11px] leading-snug text-stone-500"
              data-testid="type-palette-empty"
            >
              No data types registered.
            </p>
          ) : null}
        </div>
      </div>

      {hovered && hoveredSwatch ? (
        // Spreading `popoverProps` is what makes the card interactive
        // (FR-044): it supplies the pointer handlers that keep it open
        // together with the flag that drops `pointer-events-none`. B5 mounts
        // "Promote to My Library" by passing `actions` here.
        <TypeDetailPopover
          anchor={hovered.anchor}
          fill={hoveredSwatch.fill}
          hierarchy={hierarchy}
          ring={hoveredSwatch.ring}
          type={hovered.item}
          {...hover.popoverProps}
        />
      ) : null}
    </aside>
  );
}
