/**
 * PairEditorModal -- sortable reordering modal for the PairEditor block (#594).
 *
 * Displays N side-by-side panels (one per input port). Each panel shows items
 * as a vertically sortable list. Same-row items across panels are "paired"
 * (highlighted with matching colors). Users drag to reorder within each panel.
 *
 * Uses the HTML5 Drag and Drop API (no external dependencies).
 */

import { useState, useCallback, useRef } from "react";

interface ItemDescriptor {
  index: number;
  name: string;
  type: string;
}

interface PairEditorModalProps {
  blockId: string;
  ports: string[];
  itemsPerPort: Record<string, ItemDescriptor[]>;
  collectionLength: number;
  onConfirm: (reorder: Record<string, number[]>) => void;
  onCancel: () => void;
}

// Row pairing colors.
const PAIR_COLORS = [
  { bg: "bg-blue-50", border: "border-blue-300", text: "text-blue-700" },
  { bg: "bg-green-50", border: "border-green-300", text: "text-green-700" },
  { bg: "bg-purple-50", border: "border-purple-300", text: "text-purple-700" },
  { bg: "bg-amber-50", border: "border-amber-300", text: "text-amber-700" },
  { bg: "bg-rose-50", border: "border-rose-300", text: "text-rose-700" },
  { bg: "bg-cyan-50", border: "border-cyan-300", text: "text-cyan-700" },
  { bg: "bg-indigo-50", border: "border-indigo-300", text: "text-indigo-700" },
  { bg: "bg-lime-50", border: "border-lime-300", text: "text-lime-700" },
  { bg: "bg-teal-50", border: "border-teal-300", text: "text-teal-700" },
  { bg: "bg-orange-50", border: "border-orange-300", text: "text-orange-700" },
];

export function PairEditorModal({
  blockId,
  ports,
  itemsPerPort,
  collectionLength,
  onConfirm,
  onCancel,
}: PairEditorModalProps) {
  // State: per-port ordered list of original indices.
  // Initially [0, 1, 2, ...collectionLength-1] for each port.
  const [orders, setOrders] = useState<Record<string, number[]>>(() => {
    const initial: Record<string, number[]> = {};
    for (const port of ports) {
      const items = itemsPerPort[port] ?? [];
      initial[port] = items.map((item) => item.index);
    }
    return initial;
  });

  // Track drag state within a single panel.
  const dragPortRef = useRef<string | null>(null);
  const dragIndexRef = useRef<number>(-1);

  const handleDragStart = useCallback(
    (port: string, positionIndex: number) => (e: React.DragEvent) => {
      dragPortRef.current = port;
      dragIndexRef.current = positionIndex;
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", `${port}:${positionIndex}`);
    },
    [],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const handleDrop = useCallback(
    (targetPort: string, targetPositionIndex: number) => (e: React.DragEvent) => {
      e.preventDefault();
      const sourcePort = dragPortRef.current;
      const sourceIndex = dragIndexRef.current;

      // Only allow drops within the same panel.
      if (sourcePort !== targetPort || sourceIndex === targetPositionIndex) return;

      setOrders((prev) => {
        const portOrder = [...prev[targetPort]];
        // Remove the dragged item and insert at the target position.
        const [moved] = portOrder.splice(sourceIndex, 1);
        portOrder.splice(targetPositionIndex, 0, moved);
        return { ...prev, [targetPort]: portOrder };
      });
    },
    [],
  );

  const handleConfirm = () => {
    onConfirm(orders);
  };

  // Build item lookup by port and original index.
  const itemLookup: Record<string, Record<number, ItemDescriptor>> = {};
  for (const port of ports) {
    itemLookup[port] = {};
    for (const item of itemsPerPort[port] ?? []) {
      itemLookup[port][item.index] = item;
    }
  }

  // Determine grid columns based on port count.
  const gridCols =
    ports.length <= 2
      ? "grid-cols-2"
      : ports.length <= 3
        ? "grid-cols-3"
        : ports.length <= 4
          ? "grid-cols-4"
          : "grid-cols-4";

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
          <div className="text-sm font-semibold text-ink">Pair Editor</div>
          <div className="mt-0.5 text-xs text-stone-500">
            Reorder items within each panel so that same-row items are correctly paired. Items in
            the same row (same color) are paired by index.
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          {/* Row number header */}
          <div className={`grid gap-3 ${gridCols}`}>
            {ports.map((portName) => (
              <div key={portName} className="text-xs font-medium text-stone-600">
                {portName}
                <span className="ml-1 text-stone-400">({collectionLength})</span>
              </div>
            ))}
          </div>

          {/* Items grid — one row per index across all ports */}
          {Array.from({ length: collectionLength }, (_, rowIdx) => {
            const pairColor = PAIR_COLORS[rowIdx % PAIR_COLORS.length];
            return (
              <div key={rowIdx} className={`mt-1 grid gap-3 ${gridCols}`}>
                {ports.map((portName) => {
                  const originalIndex = orders[portName]?.[rowIdx];
                  const item = originalIndex != null ? itemLookup[portName]?.[originalIndex] : null;
                  if (!item) return <div key={portName} />;
                  return (
                    <div
                      key={portName}
                      className={`flex cursor-grab items-center gap-2 rounded border px-2 py-1.5 text-xs ${pairColor.bg} ${pairColor.border}`}
                      draggable
                      onDragStart={handleDragStart(portName, rowIdx)}
                      onDragOver={handleDragOver}
                      onDrop={handleDrop(portName, rowIdx)}
                    >
                      <span className={`shrink-0 text-[10px] font-medium ${pairColor.text}`}>
                        {rowIdx + 1}
                      </span>
                      <span className="min-w-0 flex-1 truncate font-medium text-ink">
                        {item.name}
                      </span>
                      <span className="shrink-0 text-[10px] text-stone-400">{item.type}</span>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-stone-100 px-5 py-3">
          <button
            type="button"
            className="rounded border border-stone-200 px-4 py-1.5 text-xs text-stone-600 hover:bg-stone-50"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded bg-blue-500 px-4 py-1.5 text-xs text-white hover:bg-blue-600"
            onClick={handleConfirm}
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}
