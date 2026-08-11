// The one palette grid cell — a colour swatch with an optional glyph, a 2-line
// label under it, a hover trigger, and an optional drag hook.
//
// Spec: docs/specs/adr-053-personal-tool-library.md §10.1 (shared tile).
// The Blocks tab wraps this with the canvas category visual
// (`BlockPalette.parts/BlockTile.tsx`); the Data types tab wraps it with the
// port colour (solid fill plus ring, FR-041). Neither surface reimplements the
// cell itself.

import type { ReactNode } from "react";

export interface PaletteTileSwatch {
  /** Swatch fill. */
  background: string;
  /** Swatch border. */
  border: string;
  /**
   * Optional inner ring drawn inside the swatch — the "solid fill plus ring"
   * treatment type tiles share with canvas port handles (FR-041).
   */
  ring?: string;
}

export interface PaletteTileProps {
  /** Caption under the swatch, and the tile's `title` for a11y/tooltip. */
  label: string;
  swatch: PaletteTileSwatch;
  /** Glyph rendered inside the swatch (e.g. the block's category icon). */
  children?: ReactNode;
  /** `data-testid` for the outer cell. */
  testId?: string;
  /**
   * ADR-053 (#2057) — the tutorial highlight target this cell answers to, and
   * the value that picks it out of the other cells.
   *
   * Taken from the caller rather than assumed, because this tile renders in two
   * palettes whose entries are addressed differently: a block by `block_type`,
   * a data type by its type name. A tile with no tutorial meaning passes
   * neither and carries no attribute.
   */
  tutorialTarget?: string;
  tutorialTargetKey?: string;
  draggable?: boolean;
  /** Click / keyboard activation (add the item to the canvas). */
  onActivate: () => void;
  onDragStart?: (event: React.DragEvent<HTMLDivElement>) => void;
  /** Pointer entered the cell; `rect` is the cell's viewport-space rectangle. */
  onEnter: (rect: DOMRect) => void;
  /** Pointer left the cell (also fired at drag start). */
  onLeave: () => void;
}

/** Inner ring, drawn as an inset shadow so it does not affect layout. */
const RING_WIDTH_PX = 3;

export function PaletteTile({
  label,
  swatch,
  children,
  testId,
  tutorialTarget,
  tutorialTargetKey,
  draggable,
  onActivate,
  onDragStart,
  onEnter,
  onLeave,
}: PaletteTileProps) {
  return (
    <div
      className="rounded-xl border border-transparent p-1.5 transition hover:-translate-y-0.5 hover:border-stone-200 hover:bg-white/70 hover:shadow-sm"
      data-testid={testId}
      data-tutorial-target={tutorialTarget}
      data-tutorial-target-key={tutorialTargetKey}
      draggable={draggable}
      onDragStart={(event) => {
        onLeave();
        onDragStart?.(event);
      }}
      onMouseEnter={(event) => onEnter(event.currentTarget.getBoundingClientRect())}
      onMouseLeave={onLeave}
    >
      <button
        className="flex w-full flex-col items-center gap-1.5"
        onClick={onActivate}
        title={label}
        type="button"
      >
        <span
          aria-hidden="true"
          className="flex h-[72px] w-[72px] items-center justify-center rounded-xl border shadow-sm"
          style={{
            backgroundColor: swatch.background,
            borderColor: swatch.border,
            ...(swatch.ring
              ? { boxShadow: `inset 0 0 0 ${RING_WIDTH_PX}px ${swatch.ring}` }
              : null),
          }}
        >
          {children}
        </span>
        <span className="line-clamp-2 text-center font-display text-[12px] font-medium leading-tight text-ink">
          {label}
        </span>
      </button>
    </div>
  );
}
