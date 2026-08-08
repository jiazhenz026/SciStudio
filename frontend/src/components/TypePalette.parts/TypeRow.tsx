// A single Data types tab list row — a framed colour swatch, the type name, and
// the immediate parent set in grey on the right.
//
// Specs: docs/specs/adr-053-personal-tool-library.md §9.2 FR-041 (solid fill
//        plus ring, resolved through the FR-051 precedence so a type reads
//        identically here and on a canvas port), §10.1 (the cell shape is
//        per-surface; the hover contract is not).
//
// Why a row rather than the shared `PaletteTile`: a 72×72 swatch under a
// centred caption is the Blocks tab's "thing you drag onto the canvas"
// vocabulary. Types are not draggable — the tile this replaced never passed
// `draggable`, so the grid was advertising an affordance that did nothing. A
// list reads as a reference index, which is what the tab is, and the row's
// horizontal space carries the parent the grid had nowhere to put.
//
// The fill/ring pair and the `border = ring ?? fill` rule are still lifted from
// the canvas port handles (`nodes/BlockNode.parts/PortHandles.tsx`) rather than
// restated, so a type whose ring resolves to `undefined` renders solid in both
// places and one that has a ring gets the same contrasting ring. Only the ring
// width shrinks, because the swatch does.
//
// The hover contract — `onEnter(rect)` measured from the row's own bounding
// rectangle, `onLeave`, and click/keyboard `onActivate` — is deliberately
// identical to `PaletteTile`'s. Both tabs feed one popover (FR-046), and it has
// to anchor and dwell the same way on each.

import { useRef } from "react";

import type { TypeSummary } from "../../types/api";

/**
 * Inner ring, drawn as an inset shadow so it does not affect layout.
 *
 * `PaletteTile` uses 3px inside a 72px swatch; 2px inside a 16px one keeps the
 * ring legible without swallowing the fill it is supposed to frame.
 */
const RING_WIDTH_PX = 2;

export interface TypeRowProps {
  type: TypeSummary;
  /** Fill, already resolved through the FR-051 precedence. */
  fill: string;
  /** Ring, or `undefined` for a type that renders solid. */
  ring?: string;
  /** Immediate parent, or `null` when it carries no information (`rowParent`). */
  parent: string | null;
  /**
   * FR-068 — open this type's source on a double click.
   *
   * The palette supplies one for every tier; whether the tab that opens is
   * editable or read-only is its decision, not this row's. Optional, and
   * `undefined` rather than a no-op callback, so a row that genuinely has
   * nothing to open does not advertise in its tooltip that it does.
   */
  onOpenSource?: () => void;
  onEnter: (type: TypeSummary, rect: DOMRect) => void;
  onLeave: () => void;
}

export function TypeRow({
  type,
  fill,
  ring,
  parent,
  onOpenSource,
  onEnter,
  onLeave,
}: TypeRowProps) {
  // Click / keyboard activation opens the same detail card hovering does, so
  // the popover — and the promotion action inside it (E5) — is reachable
  // without a pointer. The wrapper carries the ref because activation has no
  // event to measure from, and the card must anchor to the row either way.
  const rowRef = useRef<HTMLDivElement | null>(null);

  return (
    <div
      className="rounded-lg border border-transparent transition hover:border-stone-200 hover:bg-white/70"
      data-testid="palette-type-row"
      // FR-068 lives on the wrapper, not the button: a double click delivers
      // two `click`s first, and putting it here keeps the popover's activation
      // and the open in one place each rather than racing inside one handler.
      onDoubleClick={onOpenSource}
      onMouseEnter={(event) => onEnter(type, event.currentTarget.getBoundingClientRect())}
      onMouseLeave={onLeave}
      ref={rowRef}
    >
      <button
        className="flex w-full items-center gap-2.5 px-2 py-1.5 text-left"
        onClick={() => {
          const rect = rowRef.current?.getBoundingClientRect();
          if (rect) {
            onEnter(type, rect);
          }
        }}
        title={onOpenSource ? `${type.name} — double-click to open its source` : type.name}
        type="button"
      >
        <span
          aria-hidden="true"
          className="h-4 w-4 shrink-0 rounded-[4px] border"
          style={{
            backgroundColor: fill,
            borderColor: ring ?? fill,
            ...(ring ? { boxShadow: `inset 0 0 0 ${RING_WIDTH_PX}px ${ring}` } : null),
          }}
        />
        <span
          className="min-w-0 flex-1 truncate font-display text-[12px] font-medium leading-tight text-ink"
          data-testid="palette-type-row-name"
        >
          {type.name}
        </span>
        {parent ? (
          <span
            className="max-w-[45%] shrink-0 truncate text-[11px] leading-tight text-stone-400"
            data-testid="palette-type-row-parent"
          >
            {parent}
          </span>
        ) : null}
      </button>
    </div>
  );
}
