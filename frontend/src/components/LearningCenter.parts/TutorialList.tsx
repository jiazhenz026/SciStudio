/**
 * ADR-053 Learning Center (#2057) — the tab's tutorials, left column.
 *
 * Selecting a row shows it in the middle column; it does not start it. That
 * separation is what lets a user read what a tutorial is before committing to
 * one that will create a project on disk, and it is why FR-087's restart
 * confirmation has somewhere to live other than on top of the list.
 *
 * An unavailable tutorial is selectable. FR-085 requires the reason to be
 * shown, and the reason is in the detail column — a row that cannot be selected
 * is a reason the user cannot read.
 */

import { AlertTriangle, CheckCircle2, CircleDashed, Circle } from "lucide-react";

import type { TutorialCatalogueEntry } from "../../lib/api/learningCenter";
import { tutorialEntryKey } from "../../store/learningCenterSlice";

const STATE_ICONS: Record<TutorialCatalogueEntry["state"], typeof Circle> = {
  not_started: Circle,
  in_progress: CircleDashed,
  complete: CheckCircle2,
  unavailable: AlertTriangle,
};

const STATE_ICON_CLASS: Record<TutorialCatalogueEntry["state"], string> = {
  not_started: "text-stone-300",
  in_progress: "text-ember",
  complete: "text-pine",
  unavailable: "text-stone-400",
};

export function TutorialList({
  tutorials,
  selectedKey,
  onSelect,
  emptyMessage,
}: {
  tutorials: TutorialCatalogueEntry[];
  selectedKey: string | null;
  onSelect: (entry: TutorialCatalogueEntry) => void;
  emptyMessage: string;
}) {
  if (tutorials.length === 0) {
    return (
      <p className="px-4 py-6 text-sm leading-6 text-stone-500" data-testid="tutorial-list-empty">
        {emptyMessage}
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-0.5 p-2" data-testid="tutorial-list">
      {tutorials.map((entry, index) => {
        const key = tutorialEntryKey(entry);
        const selected = key === selectedKey;
        const Icon = STATE_ICONS[entry.state];
        return (
          <li key={key}>
            <button
              aria-current={selected ? "true" : undefined}
              className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm transition ${
                selected ? "bg-pine/10 text-ink" : "text-stone-600 hover:bg-stone-100"
              }`}
              data-testid={`tutorial-entry-${entry.source_kind}-${entry.source_id}-${entry.id}`}
              onClick={() => onSelect(entry)}
              type="button"
            >
              <Icon
                aria-hidden="true"
                className={`size-4 shrink-0 ${STATE_ICON_CLASS[entry.state]}`}
              />
              <span className="min-w-0 flex-1 truncate">{entry.title}</span>
              <span className="shrink-0 text-xs tabular-nums text-stone-400">{index + 1}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
