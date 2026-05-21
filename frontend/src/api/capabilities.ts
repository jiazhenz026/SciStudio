// ---------------------------------------------------------------------------
// ADR-043 — Frontend capability listing API client
//
// FR-012 / Phase A3 / T-020:
//   Aggregate ADR-043 IO format capabilities for the frontend port editor,
//   OME metadata browser, and lossy-save warning chip. The backend already
//   exposes capabilities per IOBlock via `BlockSummary.format_capabilities`
//   (see `src/scistudio/api/routes/blocks.py::list_blocks`), so we consume the
//   existing `/api/blocks/` endpoint and filter client-side rather than add
//   a new dedicated route. This keeps the API contract minimal (one source
//   of truth: `BlockRegistry.list_format_capabilities` semantics, surfaced
//   via the BlockListResponse already used by the palette).
//
// FR-013:
//   `getOMEMetadata` extracts the `ome` payload from a stored DataObject's
//   metadata via the existing `/api/data/{ref}` endpoint. The OME field is
//   populated by IO loaders in `scistudio-blocks-imaging` (Phase A2). When the
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
  TypeHierarchyEntry,
} from "../types/api";

export type CapabilityDirection = "load" | "save";

/**
 * Normalise an extension string for the dropdown's USER-FACING input.
 * Mirrors `PortEditorTable.normalizeExtension`: lowercase, strip any
 * leading dots, empty-in / empty-out. The port-editor persists this
 * dot-stripped form on `PortRow.extension`, so the dropdown receives
 * `"tif"` (no dot) as its prop.
 *
 * NOTE: the *backend* normalises capability extensions WITH a leading
 * dot (see `src/scistudio/blocks/io/capabilities.py::normalize_extension`),
 * so when we compare user input against backend `cap.extensions` we must
 * first re-dot the user value or strip dots from the backend values.
 * `normalizeBackendExtension` handles the backend-side normalisation;
 * `aggregateCapabilities` uses both so the user-facing "tif" matches the
 * backend's ".tif" tuple entries (Codex P1, PR #1299).
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
 * Normalise a backend-emitted extension into the user-facing form
 * (lowercase, no leading dot). Backend capability records carry their
 * extensions in canonical ".tif" / ".tiff" form per
 * `scistudio.blocks.io.capabilities.normalize_extension`; the frontend
 * compares them against the dot-stripped user input from PortEditorTable,
 * so we strip the leading dot on the backend side at compare time. We
 * keep the original tuple shape on the wire (no normalisation when the
 * client returns FormatCapabilityResponse to consumers) so any UI that
 * shows raw `cap.extensions` continues to see the canonical form.
 */
function normalizeBackendExtension(raw: string | null | undefined): string {
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
 *     `capability.data_type` (and its supertype chain). Empty string
 *     disables the type filter.
 *   - extension: lowercase. Empty string disables the extension filter so
 *     the dropdown can show every capability for a type while the user
 *     is still typing the extension.
 *   - typeHierarchy: optional `BlockSchemaResponse.type_hierarchy` for
 *     subtype-compatible matching. When omitted, the filter still walks
 *     the universal `DataObject` base so capabilities declared on
 *     `DataObject` match any subtype request — matching how the backend's
 *     `_capability_matches_type` does subtype dispatch (Codex P2, PR #1299).
 *
 * Returned capabilities are deduplicated by `id` (the same capability
 * record may be advertised by multiple aggregate IOBlocks in plugin packages
 * when they share a handler, but the `id` is package-qualified per FR-015).
 */
export interface ListCapabilitiesFilter {
  direction: CapabilityDirection;
  dataType?: string;
  extension?: string;
  typeHierarchy?: TypeHierarchyEntry[];
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
 * Walk the type ancestry of `typeName` using the supplied `typeHierarchy`.
 * Returns a set containing `typeName` plus every ancestor name reachable
 * via `base_type` links. Stops at `DataObject` (the universal base) or
 * when an entry has no base_type (root of the hierarchy).
 *
 * Even when `typeHierarchy` is not supplied, the universal `DataObject`
 * base is included so capabilities declared on `DataObject` match any
 * subtype request — that mirrors the backend's `_capability_matches_type`
 * which treats `DataObject` as the polymorphic root.
 */
export function ancestorTypeNames(
  typeName: string,
  typeHierarchy?: TypeHierarchyEntry[],
): Set<string> {
  const ancestors = new Set<string>();
  if (typeName) ancestors.add(typeName);
  // The universal DataObject base is always implicit — handlers declared
  // on it match every typed port, matching backend behaviour.
  ancestors.add("DataObject");
  if (!typeHierarchy || typeHierarchy.length === 0) return ancestors;
  const index = new Map(typeHierarchy.map((entry) => [entry.name, entry]));
  let current = index.get(typeName);
  while (current?.base_type && !ancestors.has(current.base_type)) {
    ancestors.add(current.base_type);
    current = index.get(current.base_type);
  }
  return ancestors;
}

/**
 * Pure aggregation helper extracted so unit tests can exercise the filter
 * without mocking `fetch`. Returns a stable order: capabilities are sorted
 * by `(priority DESC, id ASC)` so the first option is the highest-priority
 * default — matches `BlockRegistry`'s sort in `_find_format_capability`.
 *
 * Implementation notes (Codex review #1299):
 *  - P1: Extensions are compared after normalising BOTH sides — the user
 *    input arrives dot-stripped (PortEditorTable), and backend records
 *    arrive with leading dots (`.tif`). `normalizeBackendExtension` walks
 *    `cap.extensions` so the two agree.
 *  - P2: Type filter accepts subtype-compatible matches by walking the
 *    `typeHierarchy` ancestry of the requested type. Capabilities
 *    declared on a supertype (e.g. `DataObject`) match subtype requests
 *    (e.g. `DataFrame`/`Image`), matching the backend's
 *    `_capability_matches_type`.
 */
export function aggregateCapabilities(
  blocks: BlockListResponse,
  filter: ListCapabilitiesFilter,
): FormatCapabilityResponse[] {
  const wantedExt = normalizeExtension(filter.extension);
  const wantedType = filter.dataType?.trim() ?? "";
  const ancestors = wantedType
    ? ancestorTypeNames(wantedType, filter.typeHierarchy)
    : null;
  const seen = new Map<string, FormatCapabilityResponse>();

  for (const block of blocks.blocks ?? []) {
    for (const cap of block.format_capabilities ?? []) {
      if (cap.direction !== filter.direction) continue;
      if (ancestors && !ancestors.has(cap.data_type)) continue;
      if (wantedExt) {
        const normalized = cap.extensions.map(normalizeBackendExtension);
        if (!normalized.includes(wantedExt)) continue;
      }
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
