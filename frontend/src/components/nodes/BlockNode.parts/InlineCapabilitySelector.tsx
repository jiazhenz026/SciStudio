// Extracted from BlockNode.tsx as part of the #1422 god-file split.
// InlineCapabilitySelector — single-row Format dropdown rendered in the
// BlockNode inline-config strip when the block declares one or more
// FormatCapabilityResponse entries. Wires through `onChange(capability_id)`
// so the parent can persist the choice into `data.config.capability_id`.

import type { FormatCapabilityResponse } from "../../../types/api";
import { capabilityLabel, capabilityWarning, selectedCapability } from "./inlineConfigHelpers";

export function InlineCapabilitySelector({
  capabilities,
  value,
  onChange,
}: {
  capabilities: FormatCapabilityResponse[];
  value: unknown;
  onChange: (capabilityId: string) => void;
}) {
  if (capabilities.length === 0) return null;
  const capability = selectedCapability(capabilities, value);
  const warning = capabilityWarning(capabilities, capability);
  const selectValue = typeof value === "string" ? value : (capability?.id ?? "");

  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="flex items-center justify-between gap-2">
        <span className="shrink-0 text-stone-500">Format</span>
        <select
          className="nodrag nowheel min-w-0 flex-1 truncate rounded border border-stone-200 bg-white px-2 py-1 text-xs text-ink focus:border-sea focus:outline-none"
          disabled={capabilities.length === 1}
          value={selectValue}
          onChange={(event) => onChange(event.target.value)}
        >
          {capabilities.length > 1 && <option value="">Select format...</option>}
          {capabilities.map((option) => (
            <option key={option.id} value={option.id}>
              {capabilityLabel(option)}
            </option>
          ))}
        </select>
      </span>
      {warning ? (
        <span className="truncate rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] text-amber-700">
          {warning}
        </span>
      ) : null}
    </label>
  );
}
