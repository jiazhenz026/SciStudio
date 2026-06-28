/**
 * Left-hand "Inputs" column inside DataRouterModal. Extracted in #1413.
 */
import { ItemCard } from "./ItemCard";
import type { ItemDescriptor } from "./types";

export interface InputPanelsProps {
  inputPorts: string[];
  itemsPerPort: Record<string, ItemDescriptor[]>;
  assignedRefs: Set<string>;
  onDragStart: (e: React.DragEvent, ref: string) => void;
  onDropOnInput: (e: React.DragEvent) => void;
  onDragOver: (e: React.DragEvent) => void;
}

export function InputPanels({
  inputPorts,
  itemsPerPort,
  assignedRefs,
  onDragStart,
  onDropOnInput,
  onDragOver,
}: InputPanelsProps) {
  return (
    <div className="flex flex-1 flex-col gap-3" onDrop={onDropOnInput} onDragOver={onDragOver}>
      <div className="text-xs font-medium uppercase tracking-wide text-ink/45">Inputs</div>
      {inputPorts.map((portName) => {
        const portItems = itemsPerPort[portName] ?? [];
        const unassignedPortItems = portItems.filter((item) => !assignedRefs.has(item.ref));
        return (
          <div key={portName} className="rounded-lg border border-ink/10 bg-ink/5 p-3">
            <div className="mb-2 text-xs font-medium text-ink/70">
              {portName}{" "}
              <span className="text-ink/45">
                ({unassignedPortItems.length}/{portItems.length})
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {unassignedPortItems.map((item) => (
                <ItemCard key={item.ref} item={item} draggable onDragStart={onDragStart} />
              ))}
              {unassignedPortItems.length === 0 && (
                <span className="text-[10px] italic text-ink/45">All items assigned</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
