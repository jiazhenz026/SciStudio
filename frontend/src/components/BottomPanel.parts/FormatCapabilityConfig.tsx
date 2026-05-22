import type { FormatCapabilityResponse } from "../../types/api";

function capabilityLabel(capability: FormatCapabilityResponse): string {
  const extensions = capability.extensions.join(", ");
  return extensions ? `${capability.label} (${extensions})` : capability.label;
}

function selectedCapability(
  capabilities: FormatCapabilityResponse[],
  capabilityId: unknown,
): FormatCapabilityResponse | undefined {
  if (typeof capabilityId === "string") {
    const selected = capabilities.find((capability) => capability.id === capabilityId);
    if (selected) return selected;
  }
  if (capabilities.length === 1) return capabilities[0];
  return capabilities.find((capability) => capability.is_default);
}

function capabilityWarnings(
  capabilities: FormatCapabilityResponse[],
  capability?: FormatCapabilityResponse,
): string[] {
  const warnings: string[] = [];
  if (capabilities.length > 1 && !capability) {
    warnings.push(
      "Multiple backend capabilities match this block; choose one to persist a stable capability_id.",
    );
  }
  if (capability?.direction === "save" && capability.metadata_fidelity.level === "pixel_only") {
    warnings.push("This saver is payload-only; typed metadata may not be written.");
  }
  if (capability?.migration_scaffold) {
    warnings.push("This is a synthesized legacy capability kept for migration compatibility.");
  }
  return warnings;
}

export function FormatCapabilityConfig({
  capabilities,
  value,
  onChange,
}: {
  capabilities: FormatCapabilityResponse[];
  value: unknown;
  onChange: (capabilityId: string | null) => void;
}) {
  if (capabilities.length === 0) return null;
  const capability = selectedCapability(capabilities, value);
  const warnings = capabilityWarnings(capabilities, capability);
  const selectValue = typeof value === "string" ? value : (capability?.id ?? "");

  return (
    <div className="grid gap-2 text-sm">
      <label className="grid gap-2">
        <span className="font-medium text-ink">Format</span>
        <select
          className="w-full rounded-2xl border border-stone-300 bg-white px-4 py-3"
          disabled={capabilities.length === 1}
          onChange={(event) => onChange(event.target.value || null)}
          value={selectValue}
          title={capability?.id}
        >
          {capabilities.length > 1 ? <option value="">Select a format capability...</option> : null}
          {capabilities.map((option) => (
            <option key={option.id} value={option.id}>
              {capabilityLabel(option)}
            </option>
          ))}
        </select>
      </label>
      {capability ? (
        <div className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-600">
          {/* Verbose ``capability.id`` (e.g. ``scistudio-blocks-imaging.image.tiff.load``)
              is exposed via the select's ``title`` tooltip above. Keep only the
              structural triple here so the panel does not duplicate the dropdown
              label in a long-form id row. */}
          <div>
            {capability.data_type} / {capability.format_id} / {capability.metadata_fidelity.level}
          </div>
        </div>
      ) : null}
      {warnings.map((warning) => (
        <div
          className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
          key={warning}
        >
          {warning}
        </div>
      ))}
    </div>
  );
}
