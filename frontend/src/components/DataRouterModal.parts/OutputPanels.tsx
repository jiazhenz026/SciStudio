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
      <div className="text-xs font-medium uppercase tracking-wide text-ink/45">Outputs</div>
      {outputPorts.map((portName, portIndex) => {
        const portRefs = assignments[portName] ?? [];
        return (
          <div
            key={portName}
            className="min-h-[60px] rounded-lg border-2 border-dashed border-ink/10 bg-ink/5 p-3 transition-colors hover:border-ember/50"
            onDrop={(e) => onDropOnOutput(e, portName)}
            onDragOver={onDragOver}
          >
            <div className="mb-2 text-xs font-medium text-ink/70">
              {portName} <span className="text-ink/45">({portRefs.length})</span>
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
                <span className="text-[10px] italic text-ink/45">Drop items here</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
