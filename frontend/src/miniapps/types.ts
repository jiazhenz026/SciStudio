/**
 * ADR-054 Phase D — the MiniApp surface's shared shapes.
 *
 * A MiniApp is a panel that declares one data type and carries `panel.py`. It
 * opens as its own centre tab on one block output, and its page talks to a
 * resident Python process through `scistudio.call(...)`.
 */

/** A row of `GET /api/panels/miniapps` (FR-031). */
export interface MiniAppSummary {
  panel_id: string;
  name: string;
  description: string;
  /** The single declared type, verbatim. */
  type: string;
  tier: "project" | "user" | "package" | "core";
  /** Absolute path of the panel directory, for the card's popover. */
  directory: string;
  has_python: boolean;
}

/** A row of `GET /api/panels/miniapps/{panel_id}/sources` (FR-034). */
export interface MiniAppSource {
  workflow_id: string;
  workflow_name: string;
  block_id: string;
  block_name: string;
  port: string;
  type: string;
}

/** The block output a MiniApp runs on (FR-002). */
export interface MiniAppTarget {
  workflow_id: string;
  block_id: string;
  port: string;
}

/**
 * FR-018 — the tab id. One MiniApp on one output is one tab: opening the same
 * panel on the same output again focuses the tab that is already there rather
 * than starting a second process on the same data.
 */
export function miniAppTabId(panelId: string, target: MiniAppTarget): string {
  return `miniapp:${panelId}:${target.workflow_id}:${target.block_id}:${target.port}`;
}
