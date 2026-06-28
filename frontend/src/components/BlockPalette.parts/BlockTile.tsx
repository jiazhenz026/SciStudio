// A single palette grid cell — a compact mini canvas-node (macaron swatch +
// lucide category icon on top, 2-line block name below). Reuses the canvas
// category visual language via getCategoryVisual().
//
// Spec: docs/specs/frontend-block-palette.md §3 Tile.

import { getCategoryVisual } from "../nodes/BlockNode.parts/categoryVisuals";
import type { BlockSummary } from "../../types/api";

export interface BlockTileProps {
  block: BlockSummary;
  onDragStart: (event: React.DragEvent, block: BlockSummary) => void;
  onAddBlock: (block: BlockSummary) => void;
  onEnter: (block: BlockSummary, rect: DOMRect) => void;
  onLeave: () => void;
}

export function BlockTile({ block, onDragStart, onAddBlock, onEnter, onLeave }: BlockTileProps) {
  // #1839/#1847: honour the block's own ui_color/ui_icon so the palette tile
  // matches its canvas node (the palette is where authors pick by glyph).
  const visual = getCategoryVisual(block.base_category, block.ui_color, block.ui_icon);
  const Icon = visual.Icon;

  return (
    <div
      className="rounded-xl border border-transparent p-1.5 transition hover:-translate-y-0.5 hover:border-stone-200 hover:bg-white/70 hover:shadow-sm"
      data-testid="palette-block-tile"
      draggable
      onDragStart={(event) => {
        onLeave();
        onDragStart(event, block);
      }}
      onMouseEnter={(event) => onEnter(block, event.currentTarget.getBoundingClientRect())}
      onMouseLeave={onLeave}
    >
      <button
        className="flex w-full flex-col items-center gap-1.5"
        onClick={() => onAddBlock(block)}
        title={block.name}
        type="button"
      >
        <span
          aria-hidden="true"
          className="flex h-[72px] w-[72px] items-center justify-center rounded-xl border shadow-sm"
          style={{ backgroundColor: visual.bg, borderColor: visual.border }}
        >
          <Icon color={visual.fg} size={44} strokeWidth={1.6} />
        </span>
        <span className="line-clamp-2 text-center font-display text-[12px] font-medium leading-tight text-ink">
          {block.name}
        </span>
      </button>
    </div>
  );
}
