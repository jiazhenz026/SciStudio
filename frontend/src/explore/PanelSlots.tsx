/**
 * ADR-054 spec 4 (T-009 to T-011) — the panels the centre mounts.
 *
 * Two surfaces live here because they are the same surface seen twice:
 *
 *   - `ExplorePanelSlot` is one mounted panel over one notebook variable, with
 *     the emission path, the changed-names refresh and the submission freeze
 *     around it (FR-019, FR-021 to FR-023).
 *   - `PausePanel` and `PauseControls` are that same host mounted over a paused
 *     interactive block's inputs, with confirm and cancel on the toolbar
 *     instead of the strip (FR-024 to FR-027).
 *
 * **The host is placed, not built.** ADR-054 spec 1 landed the frame host, the
 * message contract and the capability gate under `frontend/src/panels/`; this
 * module mounts it, binds it to a name, and answers its bounded reads through
 * the session API. Nothing here creates a frame or spells a panel API version.
 *
 * **The confirm control is not in the panel.** A producing panel's only
 * outbound path is `emit` (spec 1 FR-012), so it owns no Confirm: the host
 * draws one and commits the panel's most recent emission. The retired modal
 * drew it beside the frame; a pause tab draws it on the toolbar, which is why
 * the emission has to be shared between two components and `PauseEmission`
 * below is a context rather than a `useState` in one of them.
 *
 * **What is not computed here.** The freeze reads the running cell off the
 * cell-state event and the names that cell may change off the runtime's own
 * analysis (`GraphResponse.changed_sets`, and the names the cell was last
 * observed to change); the refresh reads `explore.changed_names`. FR-034
 * leaves no room for a changed set worked out locally, and the backend refuses
 * a frozen emission as well, so the two answers can never disagree about what
 * is running — only about how early the person is told.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";

import { sendWebSocketMessage } from "../hooks/useWebSocket";
import { ApiError } from "../lib/api";
import { dataApi } from "../lib/api/data";
import { exploreApi } from "../lib/api/explore";
import { INTERACTIVE_MEMORY_KEY, readInteractiveMemory } from "../lib/interactiveMemory";
import type { PanelDescriptor, PanelFailure, PanelFrameFactory } from "../panels";
import { PanelErrorSurface, PanelHost, capabilitySatisfies, isPanelCapability } from "../panels";
import { useAppStore } from "../store";
import { usePanelReloadToken } from "../store/usePanelReload";
import { usePanelRevertOffer } from "../store/usePanelRevert";
import type {
  ExploreSessionState,
  ExploreTab as ExploreTabState,
  InteractivePrompt,
  PanelSlot,
} from "../store/types";
import type { PanelDescriptorResponse, PanelSpecSummary } from "../types/api";

/**
 * The key a producing panel's emission is committed under.
 *
 * `settle_interactive_response` in `src/scistudio/blocks/base/interactive.py`
 * reads exactly this key, and the retired modal sent exactly this shape. It is
 * repeated here rather than imported because the module that held it is gone;
 * the pause-tab test pins it against the shipped panel documents.
 */
export const EMITTED_CODE_KEY = "code";

/**
 * The decision key a packaged notebook block's pause returns (FR-027).
 *
 * `DECISION_COMMIT_KEY` in `src/scistudio/explore/packaging.py`. A packaged
 * block set to `ask` is an interactive block whose panel is this tab and whose
 * decision is a notebook commit rather than an emission.
 */
export const DECISION_COMMIT_KEY = "notebook_commit";

/**
 * The panel id a packaged notebook block declares (FR-027).
 *
 * `EXPLORE_SESSION_PANEL_ID` in `src/scistudio/explore/packaging.py`. It names
 * no panel directory: the Explore tab itself is the panel, which is what tells
 * a pause tab to open the block's notebook instead of mounting a frame.
 */
export const EXPLORE_SESSION_PANEL_ID = "core.explore.session";

