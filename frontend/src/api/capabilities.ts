// ---------------------------------------------------------------------------
// ADR-043 — Frontend capability listing API client
//
// FR-012 / Phase A3 / T-020:
//   Aggregate ADR-043 IO format capabilities for the frontend port editor,
//   OME metadata browser, and lossy-save warning chip. The backend already
//   exposes capabilities per IOBlock via `BlockSummary.format_capabilities`
//   (see `src/scieasy/api/routes/blocks.py::list_blocks`), so we consume the
//   existing `/api/blocks/` endpoint and filter client-side rather than add
//   a new dedicated route. This keeps the API contract minimal (one source
//   of truth: `BlockRegistry.list_format_capabilities` semantics, surfaced
//   via the BlockListResponse already used by the palette).
//
// FR-013:
//   `getOMEMetadata` extracts the `ome` payload from a stored DataObject's
//   metadata via the existing `/api/data/{ref}` endpoint. The OME field is
//   populated by IO loaders in `scieasy-blocks-imaging` (Phase A2). When the
//   field is absent or null, this helper returns `null` so callers can
//   gracefully hide the "OME metadata" button.
//
// Wire shapes mirror the backend `FormatCapabilityResponse` and
// `MetadataFidelityResponse` already typed in `types/api.ts`.
// ---------------------------------------------------------------------------

import { api } from "../lib/api";
import type {
  BlockListResponse,
  FormatCapabilityResponse,
  MetadataFidelityResponse,
} from "../types/api";

export type CapabilityDirection = "load" | "save";

/**
 * Normalise an extension string the same way the backend
 * (`scieasy.blocks.io.capabilities.normalize_extension`) does: lowercase,
 * strip any leading dots. Returns "" for empty input. Mirrors
 * `PortEditorTable.normalizeExtension` so the dropdown filter agrees with
 * how port-editor inputs are persisted.
 */
export function normalizeExtension(raw: string | null | undefined): string {
  if (!raw) return "";
  let text = String(raw).trim();
  while (text.startsWith(".")) {
    text = text.slice(1);
  }
  return text.toLowerCase();
}

/**
 * Capability listing filter.
 *
 * Mirrors `BlockRegistry.list_format_capabilities` keyword arguments:
 *   - direction: "load" | "save" — required for FR-012 (port editor never
 *     mixes directions).
 *   - dataType: DataObject subclass name, matched against
 *     `capability.data_type` (and inherited types if present in the
 *     `type_hierarchy`). Empty string disables the type filter.
 *   - extension: lowercase, no leading dot. Empty string disables the
 *     extension filter so the dropdown can show every capability for a
 *     type while the user is still typing the extension.
 *
 * Returned capabilities are deduplicated by `id` (the same capability
 * record may be advertised by multiple aggregate IOBlocks in plugin packages
 * when they share a handler, but the `id` is package-qualified per FR-015).
 */
export interface ListCapabilitiesFilter {
  direction: CapabilityDirection;
  dataType?: string;
  extension?: string;
}

/**
 * Fetch matching IO format capabilities from the backend. Pulls the full
 * block list once and filters client-side; the block list is already
 * cached by the palette, so this is cheap on a warm app and a single
 * round-trip on a cold one. Callers that need cross-component caching
 * should layer it in the calling component (e.g. with a Zustand slice or
 * a memoised hook).
 */
export async function listCapabilities(
  filter: ListCapabilitiesFilter,
): Promise<FormatCapabilityResponse[]> {
  const blocks: BlockListResponse = await api.listBlocks();
  return aggregateCapabilities(blocks, filter);
}

/**
 * Pure aggregation helper extracted so unit tests can exercise the filter
 * without mocking `fetch`. Returns a stable order: capabilities are sorted
 * by `(priority DESC, id ASC)` so the first option is the highest-priority
 * default — matches `BlockRegistry`'s sort in `_find_format_capability`.
 */
