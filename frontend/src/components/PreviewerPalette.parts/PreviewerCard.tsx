// One previewer card in the Previewers tab (#2113).
//
// The card answers three questions at a glance: what is this previewer (id,
// target type, capabilities), where did it come from (tier section + owner),
// and is it the one rendering its type right now (the choice badge). The
// choice controls are the card's job rather than a separate settings surface
// because the choice *is* about the card: "render this type with THIS
// previewer" (#2049).
//
// Two scopes, two buttons — `This project` writes the project layer, `All
// projects` the user layer. Both come from the same card rather than a
// dropdown: two labelled buttons are one click each and say exactly where the
// preference will live, which is the distinction the person is choosing on.

import { useState } from "react";

import type { PreviewerChoice, PreviewerSpecSummary } from "../../types/api";

import { ownerKindLabel } from "./previewerModel";

export interface PreviewerCardProps {
  previewer: PreviewerSpecSummary;
  /** The effective choice for this card's `target_type`, or `null` when the
   *  type is unchosen. */
  choice: PreviewerChoice | null;
  onChoose: (previewer: PreviewerSpecSummary, scope: "user" | "project") => Promise<void>;
  onClear: (targetType: string, scope: "user" | "project") => Promise<void>;
}

export function PreviewerCard({ previewer, choice, onChoose, onClear }: PreviewerCardProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isChosen = choice !== null && choice.previewer_id === previewer.previewer_id;
  // Another previewer holds the choice for this type — say so on this card,
  // or choosing here reads as if nothing was set before.
  const choiceHeldElsewhere = choice !== null && !isChosen;

  const run = (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    void action()
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setBusy(false));
  };

  return (
    <div
      className="rounded-xl border border-stone-200 bg-white p-3 shadow-sm"
      data-testid={`previewer-card-${previewer.previewer_id}`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="break-all text-sm font-medium text-ink">{previewer.previewer_id}</p>
        {isChosen ? (
          <span
            className="shrink-0 rounded-full bg-ember/15 px-2 py-0.5 text-[10px] font-semibold text-ember"
            data-testid="previewer-choice-badge"
          >
            {choice.scope === "project" ? "Preferred · this project" : "Preferred · all projects"}
          </span>
        ) : null}
      </div>

      <p className="mt-1 text-[11px] text-stone-500">
        renders <span className="font-medium text-stone-700">{previewer.target_type}</span>
        {previewer.supports_collection ? " (and collections)" : ""}
      </p>
      <p className="mt-0.5 text-[11px] text-stone-500">
        {ownerKindLabel(previewer.owner_kind)}
        {previewer.owner_kind === "package" && previewer.owner_name
          ? ` · ${previewer.owner_name}`
          : ""}
        {previewer.frontend_manifest ? " · custom UI" : ""}
      </p>

      {choiceHeldElsewhere ? (
        <p className="mt-1 text-[11px] text-stone-500" data-testid="previewer-current-choice">
          Current choice: <span className="font-medium text-stone-700">{choice.previewer_id}</span>
          {choice.available ? "" : " (not registered)"}
        </p>
      ) : null}

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {isChosen ? (
          <button
            className="rounded-lg border border-stone-300 bg-stone-50 px-2.5 py-1 text-[11px] font-medium text-stone-600 shadow-sm transition hover:border-red-300 hover:bg-white hover:text-red-700 disabled:opacity-50"
            data-testid="previewer-choice-clear"
            disabled={busy}
            onClick={() => run(() => onClear(previewer.target_type, choice.scope))}
            type="button"
          >
            Clear preference
          </button>
        ) : (
          <>
            <span className="text-[11px] font-medium text-stone-500">Prefer:</span>
            <button
              className="rounded-lg border border-stone-300 bg-stone-50 px-2.5 py-1 text-[11px] font-medium text-stone-700 shadow-sm transition hover:border-ember hover:bg-white hover:text-ember disabled:opacity-50"
              data-testid="previewer-choose-project"
              disabled={busy}
              onClick={() => run(() => onChoose(previewer, "project"))}
              title="Render this type with this previewer in this project only"
              type="button"
            >
              this project
            </button>
            <button
              className="rounded-lg border border-stone-300 bg-stone-50 px-2.5 py-1 text-[11px] font-medium text-stone-700 shadow-sm transition hover:border-ember hover:bg-white hover:text-ember disabled:opacity-50"
              data-testid="previewer-choose-user"
              disabled={busy}
              onClick={() => run(() => onChoose(previewer, "user"))}
              title="Render this type with this previewer in every project"
              type="button"
            >
              all projects
            </button>
          </>
        )}
      </div>

      {error ? (
        <p className="mt-1 text-[11px] text-red-700" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
