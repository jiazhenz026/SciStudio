/**
 * ADR-053 Learning Center (#2057) — the catalogue surface (FR-082 … FR-088).
 *
 * This renders what the backend returned and asks the backend to act. It holds
 * no step content and no judging logic (spec §4.1); FR-002 removed the five
 * frontend predicates that used to decide completion by reading the frontend's
 * copy of the workflow, and nothing here replaces them.
 *
 * Two confirmations in this file name directories rather than describing them.
 * That is FR-088's reasoning applied twice: the label of an action describes
 * the user's intent while its effect is deleting folders, and the two must not
 * be allowed to diverge silently. "Clear tutorial data" lists every directory
 * from `GET /data/clear-preview` before anything is removed, and restarting a
 * completed tutorial names the one project directory it will delete (FR-066,
 * FR-067, FR-087) — which is why the catalogue entry carries
 * `project_directory` at all.
 */

import { AlertTriangle, BookOpen, CheckCircle2, CircleDashed, Loader2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  learningCenterApi,
  type TutorialCatalogueEntry,
  type TutorialCatalogueGroup,
} from "../lib/api/learningCenter";
import { useAppStore } from "../store";
import { orderedTutorialGroups } from "../store/learningCenterSlice";

/** FR-068 — said plainly, on the surface, not buried in a tutorial's first step. */
export const TEMPORARY_PROJECTS_NOTICE =
  "Tutorial projects are temporary. They are deleted when you restart a tutorial or clear " +
  "tutorial data, and they are hidden from your recent projects. Do your own work in your own " +
  "project.";

/** FR-082 — the permanent toolbar entry's label, shared with the toolbar. */
export const LEARNING_CENTER_ENTRY_LABEL = "Learning Center";

const STATE_LABELS: Record<TutorialCatalogueEntry["state"], string> = {
  not_started: "Not started",
  in_progress: "In progress",
  complete: "Complete",
  unavailable: "Unavailable",
};

function EntryStateBadge({ entry }: { entry: TutorialCatalogueEntry }) {
  const label = STATE_LABELS[entry.state];
  if (entry.state === "complete") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-pine">
        <CheckCircle2 aria-hidden="true" className="size-3.5" />
        {label}
      </span>
    );
  }
  if (entry.state === "in_progress") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-ember">
        <CircleDashed aria-hidden="true" className="size-3.5" />
        {label}
      </span>
    );
  }
  if (entry.state === "unavailable") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-stone-500">
        <AlertTriangle aria-hidden="true" className="size-3.5" />
        {label}
      </span>
    );
  }
  return <span className="text-xs font-medium text-stone-500">{label}</span>;
}

function TutorialEntryCard({
  entry,
  onOpen,
}: {
  entry: TutorialCatalogueEntry;
  onOpen: (entry: TutorialCatalogueEntry) => void;
}) {
  const unavailable = entry.state === "unavailable";
  return (
    <li>
      <button
        className="flex w-full items-start gap-3 rounded-2xl border border-stone-200 p-3 text-left transition hover:border-pine hover:bg-pine/5 disabled:cursor-not-allowed disabled:opacity-70 disabled:hover:border-stone-200 disabled:hover:bg-transparent"
        data-testid={`tutorial-entry-${entry.source_kind}-${entry.source_id}-${entry.id}`}
        disabled={unavailable}
        onClick={() => onOpen(entry)}
        type="button"
      >
        {/* FR-085 — the cover is shown only when the tutorial declared one. */}
        {entry.cover_url ? (
          <img alt="" className="size-14 shrink-0 rounded-xl object-cover" src={entry.cover_url} />
        ) : null}
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-medium text-ink">{entry.title}</span>
            <EntryStateBadge entry={entry} />
          </span>
          <span className="mt-1 block text-sm leading-6 text-stone-600">{entry.summary}</span>
          {/* FR-085 — unavailable always says why, or the user cannot act on it. */}
          {unavailable && entry.unavailable_reason ? (
            <span className="mt-1 block text-xs leading-5 text-stone-500">
              {entry.unavailable_reason}
            </span>
          ) : null}
        </span>
      </button>
    </li>
  );
}

