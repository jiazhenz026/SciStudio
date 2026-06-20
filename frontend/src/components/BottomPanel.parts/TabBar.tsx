import {
  GitBranch,
  LineChart,
  MessageSquare,
  Pin,
  PinOff,
  ScrollText,
  SlidersHorizontal,
  Terminal,
  Waypoints,
} from "lucide-react";
import { type ReactNode } from "react";

import type { BottomTab } from "../../types/ui";

// Tab labels: a Lucide line icon + text for every tab so the glyphs read
// consistently across OS font sets (emoji marks were replaced in the live
// hotfix batch — they rendered inconsistently and looked off-brand).
function tabLabel(Icon: typeof Terminal, text: string): ReactNode {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon className="h-4 w-4" aria-hidden="true" />
      {text}
    </span>
  );
}

const TAB_LABELS: Record<BottomTab, ReactNode> = {
  ai: tabLabel(MessageSquare, "AI Chat"),
  terminal: tabLabel(Terminal, "Terminal"),
  config: tabLabel(SlidersHorizontal, "Config"),
  logs: tabLabel(ScrollText, "Logs"),
  // #1713 — dedicated Plots panel (card-style plot list with relink/run/new).
  plots: tabLabel(LineChart, "Plots"),
  // ADR-038 §3.8 — Lineage tab promoted to a first-class entry; replaces
  // the prior Jobs placeholder which is removed entirely.
  // #1713 follow-up — display label only is "History" (the BottomTab key and
  // all code stay "lineage"); owner-requested UI rename.
  lineage: tabLabel(Waypoints, "History"),
  // ADR-039 §3.5 (#972) — Git versioning surface moved out of the top
  // Toolbar into a dedicated bottom-panel tab so the commit history /
  // branch graph / merge flows are reachable without overflowing the
  // toolbar on narrow viewports.
  git: tabLabel(GitBranch, "Git"),
};

// Problems was removed: it duplicated the block_error rows already in Logs
// (filterable via LogViewer's level selector) plus the inline error badge
// rendered on the BlockNode itself by WorkflowCanvas.
// ADR-038 §3.8 — Jobs tab removed (subsumed by Lineage).
// ADR-039 §3.5 (#972) — Git tab added.
// Hotfix: Terminal is promoted to a top-level tab alongside AI Chat.
// #1713 — Plots sits next to Lineage; both surface workflow-wide artifacts.
export const ALL_TABS: BottomTab[] = [
  "ai",
  "config",
  "logs",
  "terminal",
  "plots",
  "lineage",
  "git",
];

function formatBadge(n: number): string {
  return n > 99 ? "99+" : String(n);
}

export function TabBar({
  activeTab,
  onTabChange,
  unreadLogsCount,
  pinned,
  onTogglePin,
}: {
  activeTab: BottomTab;
  onTabChange: (tab: BottomTab) => void;
  unreadLogsCount: number;
  pinned: boolean;
  onTogglePin?: () => void;
}) {
  const badgeFor = (tab: BottomTab): number => {
    if (tab === activeTab) return 0;
    if (tab === "logs") return unreadLogsCount;
    return 0;
  };

  return (
    <div className="flex items-center gap-3 border-b border-stone-200 px-4 py-3">
      <div className="flex flex-1 gap-2">
        {ALL_TABS.map((tab) => {
          const badge = badgeFor(tab);
          return (
            <button
              className={`inline-flex items-center rounded-full px-4 py-2 text-sm font-medium ${activeTab === tab ? "bg-ink text-white" : "bg-white text-stone-600"}`}
              key={tab}
              onClick={() => onTabChange(tab)}
              type="button"
            >
              {TAB_LABELS[tab]}
              {badge > 0 ? (
                <span
                  className="ml-2 inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-rose-500 px-1.5 text-xs font-semibold text-white"
                  data-testid={`unread-badge-${tab}`}
                >
                  {formatBadge(badge)}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
      {onTogglePin ? (
        <button
          aria-label={
            pinned ? "Unpin bottom panel" : "Pin bottom panel (disable canvas-click auto-collapse)"
          }
          aria-pressed={pinned}
          className={`inline-flex h-8 w-8 items-center justify-center rounded-full transition-colors ${
            pinned ? "bg-ember/15 text-ember" : "bg-white text-stone-500 hover:bg-stone-100"
          }`}
          data-testid="bottom-panel-pin-toggle"
          onClick={onTogglePin}
          title={
            pinned
              ? "Pinned — clicks on canvas won't fold the panel"
              : "Pin panel — clicks on canvas won't fold it"
          }
          type="button"
        >
          {pinned ? <Pin className="h-4 w-4" /> : <PinOff className="h-4 w-4" />}
        </button>
      ) : null}
    </div>
  );
}
