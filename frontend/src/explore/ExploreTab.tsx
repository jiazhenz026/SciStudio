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

import { useCallback, useEffect, useRef, useState } from "react";

import { lineageApi } from "../lib/api/lineage";
import { useAppStore } from "../store";
import type {
  ExploreSessionState,
  ExploreTab as ExploreTabState,
  InteractivePrompt,
} from "../store/types";

import {
  PauseEmissionProvider,
  PausePanel,
  isPackagedAskPrompt,
  usePausePrompt,
} from "./PanelSlots";
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
  /*
   * FR-024 — a pause tab with no session has no notebook to restore.
   *
   * The tab an interactive prompt opens is keyed on the paused block, not on a
   * notebook: there is no session until the person escalates to one (FR-026),
   * and asking the backend to reopen a notebook at that synthetic key would
   * put the tab into `failed` for a pause that is working perfectly.
   */
  const needsRestore = tab.sessionId === null && tab.mode !== "pause";

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
 * FR-026, FR-027 — open a notebook over the paused run's inputs.
 *
 * A session open like any other: `source: "paused_run"` binds a session to the
 * inputs the block received, and **nothing is sent to the engine**, so the
 * paused block goes on waiting for its decision exactly as it was. The tab the
 * session lands in carries the same `pauseNodeId`, so confirm and cancel stay
 * on the toolbar over the notebook.
 *
 * The run id is the one thing the prompt does not carry. The engine's
 * `interactive_prompt` event names the workflow, the block and the panel but no
 * run, so the newest run of the prompt's own workflow is read back — the run
 * that is paused is by construction the one that is running. Recorded as
 * `F-A3-003` in the assembly follow-up register.
 *
 * TODO(#2253): `interactive_prompt` carries no `run_id`, so the escalation
 *   resolves it from the run list instead of being told it.
 *   Out of scope per the ADR-054 assembly dispatch (no agent may edit
 *   `src/scistudio/**`).
 *   Followup: docs/planning/adr-054-assembly-followups.md, `### S4-A3`, F-A3-003.
 */
export async function openPausedRunNotebook(
  tab: ExploreTabState,
  prompt: InteractivePrompt,
): Promise<void> {
  const carried = prompt.data?.run_id;
  let runId = typeof carried === "string" && carried !== "" ? carried : null;
  if (!runId) {
    const listed = await lineageApi.lineage.getRuns({
      workflowId: prompt.workflowId,
      limit: 1,
    });
    runId = listed.runs[0]?.run_id ?? null;
  }
  if (!runId) {
    throw new Error(
      "This prompt named no run, and no run of its workflow was recorded, so there is nothing " +
        "to open a notebook over.",
    );
  }
  const store = useAppStore.getState();
  const opened = await store.openExploreTab(
    { source: "paused_run", block_id: prompt.blockId, run_id: runId },
    { mode: "pause", pauseNodeId: prompt.blockId, displayName: tab.displayName },
  );
  if (!opened) return;
  // FR-026 — the notebook pane appears; the pause is untouched.
  useAppStore.getState().setExploreNotebookVisible(opened.id, true);
  if (opened.id !== tab.id) useAppStore.getState().closeTab(tab.id);
}

/**
 * The centre column while an Explore tab is active.
 *
 * The panel host must hold more than one panel at once (FR-007), so it is a
 * grid rather than a stack: one column on a narrow centre, two from `md` up,
 * which is the width at which two panels are worth comparing rather than two
 * slivers.
 *
 * In pause mode the centre is one thing instead: the paused block's panel,
 * with no variable strip over it and no notebook beside it until the person
 * asks for one (FR-024, FR-026).
 */
export function ExploreTab({ tab }: ExploreTabProps) {
  const session = useExploreSession(tab);
  const setExploreNotebookVisible = useAppStore((state) => state.setExploreNotebookVisible);
  const [graphVisible, setGraphVisible] = useState(false);
  const [escalation, setEscalation] = useState<string | null>(null);
  const prompt = usePausePrompt(tab);
  const paused = tab.mode === "pause";

  const onToggleNotebook = useCallback(() => {
    // FR-026 — in a pause tab the control does not reveal a pane that is not
    // there; it opens a session over the paused run's inputs, and the pane
    // follows from that.
    if (paused && !tab.notebookVisible) {
      if (!prompt) {
        setEscalation("This block is no longer waiting, so there is no run to open.");
        return;
      }
      setEscalation(null);
      void openPausedRunNotebook(tab, prompt).catch((error: unknown) => {
        setEscalation(error instanceof Error ? error.message : String(error));
      });
      return;
    }
    setExploreNotebookVisible(tab.id, !tab.notebookVisible);
  }, [paused, prompt, setExploreNotebookVisible, tab]);

  const onToggleGraph = useCallback(() => setGraphVisible((visible) => !visible), []);

  /*
   * FR-027 — a packaged block set to `ask` opens its notebook in the same tab.
   *
   * Its panel *is* the Explore tab (`core.explore.session` names no document),
   * so there is no frame to mount and no emission to wait for: the decision it
   * returns is a notebook commit, and the person needs the notebook to choose
   * one. The escalation FR-026 offers is therefore taken on its behalf, once.
   */
  const escalated = useRef(false);
  useEffect(() => {
    if (!paused || !prompt || tab.sessionId !== null) return;
    if (!isPackagedAskPrompt(prompt) || escalated.current) return;
    escalated.current = true;
    void openPausedRunNotebook(tab, prompt).catch((error: unknown) => {
      setEscalation(error instanceof Error ? error.message : String(error));
    });
  }, [paused, prompt, tab]);

  return (
    <PauseEmissionProvider>
      <div className="flex h-full min-h-0 flex-col bg-stone-50/60" data-testid="explore-tab">
        <SessionToolbar
          tab={tab}
          session={session}
          onToggleNotebook={onToggleNotebook}
          graphVisible={graphVisible}
          onToggleGraph={onToggleGraph}
        />

        {/* FR-024 — a pause tab has no variable strip: it is not a session's
            namespace that is on screen, it is one block's decision. */}
        {paused ? null : (
          <div className="px-3 pt-2">
            <VariableStripRegion tab={tab} session={session} />
          </div>
        )}

        {escalation ? (
          <p
            className="mx-3 mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-800"
            data-testid="explore-pause-escalation-error"
          >
            {escalation}
          </p>
        ) : null}

        <div className="min-h-0 flex-1 overflow-auto p-3 scrollbar-thin">
          {paused ? (
            <PausePanel tab={tab} />
          ) : graphVisible ? (
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
    </PauseEmissionProvider>
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
