// A single Blocks-tab grid cell — the shared `PaletteTile` dressed in the
// canvas category visual language (macaron swatch + lucide category icon).
//
// Specs: docs/specs/frontend-block-palette.md §3 Tile.
//        docs/specs/adr-053-personal-tool-library.md §10.1 (one shared tile).

import { getCategoryVisual } from "../nodes/BlockNode.parts/categoryVisuals";
import { PaletteTile } from "../palette/PaletteTile";
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
    <PaletteTile
      draggable
      label={block.name}
      onActivate={() => onAddBlock(block)}
      onDragStart={(event) => onDragStart(event, block)}
      onEnter={(rect) => onEnter(block, rect)}
      onLeave={onLeave}
      swatch={{ background: visual.bg, border: visual.border }}
      testId="palette-block-tile"
    >
      <Icon color={visual.fg} size={44} strokeWidth={1.6} />
    </PaletteTile>
  );
}
