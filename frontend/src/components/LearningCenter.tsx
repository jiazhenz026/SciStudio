/**
 * ADR-053 Learning Center (#2057) — the catalogue surface (FR-082 … FR-088).
 *
 * This renders what the backend returned and asks the backend to act. It holds
 * no step content and no judging logic (spec §4.1); FR-002 removed the five
 * frontend predicates that used to decide completion by reading the frontend's
 * copy of the workflow, and nothing here replaces them.
 *
 * The layout is a tab per source across the top, that source's tutorials down
 * the left, the selected one in the middle, and its source's progress on the
 * right. Selecting and starting are separate gestures: a tutorial can create a
 * project on disk, so reading what one is before committing to it is worth a
 * column of its own.
 *
 * Reading tutorials sit in their own tab. `learningCenterTabs` builds that
 * split, and the backend decides which tutorials are reading ones by looking
 * at their steps rather than at a declared field — see
 * `TutorialManifest.is_reading_only`.
 *
 * One confirmation in this file names directories rather than describing them,
 * and FR-087's restart confirmation in `TutorialDetail` does the same. That is
 * FR-088's reasoning: the label of an action describes the user's intent while
 * its effect is deleting folders, and the two must not be allowed to diverge
 * silently. "Clear tutorial data" lists every directory from
 * `GET /data/clear-preview` before anything is removed.
 */

import { BookOpen, Loader2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  learningCenterApi,
  type TutorialCatalogueEntry,
  type TutorialCatalogueGroup,
} from "../lib/api/learningCenter";
import { useAppStore } from "../store";
import { learningCenterTabs, READING_TAB_ID, tutorialEntryKey } from "../store/learningCenterSlice";

import { GroupProgress } from "./LearningCenter.parts/GroupProgress";
import { TutorialDetail } from "./LearningCenter.parts/TutorialDetail";
import { TutorialList } from "./LearningCenter.parts/TutorialList";

/** FR-068 — said plainly, on the surface, not buried in a tutorial's first step. */
export const TEMPORARY_PROJECTS_NOTICE =
  "Tutorial projects are temporary. They are deleted when you restart a tutorial or clear " +
  "tutorial data, and they are hidden from your recent projects. Do your own work in your own " +
  "project.";

/** FR-082 — the permanent toolbar entry's label, shared with the toolbar. */
export const LEARNING_CENTER_ENTRY_LABEL = "Learning Center";

/*
 * TODO(#2057): the card-turning surface a reading tutorial is shown in is not
 *   built; a reading tutorial currently runs through the ordinary step view.
 *   Out of scope per the owner's 2026-08-10 decision to add the Reading tab
 *   ahead of the core summary tutorial that will fill it.
 *   Followup: https://github.com/jiazhenz026/SciStudio/issues/2057
 */
const READING_TAB_EMPTY_MESSAGE =
  "Reading tutorials will appear here. They walk through what SciStudio offers and where to " +
  "find it, without asking you to build anything.";

const GROUP_TAB_EMPTY_MESSAGE = "This source ships no hands-on tutorials.";

