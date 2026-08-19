// Block hover detail — the shared `DetailPopover` card filled with a block's
// icon + name, full description, and typed port signature. Used by the left
// block palette (hover a tile) and by the workflow canvas (hover a placed
// node), so it lives at the components root rather than under a single
// surface's `.parts`.
//
// Specs:
//   docs/specs/frontend-block-palette.md §6 (palette hover detail)
//   docs/specs/frontend-block-palette.md §10 (canvas node hover detail, #1887)
//   docs/specs/adr-053-personal-tool-library.md §9.3 (FR-044 – FR-046)

import type { ReactNode } from "react";

import { getCategoryVisual } from "./nodes/BlockNode.parts/categoryVisuals";
import { DetailPopover } from "./palette/DetailPopover";
import { portSignature } from "./BlockPalette.parts/paletteModel";
import type { PopoverAnchor } from "./palette/hoverPopover";
import type { BlockSummary } from "../types/api";

// The anchor type moved to the shared palette module; re-exported so the
// canvas anchor helper and node keep importing it from here.
export type { PopoverAnchor };

export interface BlockDetailPopoverProps {
  block: BlockSummary;
  anchor: PopoverAnchor;
  /**
   * FR-044: accept pointer events and keep the card open while the pointer is
   * inside it. Supplied together with the handlers below by spreading
   * `useHoverPopover().popoverProps`. Left off, the card stays display-only —
   * which is what the canvas node popover wants (`frontend-block-palette`
   * spec §10).
   */
  interactive?: boolean;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  /**
   * Action row rendered under the port signature.
   *
   * This is entry point E5 (ADR-053 §6.2): "Promote to My Library" mounts
   * here. The palette owns the action and passes it down, so the popover stays
   * a presentation component and one implementation still serves both surfaces
   * (FR-046).
   */
  actions?: ReactNode;
}

export function BlockDetailPopover({
  block,
  anchor,
  interactive,
  onMouseEnter,
  onMouseLeave,
  actions,
}: BlockDetailPopoverProps) {
  // #1839/#1847: honour the block's own ui_color/ui_icon (match its canvas node).
  const visual = getCategoryVisual(block.base_category, block.ui_color, block.ui_icon);
  const Icon = visual.Icon;
  const inputs = portSignature(block.input_ports);
  const outputs = portSignature(block.output_ports);

  const header = (
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
  );

  return (
    <DetailPopover
      actions={actions}
      anchor={anchor}
      header={header}
      interactive={interactive}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      testId="block-detail-popover"
    >
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
    </DetailPopover>
  );
}
