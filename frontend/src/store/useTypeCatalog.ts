// Loading and reading the registered data type catalogue (ADR-053 §7).
//
// Spec: docs/specs/adr-053-personal-tool-library.md
//   §7 FR-026/FR-027 (the listing, independent of the block listing),
//   §7.1 FR-050 (single source of type colour), FR-066 (the canvas reads it),
//   FR-067 (the loading window must be invisible).
//
// The load is demand-driven and shared. Any surface that needs the catalogue
// asks for it; the first ask fetches, later asks are answered from the store.
// That is what keeps FR-027 true without the canvas having to know the Data
// types tab exists, or the tab having to know a canvas is open: neither
// surface owns the fetch, and neither waits on a blocks request for it.
//
// FR-067 lives in what this module does NOT do. It never publishes a partial
// or placeholder catalogue: `declaredTypeColors` stays `undefined` until a
// complete listing lands, the colour resolvers read `undefined` as "declares
// nothing", and ports therefore render the pre-ADR-053 resolution during the
// window. Colour is a paint-only property — port geometry comes from
// `portRailOffset` and never from colour — so the transition cannot re-layout,
// and for a type that declares nothing the two answers are the same string, so
// there is nothing to see.
//
// Lives beside the slice rather than inside it because a zustand slice creator
// cannot reference the store it is being assembled into; importing
// `useAppStore` here (and never from `typesSlice.ts`) keeps `store/index.ts`
// the only module that assembles slices.

import { useEffect } from "react";

import { codeApi } from "../lib/api/code";
import type { DeclaredTypeColors } from "../config/typeColorMap";
import type { TypeSummary } from "../types/api";

import { useAppStore } from "./index";

/**
 * The in-flight request, so N mounting surfaces produce one fetch rather than
 * N. Module-level rather than store state on purpose: a "loading" flag in the
 * store would be a render-visible state change that no surface reads, and
 * writing it would be the one thing capable of introducing the flash FR-067
 * forbids.
 */
let inFlight: Promise<void> | null = null;

/**
 * Fetch the type catalogue into the store unless it is already there.
 *
 * A failure is warned and swallowed: the catalogue is a colour and listing
 * *enhancement*, and every consumer already renders correctly without it
 * (FR-067). Blocking or throwing here would turn a types-endpoint hiccup into
 * a broken canvas, which is precisely the failure mode FR-067 exists to
 * prevent. The attempt is not latched, so the next surface to mount retries.
 */
export async function loadTypeCatalog(options?: { force?: boolean }): Promise<void> {
  const force = options?.force === true;
  if (!force && useAppStore.getState().typesLoaded) {
    return;
  }
  if (inFlight) {
    return inFlight;
  }
  inFlight = (async () => {
    try {
      const payload = await codeApi.listTypes();
      useAppStore.getState().setTypes(payload.types ?? []);
    } catch (error) {
      console.warn(
        "[types] type catalogue unavailable; keeping the default colour resolution",
        error,
      );
    } finally {
      inFlight = null;
    }
  })();
  return inFlight;
}

/** Test seam — drop any in-flight request so each test starts clean. */
export function resetTypeCatalogLoader(): void {
  inFlight = null;
}

/**
 * The declared-colour lookup for the FR-051 precedence, loading it on first
 * use.
 *
 * Returns `undefined` until the listing lands. Callers pass the result
 * straight to `resolveTypeColor` / `resolveRingColor`, which treat `undefined`
 * as "nothing declared" — so a caller needs no loading branch of its own and
 * cannot accidentally invent a placeholder colour.
 */
export function useDeclaredTypeColors(): DeclaredTypeColors | undefined {
  const declared = useAppStore((state) => state.declaredTypeColors);
  useEffect(() => {
    void loadTypeCatalog();
  }, []);
  return declared;
}

export interface TypeCatalog {
  types: TypeSummary[];
  /** False until the first listing lands — the tab's own loading window. */
  loaded: boolean;
  declared: DeclaredTypeColors | undefined;
  /** Re-fetch, bypassing the cache. Backs the Data types tab's Reload. */
  reload: () => Promise<void>;
}

/** The full catalogue, for the Data types tab. */
export function useTypeCatalog(): TypeCatalog {
  const types = useAppStore((state) => state.types);
  const loaded = useAppStore((state) => state.typesLoaded);
  const declared = useAppStore((state) => state.declaredTypeColors);
  useEffect(() => {
    void loadTypeCatalog();
  }, []);
  return { types, loaded, declared, reload: () => loadTypeCatalog({ force: true }) };
}
