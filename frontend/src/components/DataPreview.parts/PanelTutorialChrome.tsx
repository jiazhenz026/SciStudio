/**
 * ADR-054 spec 1, D-019 — the tutorial surface a sandboxed frame cannot carry.
 *
 * A panel runs in a frame granted `allow-scripts` and nothing else, so it sits
 * at an opaque origin: it can reach neither the application's DOM nor its store.
 * Two things the shipped `what-is-a-type` tutorial depends on used to live on
 * components that are inside that frame now, and neither can cross the boundary
 * — a `querySelector` in the parent document cannot see into the frame, and a
 * ring drawn around something inside it has no box to measure.
 *
 * So the host keeps them, on its own markup, immediately around the frame:
 *
 *   - `preview_item` used to sit on every card in the collection viewer, keyed
 *     by index. The finest unit a ring can address now is the surface showing
 *     the collection, so the outer box carries the target, keyed on the first
 *     item the envelope declares. Every shipped step names index 0; a step
 *     naming another index resolves to nothing and the card is centred, which
 *     is the same graceful outcome as any target not yet on screen.
 *   - `plot_export_button` used to sit on the plot viewer's Save button, which
 *     is inside the plot document. The inner box carries it when the target is
 *     a plot artifact.
 *
 * The two are separate elements because one element carries one target, and the
 * two are nested rather than sibling because both point at the same panel: the
 * inner box is the frame's own footprint either way.
 *
 * **This is not the kind-to-panel mapping SC-010 forbids.** Nothing here chooses
 * a panel or influences what is mounted; the attributes are read off what the
 * *envelope* declares and would be identical whichever panel the backend picked.
 */

import type { ReactNode } from "react";

import type { PreviewEnvelope } from "../../types/api";

/** The resource id prefix a collection item carries, mirrored by its panel. */
export const COLLECTION_ITEM_PREFIX = "item:";

export interface PanelTutorialChromeProps {
  /** The envelope on screen, or `null` before one has arrived. */
  envelope: PreviewEnvelope | null;
  children?: ReactNode;
}

/** Which tutorial targets this envelope's chrome should carry. */
export function tutorialTargetsFor(envelope: PreviewEnvelope | null): {
  itemKey: string | null;
  isPlot: boolean;
} {
  if (!envelope) return { itemKey: null, isPlot: false };
  const resources = Array.isArray(envelope.resources) ? envelope.resources : [];
  const firstItem = resources.find((resource) =>
    resource.resource_id.startsWith(COLLECTION_ITEM_PREFIX),
  );
  const index = firstItem?.params?.index;
  return {
    itemKey: firstItem ? String(typeof index === "number" ? index : 0) : null,
    isPlot: envelope.target?.kind === "plot_artifact",
  };
}

export function PanelTutorialChrome({ envelope, children }: PanelTutorialChromeProps) {
  const { itemKey, isPlot } = tutorialTargetsFor(envelope);
  return (
    <div
      data-testid="preview-host-panel"
      className="h-full w-full"
      {...(itemKey !== null
        ? { "data-tutorial-target": "preview_item", "data-tutorial-target-key": itemKey }
        : {})}
    >
      <div
        className="h-full w-full"
        {...(isPlot ? { "data-tutorial-target": "plot_export_button" } : {})}
      >
        {children}
      </div>
    </div>
  );
}
