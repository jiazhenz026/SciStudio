/**
 * ADR-054 Phase D (#2354) - opening a MiniApp on data of its type (FR-034).
 *
 * A MiniApp declares ONE type, and that is what makes it reusable: the
 * threshold explorer written for one stack opens on any `Image` in the project.
 * So opening it is not "run this MiniApp", it is "on which data?" - and the
 * answer has to be restricted to data the MiniApp can actually read.
 *
 * THE FILTERING IS THE BACKEND'S, NOT THIS COMPONENT'S. `GET /api/panels/miniapps/{id}/sources`
 * returns only the outputs of each workflow's latest successful run whose type
 * satisfies the declared type or a subtype of it, using
 * `scistudio.panels.miniapp.declared_type` and the same `_check_type` rule the
 * context create enforces. A second subtype rule in TypeScript would be a
 * second answer to the same question, and the two would disagree on exactly the
 * cases that matter - a subclass registered by a package, a type whose chain
 * changed. This component lists what it is given.
 *
 * `restrictTo` is the block context-menu half of FR-034. Opening from a block
 * uses that block's output and asks ONLY when several ports match, so the
 * canvas hands the same picker the same listing with the rows narrowed to the
 * block the user right-clicked - rather than a second, block-shaped picker that
 * would have to re-derive which of that block's ports match.
 */
import { useCallback, useEffect, useState } from "react";

import { miniAppsApi } from "./api";
import type { MiniAppSource, MiniAppSummary, MiniAppTarget } from "./types";

export const PICKER_TITLE = "Open on which data?";
export const PICKER_LOADING = "Looking for data of this type...";
export const PICKER_CANCEL = "Cancel";

/** What the picker says when nothing in the project matches the declared type. */
export function noMatchMessage(type: string): string {
  return `No output of the project's latest successful runs is a ${type}. Run a workflow that produces one, then open this MiniApp again.`;
}

export interface MiniAppTargetPickerProps {
  open: boolean;
  onOpenChange(open: boolean): void;
  summary: MiniAppSummary | null;
  onPick(target: MiniAppTarget): void;
  /**
   * FR-034's context-menu half: narrow the listing to one block's ports.
   *
   * Additive and optional, so the pinned four-prop call site is unchanged. The
   * canvas sets it when several of a block's ports match; with one match it
   * never opens the picker at all.
   */
  restrictTo?: { workflow_id: string; block_id: string } | null;
  /** Test seam for `GET /api/panels/miniapps/{panel_id}/sources`. */
  sources?: typeof miniAppsApi.sources;
}

export function MiniAppTargetPicker(props: MiniAppTargetPickerProps) {
  if (!props.open || !props.summary) return null;
  return <MiniAppTargetPickerBody {...props} summary={props.summary} />;
}

function MiniAppTargetPickerBody({
  onOpenChange,
  summary,
  onPick,
  restrictTo,
  sources = miniAppsApi.sources,
}: MiniAppTargetPickerProps & { summary: MiniAppSummary }) {
  const [rows, setRows] = useState<MiniAppSource[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const panelId = summary.panel_id;
  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    void sources(panelId)
      .then((result) => {
        if (!cancelled) setRows(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [panelId, sources]);

  const close = useCallback(() => onOpenChange(false), [onOpenChange]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [close]);

  const visible = (rows ?? []).filter(
    (row) =>
      !restrictTo ||
      (row.workflow_id === restrictTo.workflow_id && row.block_id === restrictTo.block_id),
  );

  // FR-034 - by workflow, then block and port. The grouping is what makes a
  // list of twenty outputs readable; the order within a workflow is the
  // backend's, which follows the run.
  const byWorkflow = new Map<string, { name: string; rows: MiniAppSource[] }>();
  for (const row of visible) {
    const group = byWorkflow.get(row.workflow_id);
    if (group) group.rows.push(row);
    else byWorkflow.set(row.workflow_id, { name: row.workflow_name, rows: [row] });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4">
      <div
        aria-modal="true"
        role="dialog"
        aria-labelledby="miniapp-target-title"
        data-testid="miniapp-target-picker"
        className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-xl border border-stone-200 bg-stone-50 p-6 shadow-panel"
      >
        <div className="mb-3 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-stone-500">{summary.name}</p>
            <h2 className="mt-2 font-display text-2xl text-ink" id="miniapp-target-title">
              {PICKER_TITLE}
            </h2>
            <p className="mt-1 text-xs text-stone-500">
              This MiniApp reads <span className="font-medium">{summary.type}</span>.
            </p>
          </div>
          <button
            className="rounded-full border border-stone-300 px-3 py-1 text-sm"
            data-testid="miniapp-target-close"
            onClick={close}
            type="button"
          >
            {PICKER_CANCEL}
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
          {error ? (
            <div
              className="rounded bg-red-50 px-3 py-2 text-sm text-red-700"
              data-testid="miniapp-target-error"
              role="alert"
            >
              {error}
            </div>
          ) : rows === null ? (
            <p className="text-sm italic text-stone-500" data-testid="miniapp-target-loading">
              {PICKER_LOADING}
            </p>
          ) : visible.length === 0 ? (
            <p className="text-sm text-stone-600" data-testid="miniapp-target-empty">
              {noMatchMessage(summary.type)}
            </p>
          ) : (
            <div className="grid gap-4">
              {[...byWorkflow.entries()].map(([workflowId, group]) => (
                <div className="grid gap-1" key={workflowId}>
                  <p className="text-xs uppercase tracking-wide text-stone-500">{group.name}</p>
                  {group.rows.map((row) => (
                    <button
                      className="rounded-2xl border border-stone-300 bg-white px-3 py-2 text-left text-sm text-ink hover:bg-stone-100"
                      data-testid={`miniapp-target-row-${row.workflow_id}-${row.block_id}-${row.port}`}
                      key={`${row.block_id}:${row.port}`}
                      onClick={() => {
                        onPick({
                          workflow_id: row.workflow_id,
                          block_id: row.block_id,
                          port: row.port,
                        });
                        onOpenChange(false);
                      }}
                      type="button"
                    >
                      <span className="font-medium">{row.block_name}</span>
                      <span className="text-stone-500">
                        {" "}
                        - {row.port} ({row.type})
                      </span>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
