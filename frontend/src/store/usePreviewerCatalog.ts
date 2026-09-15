// Loading and reading the registered previewer catalogue and the person's
// per-type previewer choices (#2113, over #2095's discovery/reload routes and
// #2049's choice routes).
//
// The shape mirrors `useTypeCatalog` (ADR-053 §7) deliberately: the load is
// demand-driven and shared, and `invalidatePreviewerCatalog` re-reads it when
// the panel service says the preview candidates or the choices changed.
//
// Re-routing open previews is not this module's job any more (#2465). The
// panel service names what changed — the type claims whose candidates moved
// (`blocks.reloaded` from the panel registry), the one type whose choice moved
// (`panel.choices_changed`), or a legacy previewer reload — and only the open
// previews of those types re-create their session (`panels/panelEvents`). A
// choice write applies the effective choices it returned; the re-route follows
// the backend's `panel.choices_changed`.

import { useEffect } from "react";

import { dataApi } from "../lib/api/data";
import type {
  PreviewerChoice,
  PreviewerChoiceListResponse,
  PreviewerChoiceScope,
  PreviewerSpecSummary,
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
async function fetchPreviewerCatalog(): Promise<void> {
  try {
    const listing = await dataApi.listPreviewers();
    useAppStore.getState().setPreviewers(listing.previewers ?? [], listing.diagnostics ?? []);
  } catch (error) {
    console.warn("[previewers] previewer catalogue unavailable; keeping the empty state", error);
  }
  const choicesEpoch = choiceWriteEpoch;
  try {
    const choices = await dataApi.listPreviewerChoices();
    if (choicesEpoch === choiceWriteEpoch) {
      useAppStore.getState().setPreviewerChoices(choices.choices ?? []);
    }
  } catch (error) {
    console.warn("[previewers] previewer choices unavailable; keeping the empty state", error);
  }
}

/**
 * Fetch the previewer catalogue into the store unless it is already there.
 *
 * `force` is how a caller says the cached answer is no longer true; every such
 * caller should go through {@link invalidatePreviewerCatalog}. A forced reload
 * queues *behind* an in-flight request instead of joining it — a fetch already
 * on the wire may predate the write that invalidated this cache.
 */
export function loadPreviewerCatalog(options?: { force?: boolean }): Promise<void> {
  const force = options?.force === true;
  if (
    !force &&
    useAppStore.getState().previewersLoaded &&
    useAppStore.getState().previewerChoicesLoaded
  ) {
    return Promise.resolve();
  }
  const pending = inFlight;
  if (pending && !force) {
    return pending;
  }
  const request = pending
    ? pending.then(fetchPreviewerCatalog, fetchPreviewerCatalog)
    : fetchPreviewerCatalog();
  const tracked: Promise<void> = request.finally(() => {
    if (inFlight === tracked) inFlight = null;
  });
  inFlight = tracked;
  return tracked;
}

/**
 * The preview candidates or the choices changed — drop this cache and re-read
 * it, so the Previewers tab does not sit on the first listing it ever fetched.
 * Called only when the panel service says so (#2465): an unrelated registry
 * reload leaves the listing, and every open preview, alone. The session
 * envelope cache is dropped too, since its keys predate the change.
 */
export function invalidatePreviewerCatalog(): void {
  void loadPreviewerCatalog({ force: true }).then(() => {
    useAppStore.getState().clearPreviewEnvelopeCache();
  });
}

/** Test seam — drop any in-flight request so each test starts clean. */
export function resetPreviewerCatalogLoader(): void {
  inFlight = null;
}

/**
 * Re-scan the drop-in previewer directories, then re-read the listing and the
 * choices. Backs the tab's Reload button: the scan is the part that matters
 * (the listing endpoint answers from the in-memory registry), and the re-fetch
 * still runs when the scan fails so a reload that cannot reach the backend
 * leaves the tab showing what it had.
 */
export async function rescanPreviewers(): Promise<void> {
  try {
    await dataApi.reloadPreviewers();
  } catch (error) {
    console.error("Previewers reload: backend re-scan failed", error);
  }
  await loadPreviewerCatalog({ force: true });
}

/**
 * Apply the effective-choices answer a choice write returned and drop the
 * session-envelope cache (its keys predate the choice). The open previews of
 * the chosen type re-route on the backend's `panel.choices_changed` (#2465).
 */
function applyChoiceAnswer(result: PreviewerChoiceListResponse): void {
  choiceWriteEpoch += 1;
  const store = useAppStore.getState();
  store.setPreviewerChoices(result.choices ?? []);
  store.clearPreviewEnvelopeCache();
}

/** Record `targetType -> previewerId` at `scope` (#2049). */
export async function choosePreviewer(
  targetType: string,
  previewerId: string,
  scope: PreviewerChoiceScope,
): Promise<void> {
  const result = await dataApi.setPreviewerChoice(targetType, previewerId, scope);
  applyChoiceAnswer(result);
}

/** Clear the choice for `targetType` at `scope`. Clearing a
 *  project-layer choice reveals the user-layer choice it overrode (#2049). */
export async function clearPreviewerChoiceAt(
  targetType: string,
  scope: PreviewerChoiceScope,
): Promise<void> {
  const result = await dataApi.clearPreviewerChoice(targetType, scope);
  applyChoiceAnswer(result);
}

/**
 * Return a type to the routing ladder: clear BOTH layers. `Auto` means "no
 * preference anywhere", and clearing only the project layer would reveal the
 * user-layer choice underneath (#2049's reveal semantics) — correct for a
 * scoped Clear, wrong for Auto. Both DELETEs succeed even when the layer
 * holds nothing, so the second call is a cheap no-op in the common case.
 */
export async function clearPreviewerChoiceEverywhere(targetType: string): Promise<void> {
  try {
    await dataApi.clearPreviewerChoice(targetType, "project");
  } catch {
    // A project-scope clear 400s when no project is open — in which case no
    // project-layer choice can exist either, so the user-layer clear below is
    // the whole job.
  }
  const result = await dataApi.clearPreviewerChoice(targetType, "user");
  applyChoiceAnswer(result);
}

export interface PreviewerCatalog {
  previewers: PreviewerSpecSummary[];
  /** False until the first listing lands — the tab's own loading window. */
  loaded: boolean;
  diagnostics: string[];
  choices: PreviewerChoice[];
  /** Re-scan the drop-in dirs, then re-fetch. Backs the tab's Reload button and its on-switch auto-reload (#2151). */
  reload: () => Promise<void>;
}

/** The full catalogue plus the effective choices, for the Previewers tab. */
export function usePreviewerCatalog(): PreviewerCatalog {
  const previewers = useAppStore((state) => state.previewers);
  const loaded = useAppStore((state) => state.previewersLoaded);
  const diagnostics = useAppStore((state) => state.previewerDiagnostics);
  const choices = useAppStore((state) => state.previewerChoices);
  useEffect(() => {
    void loadPreviewerCatalog();
  }, []);
  return { previewers, loaded, diagnostics, choices, reload: rescanPreviewers };
}