function GroupSection({
  group,
  onOpen,
}: {
  group: TutorialCatalogueGroup;
  onOpen: (entry: TutorialCatalogueEntry) => void;
}) {
  return (
    <section data-testid={`tutorial-group-${group.source_kind}-${group.source_id}`}>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-xs uppercase tracking-[0.2em] text-stone-500">{group.label}</h3>
        {/*
         * FR-076 / FR-084 — every group carries its own count and there is no
         * total across groups. A package's progress is its own business; it
         * drives nothing (FR-080) and must not read as part of one score.
         */}
        <span className="text-xs text-stone-500">
          {group.completed} of {group.total} complete
        </span>
      </div>
      <ul className="mt-3 flex flex-col gap-2">
        {group.tutorials.map((entry) => (
          <TutorialEntryCard
            entry={entry}
            key={`${entry.source_kind}:${entry.source_id}:${entry.id}`}
            onOpen={onOpen}
          />
        ))}
      </ul>
    </section>
  );
}

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

  /* FR-087 — the completed tutorial awaiting a restart confirmation. */
  const [restartTarget, setRestartTarget] = useState<TutorialCatalogueEntry | null>(null);
  /* FR-088 — the directories a clear would delete, fetched before confirming. */
  const [clearPreview, setClearPreview] = useState<string[] | null>(null);
  const [clearedDirectories, setClearedDirectories] = useState<string[] | null>(null);

  /*
   * Refetch whenever the panel opens.
   *
   * The spec's edge case: a condition satisfied while the Learning Center was
   * closed is not lost, because state lives on the backend and reopening shows
   * the current step. That only holds if opening actually asks.
   */
  useEffect(() => {
    if (!open) return;
    setRestartTarget(null);
    setClearPreview(null);
    setClearedDirectories(null);
    void refresh();
  }, [open, refresh]);

  const handleOpenEntry = useCallback(
    (entry: TutorialCatalogueEntry) => {
      if (entry.state === "unavailable") return;
      /*
       * FR-087 — an in-progress tutorial resumes where it was; a completed one
       * is not silently re-run, because starting it over deletes its project.
       */
      if (entry.state === "complete") {
        setRestartTarget(entry);
        return;
      }
      void startTutorial({
        source_kind: entry.source_kind,
        source_id: entry.source_id,
        tutorial_id: entry.id,
        restart: false,
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

  const groups = orderedTutorialGroups(catalogue);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-6 backdrop-blur-sm"
      data-testid="learning-center"
    >
      <div className="flex max-h-full w-full max-w-3xl flex-col overflow-hidden rounded-[2rem] border border-stone-200 bg-white shadow-panel">
        <header className="flex items-start justify-between gap-4 border-b border-stone-200 px-6 py-4">
          <div className="min-w-0">
            <h2 className="inline-flex items-center gap-2 font-display text-2xl text-ink">
              <BookOpen aria-hidden="true" className="size-5 text-ember" />
              {LEARNING_CENTER_ENTRY_LABEL}
            </h2>
            {/* FR-068 */}
            <p className="mt-2 max-w-xl text-xs leading-5 text-stone-500">
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

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {error ? (
            <p
              className="mb-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700"
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
              className="mb-4 rounded-xl border border-ember/40 bg-ember/5 p-3"
              data-testid="learning-center-session-conflict"
            >
              <p className="text-sm leading-6 text-ink">
                One tutorial runs at a time
                {session ? `, and “${session.title}” is open right now.` : "."} Leave it to start
                this one — your place in it is kept.
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

          {/* FR-087 / FR-066 / FR-067 — the confirmation names the directory. */}
          {restartTarget ? (
            <div
              className="mb-4 rounded-xl border border-stone-300 bg-stone-50 p-3"
              data-testid="learning-center-restart-confirm"
            >
              <p className="text-sm leading-6 text-ink">
                Start “{restartTarget.title}” again? This deletes its tutorial project and creates a
                new one in its place.
              </p>
              {restartTarget.project_directory ? (
                <p className="mt-2 break-all rounded-lg bg-white px-2 py-1 font-mono text-xs text-stone-600">
                  {restartTarget.project_directory}
                </p>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  className="rounded-full bg-ink px-3 py-1.5 text-xs font-medium text-white transition hover:bg-pine"
                  onClick={() => {
                    const target = restartTarget;
                    setRestartTarget(null);
                    void startTutorial({
                      source_kind: target.source_kind,
                      source_id: target.source_id,
                      tutorial_id: target.id,
                      restart: true,
                    });
                  }}
                  type="button"
                >
                  Delete it and start over
                </button>
                <button
                  className="rounded-full border border-stone-300 px-3 py-1.5 text-xs font-medium text-stone-600 transition hover:border-pine hover:text-pine"
                  onClick={() => setRestartTarget(null)}
                  type="button"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : null}

          {loading && groups.length === 0 ? (
            <p className="inline-flex items-center gap-2 text-sm text-stone-500">
              <Loader2 aria-hidden="true" className="size-4 animate-spin" />
              Loading tutorials…
            </p>
          ) : null}

          <div className="flex flex-col gap-6">
            {groups.map((group) => (
              <GroupSection
                group={group}
                key={`${group.source_kind}:${group.source_id}`}
                onOpen={handleOpenEntry}
              />
            ))}
          </div>

          {/*
           * Discovery problems are shown rather than swallowed: one malformed
           * manifest never empties a group, but the user should be able to see
           * that something in a source did not load.
           */}
          {catalogue && catalogue.diagnostics.length > 0 ? (
            <div
              className="mt-6 rounded-xl bg-stone-50 p-3"
              data-testid="learning-center-diagnostics"
            >
              <p className="text-xs font-medium uppercase tracking-[0.2em] text-stone-500">
                Discovery notes
              </p>
              <ul className="mt-2 flex flex-col gap-1">
                {catalogue.diagnostics.map((line) => (
                  <li className="text-xs leading-5 text-stone-600" key={line}>
                    {line}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>

        <footer className="border-t border-stone-200 px-6 py-4">
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
