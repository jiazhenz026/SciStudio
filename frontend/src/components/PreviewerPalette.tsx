// The Previewers tab — the left panel's fourth activity-bar section (#2113).
//
// One card per registered previewer, grouped by discovery tier (This Project /
// My Library / Core / packages A→Z) over the shared palette section machinery
// (`PreviewerPalette.parts/previewerModel` supplies the callbacks, as
// `TypePalette.parts/typeModel` does for the Data types tab).
//
// Three backend surfaces meet here:
//   - `GET /api/previews/previewers` (#2095) — the listing and the registry
//     diagnostics, which nothing else surfaces.
//   - `POST /api/previews/reload` (#2095) — the Reload button, the previewer
//     surface's own way to rebuild the registries without calling the block
//     endpoint.
//   - `GET/PUT/DELETE /api/previews/choices` (#2049) — the per-type choice
//     controls on each card, at both scopes (this project / all projects).
//
// Like the Data types tab (FR-027), the pane takes no props: it reads the
// previewer catalogue directly from the store, so opening it neither waits
// for nor re-triggers a blocks fetch.

import { useEffect, useRef, useState } from "react";

import { useReloadFlash } from "../hooks/useReloadFlash";
import { useAppStore } from "../store";
import {
  choosePreviewer,
  clearPreviewerChoiceAt,
  clearPreviewerChoiceEverywhere,
  usePreviewerCatalog,
} from "../store/usePreviewerCatalog";
import type { PreviewerChoice, PreviewerSpecSummary } from "../types/api";

import { PreviewerCard } from "./PreviewerPalette.parts/PreviewerCard";
import {
  buildPreviewerSections,
  choiceForType,
  isFilteringPreviewers,
  staleChoices,
  type PreviewerSection,
} from "./PreviewerPalette.parts/previewerModel";

interface SectionViewProps {
  section: PreviewerSection;
  forceOpen: boolean;
  choices: PreviewerChoice[];
}