/* -------------------------------------------------------------------------- */
/* Resolving the panel for a variable's type (FR-019)                          */
/* -------------------------------------------------------------------------- */

/**
 * One catalogue row, with the descriptor the backend already puts on it.
 *
 * `PanelSpecModel.descriptor` is on the wire (`src/scistudio/api/schemas.py`)
 * but `PanelSpecSummary` in `frontend/src/types/api.ts` does not declare it, so
 * it is declared structurally here rather than by editing a type another agent
 * owns. Recorded as `F-A3-002` in the assembly follow-up register.
 */
type PanelCatalogueRow = PanelSpecSummary & {
  readonly descriptor?: PanelDescriptorResponse | null;
};

/** What one producing request resolved to (FR-019, FR-049). */
export interface ResolvedExplorePanel {
  readonly descriptor: PanelDescriptorResponse;
  /**
   * `true` when no panel claiming this type declares the producing capability
   * and a displaying one was mounted instead. The mount is then granted no
   * outbound path, exactly as spec 1 FR-049 says.
   */
  readonly fellBackToDisplay: boolean;
}

/**
 * Ask the backend which panel serves `typeName` for a producing request.
 *
 * `GET /api/panels?target_type=...` is the catalogue for one type, ordered in
 * routing precedence by the backend and carrying each panel's declared
 * capability and its descriptor. The only decision made here is the one
 * FR-048 states — take the first candidate that declares at least the required
 * capability — and it is made with the contract's own `capabilitySatisfies`.
 *
 * This is not the whole of spec 1's capability-aware resolution: the ladder's
 * specificity walk and the per-type producing choice of FR-049 live in
 * `PreviewRouter.resolve_request`, which no HTTP route exposes for a type name.
 * Recorded as `F-A3-001` in the assembly follow-up register.
 *
 * TODO(#2253): a producing request cannot reach `PreviewRouter.resolve_request`.
 *   Out of scope per the ADR-054 assembly dispatch (no agent may edit
 *   `src/scistudio/**`).
 *   Followup: docs/planning/adr-054-assembly-followups.md, `### S4-A3`, F-A3-001.
 */
export async function resolveProducingPanel(
  typeName: string | null | undefined,
): Promise<ResolvedExplorePanel | null> {
  if (!typeName) return null;
  const listing = await dataApi.listPanels(typeName);
  const rows = ((listing.panels ?? []) as PanelCatalogueRow[]).filter((row) => row.descriptor);
  const producing = rows.find(
    (row) => isPanelCapability(row.capability) && capabilitySatisfies(row.capability, "producing"),
  );
  if (producing?.descriptor) {
    return { descriptor: producing.descriptor, fellBackToDisplay: false };
  }
  const displaying = rows[0];
  if (!displaying?.descriptor) return null;
  return { descriptor: displaying.descriptor, fellBackToDisplay: true };
}

/**
 * The slot identity for one name and one panel.
 *
 * The bound name is part of it because `PanelSlot.panelId` is the slot's key in
 * the slice: two names served by the same panel are two slots, and keying them
 * on the panel id alone would collapse them into one.
 */
export function explorePanelSlotId(boundName: string, panelId: string): string {
  return `${boundName}::${panelId}`;
}

/**
 * The descriptors the strip has already resolved, by slot id.
 *
 * A cache of a backend answer, not state: `PanelSlot` carries no descriptor and
 * belongs to another agent's slice, so the strip leaves what it resolved here
 * and the slot picks it up. A slot that finds nothing resolves for itself, so
 * losing this map costs one request and nothing else.
 */
const slotDescriptors = new Map<string, PanelDescriptorResponse>();

export function rememberSlotDescriptor(slotId: string, descriptor: PanelDescriptorResponse): void {
  slotDescriptors.set(slotId, descriptor);
}

export function slotDescriptorFor(slotId: string): PanelDescriptorResponse | undefined {
  return slotDescriptors.get(slotId);
}

