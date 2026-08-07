// The one hover-detail popover card — an anchored, fixed-position shell with a
// header row, a body, and an action row.
//
// Spec: docs/specs/adr-053-personal-tool-library.md
//   §9.3 FR-044 (interactive: `pointer-events-none` is dropped and the card
//   keeps itself open while the pointer is inside it), FR-046 (one popover
//   implementation serves blocks and types), §10.1 (shared popover).
//
// The card is a shell, not a content component. `BlockDetailPopover` composes
// it with a block's description and typed port signature; the Data types tab
// composes it with a type's parent chain and supported extensions. That is how
// FR-046 is satisfied without either surface knowing about the other.

import type { ReactNode } from "react";

import type { PopoverAnchor } from "./hoverPopover";

export interface DetailPopoverProps {
  anchor: PopoverAnchor;
  /** Header row — typically a colour swatch plus the item's name. */
  header: ReactNode;
  /** Body rows. */
  children?: ReactNode;
  /**
   * Action row, rendered last above a hairline rule.
   *
   * This is the E5 promotion slot (spec §6.2): "Promote to My Library" mounts
   * here and is the reason FR-044 exists at all — before it, nothing inside
   * this card could be clicked.
   */
  actions?: ReactNode;
  /**
   * Accept pointer events (FR-044).
   *
   * Off by default, which preserves the display-only, `pointer-events-none`
   * canvas-node popover documented in `frontend-block-palette` spec §10. A
   * palette surface turns it on by spreading `useHoverPopover().popoverProps`,
   * which supplies this flag together with the handlers that keep the card
   * open — the two must arrive together, because a card that swallows pointer
   * events without maintaining its own hover state closes under the cursor.
   */
  interactive?: boolean;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  testId?: string;
}

export function DetailPopover({
  anchor,
  header,
  children,
  actions,
  interactive,
  onMouseEnter,
  onMouseLeave,
  testId,
}: DetailPopoverProps) {
  return (
    <div
      className={`fixed z-50 w-64 rounded-xl border border-stone-200 bg-white p-3 shadow-panel${
        interactive ? "" : " pointer-events-none"
      }`}
      data-testid={testId}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={{ left: anchor.left, top: anchor.top }}
    >
      {header}
      {children}
      {actions ? (
        <div className="mt-2 border-t border-stone-100 pt-2" data-testid="palette-popover-actions">
          {actions}
        </div>
      ) : null}
    </div>
  );
}
