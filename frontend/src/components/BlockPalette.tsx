import { useEffect, useRef, useState } from "react";

import { useReloadFlash } from "../hooks/useReloadFlash";
import type { BlockSummary } from "../types/api";
import { getCategoryVisual } from "./nodes/BlockNode.parts/categoryVisuals";
import { BlockDetailPopover, type PopoverAnchor } from "./BlockDetailPopover";
import { BlockTile } from "./BlockPalette.parts/BlockTile";
import { CategoryChips } from "./BlockPalette.parts/CategoryChips";
import { buildPaletteSections, type PaletteSection } from "./BlockPalette.parts/paletteModel";

interface BlockPaletteProps {
  blocks: BlockSummary[];
  search: string;
  collapsed: boolean;
  onSearch: (value: string) => void;
  onReload: () => void;
  onAddBlock: (block: BlockSummary) => void;
}

/** Gap (px) between a tile's right edge and the detail popover. */
const POPOVER_GAP = 8;
/** Hover dwell before the detail popover opens (spec §6). */
const POPOVER_OPEN_DELAY_MS = 150;
/** Rough popover height used to keep it inside the viewport. */
const POPOVER_MAX_HEIGHT = 240;

// #1857: the tile grid auto-adapts its column count to the (resizable) palette
// width instead of a hardcoded 2 columns. A tile's intrinsic minimum width is
// the 72px category swatch plus the tile's own padding, so TILE_MIN_PX leaves a
// little breathing room above that. We prefer 2 columns (the default-panel
// look), expand to at most 3 when the panel is dragged wide, and only fall back
// to 1 when the panel is too narrow to fit two swatches side by side.
const TILE_MIN_PX = 80;
const GRID_GAP_PX = 4; // Tailwind gap-1 = 0.25rem.
const MIN_COLUMNS = 1;
const MAX_COLUMNS = 3;
const DEFAULT_COLUMNS = 2;

/** Column count that fits `width` px, clamped to [MIN_COLUMNS, MAX_COLUMNS]. */
export function paletteColumns(width: number): number {
  if (width <= 0) {
    // Pre-measurement (first paint / jsdom): keep the default 2-column look.
    return DEFAULT_COLUMNS;
  }
  const fit = Math.floor((width + GRID_GAP_PX) / (TILE_MIN_PX + GRID_GAP_PX));
  return Math.max(MIN_COLUMNS, Math.min(MAX_COLUMNS, fit));
}

interface SectionViewProps {
  section: PaletteSection;
  forceOpen: boolean;
  columns: number;
  onDragStart: (event: React.DragEvent, block: BlockSummary) => void;
  onAddBlock: (block: BlockSummary) => void;
  onEnter: (block: BlockSummary, rect: DOMRect) => void;
  onLeave: () => void;
}

