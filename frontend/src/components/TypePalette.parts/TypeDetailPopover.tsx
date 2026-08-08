// Type hover detail — the shared `DetailPopover` card filled with a type's
// colour swatch + name, parent chain, description, per-direction extensions,
// and origin tier.
//
// Specs:
//   docs/specs/adr-053-personal-tool-library.md §9.2 (FR-042 rows, FR-043
//     parent chain), §7.2 (FR-055 separate directions, FR-056 explicit
//     no-formats row), §9.3 (FR-044 – FR-046: one popover implementation
//     serves blocks and types).
//   docs/specs/frontend-block-palette.md §6.1, §11.
//
// The card shell, its interactivity, and the `actions` slot are B3's shared
// `palette/DetailPopover`; this file supplies content only, exactly as
// `BlockDetailPopover` does for the Blocks tab. That is how FR-046 is
// satisfied without either surface knowing about the other.

import type { ReactNode } from "react";

import { DetailPopover } from "../palette/DetailPopover";
import type { PopoverAnchor } from "../palette/hoverPopover";
import type { TypeHierarchyEntry, TypeSummary } from "../../types/api";

import { extensionRows, NO_FORMATS_TEXT, originLabel, parentRow } from "./typeModel";

export interface TypeDetailPopoverProps {
  type: TypeSummary;
  anchor: PopoverAnchor;
  /** Swatch fill, already resolved through the FR-051 precedence. */
  fill: string;
  /** Swatch ring, or `undefined` for a type that renders solid. */
  ring?: string;
  /** The listing viewed as a `name → base_type` map, for FR-043. */
  hierarchy: readonly TypeHierarchyEntry[];
  /**
   * FR-044: accept pointer events and keep the card open while the pointer is
   * inside it. Supplied together with the handlers below by spreading
   * `useHoverPopover().popoverProps`.
   */
  interactive?: boolean;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  /**
   * Action row rendered last, under a hairline
   * (`data-testid="palette-popover-actions"`).
   *
   * This is entry point E5 (ADR-053 §6.2): **"Promote to My Library" mounts
   * here**, mirroring where `BlockDetailPopover` leaves the same slot. The
   * palette owns the action and passes it down, so this stays a presentation
   * component and one popover implementation still serves both surfaces
   * (FR-046).
   */
  actions?: ReactNode;
}

/** One `Label  value` row. */
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-2">
      <span className="w-16 shrink-0 text-stone-400">{label}</span>
      <span className="min-w-0 flex-1 break-words text-stone-600">{children}</span>
    </div>
  );
}

export function TypeDetailPopover({
  type,
  anchor,
  fill,
  ring,
  hierarchy,
  interactive,
  onMouseEnter,
  onMouseLeave,
  actions,
}: TypeDetailPopoverProps) {
  const parent = parentRow(type, hierarchy);
  const extensions = extensionRows(type);

  const header = (
    <div className="flex items-center gap-2">
      <span
        aria-hidden="true"
        className="h-6 w-6 shrink-0 rounded-md border"
        data-testid="type-detail-swatch"
        style={{
          backgroundColor: fill,
          borderColor: ring ?? fill,
          ...(ring ? { boxShadow: `inset 0 0 0 2px ${ring}` } : null),
        }}
      />
      <span className="font-display text-sm font-semibold text-ink">{type.name}</span>
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
      testId="type-detail-popover"
    >
      {type.description ? (
        <p className="mt-2 text-xs leading-snug text-stone-600">{type.description}</p>
      ) : null}

      <div className="mt-2 space-y-0.5 border-t border-stone-100 pt-2 text-[11px]">
        {parent ? (
          // FR-043 — the chain position, not only the immediate parent. The
          // core base is appended only when it differs from the parent, so
          // `Array` never renders as `Array (Array)`.
          <Row label="Parent">
            <span data-testid="type-detail-parent">
              {parent.coreBase ? `${parent.parent} (${parent.coreBase})` : parent.parent}
            </span>
          </Row>
        ) : null}

        {extensions ? (
          extensions.map((row) => (
            <Row key={row.label} label={row.label}>
              <span className="font-mono" data-testid={`type-detail-${row.label.toLowerCase()}`}>
                {/* FR-055 — an empty direction renders as an em dash rather
                    than disappearing, so a save-only type reads as save-only
                    instead of as a type with one extension list. */}
                {row.extensions ? row.extensions.join(" ") : "—"}
              </span>
            </Row>
          ))
        ) : (
          // FR-056 — absence of IO support is information, stated outright.
          <p className="text-stone-500" data-testid="type-detail-no-formats">
            {NO_FORMATS_TEXT}
          </p>
        )}

        <Row label="Origin">
          <span data-testid="type-detail-origin">{originLabel(type.origin)}</span>
        </Row>
      </div>
    </DetailPopover>
  );
}
