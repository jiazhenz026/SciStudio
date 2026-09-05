/**
 * ADR-054 spec 4 (T-008) — the variable strip above the panel host.
 *
 * The strip lists what the session says is bound: every name the analysis
 * reports, with the type the kernel reports for it, pinned outputs first
 * (FR-018). A name that does not exist in the kernel is greyed and not
 * openable — greyed, not hidden, because a name whose cell exists but has not
 * run yet is exactly what a person is about to run the cell for.
 *
 * **Nothing here decides whether a name is live.** `VariableEntry.live` is
 * `BindingModel.exists_in_kernel` copied through the slice (FR-034). The strip
 * draws it.
 *
 * **A click is a producing request** (FR-019). It asks the backend which panel
 * serves this variable's type for a request that requires the producing
 * capability, and mounts that panel in the centre bound to the name. The
 * resolution is `resolveProducingPanel`'s, which is spec 1's contract reached
 * over HTTP; the strip contains no ladder of its own.
 *
 * **Declared outputs pin themselves** (FR-020). The runtime is the authority on
 * which names a session declares as outputs: the packaging check's `outputs`
 * name them, and a session opened over a block's outputs is bound to that
 * block's output ports. When such a name becomes live the strip opens and pins
 * its panel, and a pinned panel is not closed by a later click on its name.
 */

import { useCallback, useEffect, useMemo } from "react";

import { exploreApi } from "../lib/api/explore";
import { useAppStore } from "../store";
import type {
  ExploreSessionState,
  ExploreTab as ExploreTabState,
  VariableEntry,
} from "../store/types";

import { explorePanelSlotId, rememberSlotDescriptor, resolveProducingPanel } from "./PanelSlots";

export interface VariableStripProps {
  tab: ExploreTabState;
  /** `undefined` until the open or restore lands. */
  session: ExploreSessionState | undefined;
}

/**
 * The names this session declares as outputs, as the runtime reports them.
 *
 * Two runtime answers, not a guess: the packaging check names the ports the
 * generated block would declare and the variable each is bound to, and a
 * session opened over a block's outputs is bound to that run's output ports.
 * Neither exists before the runtime has answered, so before then the strip
 * pins nothing — which is FR-020 waiting, not FR-020 failing.
 */
export function declaredOutputNames(session: ExploreSessionState | undefined): readonly string[] {
  if (!session) return [];
  const names = new Set<string>();
  for (const port of session.lastReport?.outputs ?? []) {
    if (port.bound_name) names.add(port.bound_name);
  }
  if (session.openedOver === "block_outputs") {
    for (const port of session.boundRun?.ports ?? []) names.add(port.name);
  }
  return [...names];
}

/**
 * The strip's order: pinned first, everything else in the runtime's own order
 * (FR-018). `Array.prototype.sort` is stable, so the bindings response's order
 * survives inside each group.
 */
export function stripOrder(bindings: readonly VariableEntry[]): VariableEntry[] {
  return [...bindings].sort((left, right) => Number(right.pinned) - Number(left.pinned));
}

/** What a strip entry says it is, for the reader and for a test. */
function entryLabel(entry: VariableEntry): string {
  return entry.typeName ?? entry.nativeTypeName ?? "";
}

/**
 * When the strip asks the runtime for the bindings again.
 *
 * FR-018's two halves, each with the event that makes it true: a name appears
 * as soon as the cell that binds it exists — so the analysis's own reason and
 * the cell list are in the key — and it stays greyed until the bindings
 * response says the kernel holds it — so each cell's execution count and the
 * names its last run changed are in it too. A run that is merely *starting*
 * moves neither, which is what keeps the strip from asking a busy kernel a
 * question it would only answer once the cell ends.
 */
export function bindingsRefreshKey(session: ExploreSessionState | undefined): string {
  if (!session) return "";
  const cells = session.cells
    .map((cell) => `${cell.cellId}:${cell.executionCount ?? ""}:${cell.changedNames.join("+")}`)
    .join("|");
  return `${session.lastAnalysisReason ?? ""}#${session.kernel.state}#${cells}`;
}

