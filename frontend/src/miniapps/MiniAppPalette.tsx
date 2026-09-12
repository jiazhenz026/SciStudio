// The MiniApps tab — the left panel's fifth activity-bar section.
//
// Spec: docs/specs/adr-054-miniapp.md
//   FR-031 (this tab replaces the Previewers tab in the same slot: every panel
//     declaring `miniapp`, grouped by tier, with a search box, a New MiniApp
//     button, and a double-click that opens the MiniApp),
//   FR-032 (the shared hover popover: description, declared type, tier,
//     directory, and Promote to My Library for a project MiniApp only),
//   FR-034 (opening asks for a target — the picker is the workspace's, reached
//     through `onOpen`),
//   FR-039 (promotion goes through the shared implementation, ADR-053 FR-025).
//
// The tab is built out of the same three shared pieces the Blocks and Data
// types tabs are built out of — `palette/sections` for the tier skeleton,
// `palette/hoverPopover` for the hover state machine, `palette/DetailPopover`
// for the card — so a fourth catalogue surface reads like the other three
// rather than like a new invention (ADR-053 §10.1 FR-047).
//
// It owns no opening and no creating: `onOpen` and `onCreate` are the
// workspace's, because the target picker (FR-034) and the create dialog
// (FR-024) are dialogs mounted beside the whole workspace, not inside a
// sidebar pane that a tab switch unmounts.

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { DetailPopover } from "../components/palette/DetailPopover";
import { useHoverPopover } from "../components/palette/hoverPopover";
import { buildSections, filterItems, withoutEmptyHints } from "../components/palette/sections";
import type { Section, SectionSlot } from "../components/palette/sections";
import { useDialogChannel } from "../components/promotion/dialogChannel";
import { PromoteToLibraryAction } from "../components/promotion/PromoteToLibraryAction";
import { promotableMiniApp } from "../components/promotion/promotable";

import { miniAppsApi } from "./api";
import type { MiniAppSummary } from "./types";

/** Stable id for the project-local section (`{project}/panels/`). */
const PROJECT_SECTION_ID = "__this_project__";
/** Stable id for the user-wide library section (`~/.scistudio/panels/`). */
const USER_LIBRARY_SECTION_ID = "__user_library__";
/** Stable id for the core section (MiniApps shipped with SciStudio). */
const CORE_SECTION_ID = "__core__";
/** Section a package-tier MiniApp collects in. */
const PACKAGES_SECTION_ID = "Packages";

/**
 * The ordered head of the MiniApps section list — the same skeleton the
 * Previewers tab used and the Blocks and Data types tabs still use: the two
 * drop-in tiers lead and render even when empty, Core keeps a stable position,
 * and package MiniApps close the list as the A→Z remainder.
 */
const MINIAPP_SECTION_SLOTS: readonly SectionSlot[] = [
  {
    id: PROJECT_SECTION_ID,
    title: "This Project",
    emptyHint:
      "No MiniApps in this project yet. Ask the agent for one and it lands here, next to the data it opens on.",
  },
  {
    id: USER_LIBRARY_SECTION_ID,
    title: "My Library",
    emptyHint: "No MiniApps of your own yet. Move one here and every project can open it.",
  },
  { id: CORE_SECTION_ID, title: "Core" },
];

/** The section a MiniApp belongs to — its discovery tier. */
function miniAppSectionIdFor(miniapp: MiniAppSummary): string {
  switch (miniapp.tier) {
    case "project":
      return PROJECT_SECTION_ID;
    case "user":
      return USER_LIBRARY_SECTION_ID;
    case "core":
      return CORE_SECTION_ID;
    default:
      return PACKAGES_SECTION_ID;
  }
}

/** Human label for a tier, used on the card and in the popover. */
function tierLabel(tier: MiniAppSummary["tier"]): string {
  switch (tier) {
    case "project":
      return "This Project";
    case "user":
      return "My Library";
    case "package":
      return "Package";
    default:
      return "Core";
  }
}

