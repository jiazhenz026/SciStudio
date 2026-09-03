// Loading and reading the registered panel catalogue and the person's
// per-type panel choices (#2113, over #2095's discovery/reload routes and
// #2049's choice routes).
//
// The shape mirrors `useTypeCatalog` (ADR-053 §7) deliberately: the load is
// demand-driven and shared, the cache is valid only until something rebuilds
// the registries, and `invalidatePanelCatalog` is how every such event
// says so — the `blocks.reloaded` websocket event among them, since every
// emitter of it reaches `refresh_all_registries()`, which has rebuilt the
// panel registry since #2021.
//
// Choice mutations are the one thing this module adds that the type side does
// not have: writing a choice must ALSO re-route any preview already open, or
// the person clicks "Prefer this" and nothing visibly changes. The write
// routes return the resulting effective choices, so the mutation applies that
// answer, bumps `panelChoiceVersion` (the routing epoch `DataPreview`
// feeds `PreviewHost`), and drops the session-envelope cache — the next
// session creation is routed by the backend through the new choice (#2049).

import { useEffect } from "react";

import { dataApi } from "../lib/api/data";
import type {
  PanelChoice,
  PanelChoiceListResponse,
  PanelChoiceScope,
  PanelSpecSummary,
} from "../types/api";

import { useAppStore } from "./index";

/**
 * The in-flight request, so N mounting surfaces produce one fetch rather than
 * N. Module-level rather than store state for the same reason as the type
 * catalogue's: a "loading" flag in the store would be a render-visible state
 * change no surface reads.
 */
let inFlight: Promise<void> | null = null;

/**
 * Choice-write epoch (#2153 review). A forced catalogue fetch reads the
 * choices list over the wire, and that read can be in flight while the user
 * writes a choice from the tab. The write route's response is the newer,
 * authoritative answer — `applyChoiceAnswer` applies it immediately — so a
 * fetch that STARTED before the write must not land afterwards and overwrite
 * the fresh choices with its stale list. Every choice mutation bumps this
 * counter; the fetch applies its choices only when the epoch is unchanged.
 */
let choiceWriteEpoch = 0;

/**
 * One round trip for both halves, unconditionally. A failure is warned and
 * swallowed: the catalogue is a listing *surface*, and the tab already renders
 * an empty state without it. The attempt is not latched, so the next surface
 * to mount retries.
 */
async function fetchPanelCatalog(): Promise<void> {
  try {
    const listing = await dataApi.listPanels();
    useAppStore.getState().setPanels(listing.previewers ?? [], listing.diagnostics ?? []);
  } catch (error) {
    console.warn("[panels] panel catalogue unavailable; keeping the empty state", error);
  }
  const choicesEpoch = choiceWriteEpoch;
  try {
    const choices = await dataApi.listPanelChoices();
    if (choicesEpoch === choiceWriteEpoch) {
      useAppStore.getState().setPanelChoices(choices.choices ?? []);
    }
  } catch (error) {
    console.warn("[panels] panel choices unavailable; keeping the empty state", error);
  }
}

/**
 * Fetch the panel catalogue into the store unless it is already there.
 *
 * `force` is how a caller says the cached answer is no longer true; every such
 * caller should go through {@link invalidatePanelCatalog}. A forced reload
 * queues *behind* an in-flight request instead of joining it — a fetch already
 * on the wire may predate the write that invalidated this cache.
 */
export function loadPanelCatalog(options?: { force?: boolean }): Promise<void> {
  const force = options?.force === true;
  if (!force && useAppStore.getState().panelsLoaded && useAppStore.getState().panelChoicesLoaded) {
    return Promise.resolve();
  }
  const pending = inFlight;
  if (pending && !force) {
    return pending;
  }
  const request = pending
    ? pending.then(fetchPanelCatalog, fetchPanelCatalog)
    : fetchPanelCatalog();
  const tracked: Promise<void> = request.finally(() => {
    if (inFlight === tracked) inFlight = null;
  });
  inFlight = tracked;
  return tracked;
}

