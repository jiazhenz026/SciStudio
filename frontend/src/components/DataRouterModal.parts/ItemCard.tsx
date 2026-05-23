/**
 * Single draggable item card inside DataRouterModal. Extracted in #1413.
 */
import type { ItemDescriptor } from "./types";
import { ROW_COLORS } from "./types";

export interface ItemCardProps {
  item: ItemDescriptor;
  draggable: boolean;
  onDragStart?: (e: React.DragEvent, ref: string) => void;
  colorIndex?: number;
}

export function ItemCard({ item, draggable, onDragStart, colorIndex }: ItemCardProps) {
  const colorClass =
    colorIndex !== undefined
      ? ROW_COLORS[colorIndex % ROW_COLORS.length]
      : "bg-white border-stone-200";
  return (
    <div
      className={`flex items-center gap-2 rounded border px-2 py-1.5 text-xs ${colorClass} ${draggable ? "cursor-grab" : "cursor-default opacity-50"}`}
      draggable={draggable}
      onDragStart={(e) => onDragStart?.(e, item.ref)}
    >
      <span className="truncate font-medium text-ink">{item.name}</span>
      <span className="shrink-0 text-[10px] text-stone-400">{item.type}</span>
    </div>
  );
}