/** Text a MiniApp is searched by: name, id, declared type, description. */
function miniAppHaystack(miniapp: MiniAppSummary): string {
  return `${miniapp.name} ${miniapp.panel_id} ${miniapp.type} ${miniapp.description}`;
}

const byName = (a: MiniAppSummary, b: MiniAppSummary): number =>
  a.name.localeCompare(b.name) || a.panel_id.localeCompare(b.panel_id);

/**
 * Build the ordered MiniApps sections. Under an active search the teaching
 * empty states drop out — "No MiniApps of your own yet" is a statement about
 * the library, not about the current query.
 */
function buildMiniAppSections(
  miniapps: readonly MiniAppSummary[],
  search: string,
): Section<MiniAppSummary>[] {
  const visible = filterItems(miniapps, search, miniAppHaystack);
  const filtering = search.trim().length > 0;
  const slots = filtering ? withoutEmptyHints(MINIAPP_SECTION_SLOTS) : MINIAPP_SECTION_SLOTS;
  return buildSections(visible, miniAppSectionIdFor, slots, byName);
}

interface SectionViewProps {
  section: Section<MiniAppSummary>;
  forceOpen: boolean;
  onOpen: (miniapp: MiniAppSummary) => void;
  onEnter: (miniapp: MiniAppSummary, rect: DOMRect) => void;
  onLeave: () => void;
}

function SectionView({ section, forceOpen, onOpen, onEnter, onLeave }: SectionViewProps) {
  const [collapsed, setCollapsed] = useState(false);
  const open = section.pinned || forceOpen || !collapsed;

  return (
    <section data-testid={`miniapp-section-${section.id}`}>
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
          {section.items.map((miniapp) => (
            <MiniAppCard
              key={miniapp.panel_id}
              miniapp={miniapp}
              onEnter={onEnter}
              onLeave={onLeave}
              onOpen={onOpen}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

interface MiniAppCardProps {
  miniapp: MiniAppSummary;
  onOpen: (miniapp: MiniAppSummary) => void;
  onEnter: (miniapp: MiniAppSummary, rect: DOMRect) => void;
  onLeave: () => void;
}

/**
 * One MiniApp card: the name, and the type it opens on (FR-031).
 *
 * A click opens the detail popover the hover opens, so the card's detail — and
 * the promotion action inside it — is reachable without a pointer; the double
 * click is what opens the MiniApp, matching the Data types tab's "double click
 * opens the source" vocabulary.
 */
function MiniAppCard({ miniapp, onOpen, onEnter, onLeave }: MiniAppCardProps) {
  const anchorFrom = (element: HTMLElement) => onEnter(miniapp, element.getBoundingClientRect());
  return (
    <div
      className="cursor-pointer rounded-xl border border-stone-200 bg-white p-3 shadow-sm transition hover:border-ink"
      data-testid={`miniapp-card-${miniapp.panel_id}`}
      onClick={(event) => anchorFrom(event.currentTarget)}
      onDoubleClick={() => onOpen(miniapp)}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          onOpen(miniapp);
        }
      }}
      onMouseEnter={(event) => anchorFrom(event.currentTarget)}
      onMouseLeave={onLeave}
      role="button"
      tabIndex={0}
      title={`Open ${miniapp.name}`}
    >
      <p className="break-words text-sm font-medium text-ink">{miniapp.name}</p>
      <p className="mt-1 text-[11px] text-stone-500">
        opens on <span className="font-medium text-stone-700">{miniapp.type}</span>
      </p>
    </div>
  );
}

/** One `Label  value` row in the popover, the Data types tab's row shape. */
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-2">
      <span className="w-16 shrink-0 text-stone-400">{label}</span>
      <span className="min-w-0 flex-1 break-words text-stone-600">{children}</span>
    </div>
  );
}

export interface MiniAppPaletteProps {
  /** Open this MiniApp. The workspace asks for a target (FR-034). */
  onOpen: (summary: MiniAppSummary) => void;
  /** Start a new MiniApp (FR-024's dialog, mounted by the workspace). */
  onCreate: () => void;
}