export function VariableStrip({ session }: VariableStripProps) {
  const sessionId = session?.sessionId ?? "";
  const bindings = useMemo(() => stripOrder(session?.bindings ?? []), [session?.bindings]);
  const noteExplorePanelOpened = useAppStore((state) => state.noteExplorePanelOpened);
  const noteExplorePanelClosed = useAppStore((state) => state.noteExplorePanelClosed);
  const applyExploreBindings = useAppStore((state) => state.applyExploreBindings);

  /*
   * FR-018 — the strip is what asks for the bindings.
   *
   * Nobody else does: the slice has the writer and the API client has the
   * route, and the strip is the surface that draws the answer, so the read
   * belongs here. A refusal leaves the strip showing what it had — a kernel
   * that is not up yet is the ordinary case, not an error state.
   */
  const refreshKey = bindingsRefreshKey(session);
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    void exploreApi
      .getExploreBindings(sessionId)
      .then((answer) => {
        if (!cancelled) applyExploreBindings(sessionId, answer);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [applyExploreBindings, refreshKey, sessionId]);

  /**
   * FR-019 — mount a panel for one name through the panel host.
   *
   * The descriptor is left where the slot will find it, so the slot mounts the
   * panel this click resolved rather than resolving a second time.
   */
  const openPanelFor = useCallback(
    async (entry: VariableEntry, pinned: boolean) => {
      if (!sessionId || !entry.live) return;
      const typeName = entry.typeName ?? entry.nativeTypeName ?? null;
      const resolved = await resolveProducingPanel(typeName);
      if (!resolved) return;
      const slotId = explorePanelSlotId(entry.name, resolved.descriptor.panel_id);
      rememberSlotDescriptor(slotId, resolved.descriptor);
      noteExplorePanelOpened(sessionId, {
        panelId: slotId,
        boundName: entry.name,
        pinned,
        frozen: false,
      });
    },
    [noteExplorePanelOpened, sessionId],
  );

  /**
   * FR-020 — a declared output opens and pins itself the moment it is live.
   *
   * Keyed on the names rather than on the entries so a bindings refresh that
   * reports the same names does not re-open a panel the person closed... which
   * it would anyway if the name were still declared and live. That is what
   * "pinned automatically" means: the declaration, not the click, owns it.
   */
  const declared = declaredOutputNames(session);
  const autoOpenKey = bindings
    .filter((entry) => entry.live && declared.includes(entry.name) && !entry.openPanelId)
    .map((entry) => entry.name)
    .join("|");
  useEffect(() => {
    if (!sessionId || autoOpenKey === "") return;
    const held = useAppStore.getState().sessions[session?.notebookPath ?? ""];
    for (const name of autoOpenKey.split("|")) {
      const entry = held?.bindings.find((candidate) => candidate.name === name);
      if (!entry || !entry.live || entry.openPanelId) continue;
      void openPanelFor(entry, true);
    }
  }, [autoOpenKey, openPanelFor, session?.notebookPath, sessionId]);

  const onClick = useCallback(
    (entry: VariableEntry) => {
      if (!entry.live) return;
      if (entry.openPanelId) {
        // FR-020 — a pinned panel does not close on a strip click.
        if (entry.pinned) return;
        noteExplorePanelClosed(sessionId, entry.openPanelId);
        return;
      }
      void openPanelFor(entry, false);
    },
    [noteExplorePanelClosed, openPanelFor, sessionId],
  );

  return (
    <div
      className="flex items-center gap-2 overflow-x-auto rounded border border-stone-200 bg-white/70 px-3 py-2 text-xs scrollbar-thin"
      data-testid="explore-variable-strip-region"
    >
      <span className="shrink-0 font-medium text-stone-600">Variables</span>
      {bindings.length === 0 ? (
        <span className="text-[11px] text-stone-400" data-testid="explore-variable-strip-empty">
          Nothing is bound yet.
        </span>
      ) : null}
      {bindings.map((entry) => (
        <button
          className={
            entry.live
              ? "shrink-0 rounded border border-stone-300 bg-white px-2 py-0.5 text-ink hover:bg-stone-100"
              : "shrink-0 cursor-not-allowed rounded border border-dashed border-stone-200 bg-stone-50 px-2 py-0.5 text-stone-400"
          }
          data-testid={`explore-variable-${entry.name}`}
          data-live={entry.live ? "true" : "false"}
          data-pinned={entry.pinned ? "true" : "false"}
          data-type-name={entryLabel(entry)}
          disabled={!entry.live}
          aria-disabled={!entry.live}
          key={entry.name}
          onClick={() => onClick(entry)}
          title={
            entry.live
              ? `${entry.name}${entryLabel(entry) ? `: ${entryLabel(entry)}` : ""}`
              : `${entry.name} does not exist in the kernel yet`
          }
          type="button"
        >
          <span className="font-mono">{entry.name}</span>
          {entryLabel(entry) ? (
            <span className="ml-1 text-[11px] text-stone-400">{entryLabel(entry)}</span>
          ) : null}
          {entry.pinned ? <span className="ml-1 text-[11px] text-amber-600">pinned</span> : null}
        </button>
      ))}
    </div>
  );
}
