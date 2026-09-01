/**
 * OpenAsDialog — "open this file as which type?" (#2112).
 *
 * Several registered types can load the same extension: with the imaging
 * package installed and a project-local `SRSImage`, a `.tif` is loadable as
 * `Image`, `SRSImage`, or a plain `Artifact`. Which one is right is a fact
 * about the data, so the person picks, and the choice can be remembered for
 * the extension in the open project.
 *
 * Promise-based like {@link PromptDialog}, because the caller is
 * `ProjectTree`'s plain async double-click handler rather than a component:
 * `requestOpenAs(...)` resolves with the picked type (and whether to remember
 * it), or null on cancel. The dialog mounts once in `App` and listens.
 */

import { useEffect, useState } from "react";

import { type PendingOpenAs, subscribeToOpenAsRequests } from "./OpenAsDialog.parts/request";
import type { DataOpenAsCandidate } from "../types/api";

function tierLabel(candidate: DataOpenAsCandidate): string {
  if (candidate.origin === "package") return candidate.package_name ?? "package";
  if (candidate.origin === "project") return "this project";
  if (candidate.origin === "user") return "your library";
  if (candidate.origin === "core") return "built in";
  return candidate.origin || "unknown";
}

export function OpenAsDialog() {
  const [request, setRequest] = useState<PendingOpenAs | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [remember, setRemember] = useState(true);

  useEffect(() => subscribeToOpenAsRequests(setRequest), []);

  // Reseed each time a new request opens: the remembered type when the picker
  // was reopened to change it, else the first (most specific tier) candidate.
  useEffect(() => {
    if (request === null) return;
    setSelected(request.remembered ?? request.candidates[0]?.name ?? "");
    setRemember(true);
  }, [request]);

  if (request === null) return null;

  const finish = (answer: { typeName: string; remember: boolean } | null) => {
    request.resolve(answer);
    setRequest(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-950/55 p-4 backdrop-blur-sm">
      <div
        aria-modal="true"
        role="dialog"
        className="w-full max-w-md rounded-[1.5rem] border border-stone-200 bg-stone-50 p-6 shadow-panel"
        data-testid="open-as-dialog"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            finish(null);
          }
        }}
      >
        <h2 className="font-display text-2xl text-ink">Open as</h2>
        <p className="mt-1 truncate text-sm text-stone-600" title={request.displayName}>
          {request.displayName}
        </p>

        <div className="mt-5 max-h-72 space-y-2 overflow-y-auto scrollbar-thin">
          {request.candidates.map((candidate) => (
            <label
              key={candidate.name}
              className={`flex cursor-pointer gap-3 rounded-xl border px-3 py-2 transition ${
                selected === candidate.name
                  ? "border-ink bg-white"
                  : "border-stone-200 bg-white/50 hover:border-stone-300"
              }`}
            >
              <input
                checked={selected === candidate.name}
                className="mt-1 accent-ink"
                name="open-as-type"
                onChange={() => setSelected(candidate.name)}
                type="radio"
                value={candidate.name}
              />
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-2">
                  <span className="text-sm font-medium text-ink">{candidate.name}</span>
                  <span className="text-[11px] text-stone-500">{tierLabel(candidate)}</span>
                </span>
                {candidate.description ? (
                  <span className="mt-0.5 block line-clamp-2 text-xs text-stone-600">
                    {candidate.description}
                  </span>
                ) : null}
                {candidate.loadable ? null : (
                  <span className="mt-0.5 block text-xs text-stone-500">
                    No loader for {request.extension} — opens as a plain file.
                  </span>
                )}
              </span>
            </label>
          ))}
        </div>

        <label className="mt-4 flex items-center gap-2 text-sm text-stone-700">
          <input
            checked={remember}
            className="accent-ink"
            onChange={(event) => setRemember(event.currentTarget.checked)}
            type="checkbox"
            data-testid="open-as-remember"
          />
          Remember for {request.extension} files in this project
        </label>

        <div className="mt-6 flex justify-end gap-3">
          <button
            className="rounded-full border border-stone-300 px-4 py-2 text-sm"
            onClick={() => finish(null)}
            type="button"
          >
            Cancel
          </button>
          <button
            className="rounded-full bg-ink px-5 py-2 text-sm font-medium text-stone-50 transition hover:bg-pine disabled:opacity-50"
            disabled={selected === ""}
            onClick={() => finish({ typeName: selected, remember })}
            type="button"
            data-testid="open-as-submit"
          >
            Open
          </button>
        </div>
      </div>
    </div>
  );
}