/** Test seam — drop the cache so each test resolves from its own stub. */
export function forgetSlotDescriptors(): void {
  slotDescriptors.clear();
}

/* -------------------------------------------------------------------------- */
/* What the runtime says is running, and what it changed (FR-022, FR-023)      */
/* -------------------------------------------------------------------------- */

/**
 * The names a currently running cell may change (FR-023).
 *
 * Two runtime-supplied sources, unioned, and neither is computed here: the
 * analysis's own changed set for that cell (`GraphResponse.changed_sets`, the
 * very map `Session._changed_names_of` freezes on) and the names the runtime
 * last observed that cell to change (`explore.changed_names`). Which cell is
 * running comes from the cell-state event alone.
 */
export function frozenNamesOf(session: ExploreSessionState | undefined): ReadonlySet<string> {
  const names = new Set<string>();
  if (!session) return names;
  for (const cell of session.cells) {
    if (cell.runState !== "running") continue;
    for (const name of session.graph?.changedSets[cell.cellId] ?? []) names.add(name);
    for (const name of cell.changedNames) names.add(name);
  }
  return names;
}

/**
 * A key that changes exactly when a `changed_names` event named `name` (FR-022).
 *
 * Only the cells that changed this name contribute, so a run of a cell that
 * changed something else leaves the key alone — which is the whole of FR-022's
 * "other panels MUST NOT refresh". The execution count and the cell's last
 * event timestamp are in it so a second run changing the same name is a second
 * refresh rather than a no-op.
 */
export function panelRefreshKey(session: ExploreSessionState | undefined, name: string): string {
  if (!session) return "";
  return session.cells
    .filter((cell) => cell.changedNames.includes(name))
    .map((cell) => `${cell.cellId}:${cell.executionCount ?? ""}:${cell.lastEventAt ?? ""}`)
    .join("|");
}

/* -------------------------------------------------------------------------- */
/* One mounted panel over one variable (FR-019, FR-021 to FR-023)              */
/* -------------------------------------------------------------------------- */

export interface ExplorePanelSlotProps {
  tab: ExploreTabState;
  /** `undefined` until the open or restore lands. */
  session: ExploreSessionState | undefined;
  slot: PanelSlot;
  /** Test seam: the frame-creation seam `mountPanelFrame` builds through. */
  frameFactory?: PanelFrameFactory;
}

/** What the shell is telling the person about this panel's last submission. */
interface SlotNote {
  readonly kind: "refused" | "frozen";
  readonly panel: string;
  readonly message: string;
}

