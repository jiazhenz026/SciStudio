// The workspace activity bar (#2090): the narrow vertical icon rail at the far
// left of the window, VS Code-style. Each icon opens its section of the left
// panel; clicking the active section's icon collapses the panel instead
// (click again — or press Ctrl+B — to reopen). Hovering an icon shows the
// section name in a tooltip.
//
// The rail is intentionally outside the `ResizablePanelGroup`: it never
// resizes and stays visible when the panel is collapsed, which is what makes
// the collapsed state discoverable.

import {
  AppWindow,
  Database,
  ScanEye,
  FolderTree,
  Puzzle,
  Shapes,
  Waypoints,
  type LucideIcon,
} from "lucide-react";

import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

import {
  moveActivityBarKey,
  saveActivityBarOrder,
  useActivityBarOrder,
} from "../lib/activityBarOrder";
import { useSidebarSide } from "../lib/presentation";
import { cn } from "@/lib/utils";

import type { LeftTab } from "../App.parts/ProjectWorkspace";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

interface ActivityBarEntry {
  key: LeftTab;
  label: string;
  icon: LucideIcon;
}

// Default top-to-bottom order (owner decision in #2415): Blocks, Workflows,
// MiniApps, Data types, Data, Project. The three things a user builds and
// opens come first; the type catalogue, the data folders, and the project
// tree follow. This is only the default: each viewer can drag the icons (or
// press Alt+ArrowUp / Alt+ArrowDown on a focused icon) into their own order,
// kept as a browser-local preference by `lib/activityBarOrder`, and reset it
// from the rail's context menu.
const ACTIVITY_BAR_ENTRIES: readonly ActivityBarEntry[] = [
  { key: "blocks", label: "Blocks", icon: Puzzle },
  { key: "workflows", label: "Workflows", icon: Waypoints },
  { key: "miniapps", label: "MiniApps", icon: AppWindow },
  { key: "types", label: "Data types", icon: Shapes },
  { key: "data", label: "Data", icon: Database },
  { key: "project", label: "Project", icon: FolderTree },
];

const DEFAULT_ORDER: readonly LeftTab[] = ACTIVITY_BAR_ENTRIES.map((entry) => entry.key);
const ENTRY_BY_KEY = new Map(ACTIVITY_BAR_ENTRIES.map((entry) => [entry.key, entry]));
const PREVIEW_ENTRY: ActivityBarEntry = { key: "preview", label: "Preview", icon: ScanEye };

// Pointer travel (px) before a press becomes a drag. Below it the press is a
// click, so a slightly shaky click still selects its section.
const DRAG_THRESHOLD_PX = 4;