/**
 * The registries changed — drop this cache and re-read it. Called from the
 * `blocks.reloaded` websocket dispatch for the same reason the type catalogue
 * is invalidated there (ADR-053 FR-062): without it the Panels tab would
 * sit on the first listing it ever fetched until someone pressed Reload by
 * hand, which is runtime truth living in frontend state.
 *
 * Re-reading the listing is not enough on its own. A preview that is already
 * open renders through the routing that was in force when its session was
 * created, and `PreviewHost` re-creates that session only when its target or
 * the routing epoch changes. A newly registered panel changes neither, so
 * the panel went on showing the old rendering — a project's own Image would
 * stay in the core Array number table until the person clicked away to empty
 * canvas and back, which is what makes `target` change. Bumping the epoch here
 * is what a manual panel choice already does (`applyChoiceAnswer`); the
 * two ways routing can change now behave the same.
 *
 * Unconditional rather than diffed against the previous listing: an edit to a
 * panel that is already registered changes what it draws without changing
 * any id, so a set comparison would miss exactly the case a person hits while
 * writing one. The cost is re-creating open preview sessions on any registry
 * reload, which is one request against a preview whose block may well have
 * changed too.
 */
export function invalidatePanelCatalog(): void {
  void loadPanelCatalog({ force: true }).then(() => {
    const store = useAppStore.getState();
    store.clearPreviewEnvelopeCache();
    store.bumpPanelChoiceVersion();
  });
}

/** Test seam — drop any in-flight request so each test starts clean. */
export function resetPanelCatalogLoader(): void {
  inFlight = null;
}

/**
 * Re-scan the drop-in panel directories, then re-read the listing and the
 * choices. Backs the tab's Reload button: the scan is the part that matters
 * (the listing endpoint answers from the in-memory registry), and the re-fetch
 * still runs when the scan fails so a reload that cannot reach the backend
 * leaves the tab showing what it had.
 */
export async function rescanPanels(): Promise<void> {
  try {
    await dataApi.reloadPanels();
  } catch (error) {
    console.error("Panels reload: backend re-scan failed", error);
  }
  await loadPanelCatalog({ force: true });
}

/**
 * Apply the effective-choices answer a choice write returned, then re-route
 * every open preview: bump the routing epoch (the open `PreviewHost` session
 * is re-created through the new choice) and drop the session-envelope cache
 * (its keys predate the choice).
 */
function applyChoiceAnswer(result: PanelChoiceListResponse): void {
  choiceWriteEpoch += 1;
  const store = useAppStore.getState();
  store.setPanelChoices(result.choices ?? []);
  store.clearPreviewEnvelopeCache();
  store.bumpPanelChoiceVersion();
}

/** Record `targetType -> panelId` at `scope` (#2049), then re-route. */
export async function choosePanel(
  targetType: string,
  panelId: string,
  scope: PanelChoiceScope,
): Promise<void> {
  const result = await dataApi.setPanelChoice(targetType, panelId, scope);
  applyChoiceAnswer(result);
}

/** Clear the choice for `targetType` at `scope`, then re-route. Clearing a
 *  project-layer choice reveals the user-layer choice it overrode (#2049). */
export async function clearPanelChoiceAt(
  targetType: string,
  scope: PanelChoiceScope,
): Promise<void> {
  const result = await dataApi.clearPanelChoice(targetType, scope);
  applyChoiceAnswer(result);
}

/**
 * Return a type to the routing ladder: clear BOTH layers. `Auto` means "no
 * preference anywhere", and clearing only the project layer would reveal the
 * user-layer choice underneath (#2049's reveal semantics) — correct for a
 * scoped Clear, wrong for Auto. Both DELETEs succeed even when the layer
 * holds nothing, so the second call is a cheap no-op in the common case.
 */
export async function clearPanelChoiceEverywhere(targetType: string): Promise<void> {
  try {
    await dataApi.clearPanelChoice(targetType, "project");
  } catch {
    // A project-scope clear 400s when no project is open — in which case no
    // project-layer choice can exist either, so the user-layer clear below is
    // the whole job.
  }
  const result = await dataApi.clearPanelChoice(targetType, "user");
  applyChoiceAnswer(result);
}

export interface PanelCatalog {
  panels: PanelSpecSummary[];
  /** False until the first listing lands — the tab's own loading window. */
  loaded: boolean;
  diagnostics: string[];
  choices: PanelChoice[];
  /** Re-scan the drop-in dirs, then re-fetch. Backs the tab's Reload button and its on-switch auto-reload (#2151). */
  reload: () => Promise<void>;
}

/** The full catalogue plus the effective choices, for the Panels tab. */
export function usePanelCatalog(): PanelCatalog {
  const panels = useAppStore((state) => state.panels);
  const loaded = useAppStore((state) => state.panelsLoaded);
  const diagnostics = useAppStore((state) => state.panelDiagnostics);
  const choices = useAppStore((state) => state.panelChoices);
  useEffect(() => {
    void loadPanelCatalog();
  }, []);
  return { panels, loaded, diagnostics, choices, reload: rescanPanels };
}