export function ExplorePanelSlot({ tab, session, slot, frameFactory }: ExplorePanelSlotProps) {
  const slotId = slot.panelId;
  const boundName = slot.boundName;
  const sessionId = session?.sessionId ?? "";
  const binding = session?.bindings.find((entry) => entry.name === boundName) ?? null;
  const typeName = binding?.typeName ?? binding?.nativeTypeName ?? null;

  const [descriptor, setDescriptor] = useState<PanelDescriptorResponse | null>(
    () => slotDescriptorFor(slotId) ?? null,
  );
  const [resolution, setResolution] = useState<string | null>(null);
  const [envelope, setEnvelope] = useState<Record<string, unknown> | null>(null);
  const [note, setNote] = useState<SlotNote | null>(null);
  const [failure, setFailure] = useState<PanelFailure | null>(null);

  const noteExplorePanelClosed = useAppStore((state) => state.noteExplorePanelClosed);
  const setExplorePanelPinned = useAppStore((state) => state.setExplorePanelPinned);
  const applyExploreCells = useAppStore((state) => state.applyExploreCells);
  const applyExploreRunRequests = useAppStore((state) => state.applyExploreRunRequests);

  const reloadToken = usePanelReloadToken(descriptor?.panel_id ?? null);
  const revertOffer = usePanelRevertOffer(descriptor?.panel_id ?? null);

  // FR-019 — the producing request for this variable's type. Resolved once per
  // slot; a descriptor the strip already resolved is used as it is.
  useEffect(() => {
    if (slotDescriptorFor(slotId)) {
      setDescriptor(slotDescriptorFor(slotId) ?? null);
      return;
    }
    let cancelled = false;
    void resolveProducingPanel(typeName)
      .then((resolved) => {
        if (cancelled) return;
        if (!resolved) {
          setResolution(
            typeName
              ? `No panel is registered for ${typeName}, so there is nothing to mount over ${boundName}.`
              : `The kernel has not reported a type for ${boundName} yet.`,
          );
          return;
        }
        rememberSlotDescriptor(slotId, resolved.descriptor);
        setDescriptor(resolved.descriptor);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setResolution(error instanceof Error ? error.message : String(error));
      });
    return () => {
      cancelled = true;
    };
  }, [slotId, typeName, boundName]);

  // The opening read, and FR-022's refresh: the same read, re-issued when a
  // changed-names event named this variable and at no other time.
  const refreshKey = panelRefreshKey(session, boundName);
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    void exploreApi
      .windowExploreVariable(sessionId, { name: boundName })
      .then((answer) => {
        if (!cancelled) setEnvelope(answer.envelope);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setResolution(error instanceof Error ? error.message : String(error));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, boundName, refreshKey]);

  const frozenNames = frozenNamesOf(session);
  const frozen = frozenNames.has(boundName);
  // The freeze must be readable from the emit handler without re-mounting the
  // frame for it, so the handler reads a ref rather than the closed-over value.
  const frozenRef = useRef(frozen);
  frozenRef.current = frozen;
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  const onRead = useCallback(
    async (query: Readonly<Record<string, unknown>>) => {
      // FR-023 — reading continues while a run holds this name. The freeze is
      // on submission only, and the session's own windowed read queues behind
      // the running cell in the kernel rather than being refused.
      const answer = await exploreApi.windowExploreVariable(sessionIdRef.current, {
        name: boundName,
        query: { ...query },
      });
      setEnvelope(answer.envelope);
      return answer.envelope;
    },
    [boundName],
  );

  const onEmit = useCallback(
    (code: string) => {
      const panelId = descriptor?.panel_id ?? slotId;
      if (frozenRef.current) {
        setNote({
          kind: "frozen",
          panel: panelId,
          message:
            `Panel ${panelId} cannot submit while a running cell may change ${boundName}. ` +
            "The panel keeps reading; try again when the run ends.",
        });
        return;
      }
      setNote(null);
      void exploreApi
        .emitExploreSnippet(sessionIdRef.current, {
          source: code,
          panel: panelId,
          bound_names: [boundName],
        })
        .then(async (answer) => {
          // The runtime inserted the cell after the current cell and queued it;
          // the shell re-reads the notebook and writes the queued request, which
          // is the one door a cell reaches `queued` through (FR-021).
          const cells = await exploreApi.readExploreCells(sessionIdRef.current);
          applyExploreCells(sessionIdRef.current, cells.cells);
          applyExploreRunRequests(sessionIdRef.current, [answer.request]);
        })
        .catch((error: unknown) => {
          // The session's own refusal names the panel and the statement; it is
          // shown verbatim rather than re-worded, because a re-worded refusal is
          // one nobody wrote.
          setNote({
            kind: error instanceof ApiError && error.status === 409 ? "frozen" : "refused",
            panel: panelId,
            message: error instanceof Error ? error.message : String(error),
          });
        });
    },
    [applyExploreCells, applyExploreRunRequests, boundName, descriptor, slotId],
  );

  const bindings = useMemo(
    () => ({ [boundName]: { type: typeName ?? "", snapshot: envelope } }),
    [boundName, typeName, envelope],
  );
  const update = useMemo(
    () => (envelope ? { reason: "changed_names", changed: { target: envelope } } : null),
    [envelope],
  );

  return (
    <div
      className="flex h-full min-h-0 flex-col overflow-hidden rounded border border-stone-200 bg-white"
      data-testid={`explore-panel-slot-${slotId}`}
      data-bound-name={boundName}
      data-frozen={frozen ? "true" : "false"}
    >
      <div className="flex shrink-0 items-center gap-2 border-b border-stone-200 bg-stone-50 px-2 py-1">
        <span className="truncate text-xs font-medium text-ink" title={boundName}>
          {boundName}
        </span>
        {typeName ? <span className="text-[11px] text-stone-400">{typeName}</span> : null}
        <div className="ml-auto flex items-center gap-1">
          <button
            className="rounded px-1.5 py-0.5 text-[11px] text-stone-500 hover:bg-stone-100"
            data-testid={`explore-panel-pin-${slotId}`}
            onClick={() => setExplorePanelPinned(sessionId, slotId, !slot.pinned)}
            type="button"
          >
            {slot.pinned ? "Unpin" : "Pin"}
          </button>
          <button
            className="rounded px-1.5 py-0.5 text-[11px] text-stone-500 hover:bg-stone-100"
            data-testid={`explore-panel-close-${slotId}`}
            onClick={() => noteExplorePanelClosed(sessionId, slotId)}
            type="button"
          >
            Close
          </button>
        </div>
      </div>

      {note ? (
        <p
          className="shrink-0 border-b border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-800"
          data-testid={`explore-panel-note-${slotId}`}
          data-note-kind={note.kind}
          data-note-panel={note.panel}
        >
          {note.message}
        </p>
      ) : null}

      <div className="min-h-0 flex-1">
        {descriptor ? (
          <PanelHost
            className="h-full w-full"
            descriptor={descriptor as PanelDescriptor}
            revert={revertOffer}
            target={envelope}
            bindings={bindings}
            update={update}
            remountToken={reloadToken}
            onRead={onRead}
            onEmit={onEmit}
            onFailure={setFailure}
            frameFactory={frameFactory}
          />
        ) : (
          <p className="p-3 text-xs text-stone-400" data-testid={`explore-panel-pending-${slotId}`}>
            {resolution ?? `Resolving a panel for ${boundName}…`}
          </p>
        )}
      </div>
      {failure && !descriptor ? <PanelErrorSurface failure={failure} /> : null}
      <span className="hidden" data-testid={`explore-panel-tab-${slotId}`}>
        {tab.id}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* The pause tab (FR-024 to FR-027)                                            */
/* -------------------------------------------------------------------------- */

/**
 * The emission the pause tab's panel last made, shared between the frame in the
 * centre and Confirm on the toolbar.
 *
 * A context rather than state in one of them because the two are siblings under
 * `ExploreTab`: the modal drew Confirm beside its frame and could hold the
 * emission in one component, and the tab cannot.
 */
interface PauseEmissionValue {
  readonly emitted: string | null;
  readonly setEmitted: (code: string | null) => void;
}

const PauseEmissionContext = createContext<PauseEmissionValue>({
  emitted: null,
  setEmitted: () => undefined,
});

export function PauseEmissionProvider({ children }: { children: ReactNode }) {
  const [emitted, setEmitted] = useState<string | null>(null);
  const value = useMemo(() => ({ emitted, setEmitted }), [emitted]);
  return <PauseEmissionContext.Provider value={value}>{children}</PauseEmissionContext.Provider>;
}

/**
 * The frame seam a pause panel uses when its caller passes none.
 *
 * `ExploreTab` renders `PausePanel` itself, so a test that drives the whole tab
 * from a real `interactive_prompt` event has no prop to pass a seam through.
 * This is that seam, and it is the only way the pause path can be tested as the
 * person meets it rather than one component at a time. Unset in production.
 */
let defaultPauseFrameFactory: PanelFrameFactory | undefined;

export function setPausePanelFrameFactory(factory: PanelFrameFactory | undefined): void {
  defaultPauseFrameFactory = factory;
}

/** The prompt this pause tab is waiting on, or `null`. */
export function usePausePrompt(tab: ExploreTabState): InteractivePrompt | null {
  const prompt = useAppStore((state) => state.interactivePrompt);
  if (!prompt) return null;
  if (tab.pauseNodeId && prompt.blockId !== tab.pauseNodeId) return null;
  return prompt;
}

/** `true` when this prompt is a packaged notebook block asking (FR-027). */
export function isPackagedAskPrompt(prompt: InteractivePrompt | null): boolean {
  return prompt?.panelManifest?.panel_id === EXPLORE_SESSION_PANEL_ID;
}

/**
 * The block's panel, mounted over the run's inputs (FR-024).
 *
 * The descriptor is the backend's, carried on the `interactive_prompt` event —
 * there is no frontend registry from a block name to a component any more, and
 * a prompt that carried no descriptor gets the host's error surface rather than
 * a blank tab, which is #2195's property carried across the migration.
 */
export function PausePanel({
  tab,
  frameFactory,
}: {
  tab: ExploreTabState;
  frameFactory?: PanelFrameFactory;
}) {
  const prompt = usePausePrompt(tab);
  const { setEmitted } = useContext(PauseEmissionContext);
  const [diagnostics, setDiagnostics] = useState<PanelFailure | null>(null);
  const descriptor = prompt?.panelDescriptor ?? null;
  const declaredPanelId = prompt?.panelManifest?.panel_id ?? null;
  const reloadToken = usePanelReloadToken(descriptor?.panel_id ?? null);
  const revertOffer = usePanelRevertOffer(descriptor?.panel_id ?? declaredPanelId);

  const bindings = useMemo(
    () => ({
      prompt: { type: "interactive_prompt", snapshot: prompt?.panelPayload ?? {} },
    }),
    [prompt?.panelPayload],
  );

  const onEmit = useCallback((code: string) => setEmitted(code), [setEmitted]);

  if (!prompt) {
    return (
      <p className="p-3 text-xs text-stone-400" data-testid="explore-pause-resolved">
        This block is no longer waiting for a decision.
      </p>
    );
  }

  if (!descriptor) {
    const missing: PanelFailure = {
      panelId: declaredPanelId ?? prompt.blockId,
      reason: "invalid_descriptor",
      message: declaredPanelId
        ? `this block asked for panel "${declaredPanelId}" but the prompt carried no descriptor ` +
          "for it, so there is no document to mount"
        : "this block's prompt named no panel to mount",
    };
    return (
      <div className="p-3" data-testid="explore-pause-panel">
        <PanelErrorSurface failure={missing} revert={revertOffer} />
      </div>
    );
  }

  return (
    <div
      className="flex h-full min-h-0 flex-col overflow-hidden rounded border border-stone-200 bg-white"
      data-testid="explore-pause-panel"
      data-block-id={prompt.blockId}
    >
      <PanelHost
        className="h-full w-full"
        descriptor={descriptor as PanelDescriptor}
        revert={revertOffer}
        target={prompt.panelPayload}
        bindings={bindings}
        remountToken={reloadToken}
        onEmit={onEmit}
        onFailure={setDiagnostics}
        frameFactory={frameFactory ?? defaultPauseFrameFactory}
      />
      {diagnostics ? <PanelErrorSurface failure={diagnostics} /> : null}
    </div>
  );
}

/**
 * Confirm and cancel for a pause tab (FR-024, FR-025).
 *
 * **The messages are the modal's, unchanged.** Confirm sends
 * `interactive_complete` carrying the emission under `code`, scoped to the
 * workflow the *prompt* belongs to; cancel sends `cancel_block` with the same
 * scoping. The interaction memory is recorded from the same verbatim response,
 * as it was. That is FR-025 in full: the backend's interactive path never
 * learns that the window it is answering moved.
 *
 * A packaged block asking (FR-027) confirms a notebook commit instead of an
 * emission, because that is the decision its own `response_schema` declares.
 */
export function PauseControls({
  tab,
  session,
}: {
  tab: ExploreTabState;
  session: ExploreSessionState | undefined;
}) {
  const prompt = usePausePrompt(tab);
  const { emitted } = useContext(PauseEmissionContext);
  const setInteractivePrompt = useAppStore((state) => state.setInteractivePrompt);

  const packagedAsk = isPackagedAskPrompt(prompt);
  const commit = session?.notebookCommit ?? null;
  const decision: Record<string, unknown> | null = useMemo(() => {
    if (packagedAsk) return commit ? { [DECISION_COMMIT_KEY]: commit } : null;
    return emitted !== null ? { [EMITTED_CODE_KEY]: emitted } : null;
  }, [commit, emitted, packagedAsk]);

  /**
   * The pause is over: the prompt is cleared and the tab says so.
   *
   * **The tab is not closed here, deliberately.** `closeTab` restores whichever
   * tab it activates next, and that restore overwrites the live workflow slice
   * with that tab's snapshot — including the node config `onConfirm` has just
   * written the remembered decision into, and including everything else when
   * the pause tab was the only one open. The modal never switched tabs, so it
   * never had that problem; closing this one on the person's behalf would
   * introduce it. Recorded as `F-A3-004` in the assembly follow-up register.
   *
   * TODO(#2253): a settled pause leaves its tab on screen for the person to
   *   close, because closing it here would lose the interaction-memory write.
   *   Out of scope per the ADR-054 assembly dispatch: a safe auto-close needs
   *   `closeTab` to capture the live slice first, which is S4-A1's file.
   *   Followup: docs/planning/adr-054-assembly-followups.md, `### S4-A3`, F-A3-004.
   */
  const settle = useCallback(() => {
    setInteractivePrompt(null);
  }, [setInteractivePrompt]);

  const onConfirm = useCallback(() => {
    if (!prompt || !decision) return;
    sendWebSocketMessage({
      type: "interactive_complete",
      block_id: prompt.blockId,
      workflow_id: prompt.workflowId,
      data: decision,
    });
    // ADR-051 interaction memory: the verbatim response is what a later run
    // replays, so it is stored exactly as it was sent.
    const node = useAppStore.getState().workflowNodes.find((each) => each.id === prompt.blockId);
    const memory = readInteractiveMemory(node?.config as Record<string, unknown> | undefined);
    if (memory?.enabled) {
      useAppStore.getState().updateNodeConfig(prompt.blockId, {
        [INTERACTIVE_MEMORY_KEY]: {
          enabled: true,
          decision,
          signature: prompt.inputSignature,
        },
      });
    }
    settle();
  }, [decision, prompt, settle]);

  const onCancel = useCallback(() => {
    if (!prompt) return;
    sendWebSocketMessage({
      type: "cancel_block",
      block_id: prompt.blockId,
      workflow_id: prompt.workflowId,
    });
    settle();
  }, [prompt, settle]);

  return (
    <span className="flex items-center gap-1" data-testid="explore-toolbar-pause-controls">
      <button
        className="toolbar-button"
        data-testid="explore-pause-cancel"
        onClick={onCancel}
        type="button"
      >
        Cancel
      </button>
      <button
        className="toolbar-button"
        data-testid="explore-pause-confirm"
        disabled={decision === null}
        onClick={onConfirm}
        title={
          decision === null
            ? packagedAsk
              ? "Commit the notebook first; the decision this block reads is a commit"
              : "This panel has not made a decision yet"
            : "Send this decision back to the block"
        }
        type="button"
      >
        Confirm
      </button>
    </span>
  );
}
