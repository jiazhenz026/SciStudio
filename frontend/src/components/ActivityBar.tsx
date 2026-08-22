// The workspace activity bar (#2090): the narrow vertical icon rail at the far
// left of the window, VS Code-style. Each icon opens its section of the left
// panel; clicking the active section's icon collapses the panel instead
// (click again — or press Ctrl+B — to reopen). Hovering an icon shows the
// section name in a tooltip.
//
// The rail is intentionally outside the `ResizablePanelGroup`: it never
// resizes and stays visible when the panel is collapsed, which is what makes
// the collapsed state discoverable.

import { Database, FolderTree, Puzzle, Shapes, Waypoints, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

import type { LeftTab } from "../App.parts/ProjectWorkspace";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

interface ActivityBarEntry {
  key: LeftTab;
  label: string;
  icon: LucideIcon;
}

// Top-to-bottom visual order. `workflows` sits between the library sections
// (blocks / types) and the data/project trees; `data` (#2090) is the project
// tree rooted at data/.
const ACTIVITY_BAR_ENTRIES: readonly ActivityBarEntry[] = [
  { key: "blocks", label: "Blocks", icon: Puzzle },
  { key: "types", label: "Data types", icon: Shapes },
  { key: "workflows", label: "Workflows", icon: Waypoints },
  { key: "data", label: "Data", icon: Database },
  { key: "project", label: "Project", icon: FolderTree },
];

export interface ActivityBarProps {
  /** The section the left panel shows (or would show when reopened). */
  activeTab: LeftTab;
  /** Whether the left panel is currently expanded. */
  panelOpen: boolean;
  /**
   * Icon click. The owner (App) decides between "switch section", "expand",
   * and "collapse": clicking the active section while the panel is open
   * collapses it, everything else opens that section.
   */
  onSelect: (tab: LeftTab) => void;
}

export function ActivityBar({ activeTab, panelOpen, onSelect }: ActivityBarProps) {
  return (
    <nav
      aria-label="Workspace sections"
      className="flex w-12 shrink-0 flex-col items-center gap-1 border-r border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))] py-2"
      data-testid="activity-bar"
    >
      {ACTIVITY_BAR_ENTRIES.map(({ key, label, icon: Icon }) => {
        // A collapsed panel shows no active marker at all — same as VS Code.
        const active = panelOpen && activeTab === key;
        return (
          <Tooltip key={key}>
            <TooltipTrigger asChild>
              <button
                aria-label={label}
                aria-pressed={active}
                className={cn(
                  "relative flex h-10 w-10 items-center justify-center rounded-md transition",
                  // #2090 — active section: soft ember fill + ember icon, on
                  // top of the edge accent bar (owner-requested color fill,
                  // same `bg-ember/15` treatment as the bottom-panel pin).
                  active
                    ? "bg-ember/15 text-ember"
                    : "text-stone-400 hover:bg-white/70 hover:text-stone-600",
                )}
                data-testid={`activity-bar-${key}`}
                onClick={() => onSelect(key)}
                type="button"
              >
                {/* VS Code-style active marker: a short accent bar on the
                    rail's left edge rather than a background fill. The button
                    is centered in the 48px rail, so -left-1 lands the bar on
                    the rail edge. */}
                {active ? (
                  <span className="absolute -left-1 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-ember" />
                ) : null}
                <Icon className="h-5 w-5" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">{label}</TooltipContent>
          </Tooltip>
        );
      })}
    </nav>
  );
}
