/*
 * frontend/src/components/Lineage/LineageTab.tsx — ADR-038 §3.8 root view
 * =======================================================================
 *
 * SKELETON ONLY. Function body throws `new Error("TODO: D38-2.4c — ...")`.
 * The D38-2.4c IMPL agent fills the body using ONLY these comments.
 *
 * Purpose
 * -------
 * Top-level container for the Lineage tab. ADR-038 §3.8 mandates a single
 * two-pane surface: RunsList (left) + RunDetail (right). LineageTab owns:
 *   - First-mount fetch of the runs list
 *   - The split-pane sizing (resizable left list / right detail)
 *   - Empty / loading / error states for the whole tab
 *   - Mount points for the two dialogs (MethodsExportDialog + RerunDialog),
 *     which are portal-rendered children but conceptually owned by this tab
 *   - Keyboard shortcuts (see below)
 *
 * Props
 * -----
 * Accepts NO props. State lives in `useAppStore().lineageSlice`. The parent
 * `BottomPanel` mounts this component only when activeTab === "lineage".
 * Mounting/unmounting is cheap because all data lives in the store; the
 * websocket-driven live-running row updates while LineageTab is unmounted
 * are still recorded (slice subscribes globally — see useWebSocket.ts hook).
 *
 * State consumed from store
 * -------------------------
 *   - runs, runsLoading, runsError
 *   - selectedRunId
 *   - methodsDialogRunId, rerunDialogRunId
 *   - fetchRuns, selectRun, closeMethodsDialog, closeRerunDialog
 *
 * Layout markup (vitest will assert on these data-testids and selectors)
 * ----------------------------------------------------------------------
 *
 *   <section
 *     className="flex h-full flex-col"
 *     data-testid="lineage-tab"
 *     role="region"
 *     aria-label="Run lineage"
 *   >
 *     <header className="border-b border-stone-200 px-4 py-3"
 *             data-testid="lineage-tab-header">
 *       <h2 className="text-sm font-semibold text-ink">Run history</h2>
 *       <p className="text-xs text-stone-500">
 *         {runs.length} {runs.length === 1 ? "run" : "runs"} recorded
 *       </p>
 *     </header>
 *
 *     <div className="flex min-h-0 flex-1" data-testid="lineage-tab-body">
 *       <div className="w-[36%] min-w-[260px] border-r border-stone-200"
 *            data-testid="lineage-tab-list-pane">
 *         <RunsList />
 *       </div>
 *       <div className="min-w-0 flex-1" data-testid="lineage-tab-detail-pane">
 *         <RunDetail />
 *       </div>
 *     </div>
 *
 *     {methodsDialogRunId !== null && (
 *       <MethodsExportDialog runId={methodsDialogRunId} onClose={closeMethodsDialog} />
 *     )}
 *     {rerunDialogRunId !== null && (
 *       <RerunDialog runId={rerunDialogRunId} onClose={closeRerunDialog} />
 *     )}
 *   </section>
 *
 *   Pane-split heuristic for v1: fixed 36% / 64%. Resizable handle is a
 *   future polish issue (file under "Lineage polish" backlog). Do NOT add
 *   react-resizable-panels here in v1 — keeps the skeleton small.
 *
 * Copy strings (English, freeze for v1)
 * -------------------------------------
 *   Header heading:               "Run history"
 *   Header subline:               "{N} run(s) recorded"
 *   Empty state (runs.length===0): "No runs yet. Run a workflow to populate this view."
 *   Loading (initial fetch):      "Loading runs…"
 *   Error banner:                 "Could not load runs: {message}. [Retry]"
 *
 * Keyboard shortcuts (LineageTab-scope, only when activeTab === "lineage")
 * ----------------------------------------------------------------------
 *   ArrowDown / ArrowUp  — move selection within RunsList (slice action
 *                          selectNextRun / selectPrevRun — to be added in
 *                          IMPL phase if needed; can be omitted for v1)
 *   Enter on a row       — already handled by RunsList (no global handler)
 *   "m" while a run selected — openMethodsDialog(selectedRunId)
 *   "r" while a run selected — openRerunDialog(selectedRunId)
 *   Esc                  — close any open dialog
 *
 *   The shortcut handler must check `document.activeElement` to avoid
 *   stealing keystrokes while an input is focused (matches AIChat pattern).
 *
 *   IMPL note: useEffect with window.addEventListener("keydown", handler);
 *   cleanup on unmount. Skip handlers when (activeElement.tagName in
 *   ["INPUT", "TEXTAREA"] OR activeElement.isContentEditable).
 *
 * Accessibility
 * -------------
 *   - section role="region" with aria-label="Run lineage" (above)
 *   - RunsList renders a <ul role="listbox">; RunDetail renders standard
 *     headings and live regions for inline state changes
 *   - When the dialog opens, focus moves to the dialog's primary action
 *     button (focus trap handled inside each dialog component)
 *   - Esc closes dialog AND returns focus to the row that opened it
 *     (RunDetail Re-run / Export methods buttons capture activeElement
 *     pre-open into a ref; IMPL detail)
 *
 * Edge cases
 * ----------
 *   1. Empty state — runs.length === 0 AND runsLoading === false: render
 *      the empty-state message centered in the detail pane area; RunsList
 *      still renders its own empty placeholder (separate concern).
 *   2. Loading state (initial) — runsLoading === true AND runs.length === 0:
 *      render a top-banner "Loading runs…" message; both panes show their
 *      own skeletons.
 *   3. Loading state (refresh) — runsLoading === true AND runs.length > 0:
 *      keep panes populated; render a subtle inline spinner in the header
 *      next to "{N} runs recorded".
 *   4. Error state — runsError !== null: render a dismissible banner above
 *      the panes (rose-50 background, rose-700 text) with a Retry button
 *      that calls fetchRuns() again.
 *   5. Stale-detail state — if selectedRunId references a run that was
 *      since deleted server-side (rare; only if the user manually deletes
 *      the lineage.db row), the detail pane shows "Run not found" — that's
 *      RunDetail's concern, NOT this component's.
 *
 * Mount-time fetch policy
 * -----------------------
 *   useEffect(() => { fetchRuns(); }, []);
 *
 *   The empty-deps array is intentional: fetch only on FIRST mount of this
 *   tab in a given page session. Tab switches reuse the cached `runs`.
 *   Project switches invalidate the cache via clearLineage() (called from
 *   projectSlice on setCurrentProject — see lineageSlice top comment).
 *
 * Live-running rows (OQ-3 ADR-038 §8)
 * -----------------------------------
 *   Tentative resolution per ADR §8: show running rows with a live spinner.
 *   LineageTab does NOT poll — it relies on a websocket event
 *   "run_completed" (and "block_done" piggyback if needed) to call
 *   fetchRuns(). Wiring lives in useWebSocket.ts. Skeleton just exposes the
 *   fetch action; the wiring is part of D38-2.4c.
 *
 * Test plan (LineageTab.test.tsx)
 * -------------------------------
 *   1. renders [data-testid=lineage-tab] with the two panes
 *   2. mount fires fetchRuns once
 *   3. empty state renders the message when runs.length === 0 && !loading
 *   4. error banner renders + Retry button calls fetchRuns
 *   5. methodsDialogRunId !== null renders MethodsExportDialog
 *   6. rerunDialogRunId !== null renders RerunDialog
 *   7. Esc keypress closes the open dialog
 */

