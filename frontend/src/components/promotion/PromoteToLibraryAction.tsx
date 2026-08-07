// "Save to My Library" — the one promotion control, rendered at E1, E2 and E5.
//
// Spec: docs/specs/adr-053-personal-tool-library.md
//   §6   FR-019 (offered only for a resolved origin of `project`; **hidden**,
//        not shown disabled, for built-in, packaged, and already-in-library
//        items),
//   §6.2 FR-025 (E1, E2, E3 and E5 share one implementation).
//
// The three frontend entry points render *this component*, and it calls
// `runPromotion`, which calls the one action. Nothing about the collision
// prompt, the cascade offer, or the reveal is restated per entry point — the
// entry points differ only in `variant` and in how `promotable.ts` built the
// item they pass.
//
//   E1  Block source editor toolbar   `Toolbar.parts/FileOperationsGroup`
//   E2  Canvas node action toolbar    `nodes/BlockNode`
//   E5  Palette hover popovers        `BlockPalette` and `TypePalette`

import { Library } from "lucide-react";
import { useState } from "react";

import { isPromotable, type PromotableItem } from "./promotable";
import { runPromotion } from "./runPromotion";

export type PromoteActionVariant = "popover" | "toolbar" | "icon";

export interface PromoteToLibraryActionProps {
  /** The resolved item, or `null` when the surface has nothing promotable. */
  item: PromotableItem | null;
  variant?: PromoteActionVariant;
  /** Which entry point rendered it — surfaced for tests and telemetry. */
  entryPoint: "E1" | "E2" | "E5";
}

const LABEL = "Save to My Library";

const VARIANT_CLASS: Record<PromoteActionVariant, string> = {
  popover:
    "flex w-full items-center justify-center gap-1.5 rounded-lg border border-stone-200 px-2 py-1.5 text-[11px] font-medium text-ink transition hover:border-ink hover:bg-white disabled:opacity-60",
  toolbar:
    "inline-flex shrink-0 items-center gap-1.5 rounded-full border border-stone-300 px-3 py-1 text-xs font-medium text-stone-600 transition hover:bg-stone-100 disabled:opacity-60",
  icon: "nodrag rounded p-1 text-stone-400 transition-colors hover:bg-stone-100 hover:text-ink disabled:opacity-60",
};

export function PromoteToLibraryAction({
  item,
  variant = "popover",
  entryPoint,
}: PromoteToLibraryActionProps) {
  const [busy, setBusy] = useState(false);

  // FR-019 — hidden, not disabled. A built-in, packaged, or already-promoted
  // item can never become promotable, so a greyed-out control would advertise
  // an action that will never light up.
  if (!isPromotable(item)) {
    return null;
  }

  const start = (event: React.MouseEvent) => {
    event.stopPropagation();
    if (busy) return;
    setBusy(true);
    void runPromotion(item).finally(() => setBusy(false));
  };

  return (
    <button
      aria-label={LABEL}
      className={VARIANT_CLASS[variant]}
      data-entry-point={entryPoint}
      data-testid="promote-to-library-action"
      disabled={busy}
      onClick={start}
      title={LABEL}
      type="button"
    >
      <Library aria-hidden="true" className={variant === "icon" ? "size-3.5" : "size-3.5"} />
      {variant === "icon" ? null : <span>{LABEL}</span>}
    </button>
  );
}
