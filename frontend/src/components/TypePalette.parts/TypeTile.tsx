// A single Data types tab grid cell — the shared `PaletteTile` dressed in the
// canvas port's colour language.
//
// Specs: docs/specs/adr-053-personal-tool-library.md §9.2 FR-041 (solid fill
//        plus ring, resolved through the FR-051 precedence so a type reads
//        identically here and on a canvas port), §10.1 (one shared tile).
//
// The fill/ring pair and the `border = ring ?? fill` rule are lifted verbatim
// from the canvas port handles (`nodes/BlockNode.parts/PortHandles.tsx`)
// rather than restated: a type whose ring resolves to `undefined` renders
// solid with a matching border in both places, and one that has a ring gets
// the same contrasting ring in both. No new colour table is introduced.

import { useRef } from "react";

import { PaletteTile } from "../palette/PaletteTile";
import type { TypeSummary } from "../../types/api";

export interface TypeTileProps {
  type: TypeSummary;
  /** Fill, already resolved through the FR-051 precedence. */
  fill: string;
  /** Ring, or `undefined` for a type that renders solid. */
  ring?: string;
  onEnter: (type: TypeSummary, rect: DOMRect) => void;
  onLeave: () => void;
}

export function TypeTile({ type, fill, ring, onEnter, onLeave }: TypeTileProps) {
  // Click / keyboard activation opens the same detail card hovering does, so
  // the popover — and the promotion action inside it (E5) — is reachable
  // without a pointer. The wrapper carries the ref because activation has no
  // event to measure from, and the card must anchor to the tile either way.
  const cellRef = useRef<HTMLDivElement | null>(null);

  return (
    <div ref={cellRef}>
      <PaletteTile
        label={type.name}
        onActivate={() => {
          const rect = cellRef.current?.getBoundingClientRect();
          if (rect) {
            onEnter(type, rect);
          }
        }}
        onEnter={(rect) => onEnter(type, rect)}
        onLeave={onLeave}
        swatch={{ background: fill, border: ring ?? fill, ring }}
        testId="palette-type-tile"
      />
    </div>
  );
}
