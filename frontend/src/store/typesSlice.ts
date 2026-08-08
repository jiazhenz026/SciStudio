// The registered data type catalogue (ADR-053 §7, FR-026 / FR-027).
//
// One store-held copy of `GET /api/types/` serves both surfaces that need it:
// the Data types tab renders it, and canvas port + edge colour resolve
// declared colours out of it (FR-066). Holding it here rather than fetching it
// per surface is what makes FR-066 true by construction — there is one copy,
// so the palette and the canvas cannot be looking at different answers.
//
// `declaredTypeColors` is derived once at set time rather than per render.
// Canvas ports re-resolve colour on every paint, so a map rebuilt per render
// would be both wasted work and a new object identity on every frame; a stable
// map keeps the resolvers cheap and their memo dependencies honest.
//
// FR-067: `declaredTypeColors` is `undefined` until the listing lands, and the
// resolvers treat "absent" exactly as "declares nothing". The loading window
// therefore renders the pre-ADR-053 resolution rather than a placeholder, and
// every type that declares nothing looks identical before and after.

import type { StateCreator } from "zustand";

import { buildDeclaredTypeColors } from "../config/typeColorMap";

import type { AppStore, TypesSlice } from "./types";

export const createTypesSlice: StateCreator<AppStore, [], [], TypesSlice> = (set) => ({
  types: [],
  typesLoaded: false,
  declaredTypeColors: undefined,
  setTypes: (types) =>
    set({
      types,
      typesLoaded: true,
      declaredTypeColors: buildDeclaredTypeColors(types),
    }),
});
