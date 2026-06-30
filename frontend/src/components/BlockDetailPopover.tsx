// Hover detail popover — a display-only card showing a block's icon + name,
// full description, and typed port signature. Shared between the left block
// palette (hover a tile) and the workflow canvas (hover a placed node), so it
// lives at the components root rather than under a single surface's `.parts`.
//
// Specs:
//   docs/specs/frontend-block-palette.md §6 (palette hover detail)
//   docs/specs/frontend-block-palette.md §7 (canvas node hover detail, #1887)

import { getCategoryVisual } from "./nodes/BlockNode.parts/categoryVisuals";
import { portSignature } from "./BlockPalette.parts/paletteModel";
import type { BlockSummary } from "../types/api";

export interface PopoverAnchor {
  /** Viewport-space left edge for the popover. */
  left: number;
  /** Viewport-space top edge for the popover. */
  top: number;
}

export interface BlockDetailPopoverProps {
  block: BlockSummary;
  anchor: PopoverAnchor;
}

export function BlockDetailPopover({ block, anchor }: BlockDetailPopoverProps) {
  // #1839/#1847: honour the block's own ui_color/ui_icon (match its canvas node).
  const visual = getCategoryVisual(block.base_category, block.ui_color, block.ui_icon);
  const Icon = visual.Icon;
  const inputs = portSignature(block.input_ports);
  const outputs = portSignature(block.output_ports);

  return (
    <div
      className="pointer-events-none fixed z-50 w-64 rounded-xl border border-stone-200 bg-white p-3 shadow-panel"
      data-testid="block-detail-popover"
      style={{ left: anchor.left, top: anchor.top }}
    >
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="flex h-6 w-6 items-center justify-center rounded-md border"
          style={{ backgroundColor: visual.bg, borderColor: visual.border }}
        >
          <Icon color={visual.fg} size={14} strokeWidth={1.9} />
        </span>
        <span className="font-display text-sm font-semibold text-ink">{block.name}</span>
      </div>

      {block.description ? (
        <p className="mt-2 text-xs leading-snug text-stone-600">{block.description}</p>
      ) : null}

      {inputs.length > 0 || outputs.length > 0 ? (
        <div className="mt-2 space-y-0.5 border-t border-stone-100 pt-2 font-mono text-[11px] text-stone-500">
          {inputs.map((port) => (
            <div key={`in-${port.name}`}>
              <span className="font-semibold text-pine">in</span> {port.name} :{" "}
              <span className="text-ink">{port.type}</span>
            </div>
          ))}
          {outputs.map((port) => (
            <div key={`out-${port.name}`}>
              <span className="font-semibold text-ember">out</span> {port.name} :{" "}
              <span className="text-ink">{port.type}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