function SectionView({
  section,
  forceOpen,
  columns,
  onDragStart,
  onAddBlock,
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
      {open ? (
        <div
          className="grid gap-1"
          style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
        >
          {section.blocks.map((block) => (
            <BlockTile
              block={block}
              key={`${block.type_name}-${block.name}`}
              onAddBlock={onAddBlock}
              onDragStart={onDragStart}
              onEnter={onEnter}
              onLeave={onLeave}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function BlockPalette({
  blocks,
  search,
  collapsed,
  onSearch,
  onReload,
  onAddBlock,
}: BlockPaletteProps) {
  const dragImageRef = useRef<HTMLDivElement | null>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Blink the palette body (search + chips + grid) once a Reload actually lands.
  const { ref: contentRef, trigger: triggerFlash } = useReloadFlash<HTMLDivElement, BlockSummary[]>(
    blocks,
  );

  const [activeCategories, setActiveCategories] = useState<string[]>([]);
  const [hovered, setHovered] = useState<{ block: BlockSummary; anchor: PopoverAnchor } | null>(
    null,
  );

  // #1857: measure the scrollable grid area so the tile grid can pick a column
  // count that fits the resizable palette. clientWidth excludes the scrollbar,
  // so it reflects the space tiles actually get.
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

  const handleReload = () => {
    triggerFlash();
    onReload();
  };

  const sections = buildPaletteSections(blocks, search, activeCategories);
  const forceOpen = search.trim().length > 0 || activeCategories.length > 0;

  const toggleCategory = (key: string) => {
    setActiveCategories((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  };

  const clearHover = () => {
    if (hoverTimer.current) {
      clearTimeout(hoverTimer.current);
      hoverTimer.current = null;
    }
    setHovered(null);
  };

  const handleTileEnter = (block: BlockSummary, rect: DOMRect) => {
    if (hoverTimer.current) {
      clearTimeout(hoverTimer.current);
    }
    const maxTop =
      typeof window === "undefined"
        ? rect.top
        : Math.max(8, window.innerHeight - POPOVER_MAX_HEIGHT);
    const anchor: PopoverAnchor = {
      left: rect.right + POPOVER_GAP,
      top: Math.min(rect.top, maxTop),
    };
    hoverTimer.current = setTimeout(() => setHovered({ block, anchor }), POPOVER_OPEN_DELAY_MS);
  };

  const handleDragStart = (event: React.DragEvent, block: BlockSummary) => {
    const payload = { ...block };
    if (block.direction) {
      (payload as Record<string, unknown>)._default_direction = block.direction;
    }
    event.dataTransfer.setData("application/scistudio-block", JSON.stringify(payload));
    event.dataTransfer.effectAllowed = "copy";

    if (dragImageRef.current) {
      dragImageRef.current.textContent = block.name;
      dragImageRef.current.style.display = "block";
      event.dataTransfer.setDragImage(dragImageRef.current, 40, 16);
      requestAnimationFrame(() => {
        if (dragImageRef.current) dragImageRef.current.style.display = "none";
      });
    }
  };

  // Collapsed (rail) mode: a single column of icon-only swatches; no chips,
  // search, or popover. Behavior preserved as-is per spec §3.
  if (collapsed) {
    const railBlocks = sections.flatMap((section) => section.blocks);
    return (
      <aside className="flex h-full flex-col overflow-hidden border-r border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))] p-2">
        <button className="toolbar-button mb-2 self-center" onClick={handleReload} type="button">
          {"↻"}
        </button>
        <div
          className="flex min-h-0 flex-1 flex-col items-center gap-2 overflow-y-auto scrollbar-thin"
          ref={contentRef}
        >
          {railBlocks.map((block) => {
            const visual = getCategoryVisual(block.base_category);
            const Icon = visual.Icon;
            return (
              <button
                className="flex h-9 w-9 items-center justify-center rounded-lg border shadow-sm"
                key={`${block.type_name}-${block.name}`}
                onClick={() => onAddBlock(block)}
                style={{ backgroundColor: visual.bg, borderColor: visual.border }}
                title={block.name}
                type="button"
              >
                <Icon color={visual.fg} size={20} strokeWidth={1.75} />
              </button>
            );
          })}
        </div>
      </aside>
    );
  }

  return (
    <aside className="flex h-full flex-col overflow-hidden border-r border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))] p-4">
      {/* Drag ghost element (offscreen) */}
      <div
        className="pointer-events-none fixed -left-[9999px] -top-[9999px] rounded-xl border border-ember bg-white px-4 py-2 text-sm font-medium text-ink shadow-lg"
        ref={dragImageRef}
        style={{ display: "none" }}
      />

      <div className="flex items-center justify-between gap-2">
        <p className="font-display text-xl text-ink">Palette</p>
        <button className="toolbar-button" onClick={handleReload} type="button">
          Reload
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col" data-testid="palette-content" ref={contentRef}>
        <input
          className="mt-4 w-full rounded-2xl border border-stone-300 bg-white px-4 py-3 text-sm outline-none transition focus:border-ember"
          onChange={(event) => onSearch(event.target.value)}
          placeholder="Search blocks"
          value={search}
        />

        <CategoryChips active={activeCategories} onToggle={toggleCategory} />

        <div
          className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto pb-6 scrollbar-thin"
          ref={gridScrollRef}
        >
          {sections.map((section) => (
            <SectionView
              columns={columns}
              forceOpen={forceOpen}
              key={section.id}
              onAddBlock={onAddBlock}
              onDragStart={handleDragStart}
              onEnter={handleTileEnter}
              onLeave={clearHover}
              section={section}
            />
          ))}
        </div>
      </div>

      {hovered ? <BlockDetailPopover anchor={hovered.anchor} block={hovered.block} /> : null}
    </aside>
  );
}
