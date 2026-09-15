/**
 * ADR-054 (#2465) — the panel service's realtime signals, fanned out to the
 * mounts they concern.
 *
 * The `/ws` dispatcher calls the `notify*` / `request*` functions; the shared
 * panel host (`PanelFrame`) and the routed preview host (`PreviewHost`)
 * subscribe. A plain in-module registry rather than store state: these are
 * events, each mount decides for itself whether one concerns it, and nothing
 * is rendered from them. It imports nothing, so a panel host can listen
 * without pulling the whole store into a frame's module graph.
 *
 *  - `panel.files_changed {panel_id}` — a page file of an open panel changed.
 *    Every mount of that panel, whatever its context kind, reloads in place.
 *  - `panel.contexts_revoked {context_ids}` — the backend closed these
 *    contexts (their panel was removed, changed or shadowed, or the project
 *    was left). Only the mounts holding them remount.
 *  - preview re-route — the candidates for some type claims changed (a panel
 *    added, changed or removed), a choice changed for one type, or the legacy
 *    previewers were reloaded. Only previews the signal names re-route.
 */
import type { PreviewEnvelope, PreviewTarget } from "../types/api";

type Listener<T> = (value: T) => void;

function channel<T>() {
  const listeners = new Set<Listener<T>>();
  return {
    emit(value: T) {
      for (const listener of [...listeners]) listener(value);
    },
    subscribe(listener: Listener<T>): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

const filesChanged = channel<string>();
const contextsRevoked = channel<ReadonlySet<string>>();
const previewReroute = channel<PreviewRerouteSignal>();

/** FR-022 — a page file of `panelId` changed on disk. */
export function notifyPanelFilesChanged(panelId: string): void {
  filesChanged.emit(panelId);
}

/** Call `listener` whenever a page file of `panelId` changes. */
export function subscribePanelFilesChanged(panelId: string, listener: () => void): () => void {
  return filesChanged.subscribe((changed) => {
    if (changed === panelId) listener();
  });
}

/** The backend revoked these contexts. */
export function notifyPanelContextsRevoked(contextIds: readonly string[]): void {
  if (contextIds.length > 0) contextsRevoked.emit(new Set(contextIds));
}

/** Call `listener` when `contextId` is revoked. */
export function subscribePanelContextRevoked(contextId: string, listener: () => void): () => void {
  return contextsRevoked.subscribe((revoked) => {
    if (revoked.has(contextId)) listener();
  });
}

export interface PreviewRerouteSignal {
  /** Type claims (`panel.json` spelling) whose routing candidates changed. */
  types?: readonly string[];
  /** A previewer choice changed for exactly this type. */
  choiceType?: string;
  /** The legacy previewers were reloaded: legacy-rendered previews recreate their session. */
  legacy?: boolean;
}

/** Ask the open previews the signal concerns to re-route. */
export function requestPreviewReroute(signal: PreviewRerouteSignal): void {
  if (!signal.legacy && !signal.choiceType && !(signal.types && signal.types.length > 0)) return;
  previewReroute.emit(signal);
}

export function subscribePreviewReroute(listener: Listener<PreviewRerouteSignal>): () => void {
  return previewReroute.subscribe(listener);
}

/** The target's type names, specific first, and whether it is a collection. */
function targetTypes(target: PreviewTarget): { chain: string[]; collection: boolean } {
  const collection = target.kind === "collection_ref";
  const chain: string[] = [];
  const push = (name: string | null | undefined) => {
    if (name && !chain.includes(name)) chain.push(name);
  };
  if (collection) push(target.collection_item_type);
  for (const name of [...(target.type_chain ?? [])].reverse()) push(name);
  if (chain.length === 0 && !collection) push(target.recorded_type);
  return { chain, collection };
}

function claimAffects(claim: string, chain: readonly string[], collection: boolean): boolean {
  const wrapped = claim.startsWith("Collection[") && claim.endsWith("]");
  const claimsCollection = wrapped || claim === "Collection";
  if (claimsCollection !== collection) return false;
  if (claim === "Collection" || (!collection && claim === "DataObject")) return true;
  return chain.includes(wrapped ? claim.slice(11, -1) : claim);
}

/**
 * Whether a preview showing `envelope` must re-route for `signal`: its data
 * type (type chain and collection-ness) is one the changed claims or the
 * changed choice concern, or it is rendered by a legacy previewer and those
 * were reloaded.
 */
export function previewIsAffected(
  envelope: PreviewEnvelope,
  signal: PreviewRerouteSignal,
): boolean {
  if (signal.legacy && envelope.kind !== "panel") return true;
  const { chain, collection } = targetTypes(envelope.target);
  if (signal.choiceType && chain[0] === signal.choiceType) return true;
  return (signal.types ?? []).some((claim) => claimAffects(claim, chain, collection));
}
