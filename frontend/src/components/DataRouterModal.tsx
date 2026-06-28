/**
 * DataRouterModal -- drag-and-drop routing modal for the DataRouter block (#591).
 *
 * Displays N input panels (left) and M output panels (right). Users drag items
 * from input panels to output panels. All items must be assigned before Confirm.
 *
 * Uses the HTML5 Drag and Drop API (no external dependencies).
 */

import { useCallback, useState } from "react";

import { Button } from "./ui/button";
import { InputPanels } from "./DataRouterModal.parts/InputPanels";
import { OutputPanels } from "./DataRouterModal.parts/OutputPanels";
import type { ItemDescriptor } from "./DataRouterModal.parts/types";

interface DataRouterModalProps {
  blockId: string;
  inputPorts: string[];
  outputPorts: string[];
  itemsPerPort: Record<string, ItemDescriptor[]>;
  onConfirm: (assignments: Record<string, string[]>) => void;
  onCancel: () => void;
}

export function DataRouterModal({
  blockId,
  inputPorts,
  outputPorts,
  itemsPerPort,
  onConfirm,
  onCancel,
}: DataRouterModalProps) {
  // `blockId` is part of the public contract and is surfaced as a
  // data attribute on the modal root for tests / analytics hooks
  // (also prevents the no-unused-vars lint per #1417).
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
      data-block-id={blockId}
      data-testid="data-router-modal"
    >
      <div
        className="flex max-h-[85vh] w-[900px] flex-col rounded-xl border border-ink/10 bg-white shadow-panel"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-b border-ink/5 px-5 py-3">
          <div className="text-sm font-semibold text-ink">Data Router</div>
          <div className="mt-0.5 text-xs text-ink/60">
            Drag items from input panels to output panels. All items must be assigned.
          </div>
        </div>

        {/* Body */}
        <div className="flex flex-1 gap-4 overflow-y-auto p-5">
          <InputPanels
            inputPorts={inputPorts}
            itemsPerPort={itemsPerPort}
            assignedRefs={assignedRefs}
            onDragStart={handleDragStart}
            onDropOnInput={handleDropOnInput}
            onDragOver={handleDragOver}
          />

          {/* Arrow divider */}
          <div className="flex items-center text-ink/30">
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

          <OutputPanels
            outputPorts={outputPorts}
            assignments={assignments}
            itemByRef={itemByRef}
            onDropOnOutput={handleDropOnOutput}
            onDragOver={handleDragOver}
            onDragStart={handleDragStart}
          />
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-ink/5 px-5 py-3">
          <div className="text-xs text-ink/60">
            {allAssigned ? (
              <span className="text-pine">All items assigned</span>
            ) : (
              <span className="text-amber-600">
                {unassignedItems.length} item(s) not yet assigned
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="button" size="sm" disabled={!allAssigned} onClick={handleConfirm}>
              Confirm
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
