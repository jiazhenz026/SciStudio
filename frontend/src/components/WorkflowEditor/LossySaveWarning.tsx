// ---------------------------------------------------------------------------
// ADR-043 FR-014 — Lossy-save warning chip
//
// Renders a warning chip on a SaveImage node when the source object's OME
// fields are not fully writable by the target capability's
// `metadata_fidelity`. Behaviour per spec §3 FR-014 + §4.3 T-023:
//   - Compute the set of source OME field paths NOT declared in
//     `targetCapabilityFidelity.format_metadata_writes` OR
//     `typed_meta_writes`. (`lossless` capabilities round-trip everything;
//     `pixel_only` capabilities round-trip nothing.)
//   - When the dropped set is empty, render nothing.
//   - When non-empty, render a compact amber chip listing the first few
//     dropped fields with a "+N more" suffix; a tooltip / details
//     disclosure shows the full list.
//
// The component is fully presentational and pure. Callers compute the
// source field list however they like (e.g. flatten an `OME` tree to a
// dotted-path list) and pass it via props.
// ---------------------------------------------------------------------------

import { useState } from "react";

import { extractOMEFromMetadata, lossyOmeFields } from "../../api/capabilities";
import type { MetadataFidelityResponse } from "../../types/api";

export interface LossySaveWarningProps {
  /** Dotted OME field paths present on the source object. */
  sourceOmeFields: readonly string[];
  /** `metadata_fidelity` of the target SaveImage capability. */
  targetCapabilityFidelity: MetadataFidelityResponse;
  /** How many dropped fields to show inline before truncating. Default 3. */
  inlineLimit?: number;
}

const TOOLTIP_TEXT =
  "These OME fields will be dropped when saving in this format. Pick a higher-fidelity capability to preserve them.";

export function LossySaveWarning({
  sourceOmeFields,
  targetCapabilityFidelity,
  inlineLimit = 3,
}: LossySaveWarningProps) {
  const dropped = lossyOmeFields(sourceOmeFields, targetCapabilityFidelity);
  const [showAll, setShowAll] = useState(false);

  if (dropped.length === 0) return null;

  const visible = showAll ? dropped : dropped.slice(0, inlineLimit);
  const remaining = dropped.length - visible.length;

  return (
    <div
      role="status"
      aria-label={`${dropped.length} OME field(s) will be dropped on save`}
      title={TOOLTIP_TEXT}
      data-testid="lossy-save-warning"
      className="flex flex-wrap items-center gap-1 rounded-lg border border-amber-300 bg-amber-50 px-2 py-1 text-[10px] text-amber-800"
    >
      <span aria-hidden="true">⚠</span>
      <span className="font-medium">Lossy save:</span>
      <span className="font-mono text-amber-900">
        {visible.map((field, idx) => (
          <span key={field}>
            {field}
            {idx < visible.length - 1 ? ", " : ""}
          </span>
        ))}
      </span>
      {remaining > 0 && (
        <button
          type="button"
          className="rounded border border-amber-300 bg-white px-1 text-[10px] text-amber-700 hover:bg-amber-100"
          onClick={() => setShowAll(true)}
        >
          +{remaining} more
        </button>
      )}
      {showAll && dropped.length > inlineLimit && (
        <button
          type="button"
          className="rounded border border-amber-300 bg-white px-1 text-[10px] text-amber-700 hover:bg-amber-100"
          onClick={() => setShowAll(false)}
        >
          collapse
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Flatten an OME tree (as returned by `getOMEMetadata` /
 * `extractOMEFromMetadata`) into a dotted-path list of leaf field names.
 * Used by SaveImage warning callers that have the source OME tree but not
 * a pre-computed field list.
 *
 * Arrays are indexed numerically — e.g. `channels[0].emission_wavelength`
 * becomes `channels.0.emission_wavelength`.
 *
 * Empty / undefined trees return `[]`.
 */
export function flattenOmeFields(
  tree: Record<string, unknown> | null | undefined,
  prefix = "",
): string[] {
  if (!tree || typeof tree !== "object") return [];
  const out: string[] = [];
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    // Fix #1313 bug 2: backend serializes Pydantic OME via
    // ``model_dump(mode='json')`` which includes None-valued fields by
    // default. Treating null/undefined as "present" inflated
    // sourceOmeFields and produced false-positive lossy warnings for
    // fields that were never populated. Skip null/undefined here so
    // only actually-set fields enter the comparison set.
    if (value === null || value === undefined) {
      continue;
    } else if (Array.isArray(value)) {
      value.forEach((item, idx) => {
        if (item === null || item === undefined) return;
        const arrPath = `${path}.${idx}`;
        if (typeof item === "object" && !Array.isArray(item)) {
          out.push(...flattenOmeFields(item as Record<string, unknown>, arrPath));
        } else {
          out.push(arrPath);
        }
      });
    } else if (typeof value === "object") {
      out.push(...flattenOmeFields(value as Record<string, unknown>, path));
    } else {
      out.push(path);
    }
  }
  return out;
}

/**
 * Fix #1313 bug 1 helper. Walks a block's cached outputs (the shape
 * `blockOutputs[sourceId]`) and returns the union of OME field paths
 * reachable from any nested `metadata` payload. Many imaging blocks
 * (notably `LoadImage`) emit `{ kind: "collection", items: [...] }`
 * payloads where `metadata` lives under `items[*].metadata`; the
 * previous flat `Object.values` walk in WorkflowCanvas never saw those,
 * so LossySaveWarning silently suppressed.
 *
 * Mirrors `extractRefEntries` (DataPreview.tsx) in shape:
 *   - If `value.metadata` is set, parse OME from it.
 *   - If `value.kind === "collection"` and `value.items` is an array,
 *     recurse into each item.
 *   - Otherwise (other nested objects), recurse into the values so
 *     wrappers like `{ output: { metadata: ... } }` still surface OME.
 *   - Arrays of non-collection-shaped scalars are not entered.
 */
export function collectUpstreamOmeFields(
  outputs: Record<string, unknown> | null | undefined,
): string[] {
  if (!outputs || typeof outputs !== "object") return [];
  const collected = new Set<string>();
  const visit = (value: unknown): void => {
    if (!value || typeof value !== "object") return;
    const record = value as Record<string, unknown>;
    const meta = record.metadata;
    if (meta && typeof meta === "object") {
      const ome = extractOMEFromMetadata(meta as Record<string, unknown>);
      if (ome) {
        for (const field of flattenOmeFields(ome)) collected.add(field);
      }
    }
    if (record.kind === "collection" && Array.isArray(record.items)) {
      for (const item of record.items) visit(item);
      return;
    }
    for (const v of Object.values(record)) {
      if (v && typeof v === "object" && !Array.isArray(v) && v !== meta) {
        visit(v);
      }
    }
  };
  for (const value of Object.values(outputs)) visit(value);
  return Array.from(collected);
}
