/**
 * ADR-054 spec 4 (T-002) — the Explore tab's layout (FR-005 to FR-007).
 *
 * The tab occupies two of the workspace's columns, which is why this module
 * exports two components rather than one:
 *
 *   - `ExploreTab` is the **centre**: the session toolbar, the variable strip
 *     under it, and the panel host below that — or the dependency graph, which
 *     is the same area showing the secondary view.
 *   - `ExploreNotebookPane` is the **right column**, replacing the data
 *     preview while the tab is active (FR-005).
 *
 * Splitting them is what makes FR-006 fall out rather than be arranged for:
 * the right pane is a sibling `ResizablePanel` and collapses exactly as the
 * preview does today, and the centre and the toolbar, being in a different
 * column, are untouched by that. The left pane and the bottom panel are not
 * mentioned here at all, and that is ADR-054 §4.4's reason for a tab over a
 * separate application: the palette, the tree, and the block cards stay where
 * they were while a person explores.
 *
 * FR-007 — the panel host is a two-column grid, so two panels sit side by side
 * and can be compared. The slots are filled by S4-A3's `PanelSlotRegion`;
 * the arrangement is here.
 *
 * Each region is a placeholder in `regions/ExploreRegions.tsx` with the props
 * its real component takes. An owner replaces a body there; nobody has to come
 * back into this file to restructure the layout.
 */

import { useCallback, useEffect, useState } from "react";

import { useAppStore } from "../store";
import type { ExploreSessionState, ExploreTab as ExploreTabState } from "../store/types";

import {
  GraphViewRegion,
  NotebookRegion,
  PanelSlotRegion,
  VariableStripRegion,
} from "./regions/ExploreRegions";
import { SessionToolbar } from "./SessionToolbar";

/**
 * Read the tab's session out of the store and, when the tab was rehydrated,
 * ask for it back.
 *
 * FR-001's "re-fetch its session state on restore" lives here rather than in
 * the store because it is a mount concern: a persisted tab is restored by
 * zustand before anything is on screen, and the request that reopens its
 * notebook should be the shell asking for what it is about to draw.
 */
function useExploreSession(tab: ExploreTabState): ExploreSessionState | undefined {
  const session = useAppStore((state) => state.sessions[tab.notebookPath]);
  const restoreExploreTab = useAppStore((state) => state.restoreExploreTab);
  const needsRestore = tab.sessionId === null;

  useEffect(() => {
    if (!needsRestore) return;
    void restoreExploreTab(tab.notebookPath);
  }, [needsRestore, restoreExploreTab, tab.notebookPath]);

  return session;
}

export interface ExploreTabProps {
  tab: ExploreTabState;
}

/**
 * The centre column while an Explore tab is active.
 *
 * The panel host must hold more than one panel at once (FR-007), so it is a
 * grid rather than a stack: one column on a narrow centre, two from `md` up,
 * which is the width at which two panels are worth comparing rather than two
 * slivers.
 */
export function ExploreTab({ tab }: ExploreTabProps) {
  const session = useExploreSession(tab);
  const setExploreNotebookVisible = useAppStore((state) => state.setExploreNotebookVisible);
  const [graphVisible, setGraphVisible] = useState(false);

  const onToggleNotebook = useCallback(() => {
    setExploreNotebookVisible(tab.id, !tab.notebookVisible);
  }, [setExploreNotebookVisible, tab.id, tab.notebookVisible]);

  const onToggleGraph = useCallback(() => setGraphVisible((visible) => !visible), []);

  return (
    <div className="flex h-full min-h-0 flex-col bg-stone-50/60" data-testid="explore-tab">
      <SessionToolbar
        tab={tab}
        session={session}
        onToggleNotebook={onToggleNotebook}
        graphVisible={graphVisible}
        onToggleGraph={onToggleGraph}
      />

      <div className="px-3 pt-2">
        <VariableStripRegion tab={tab} session={session} />
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-3 scrollbar-thin">
        {graphVisible ? (
          <GraphViewRegion tab={tab} session={session} />
        ) : (
          <div
            className="grid h-full min-h-0 grid-cols-1 gap-3 md:grid-cols-2"
            data-testid="explore-panel-host"
          >
            {(session?.panels ?? []).map((slot) => (
              <PanelSlotRegion key={slot.panelId} tab={tab} session={session} slot={slot} />
            ))}
            {(session?.panels.length ?? 0) === 0 ? (
              <p
                className="col-span-full self-start text-xs text-stone-400"
                data-testid="explore-panel-host-empty"
              >
                {session?.shellState === "failed"
                  ? (session.error ?? "This session could not be opened.")
                  : "Open a variable from the strip to mount a panel here."}
              </p>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * The right column while an Explore tab is active (FR-005).
 *
 * Returns `null` when the tab hides the notebook — a pause tab before the
 * person asks for one (FR-024, FR-026), or a session tab whose pane the person
 * collapsed from the toolbar. `ProjectWorkspace` renders this in place of the
 * data preview, so a `null` here is a right column with nothing in it, which
 * is the same thing a collapsed preview is today.
 */
export function ExploreNotebookPane({ tab }: ExploreTabProps) {
  const session = useAppStore((state) => state.sessions[tab.notebookPath]);
  if (!tab.notebookVisible) return null;
  return (
    <div
      className="h-full min-h-0 overflow-auto p-3 scrollbar-thin"
      data-testid="explore-notebook-pane"
    >
      <NotebookRegion tab={tab} session={session} />
    </div>
  );
}
