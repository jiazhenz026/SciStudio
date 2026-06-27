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
  const visual = getCategoryVisual(block.base_category);
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
          className="flex h-9 w-9 items-center justify-center rounded-lg border shadow-sm"
          style={{ backgroundColor: visual.bg, borderColor: visual.border }}
        >
          <Icon color={visual.fg} size={22} strokeWidth={1.75} />
        </span>
        <span className="line-clamp-2 text-center font-display text-[12px] font-medium leading-tight text-ink">
          {block.name}
        </span>
      </button>
    </div>
  );
}