function SectionView({ section, forceOpen, choices }: SectionViewProps) {
  const [collapsed, setCollapsed] = useState(false);
  const open = section.pinned || forceOpen || !collapsed;

  return (
    <section data-testid={`previewer-section-${section.id}`}>
      {section.pinned ? (
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.3em] text-stone-700">
          {section.title}
        </p>
      ) : (
        <button
          className="mb-2 flex w-full items-center gap-1 text-left"
          onClick={() => setCollapsed((prev) => !prev)}
          type="button"
        >
          <span className="text-[11px] text-stone-600">{open ? "▼" : "▶"}</span>
          <span className="text-[11px] font-semibold uppercase tracking-[0.3em] text-stone-700">
            {section.title}
          </span>
        </button>
      )}
      {open && section.items.length === 0 ? (
        <p
          className="px-1 text-[11px] leading-snug text-stone-500"
          data-testid="palette-section-empty"
        >
          {section.emptyHint}
        </p>
      ) : null}
      {open && section.items.length > 0 ? (
        <div className="flex flex-col gap-2">
          {section.items.map((previewer) => (
            <PreviewerCard
              choice={choiceForType(choices, previewer.target_type)}
              key={previewer.previewer_id}
              onChoose={(p, scope) => choosePreviewer(p.target_type, p.previewer_id, scope)}
              onClearEverywhere={clearPreviewerChoiceEverywhere}
              previewer={previewer}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

/**
 * One row per stale choice — a recorded preference whose previewer is not
 * registered right now (#2049: the choice outlives the package that provided
 * it). No card exists for it, so without this strip the choice would be both
 * invisible and un-clearable from the tab that owns choices.
 */
function StaleChoicesStrip({ choices }: { choices: PreviewerChoice[] }) {
  const stale = staleChoices(choices);
  if (stale.length === 0) return null;
  return (
    <div
      className="mt-3 rounded-xl border border-amber-300 bg-amber-50 p-2"
      data-testid="previewer-stale-choices"
    >
      <p className="px-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-amber-800">
        Unavailable choices
      </p>
      {stale.map((choice) => (
        <div
          className="mt-1 flex items-center justify-between gap-2 px-1"
          key={`${choice.target_type}-${choice.previewer_id}`}
        >
          <p className="text-[11px] text-amber-900">
            {choice.target_type} → {choice.previewer_id} ({choice.scope}) — not registered
          </p>
          <button
            className="shrink-0 rounded-full border border-amber-300 bg-white px-2 py-0.5 text-[11px] text-amber-900 hover:bg-amber-100"
            data-testid={`previewer-stale-clear-${choice.target_type}`}
            onClick={() => void clearPreviewerChoiceAt(choice.target_type, choice.scope)}
            type="button"
          >
            Clear
          </button>
        </div>
      ))}
    </div>
  );
}

export function PreviewerPalette() {
  const { previewers, loaded, diagnostics, choices, reload } = usePreviewerCatalog();
  // #2151 — same auto-reload-on-switch as the Data types tab: mounting this
  // pane *is* switching to the section (the panes are conditionally rendered),
  // so a mount that finds the catalogue already loaded is a revisit holding a
  // possibly stale cache. Do one automatic rescan — the path the Reload
  // button drives. A first-ever mount skips it (the hook's own load is
  // already fetching); the store is read imperatively so the effect sees the
  // mount-time snapshot rather than subscribing to `loaded` flipping true.
  // The ref latch keeps it to one rescan under StrictMode's dev effect
  // replay, which re-runs mount effects on the same instance (#2153 review).
  const didAutoReload = useRef(false);
  useEffect(() => {
    if (didAutoReload.current) return;
    didAutoReload.current = true;
    if (useAppStore.getState().previewersLoaded) {
      void reload();
    }
  }, [reload]);
  const [search, setSearch] = useState("");
  // Same one-shot blink the Blocks tab, the Data types tab, and the project
  // tree use, so every side panel confirms a completed reload identically.
  const { ref: contentRef, trigger: triggerFlash } = useReloadFlash<
    HTMLDivElement,
    PreviewerSpecSummary[]
  >(previewers);

  const handleReload = () => {
    triggerFlash();
    void reload();
  };

  const sections = buildPreviewerSections(previewers, search);
  const forceOpen = isFilteringPreviewers(search);

  return (
    <aside className="flex h-full flex-col overflow-hidden border-r border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))] p-4">
      <div className="flex items-center justify-between gap-2">
        {/* The panel names itself after its tab, so `Previewers` reads as a
            peer of `Blocks` and `Data types` (FR-034/FR-039). */}
        <p className="font-display text-xl text-ink">Previewers</p>
        <button className="toolbar-button" onClick={handleReload} type="button">
          Reload
        </button>
      </div>

      <div
        className="flex min-h-0 flex-1 flex-col"
        data-testid="previewer-palette-content"
        ref={contentRef}
      >
        <input
          className="mt-4 w-full rounded-2xl border border-stone-300 bg-white px-4 py-3 text-sm outline-none transition focus:border-ember"
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search previewers"
          value={search}
        />

        {/* Registry diagnostics (#2095): a duplicate previewer id or a refused
            drop-in was invisible before this surface existed. */}
        {diagnostics.length > 0 ? (
          <div
            className="mt-3 rounded-xl border border-amber-300 bg-amber-50 p-2"
            data-testid="previewer-diagnostics"
          >
            {diagnostics.map((line) => (
              <p className="px-1 text-[11px] leading-snug text-amber-900" key={line}>
                {line}
              </p>
            ))}
          </div>
        ) : null}

        <StaleChoicesStrip choices={choices} />

        <div className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto pb-6 scrollbar-thin">
          {sections.map((section) => (
            <SectionView
              choices={choices}
              forceOpen={forceOpen}
              key={section.id}
              section={section}
            />
          ))}
          {loaded && previewers.length === 0 ? (
            <p
              className="px-1 text-[11px] leading-snug text-stone-500"
              data-testid="previewer-palette-empty"
            >
              No previewers registered.
            </p>
          ) : null}
        </div>
      </div>
    </aside>
  );
}
