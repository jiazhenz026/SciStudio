/**
 * DataRouterModal -- drag-and-drop routing modal for the DataRouter block (#591).
 *
 * Displays N input panels (left) and M output panels (right). Users drag items
 * from input panels to output panels. All items must be assigned before Confirm.
 *
 * Uses the HTML5 Drag and Drop API (no external dependencies).
 */

import { useState, useCallback } from "react";

interface ItemDescriptor {
  index: number;
  port: string;
  ref: string;
  name: string;
  type: string;
}

interface DataRouterModalProps {
  blockId: string;
  inputPorts: string[];
  outputPorts: string[];
  itemsPerPort: Record<string, ItemDescriptor[]>;
  onConfirm: (assignments: Record<string, string[]>) => void;
  onCancel: () => void;
}

// Row colors for visual grouping.
const ROW_COLORS = [
  "bg-blue-50 border-blue-200",
  "bg-green-50 border-green-200",
  "bg-purple-50 border-purple-200",
  "bg-amber-50 border-amber-200",
  "bg-rose-50 border-rose-200",
  "bg-cyan-50 border-cyan-200",
  "bg-indigo-50 border-indigo-200",
  "bg-lime-50 border-lime-200",
];

function ItemCard({
  item,
  draggable,
  onDragStart,
  colorIndex,
}: {
  item: ItemDescriptor;
  draggable: boolean;
  onDragStart?: (e: React.DragEvent, ref: string) => void;
  colorIndex?: number;
}) {
  const colorClass =
    colorIndex != null ? ROW_COLORS[colorIndex % ROW_COLORS.length] : "bg-white border-stone-200";
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

export function DataRouterModal({
  blockId,
  inputPorts,
  outputPorts,
  itemsPerPort,
  onConfirm,
  onCancel,
}: DataRouterModalProps) {
  // Track which items have been assigned to which output port.
  // Key: output port name, Value: list of item refs.
  const [assignments, setAssignments] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(outputPorts.map((p) => [p, []])),
  );

  // Track which items are still unassigned.
  const allItems = inputPorts.flatMap((p) => itemsPerPort[p] ?? []);
  const assignedRefs = new Set(Object.values(assignments).flat());
  const unassignedItems = allItems.filter((item) => !assignedRefs.has(item.ref));
  const allAssigned = unassignedItems.length === 0;

  // Lookup for item by ref.
  const itemByRef: Record<string, ItemDescriptor> = {};
  for (const item of allItems) {
    itemByRef[item.ref] = item;
  }

  const handleDragStart = useCallback((e: React.DragEvent, ref: string) => {
    e.dataTransfer.setData("text/plain", ref);
    e.dataTransfer.effectAllowed = "move";
  }, []);

  const handleDropOnOutput = useCallback((e: React.DragEvent, outputPort: string) => {
    e.preventDefault();
    const ref = e.dataTransfer.getData("text/plain");
    if (!ref) return;

    setAssignments((prev) => {
      // Remove from any other output port first.
      const next: Record<string, string[]> = {};
      for (const [port, refs] of Object.entries(prev)) {
        next[port] = refs.filter((r) => r !== ref);
      }
      // Add to target port.
      next[outputPort] = [...(next[outputPort] ?? []), ref];
      return next;
    });
  }, []);

  const handleDropOnInput = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const ref = e.dataTransfer.getData("text/plain");
    if (!ref) return;

    // Remove from all output ports (move back to unassigned).
    setAssignments((prev) => {
      const next: Record<string, string[]> = {};
      for (const [port, refs] of Object.entries(prev)) {
        next[port] = refs.filter((r) => r !== ref);
      }
      return next;
    });
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const handleConfirm = () => {
    onConfirm(assignments);
  };

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40"
      onClick={onCancel}
    >
      <div
        className="flex max-h-[85vh] w-[900px] flex-col rounded-xl border border-stone-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-b border-stone-100 px-5 py-3">
          <div className="text-sm font-semibold text-ink">Data Router</div>
          <div className="mt-0.5 text-xs text-stone-500">
            Drag items from input panels to output panels. All items must be assigned.
          </div>
        </div>

        {/* Body */}
        <div className="flex flex-1 gap-4 overflow-y-auto p-5">
          {/* Input panels */}
          <div
            className="flex flex-1 flex-col gap-3"
            onDrop={handleDropOnInput}
            onDragOver={handleDragOver}
          >
            <div className="text-xs font-medium uppercase tracking-wide text-stone-400">Inputs</div>
            {inputPorts.map((portName) => {
              const portItems = itemsPerPort[portName] ?? [];
              const unassignedPortItems = portItems.filter((item) => !assignedRefs.has(item.ref));
              return (
                <div key={portName} className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                  <div className="mb-2 text-xs font-medium text-stone-600">
                    {portName}{" "}
                    <span className="text-stone-400">
                      ({unassignedPortItems.length}/{portItems.length})
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {unassignedPortItems.map((item) => (
                      <ItemCard
                        key={item.ref}
                        item={item}
                        draggable
                        onDragStart={handleDragStart}
                      />
                    ))}
                    {unassignedPortItems.length === 0 && (
                      <span className="text-[10px] italic text-stone-400">All items assigned</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Arrow divider */}
          <div className="flex items-center text-stone-300">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M5 12h14M13 5l6 7-6 7" />
            </svg>
          </div>

          {/* Output panels */}
          <div className="flex flex-1 flex-col gap-3">
            <div className="text-xs font-medium uppercase tracking-wide text-stone-400">
              Outputs
            </div>
            {outputPorts.map((portName, portIndex) => {
              const portRefs = assignments[portName] ?? [];
              return (
                <div
                  key={portName}
                  className="min-h-[60px] rounded-lg border-2 border-dashed border-stone-200 bg-stone-50 p-3 transition-colors hover:border-blue-300"
                  onDrop={(e) => handleDropOnOutput(e, portName)}
                  onDragOver={handleDragOver}
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
                          onDragStart={handleDragStart}
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
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-stone-100 px-5 py-3">
          <div className="text-xs text-stone-500">
            {allAssigned ? (
              <span className="text-green-600">All items assigned</span>
            ) : (
              <span className="text-amber-600">
                {unassignedItems.length} item(s) not yet assigned
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded border border-stone-200 px-4 py-1.5 text-xs text-stone-600 hover:bg-stone-50"
              onClick={onCancel}
            >
              Cancel
            </button>
            <button
              type="button"
              className="rounded bg-blue-500 px-4 py-1.5 text-xs text-white hover:bg-blue-600 disabled:opacity-40"
              disabled={!allAssigned}
              onClick={handleConfirm}
            >
              Confirm
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