import type { ReactElement } from "react";

/**
 * D38-2.4b skeleton runtime stance — IMPORTANT
 * --------------------------------------------
 * Codex P1 (PR #937): leaf components in this skeleton all throw
 * `new Error("TODO: D38-2.4c — ...")` to make the IMPL surface explicit.
 * However, `BottomPanel.tsx` mounts THIS component when activeTab ===
 * "lineage", which means a click on the Lineage tab would crash the
 * panel before D38-2.4c lands. That is a functional regression from
 * the prior PlaceholderTab behaviour.
 *
 * Resolution: the ROOT component renders a non-throwing placeholder
 * ("Lineage tab — coming in D38-2.4c"), while the leaf components
 * (RunsList, RunDetail, BlockExecutionCard, MethodsExportDialog,
 * RerunDialog) keep their throw-stub bodies. The IMPL agent (D38-2.4c)
 * replaces this placeholder + the leaf throws in one PR.
 *
 * The full IMPL contract for this component lives above this docstring
 * (props, state, layout markup, copy strings, keyboard, a11y, tests).
 */
export function LineageTab(): ReactElement {
  return (
    <div
      className="flex h-full items-center justify-center"
      data-testid="lineage-tab-placeholder"
      role="region"
      aria-label="Run lineage"
    >
      <p className="text-sm text-stone-500">
        Lineage tab — coming in D38-2.4c (ADR-038 §3.8)
      </p>
    </div>
  );
}
