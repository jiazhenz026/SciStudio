/**
 * Conflict-marker inline action widget (ADR-039 §3.5a).
 *
 * Extracted from `ConflictMarkerDecoration.ts` (#1422). Builds the DOM
 * subtree that hosts the four conflict-action buttons. Loose typing on
 * Monaco params preserves the ADR-036 §3.1 lazy-load boundary.
 */

import type { ConflictAction, ConflictRegion } from "./types";

/** Subset of the Monaco IContentWidget interface we construct. */
export interface ConflictWidget {
  getId: () => string;
  getDomNode: () => HTMLDivElement;
  getPosition: () => {
    position: { lineNumber: number; column: number };
    preference: number[];
  };
}

/**
 * Build a single conflict-action widget for `region`.
 *
 * @param region      - parsed conflict region.
 * @param indexLabel  - human label like "1 of 3".
 * @param monaco      - Monaco namespace (loose typed); used only to read
 *                      `ContentWidgetPositionPreference` enum values.
 * @param onAction    - callback fired when the user clicks a button.
 */
export function buildWidget(
  region: ConflictRegion,
  indexLabel: string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  monaco: any,
  onAction: (action: ConflictAction, region: ConflictRegion) => void,
): ConflictWidget {
  const dom = document.createElement("div");
  dom.className =
    "conflict-action-widget flex gap-2 px-2 py-0.5 text-[11px] " +
    "bg-stone-100 border border-stone-300 rounded shadow-sm";
  dom.dataset.testid = `conflict-action-${region.startLine}`;
  dom.setAttribute("aria-label", `Conflict region ${indexLabel}`);

  const mkBtn = (label: string, type: ConflictAction["type"], testid: string) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.dataset.testid = testid;
    b.className = "rounded border border-stone-400 bg-white px-1.5 py-0.5 " + "hover:bg-stone-50";
    b.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      onAction({ type }, region);
    });
    return b;
  };

  const label = document.createElement("span");
  label.textContent = `Conflict ${indexLabel}`;
  label.className = "mr-2 font-semibold text-stone-600";
  dom.appendChild(label);
  dom.appendChild(
    mkBtn("Accept Current", "accept_current", `conflict-accept-current-${region.startLine}`),
  );
  dom.appendChild(
    mkBtn("Accept Incoming", "accept_incoming", `conflict-accept-incoming-${region.startLine}`),
  );
  dom.appendChild(mkBtn("Accept Both", "accept_both", `conflict-accept-both-${region.startLine}`));
  dom.appendChild(mkBtn("Manual edit", "manual_edit", `conflict-manual-${region.startLine}`));

  return {
    getId: () => `conflict-widget-${region.startLine}`,
    getDomNode: () => dom,
    getPosition: () => ({
      position: { lineNumber: region.startLine, column: 1 },
      preference: [
        // ABOVE — Monaco's enum value for ContentWidgetPositionPreference.ABOVE.
        // The values are stable: ABOVE=1, BELOW=2, EXACT=0. Use the
        // enum if available, else fall back to the numeric literal.
        monaco.editor?.ContentWidgetPositionPreference?.ABOVE ?? 1,
        monaco.editor?.ContentWidgetPositionPreference?.BELOW ?? 2,
      ],
    }),
  };
}
