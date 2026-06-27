// Hover detail popover — anchored to the right of a tile, showing the block's
// icon + name, full description, and typed port signature. Display-only.
//
// Spec: docs/specs/frontend-block-palette.md §6 Hover Detail Popover.

import { getCategoryVisual } from "../nodes/BlockNode.parts/categoryVisuals";
import type { BlockSummary } from "../../types/api";
import { portSignature } from "./paletteModel";

export interface PopoverAnchor {
  /** Viewport-space left edge for the popover (tile right + gap). */
  left: number;
  /** Viewport-space top edge for the popover. */
  top: number;
}

export interface BlockDetailPopoverProps {
  block: BlockSummary;
  anchor: PopoverAnchor;
}

export function BlockDetailPopover({ block, anchor }: BlockDetailPopoverProps) {
  const visual = getCategoryVisual(block.base_category);
  const Icon = visual.Icon;
  const inputs = portSignature(block.input_ports);
  const outputs = portSignature(block.output_ports);

  return (
    <div
      className="pointer-events-none fixed z-50 w-64 rounded-xl border border-stone-200 bg-white p-3 shadow-panel"
      data-testid="palette-detail-popover"
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
