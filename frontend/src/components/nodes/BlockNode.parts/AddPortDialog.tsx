// Issue #1325 — add-port dialog for variadic block canvas nodes.
//
// Replaces the silent auto-add path in PortHandles (which generated
// ``port_N`` names with the schema's default type) with an explicit
// user-facing dialog that:
//   * lets the user type the port name (default pre-filled with
//     ``port_N`` so a one-click flow still works), and
//   * lets the user pick the port's data type from the block's
//     ``allowed_{input,output}_types`` constraint list.
//
// Hosted inline by BlockNode.tsx so a single dialog state lives at the
// per-node level (open / close / direction / draft name + type).
import { useState } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";

import type { TypeHierarchyEntry } from "../../../types/api";

export interface AddPortDialogProps {
  direction: "input" | "output";
  /** Allowed type names for this direction (from
   *  ``BlockSchemaResponse.allowed_input_types`` /
   *  ``allowed_output_types``). When empty, falls back to the type
   *  hierarchy so the user can pick any registered DataObject subtype. */
  allowedTypes: string[];
  typeHierarchy: TypeHierarchyEntry[] | undefined;
  /** Default name pre-filled in the name field (e.g. ``port_3`` when
   *  the block already has two ports). The user may edit or replace
   *  before confirming. */
  defaultName: string;
  onCancel: () => void;
  onSubmit: (name: string, typeName: string) => void;
}

export function AddPortDialog({
  direction,
  allowedTypes,
  typeHierarchy,
  defaultName,
  onCancel,
  onSubmit,
}: AddPortDialogProps) {
  // Type pick list: prefer the block's explicit allowedTypes constraint;
  // fall back to the global type hierarchy when the block declares no
  // constraint (allowedTypes is empty per Block.allowed_*_types semantics
  // — "accept any DataObject subclass").
  const typeOptions =
    allowedTypes.length > 0 ? allowedTypes : (typeHierarchy ?? []).map((t) => t.name);
  const initialType = typeOptions[0] ?? "DataObject";

  const [name, setName] = useState(defaultName);
  const [typeName, setTypeName] = useState(initialType);

  const trimmed = name.trim();
  const canSubmit = trimmed.length > 0 && typeName.length > 0;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-port-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        data-testid="add-port-dialog"
        className="w-full max-w-md rounded-lg bg-white p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="add-port-title" className="mb-3 text-base font-semibold">
          Add {direction} port
        </h2>
        <label className="mt-2 block text-xs font-medium text-stone-600">
          Name
          <input
            data-testid="add-port-name"
            autoFocus
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && canSubmit) {
                e.preventDefault();
                onSubmit(trimmed, typeName);
              } else if (e.key === "Escape") {
                e.preventDefault();
                onCancel();
              }
            }}
            placeholder="port_N"
            className="mt-1 block w-full rounded border border-stone-300 px-3 py-2 text-sm outline-none focus:border-pine"
          />
        </label>
        <label className="mt-3 block text-xs font-medium text-stone-600">
          Type
          <select
            data-testid="add-port-type"
            value={typeName}
            onChange={(e) => setTypeName(e.target.value)}
            className="mt-1 block w-full rounded border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-pine"
          >
            {typeOptions.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="toolbar" size="toolbar" type="button" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            data-testid="add-port-submit"
            variant="toolbar-dark"
            size="toolbar"
            type="button"
            disabled={!canSubmit}
            onClick={() => onSubmit(trimmed, typeName)}
          >
            Add
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