export function LearningCenter() {
  const open = useAppStore((state) => state.learningCenterOpen);
  const catalogue = useAppStore((state) => state.learningCenterCatalogue);
  const session = useAppStore((state) => state.learningCenterSession);
  const loading = useAppStore((state) => state.learningCenterLoading);
  const error = useAppStore((state) => state.learningCenterError);
  const startConflict = useAppStore((state) => state.learningCenterStartConflict);
  const closeLearningCenter = useAppStore((state) => state.closeLearningCenter);
  const refresh = useAppStore((state) => state.refreshLearningCenter);
  const startTutorial = useAppStore((state) => state.startTutorial);
  const leaveActiveTutorial = useAppStore((state) => state.leaveActiveTutorial);
  const clearTutorialData = useAppStore((state) => state.clearTutorialData);
  const clearStartConflict = useAppStore((state) => state.clearLearningCenterStartConflict);

  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  /* FR-088 — the directories a clear would delete, fetched before confirming. */
  const [clearPreview, setClearPreview] = useState<string[] | null>(null);
  const [clearedDirectories, setClearedDirectories] = useState<string[] | null>(null);

  const tabs = useMemo(() => learningCenterTabs(catalogue), [catalogue]);
  const activeTab = tabs.find((tab) => tab.id === activeTabId) ?? tabs[0] ?? null;

  /*
   * Refetch whenever the panel opens.
   *
   * The spec's edge case: a condition satisfied while the Learning Center was
   * closed is not lost, because state lives on the backend and reopening shows
   * the current step. That only holds if opening actually asks.
   */
  useEffect(() => {
    if (!open) return;
    setClearPreview(null);
    setClearedDirectories(null);
    void refresh();
  }, [open, refresh]);

  /*
   * Land on the running tutorial when there is one.
   *
   * Opening the panel mid-tutorial to look up something else is ordinary, so
   * the selection is seeded rather than pinned — it moves only when the panel
   * has nothing selected yet.
   */
  useEffect(() => {
    if (!open || !session) return;
    setActiveTabId((current) => current ?? `${session.source_kind}:${session.source_id}`);
    setSelectedKey(
      (current) =>
        current ??
        tutorialEntryKey({
          source_kind: session.source_kind,
          source_id: session.source_id,
          id: session.tutorial_id,
        }),
    );
  }, [open, session]);

  /* A tab with nothing selected shows its first tutorial rather than a blank column. */
  useEffect(() => {
    if (!activeTab) return;
    const keys = activeTab.tutorials.map(tutorialEntryKey);
    setSelectedKey((current) => (current && keys.includes(current) ? current : (keys[0] ?? null)));
  }, [activeTab]);

  const selectedEntry = useMemo<TutorialCatalogueEntry | null>(() => {
    if (!selectedKey) return null;
    for (const tab of tabs) {
      const found = tab.tutorials.find((entry) => tutorialEntryKey(entry) === selectedKey);
      if (found) return found;
    }
    return null;
  }, [selectedKey, tabs]);

  /*
   * The ring counts one source. In a source's own tab that is the tab; in the
   * Reading tab, whose tutorials may come from several sources at once, it is
   * the selected tutorial's source — never a sum across them (FR-076).
   */
  const ringGroup = useMemo<TutorialCatalogueGroup | null>(() => {
    if (activeTab?.group) return activeTab.group;
    if (!selectedEntry) return null;
    return (
      tabs.find(
        (tab) =>
          tab.group?.source_kind === selectedEntry.source_kind &&
          tab.group?.source_id === selectedEntry.source_id,
      )?.group ?? null
    );
  }, [activeTab, selectedEntry, tabs]);

  const handleStart = useCallback(
    (entry: TutorialCatalogueEntry, restart: boolean) => {
      if (entry.state === "unavailable") return;
      void startTutorial({
        source_kind: entry.source_kind,
        source_id: entry.source_id,
        tutorial_id: entry.id,
        restart,
      });
    },
    [startTutorial],
  );

  const handleClearRequested = useCallback(async () => {
    setClearedDirectories(null);
    const preview = await learningCenterApi.previewTutorialDataClear();
    setClearPreview(preview.directories);
  }, []);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-6 backdrop-blur-sm"
      data-testid="learning-center"
    >
      <div className="flex h-[min(42rem,88vh)] w-full max-w-5xl flex-col overflow-hidden rounded-[2rem] border border-stone-200 bg-white shadow-panel">
        <header className="flex items-start justify-between gap-4 px-6 pt-4">
          <div className="min-w-0">
            <h2 className="inline-flex items-center gap-2 font-display text-2xl text-ink">
              <BookOpen aria-hidden="true" className="size-5 text-ember" />
              {LEARNING_CENTER_ENTRY_LABEL}
            </h2>
            {/* FR-068 */}
            <p className="mt-1 max-w-2xl text-xs leading-5 text-stone-500">
              {TEMPORARY_PROJECTS_NOTICE}
            </p>
          </div>
          <button
            aria-label="Close Learning Center"
            className="inline-flex size-8 shrink-0 items-center justify-center rounded-full text-stone-400 transition hover:bg-stone-100 hover:text-ink"
            onClick={closeLearningCenter}
            type="button"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        </header>

        {/* FR-084 — one tab per source, core first, with the Reading tab last. */}
        <div className="mt-3 flex gap-1 overflow-x-auto border-b border-stone-200 px-6">
          {tabs.map((tab) => {
            const selected = activeTab?.id === tab.id;
            return (
              <button
                aria-selected={selected}
                className={`-mb-px shrink-0 border-b-2 px-3 py-2 text-sm font-medium transition ${
                  selected
                    ? "border-ember text-ink"
                    : "border-transparent text-stone-500 hover:text-ink"
                }`}
                data-testid={`tutorial-tab-${tab.id}`}
                key={tab.id}
                onClick={() => setActiveTabId(tab.id)}
                role="tab"
                type="button"
              >
                {tab.label}
                {/* A source's own count, never a total across sources (FR-076). */}
                {tab.group ? (
                  <span className="ml-2 text-xs font-normal tabular-nums text-stone-400">
                    {tab.group.completed}/{tab.group.total}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>

        {error ? (
          <p
            className="mx-6 mt-3 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700"
            data-testid="learning-center-error"
          >
            {error}
          </p>
        ) : null}

        {/*
         * The spec's edge case: one tutorial runs at a time. The product says
         * so and offers to leave the running one, rather than refusing.
         */}
        {startConflict ? (
          <div
            className="mx-6 mt-3 rounded-xl border border-ember/40 bg-ember/5 p-3"
            data-testid="learning-center-session-conflict"
          >
            <p className="text-sm leading-6 text-ink">
              One tutorial runs at a time
              {session ? `, and “${session.title}” is open right now.` : "."} Leave it to start this
              one — your place in it is kept.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                className="rounded-full bg-ink px-3 py-1.5 text-xs font-medium text-white transition hover:bg-pine"
                onClick={() => {
                  const pending = startConflict;
                  void (async () => {
                    await leaveActiveTutorial();
                    await startTutorial(pending);
                  })();
                }}
                type="button"
              >
                Leave it and start this one
              </button>
              <button
                className="rounded-full border border-stone-300 px-3 py-1.5 text-xs font-medium text-stone-600 transition hover:border-pine hover:text-pine"
                onClick={clearStartConflict}
                type="button"
              >
                Keep the current tutorial
              </button>
            </div>
          </div>
        ) : null}

        <div className="flex min-h-0 flex-1">
          <div className="w-60 shrink-0 overflow-y-auto border-r border-stone-200">
            {loading && tabs.length === 0 ? (
              <p className="inline-flex items-center gap-2 px-4 py-6 text-sm text-stone-500">
                <Loader2 aria-hidden="true" className="size-4 animate-spin" />
                Loading tutorials…
              </p>
            ) : (
              <TutorialList
                emptyMessage={
                  activeTab?.id === READING_TAB_ID
                    ? READING_TAB_EMPTY_MESSAGE
                    : GROUP_TAB_EMPTY_MESSAGE
                }
                onSelect={(entry) => setSelectedKey(tutorialEntryKey(entry))}
                selectedKey={selectedKey}
                tutorials={activeTab?.tutorials ?? []}
              />
            )}
          </div>

          <div className="min-w-0 flex-1 overflow-y-auto">
            <TutorialDetail entry={selectedEntry} onStart={handleStart} />
          </div>

          <div className="w-60 shrink-0 overflow-y-auto border-l border-stone-200">
            <GroupProgress
              group={ringGroup}
              onLeave={() => void leaveActiveTutorial()}
              session={session}
            />
          </div>
        </div>

        <footer className="border-t border-stone-200 px-6 py-3">
          {/*
           * Discovery problems are shown rather than swallowed: one malformed
           * manifest never empties a group, but the user should be able to see
           * that something in a source did not load.
           */}
          {catalogue && catalogue.diagnostics.length > 0 ? (
            <ul className="mb-3 flex flex-col gap-1" data-testid="learning-center-diagnostics">
              {catalogue.diagnostics.map((line) => (
                <li className="text-xs leading-5 text-stone-500" key={line}>
                  {line}
                </li>
              ))}
            </ul>
          ) : null}

          {/* FR-088 */}
          {clearPreview === null && clearedDirectories === null ? (
            <button
              className="rounded-full border border-stone-300 px-3 py-1.5 text-xs font-medium text-stone-600 transition hover:border-red-400 hover:text-red-600"
              onClick={() => void handleClearRequested()}
              type="button"
            >
              Clear tutorial data
            </button>
          ) : null}

          {clearPreview !== null ? (
            <div data-testid="learning-center-clear-confirm">
              <p className="text-sm leading-6 text-ink">
                Clearing tutorial data resets your tutorial progress and deletes these directories:
              </p>
              {clearPreview.length > 0 ? (
                <ul className="mt-2 flex flex-col gap-1">
                  {clearPreview.map((directory) => (
                    <li
                      className="break-all rounded-lg bg-stone-50 px-2 py-1 font-mono text-xs text-stone-600"
                      key={directory}
                    >
                      {directory}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-xs text-stone-500">
                  There is nothing on disk to delete right now.
                </p>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  className="rounded-full bg-red-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-red-700"
                  onClick={() => {
                    void (async () => {
                      const deleted = await clearTutorialData();
                      setClearPreview(null);
                      setClearedDirectories(deleted);
                    })();
                  }}
                  type="button"
                >
                  Delete them and clear progress
                </button>
                <button
                  className="rounded-full border border-stone-300 px-3 py-1.5 text-xs font-medium text-stone-600 transition hover:border-pine hover:text-pine"
                  onClick={() => setClearPreview(null)}
                  type="button"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}

          {clearedDirectories !== null ? (
            <p className="text-sm leading-6 text-stone-600" data-testid="learning-center-cleared">
              {clearedDirectories.length > 0
                ? `Tutorial progress is cleared and ${clearedDirectories.length} director${
                    clearedDirectories.length === 1 ? "y was" : "ies were"
                  } deleted.`
                : "Tutorial progress is cleared."}
            </p>
          ) : null}
        </footer>
      </div>
    </div>
  );
}
