// ADR-054 T-010, FR-028 and FR-029 — reverting a panel edit.
//
// FR-028 puts an obligation on the *host*: when an edited panel fails to load,
// it must report the failure explicitly **and offer to revert**. The reporting
// half is `PanelErrorSurface`; this module is the other half, and it lives here
// rather than beside that component because the answer to "is there anything to
// revert?" is registry truth — it comes from the panel catalogue — and nothing
// under `frontend/src/panels/` reads the store (see `panels/index.ts`).
//
// Reverting is FR-029: delete the shadowing copy, and whatever it shadowed
// resolves again. A panel that shadows nothing is not offered the control at
// all, because deleting the only copy of a panel is a different request nobody
// made — the route refuses it, and an affordance that only ever produces a
// refusal is worse than no affordance.

import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api } from "../lib/api";
import type { PanelRevertOffer } from "../panels";
import type { PanelOverrideRevertResponse, PanelSpecSummary } from "../types/api";

import { useAppStore } from "./index";
import { invalidatePanelCatalog, loadPanelCatalog } from "./usePanelCatalog";

/**
 * Can this panel's edit be reverted, and to which tier?
 *
 * Both halves of the route's own precondition, checked here so the control is
 * offered exactly when it will work: the panel must resolve from a tier that
 * holds an override (project or user library), and it must shadow something.
 */
export function panelRevertTarget(panel: PanelSpecSummary | null | undefined): string | null {
  if (!panel || panel.shadows == null) return null;
  if (panel.tier !== "project" && panel.tier !== "user") return null;
  return panel.shadows;
}

/**
 * Delete a panel's shadowing copy, then reload every mounted instance of it.
 *
 * `notePanelDocumentChanged` is the same counter `usePanelReloadToken` reads
 * and the `file.changed` dispatcher writes — one hot-reload path, triggered
 * from a second place. It is triggered here because a revert *deletes* the
 * directory the watcher was watching, which is the one change a
 * path-keyed watcher is least able to attribute to a panel.
 */
export async function revertPanelOverride(panelId: string): Promise<PanelOverrideRevertResponse> {
  const response = await api.revertPanelOverride(panelId);
  useAppStore.getState().notePanelDocumentChanged(panelId);
  invalidatePanelCatalog();
  return response;
}

/**
 * The FR-028 revert offer for one panel, or `undefined` when there is nothing
 * to revert. Pass it straight to `PanelHost`'s (or `PanelErrorSurface`'s)
 * `revert` prop.
 *
 * The catalogue load is requested rather than assumed: this hook is mounted by
 * a *failing* panel, and the surface that failed may be the first thing the
 * person opened. `loadPanelCatalog` is shared and cached, so a session with the
 * Panels tab already open pays nothing.
 */
export function usePanelRevertOffer(
  panelId: string | null | undefined,
): PanelRevertOffer | undefined {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panel = useAppStore((state) =>
    panelId ? (state.panels.find((entry) => entry.panel_id === panelId) ?? null) : null,
  );

  useEffect(() => {
    if (panelId) void loadPanelCatalog();
  }, [panelId]);

  const restoresTier = panelRevertTarget(panel);

  const onRevert = useCallback(() => {
    if (!panelId) return;
    setPending(true);
    setError(null);
    void revertPanelOverride(panelId)
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : String(err));
      })
      .finally(() => setPending(false));
  }, [panelId]);

  return useMemo(
    () => (restoresTier ? { restoresTier, onRevert, pending, error } : undefined),
    [restoresTier, onRevert, pending, error],
  );
}
