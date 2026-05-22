// Extracted from BlockNode.tsx as part of the #1422 god-file split.
// Inline-config helper data and capability-selector helpers. Pure functions
// over schema / capability objects — no React, no hooks.

import type { FormatCapabilityResponse } from "../../../types/api";

export interface ConfigProperty {
  key: string;
  schema: Record<string, unknown>;
}

export function getTopConfigProperties(configSchema?: {
  properties?: Record<string, Record<string, unknown>>;
}): ConfigProperty[] {
  if (!configSchema?.properties) return [];

  return Object.entries(configSchema.properties)
    .map(([key, schema]) => ({ key, schema }))
    .sort((a, b) => {
      const pa = (a.schema.ui_priority as number) ?? 999;
      const pb = (b.schema.ui_priority as number) ?? 999;
      return pa - pb;
    })
    .slice(0, 3);
}

export function capabilityLabel(capability: FormatCapabilityResponse): string {
  const extensions = capability.extensions.join(", ");
  return extensions ? `${capability.label} (${extensions})` : capability.label;
}

export function selectedCapability(
  capabilities: FormatCapabilityResponse[],
  capabilityId: unknown,
): FormatCapabilityResponse | undefined {
  if (typeof capabilityId === "string") {
    const selected = capabilities.find((capability) => capability.id === capabilityId);
    if (selected) return selected;
  }
  if (capabilities.length === 1) return capabilities[0];
  const defaultCapability = capabilities.find((capability) => capability.is_default);
  return defaultCapability;
}

export function capabilityWarning(
  capabilities: FormatCapabilityResponse[],
  capability?: FormatCapabilityResponse,
): string | null {
  if (capabilities.length > 1 && !capability) {
    return "Choose a format capability";
  }
  if (!capability) return null;
  if (capability.direction === "save" && capability.metadata_fidelity.level === "pixel_only") {
    return "Payload only; typed metadata may not be written";
  }
  if (capability.migration_scaffold) {
    return "Legacy synthesized capability";
  }
  return null;
}
