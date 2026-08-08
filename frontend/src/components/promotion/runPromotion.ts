// The application's single call into the promotion action.
//
// Spec: docs/specs/adr-053-personal-tool-library.md §6.2 FR-025 — E1, E2, E3
// and E5 share one implementation, "four copies of this logic is exactly the
// drift this spec is written to avoid". E3 is the backend MCP tool; the three
// frontend entry points all reach `promoteToUserLibrary` through this function
// and nowhere else, so `promoteToUserLibrary(` appears exactly twice in the
// frontend: its definition, and the line below.
//
// It is also where the three cross-cutting obligations that are not the
// action's own business are discharged: binding the io to the open project,
// FR-020's reveal, and FR-020's inline confirmation.

import { useAppStore } from "../../store";

import {
  askCollisionResolution,
  askPromotionConfirmation,
  showPromotionResult,
} from "./dialogChannel";
import type { PromotableItem } from "./promotable";
import { promoteToUserLibrary, type PromotionOutcome } from "./promoteToUserLibrary";
import { createPromotionIo } from "./promotionIo";
import { revealInLibrary } from "./revealInLibrary";

export async function runPromotion(item: PromotableItem): Promise<PromotionOutcome> {
  const projectId = useAppStore.getState().currentProject?.id ?? null;
  const outcome = await promoteToUserLibrary(item, {
    io: createPromotionIo(projectId),
    prompts: {
      confirm: askPromotionConfirmation,
      resolveCollision: askCollisionResolution,
    },
  });

  if (outcome.status === "promoted") {
    // FR-020 — land the user looking at `My Library`, the section this whole
    // feature exists to teach. It brings that section into view; it does not
    // filter the palette down to the item, which read as the palette breaking.
    revealInLibrary(item.target === "types" ? "types" : "blocks");
  }
  if (outcome.status !== "cancelled") {
    // A cancellation is the user's own decision and needs no confirmation; a
    // success and a failure both do — and so does a `partial`, which is a
    // cancellation the library did not fully honour: cascade files were
    // already written and stay written. Suppressing that notice was the one
    // case where the UI looked like nothing had happened while My Library had
    // in fact changed.
    showPromotionResult(outcome);
  }
  return outcome;
}