interface PointerSession {
  key: LeftTab;
  pointerId: number;
  startY: number;
  /** Vertical centre of each slot, in the order shown when the press began. */
  slotCenters: number[];
  dragging: boolean;
}

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
  const isAi = useSidebarSide() === "right";
  const savedOrder = useActivityBarOrder(DEFAULT_ORDER);
  // While a drag is in progress the rail shows where the icon would land;
  // the preference is written once, on release.
  const [dragOrder, setDragOrder] = useState<LeftTab[] | null>(null);
  const [draggingKey, setDraggingKey] = useState<LeftTab | null>(null);
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const order = dragOrder ?? savedOrder;

  const buttons = useRef(new Map<LeftTab, HTMLButtonElement>());
  const session = useRef<PointerSession | null>(null);
  // A drag ends with a click event on the dragged button; that click must not
  // select (or collapse) the section.
  const suppressClick = useRef(false);
  const refocusKey = useRef<LeftTab | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const key = refocusKey.current;
    if (key === null) return;
    refocusKey.current = null;
    buttons.current.get(key)?.focus();
  });

  useEffect(() => {
    if (!menu) return undefined;
    const onMouseDown = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setMenu(null);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenu(null);
    };
    window.addEventListener("mousedown", onMouseDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [menu]);

  const endSession = () => {
    session.current = null;
    setDragOrder(null);
    setDraggingKey(null);
  };

  const handlePointerDown = (key: LeftTab, event: ReactPointerEvent<HTMLButtonElement>) => {
    suppressClick.current = false;
    if (event.button !== 0) return;
    session.current = {
      key,
      pointerId: event.pointerId,
      startY: event.clientY,
      slotCenters: order.map((slotKey) => {
        const rect = buttons.current.get(slotKey)?.getBoundingClientRect();
        return rect ? rect.top + rect.height / 2 : 0;
      }),
      dragging: false,
    };
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const current = session.current;
    if (!current || current.pointerId !== event.pointerId) return;
    if (!current.dragging) {
      if (Math.abs(event.clientY - current.startY) < DRAG_THRESHOLD_PX) return;
      current.dragging = true;
      setDraggingKey(current.key);
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {
        // Capture is best-effort; without it the drag still tracks while the
        // pointer stays over the rail.
      }
    }
    let target = 0;
    current.slotCenters.forEach((center, index) => {
      if (
        Math.abs(event.clientY - center) < Math.abs(event.clientY - current.slotCenters[target])
      ) {
        target = index;
      }
    });
    setDragOrder(moveActivityBarKey(savedOrder, current.key, target));
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const current = session.current;
    if (!current || current.pointerId !== event.pointerId) return;
    if (current.dragging) {
      suppressClick.current = true;
      if (dragOrder) saveActivityBarOrder(dragOrder);
    }
    endSession();
  };

  const handleKeyDown = (key: LeftTab, event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (!event.altKey || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
    event.preventDefault();
    const from = savedOrder.indexOf(key);
    const to = from + (event.key === "ArrowUp" ? -1 : 1);
    if (from === -1 || to < 0 || to >= savedOrder.length) return;
    refocusKey.current = key;
    saveActivityBarOrder(moveActivityBarKey(savedOrder, key, to));
  };

  const entries: ActivityBarEntry[] = order.flatMap((key) => {
    const entry = ENTRY_BY_KEY.get(key);
    return entry ? [entry] : [];
  });
  // The AI presentation's Preview entry is always last and is not reorderable.
  if (isAi) entries.push(PREVIEW_ENTRY);

  const isDefaultOrder = savedOrder.every((key, index) => key === DEFAULT_ORDER[index]);

  return (
    <nav
      aria-label="Workspace sections"
      className={cn(
        "flex w-12 shrink-0 flex-col items-center gap-1 border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))] py-2",
        isAi ? "order-last border-l" : "border-r",
      )}
      data-testid="activity-bar"
      onContextMenu={(event) => {
        event.preventDefault();
        setMenu({ x: event.clientX, y: event.clientY });
      }}
    >
      {entries.map(({ key, label, icon: Icon }) => {
        // A collapsed panel shows no active marker at all — same as VS Code.
        const active = panelOpen && activeTab === key;
        const reorderable = key !== "preview";
        return (
          <Tooltip key={key}>
            <TooltipTrigger asChild>
              <button
                aria-keyshortcuts={reorderable ? "Alt+ArrowUp Alt+ArrowDown" : undefined}
                aria-label={label}
                aria-pressed={active}
                className={cn(
                  "relative flex h-10 w-10 touch-none items-center justify-center rounded-md transition",
                  // #2090 — active section: soft ember fill + ember icon, on
                  // top of the edge accent bar (owner-requested color fill,
                  // same `bg-ember/15` treatment as the bottom-panel pin).
                  active
                    ? "bg-ember/15 text-ember"
                    : "text-stone-400 hover:bg-white/70 hover:text-stone-600",
                  draggingKey === key && "cursor-grabbing opacity-60 ring-1 ring-ember/40",
                )}
                data-dragging={draggingKey === key ? "true" : undefined}
                data-testid={`activity-bar-${key}`}
                onClick={(event) => {
                  // `detail === 0` is a keyboard (Enter/Space) click, which a
                  // pointer drag can never have produced.
                  if (suppressClick.current && event.detail !== 0) {
                    suppressClick.current = false;
                    return;
                  }
                  onSelect(key);
                }}
                onKeyDown={reorderable ? (event) => handleKeyDown(key, event) : undefined}
                onLostPointerCapture={reorderable ? handlePointerUp : undefined}
                onPointerCancel={reorderable ? endSession : undefined}
                onPointerDown={reorderable ? (event) => handlePointerDown(key, event) : undefined}
                onPointerMove={reorderable ? handlePointerMove : undefined}
                onPointerUp={reorderable ? handlePointerUp : undefined}
                ref={(element) => {
                  if (element) buttons.current.set(key, element);
                  else buttons.current.delete(key);
                }}
                type="button"
              >
                {/* VS Code-style active marker: a short accent bar on the
                    rail's left edge rather than a background fill. The button
                    is centered in the 48px rail, so -left-1 lands the bar on
                    the rail edge. */}
                {active ? (
                  <span
                    className={cn(
                      "absolute top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-ember",
                      isAi ? "-right-1" : "-left-1",
                    )}
                  />
                ) : null}
                <Icon className="h-5 w-5" />
              </button>
            </TooltipTrigger>
            <TooltipContent side={isAi ? "left" : "right"}>{label}</TooltipContent>
          </Tooltip>
        );
      })}
      {menu ? (
        <div
          className="fixed z-50 rounded-lg border border-stone-200 bg-white py-1 shadow-lg"
          data-testid="activity-bar-menu"
          ref={menuRef}
          role="menu"
          style={{ left: menu.x, top: menu.y }}
        >
          <button
            className="w-full whitespace-nowrap px-4 py-1.5 text-left text-xs text-stone-700 hover:bg-stone-100 disabled:text-stone-300 disabled:hover:bg-transparent"
            data-testid="activity-bar-reset-order"
            disabled={isDefaultOrder}
            onClick={() => {
              saveActivityBarOrder(null);
              setMenu(null);
            }}
            role="menuitem"
            type="button"
          >
            Reset order
          </button>
        </div>
      ) : null}
    </nav>
  );
}
