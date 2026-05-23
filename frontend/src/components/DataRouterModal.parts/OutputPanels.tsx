/**
 * Right-hand "Outputs" column inside DataRouterModal. Extracted in #1413.
 */
import { ItemCard } from "./ItemCard";
import type { ItemDescriptor } from "./types";

export interface OutputPanelsProps {
  outputPorts: string[];
  assignments: Record<string, string[]>;
  itemByRef: Record<string, ItemDescriptor>;
  onDropOnOutput: (e: React.DragEvent, port: string) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragStart: (e: React.DragEvent, ref: string) => void;
}

export function OutputPanels({
  outputPorts,
  assignments,
  itemByRef,
  onDropOnOutput,
  onDragOver,
  onDragStart,
}: OutputPanelsProps) {
  return (
    <div className="flex flex-1 flex-col gap-3">
      <div className="text-xs font-medium uppercase tracking-wide text-stone-400">Outputs</div>
      {outputPorts.map((portName, portIndex) => {
        const portRefs = assignments[portName] ?? [];
        return (
          <div
            key={portName}
            className="min-h-[60px] rounded-lg border-2 border-dashed border-stone-200 bg-stone-50 p-3 transition-colors hover:border-blue-300"
            onDrop={(e) => onDropOnOutput(e, portName)}
            onDragOver={onDragOver}
          >
            <div className="mb-2 text-xs font-medium text-stone-600">
              {portName} <span className="text-stone-400">({portRefs.length})</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {portRefs.map((ref) => {
                const item = itemByRef[ref];
                if (!item) return null;
                return (
                  <ItemCard
                    key={ref}
                    item={item}
                    draggable
                    onDragStart={onDragStart}
                    colorIndex={portIndex}
                  />
                );
              })}
              {portRefs.length === 0 && (
                <span className="text-[10px] italic text-stone-400">Drop items here</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
