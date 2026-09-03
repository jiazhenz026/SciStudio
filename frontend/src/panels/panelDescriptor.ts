/**
 * ADR-054 spec 1, T-005 — what the backend tells the host about one panel, and
 * the validation the host applies before it creates a frame.
 *
 * Nothing here is invented by the frontend. The accepted API version, the
 * declared capability, the entry document, the asset base and the read limits
 * are all the backend's answers, carried on the response the caller is already
 * reading. In particular there is no version constant in this file: D-010 puts
 * the one definition in `scistudio.core.panels`, and a frontend constant
 * spelling a version literal would be a defect against SC-001.
 */

import type { PanelFailure } from "./panelFrame";
import { panelFailure } from "./panelFrame";
import type { PanelCapability, PanelReadLimits } from "./panelMessages";
import { isAcceptedApiVersion } from "./panelMessages";
import { isPanelCapability } from "./panelCapability";

/**
 * Everything the host needs to mount one panel. Field names are the wire's, so
 * a caller can hand a backend response object straight in.
 */
export interface PanelDescriptor {
  readonly panel_id: string;
  readonly display_name?: string;
  /** The version this panel's declaration states. */
  readonly api_version: string;
  /** The version the backend accepts — its `PANEL_API_VERSION` (D-010). */
  readonly accepted_api_version: string;
  /** The capability this mount is granted (FR-005). */
  readonly capability: PanelCapability;
  /** Same-origin path of the entry document on the merged asset route. */
  readonly document_url: string;
  /** Same-origin base the panel fetches its own bulk assets from. */
  readonly asset_base_url: string;
  /** The bounds on one windowed read. The host does not invent them. */
  readonly read_limits: PanelReadLimits;
}

/**
 * FR-004 and FR-005, applied before a frame is created: a descriptor that does
 * not name a panel, a capability, an asset base and the read limits cannot be
 * mounted, and a panel whose declared version the backend does not accept is
 * refused rather than framed. Returns `null` when the descriptor is usable.
 */
export function validatePanelDescriptor(descriptor: PanelDescriptor): PanelFailure | null {
  const panelId = typeof descriptor?.panel_id === "string" ? descriptor.panel_id.trim() : "";
  if (panelId === "") {
    return {
      panelId: "(unnamed)",
      reason: "invalid_descriptor",
      message: "a panel descriptor arrived without a panel id",
    };
  }
  if (!isPanelCapability(descriptor.capability)) {
    return panelFailure(
      panelId,
      "invalid_descriptor",
      `declares no capability the host knows: ${JSON.stringify(descriptor.capability)}`,
    );
  }
  if (typeof descriptor.asset_base_url !== "string" || descriptor.asset_base_url === "") {
    return panelFailure(panelId, "invalid_descriptor", "was described without an asset base URL");
  }
  const limits = descriptor.read_limits;
  if (
    typeof limits !== "object" ||
    limits === null ||
    typeof limits.max_rows !== "number" ||
    typeof limits.max_bytes !== "number"
  ) {
    return panelFailure(
      panelId,
      "invalid_descriptor",
      "was described without the read limits the backend owns",
    );
  }
  if (!isAcceptedApiVersion(descriptor.api_version, descriptor.accepted_api_version)) {
    return panelFailure(
      panelId,
      "version_mismatch",
      `declares panel API version ${JSON.stringify(descriptor.api_version)}, which this host ` +
        `does not accept (it accepts ${JSON.stringify(descriptor.accepted_api_version)})`,
    );
  }
  return null;
}