export function MiniAppPalette({ onOpen, onCreate }: MiniAppPaletteProps) {
  const [miniapps, setMiniApps] = useState<MiniAppSummary[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  // FR-044/FR-046 — the shared hover state machine. Spreading `popoverProps`
  // onto the card below is what makes the popover interactive and keeps it open
  // across the card→card gap, which is what lets FR-032's promotion action be
  // clicked at all.
  const hover = useHoverPopover<MiniAppSummary>();

  const refresh = useCallback(() => {
    let cancelled = false;
    miniAppsApi
      .list()
      .then((listed) => {
        if (cancelled) return;
        setMiniApps(listed);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => refresh(), [refresh]);

  // FR-039 scenario 2 — a promoted MiniApp is "still listed and opens": it has
  // moved from the project tier to the user tier, so the listing this pane is
  // holding is stale the moment the promotion lands. The promotion channel is
  // already the one place every entry point reports through, so subscribing to
  // it costs nothing and needs no callback threaded through the shared action.
  const { notice } = useDialogChannel();
  const promoted =
    notice !== null &&
    notice.item.kind === "miniapp" &&
    (notice.status === "promoted" || notice.status === "partial");
  useEffect(() => {
    if (!promoted) return undefined;
    return refresh();
  }, [promoted, refresh]);

  const sections = buildMiniAppSections(miniapps, search);
  const forceOpen = search.trim().length > 0;
  const hovered = hover.hovered;

  return (
    <aside className="flex h-full flex-col overflow-hidden border-r border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))] p-4">
      <div className="flex items-center justify-between gap-2">
        {/* The panel names itself after its tab, so `MiniApps` reads as a peer
            of `Blocks` and `Data types`. */}
        <p className="font-display text-xl text-ink">MiniApps</p>
        <button
          className="toolbar-button"
          data-testid="miniapp-new"
          onClick={onCreate}
          type="button"
        >
          New MiniApp
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col" data-testid="miniapp-palette-content">
        <input
          className="mt-4 w-full rounded-2xl border border-stone-300 bg-white px-4 py-3 text-sm outline-none transition focus:border-ember"
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search MiniApps"
          value={search}
        />

        {error ? (
          <p
            className="mt-3 rounded-xl border border-amber-300 bg-amber-50 p-2 text-[11px] leading-snug text-amber-900"
            data-testid="miniapp-palette-error"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        <div className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto pb-6 scrollbar-thin">
          {sections.map((section) => (
            <SectionView
              forceOpen={forceOpen}
              key={section.id}
              onEnter={hover.openFor}
              onLeave={hover.scheduleClose}
              onOpen={(miniapp) => {
                hover.closeNow();
                onOpen(miniapp);
              }}
              section={section}
            />
          ))}
          {loaded && miniapps.length === 0 ? (
            <p
              className="px-1 text-[11px] leading-snug text-stone-500"
              data-testid="miniapp-palette-empty"
            >
              No MiniApps yet.
            </p>
          ) : null}
        </div>
      </div>

      {hovered ? (
        <DetailPopover
          actions={
            // FR-032 — Promote to My Library, and only for a project MiniApp.
            // The rule is not restated here: `promotableMiniApp` resolves the
            // origin and the shared action hides itself for every other tier.
            <PromoteToLibraryAction
              entryPoint="E5"
              item={promotableMiniApp(hovered.item)}
              variant="popover"
            />
          }
          anchor={hovered.anchor}
          header={
            <p className="mb-2 break-words text-sm font-medium text-ink">{hovered.item.name}</p>
          }
          testId="miniapp-detail-popover"
          {...hover.popoverProps}
        >
          <div className="flex flex-col gap-1 text-[11px]">
            {hovered.item.description ? (
              <p className="mb-1 leading-snug text-stone-600">{hovered.item.description}</p>
            ) : null}
            <Row label="Opens on">{hovered.item.type}</Row>
            <Row label="Tier">{tierLabel(hovered.item.tier)}</Row>
            <Row label="Folder">{hovered.item.directory}</Row>
          </div>
        </DetailPopover>
      ) : null}
    </aside>
  );
}
