import { useMemo, useState } from "react";

import type { TypeHierarchyEntry } from "../types/api";
import { resolveRingColor, resolveTypeColor } from "../config/typeColorMap";

interface TypeLegendProps {
  /**
   * Set of type names that are actually present in the current workflow.
   * The legend only shows entries for types in this set.
   */
  activeTypes: Set<string>;
  /** Type hierarchy from the backend schema, used for color resolution. */
  typeHierarchy?: TypeHierarchyEntry[];
}

export function TypeLegend({ activeTypes, typeHierarchy }: TypeLegendProps) {
  const [collapsed, setCollapsed] = useState(true);

  const visible = useMemo(() => {
    const entries: { name: string; fill: string; ring?: string }[] = [];
    for (const name of activeTypes) {
      const types = [name];
      const fill = resolveTypeColor(types, typeHierarchy);
      const ring = resolveRingColor(types, typeHierarchy);
      entries.push({ name, fill, ring });
    }
    // Sort: put "Any" last, otherwise alphabetical.
    entries.sort((a, b) => {
      if (a.name === "Any") return 1;
      if (b.name === "Any") return -1;
      return a.name.localeCompare(b.name);
    });
    return entries;
  }, [activeTypes, typeHierarchy]);

  if (visible.length === 0) return null;

  return (
    <div
      className="absolute bottom-3 right-3 z-10 rounded-lg border border-stone-200 bg-white/95 shadow-sm backdrop-blur-sm"
      style={{ minWidth: collapsed ? "auto" : 140 }}
    >
      <button
        type="button"
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-wider text-stone-500 hover:text-stone-700"
        onClick={() => setCollapsed((prev) => !prev)}
      >
        <span
          className="inline-block h-2.5 w-2.5 rounded-sm"
          style={{
            background: "linear-gradient(135deg, #3b82f6, #f59e0b, #22c55e, #8b5cf6)",
          }}
        />
        {collapsed ? "Legend" : "Type Legend"}
        <span className="ml-auto text-[9px]">{collapsed ? "\u25B6" : "\u25BC"}</span>
      </button>
      {!collapsed && (
        <div className="space-y-1 border-t border-stone-100 px-2.5 pb-2 pt-1.5">
          {visible.map((entry) => (
            <div key={entry.name} className="flex items-center gap-2">
              <span
                className="inline-block h-3 w-3 shrink-0 rounded-full border-2"
                style={{
                  backgroundColor: entry.fill,
                  borderColor: entry.ring ?? entry.fill,
                  borderStyle: entry.name === "Any" ? "dashed" : "solid",
                }}
              />
              <span className="text-[11px] text-stone-600">{entry.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
