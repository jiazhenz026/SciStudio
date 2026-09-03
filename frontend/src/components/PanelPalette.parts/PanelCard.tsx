// One panel card in the Panels tab (#2113).
//
// The card answers three questions at a glance: what is this panel (id,
// target type, features), where did it come from (tier section + owner),
// and is it the one rendering its type right now. The choice control is a
// three-way segmented selector — Auto / This project / All projects (owner
// call in the #2119 live review): Auto is the default and means "no recorded
// preference, the FR-003 ladder decides"; the active segment is highlighted.
//
// The selector's state is per card, not per type: a card whose panel does
// not hold the type's choice reads Auto — clicking Auto there changes nothing,
// because clearing from an unchosen card would silently delete a preference
// that points at a *different* panel. On the chosen card, Auto clears both
// layers for the type, so it deterministically returns to the ladder rather
// than revealing a user-layer choice underneath (#2049's reveal semantics).

import { useState } from "react";

import type { PanelChoice, PanelSpecSummary } from "../../types/api";

import { ownerKindLabel } from "./panelModel";

type ChoiceSegment = "auto" | "project" | "user";

const SEGMENTS: readonly { key: ChoiceSegment; label: string; title: string }[] = [
  {
    key: "auto",
    label: "Auto",
    title: "No preference — the routing ladder decides (project > user > package > core)",
  },
  {
    key: "project",
    label: "This project",
    title: "Render this type with this previewer in this project only",
  },
  {
    key: "user",
    label: "All projects",
    title: "Render this type with this previewer in every project",
  },
];

export interface PanelCardProps {
  panel: PanelSpecSummary;
  /** The effective choice for this card's `target_type`, or `null` when the
   *  type is unchosen. */
  choice: PanelChoice | null;
  onChoose: (panel: PanelSpecSummary, scope: "user" | "project") => Promise<void>;
  /** Clear the choice for the type at BOTH layers — the Auto segment. */
  onClearEverywhere: (targetType: string) => Promise<void>;
}

export function PanelCard({ panel, choice, onChoose, onClearEverywhere }: PanelCardProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isChosen = choice !== null && choice.previewer_id === panel.previewer_id;
  // Another panel holds the choice for this type — say so on this card, or
  // its Auto highlight would read as "no preference exists for this type".
  const choiceHeldElsewhere = choice !== null && !isChosen;
  const active: ChoiceSegment = isChosen ? choice.scope : "auto";

  const run = (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    void action()
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setBusy(false));
  };

  const select = (segment: ChoiceSegment) => {
    if (segment === active) return;
    if (segment === "auto") {
      // Only the chosen card's Auto can change anything (see the module
      // comment): an unchosen card is already at Auto for this panel.
      if (isChosen) {
        run(() => onClearEverywhere(panel.target_type));
      }
      return;
    }
    run(() => onChoose(panel, segment));
  };

  return (
    <div
      className="rounded-xl border border-stone-200 bg-white p-3 shadow-sm"
      data-testid={`panel-card-${panel.previewer_id}`}
    >
      <p className="break-all text-sm font-medium text-ink">{panel.previewer_id}</p>

      <p className="mt-1 text-[11px] text-stone-500">
        renders <span className="font-medium text-stone-700">{panel.target_type}</span>
        {panel.supports_collection ? " (and collections)" : ""}
      </p>
      <p className="mt-0.5 text-[11px] text-stone-500">
        {ownerKindLabel(panel.owner_kind)}
        {panel.owner_kind === "package" && panel.owner_name ? ` · ${panel.owner_name}` : ""}
        {panel.frontend_manifest ? " · custom UI" : ""}
      </p>

      {choiceHeldElsewhere ? (
        <p className="mt-1 text-[11px] text-stone-500" data-testid="panel-current-choice">
          Current choice: <span className="font-medium text-stone-700">{choice.previewer_id}</span>
          {choice.available ? "" : " (not registered)"}
        </p>
      ) : null}

      <div
        aria-label={`Previewer choice for ${panel.target_type}`}
        className="mt-2 inline-flex overflow-hidden rounded-full border border-stone-300 bg-white shadow-sm"
        data-testid="panel-choice-segments"
        role="group"
      >
        {SEGMENTS.map((segment, index) => {
          const isActive = segment.key === active;
          return (
            <button
              aria-pressed={isActive}
              className={`px-2.5 py-1 text-[11px] transition disabled:opacity-50 ${
                index > 0 ? "border-l border-stone-200" : ""
              } ${
                isActive
                  ? "bg-ember/15 font-semibold text-ember shadow-inner"
                  : "text-stone-500 hover:bg-stone-50 hover:text-stone-700"
              }`}
              data-testid={`panel-seg-${segment.key}`}
              disabled={busy}
              key={segment.key}
              onClick={() => select(segment.key)}
              title={segment.title}
              type="button"
            >
              {segment.label}
            </button>
          );
        })}
      </div>

      {error ? (
        <p className="mt-1 text-[11px] text-red-700" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