export function aggregateCapabilities(
  blocks: BlockListResponse,
  filter: ListCapabilitiesFilter,
): FormatCapabilityResponse[] {
  const wantedExt = normalizeExtension(filter.extension);
  const wantedType = filter.dataType?.trim() ?? "";
  const seen = new Map<string, FormatCapabilityResponse>();

  for (const block of blocks.blocks ?? []) {
    for (const cap of block.format_capabilities ?? []) {
      if (cap.direction !== filter.direction) continue;
      if (wantedType && cap.data_type !== wantedType) continue;
      if (wantedExt && !cap.extensions.includes(wantedExt)) continue;
      if (!seen.has(cap.id)) {
        seen.set(cap.id, cap);
      }
    }
  }

  const list = Array.from(seen.values());
  list.sort((a, b) => {
    if (a.priority !== b.priority) return b.priority - a.priority;
    return a.id.localeCompare(b.id);
  });
  return list;
}

// ---------------------------------------------------------------------------
// FR-013 — OME metadata accessor
// ---------------------------------------------------------------------------

/**
 * Loose OME tree. The backend serialises `Image.Meta.ome` (an
 * `ome_types.model.OME` instance) via pydantic `model_dump()` into the
 * `metadata` dict on `/api/data/{ref}`. The exact key path is
 * `metadata.meta.ome` (mirrors the typed Meta carrier).
 *
 * We model the wire shape as a permissive nested record because OME-XML
 * carries arbitrary StructuredAnnotations and vendor-specific extensions
 * that we cannot fully type at the frontend boundary. The panel renders
 * a generic tree; consumers that need typed access should extract typed
 * subfields at the call site.
 */
export type OMETree = Record<string, unknown>;

/**
 * Return the OME tree attached to a stored DataObject, or `null` when the
 * object has no OME metadata (e.g. DataFrame outputs, or Image objects
 * loaded before Phase A2 populated the field).
 *
 * Probes three locations in order:
 *   1. `metadata.meta.ome` — canonical location for typed Image.Meta.ome.
 *   2. `metadata.ome` — flat alias used by some preview adapters.
 *   3. `metadata.framework.ome` — defensive fallback for plugin packages
 *      that namespace metadata under `framework.*`.
 */
export async function getOMEMetadata(objectId: string): Promise<OMETree | null> {
  const payload = await api.getDataMetadata(objectId);
  return extractOMEFromMetadata(payload.metadata);
}

/**
 * Pure extractor — broken out so tests can exercise it without a mocked
 * fetch and so other components (e.g. `DataPreview`) can call it with an
 * already-loaded metadata payload to decide whether to render the OME
 * button.
 */
export function extractOMEFromMetadata(
  metadata: Record<string, unknown> | null | undefined,
): OMETree | null {
  if (!metadata || typeof metadata !== "object") return null;
  const meta = metadata as Record<string, unknown>;

  const fromTypedMeta = (meta.meta as Record<string, unknown> | undefined)?.ome;
  if (isRecord(fromTypedMeta)) return fromTypedMeta;

  const fromFlat = meta.ome;
  if (isRecord(fromFlat)) return fromFlat;

  const fromFramework = (meta.framework as Record<string, unknown> | undefined)
    ?.ome;
  if (isRecord(fromFramework)) return fromFramework;

  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// ---------------------------------------------------------------------------
// FR-014 — Lossy-save field diff
// ---------------------------------------------------------------------------

/**
 * Return the OME field names present on the source object but NOT declared
 * as writable by the target capability's `metadata_fidelity`. Used by the
 * SaveImage warning chip to surface which fields will silently drop.
 *
 * `sourceOmeFields` is a flat list of dotted field paths (e.g.
 * `pixels.physical_size_x`, `channels.0.emission_wavelength`); the
 * dotted form mirrors how OME-types lays out its model in `model_dump()`.
 *
 * A field is considered "writable" when it appears in EITHER:
 *   - `metadata_fidelity.format_metadata_writes` (round-tripped via the
 *     format's native metadata block), OR
 *   - `metadata_fidelity.typed_meta_writes` (round-tripped via the
 *     typed Image.Meta sidecar).
 *
 * `lossless` capabilities round-trip everything; the helper returns `[]`
 * regardless of source field count. `pixel_only` capabilities round-trip
 * nothing; every source field appears in the dropped list.
 */
export function lossyOmeFields(
  sourceOmeFields: readonly string[],
  targetFidelity: MetadataFidelityResponse,
): string[] {
  if (targetFidelity.level === "lossless") return [];
  const writable = new Set<string>([
    ...(targetFidelity.format_metadata_writes ?? []),
    ...(targetFidelity.typed_meta_writes ?? []),
  ]);
  return sourceOmeFields.filter((field) => !writable.has(field));
}
