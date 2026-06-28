/**
 * #898 — derive human-friendly pill labels from output payloads.
 *
 * Every output dict in ``blockOutputs[block_id]`` already carries
 * ``metadata.meta.source_file`` / ``metadata.framework.source`` (full source
 * file path stamped by IO blocks). Walk the payload and pair each
 * ``data_ref`` with a display name so the pill labels read e.g.
 * ``beads.tif`` instead of ``data-873de``.
 *
 * Mirror of `LossySaveWarning.extractRefEntries` shape — keep in sync.
 */

import type { PreviewTarget } from "../../types/api";

export interface RefEntry {
  id: string;
  ref: string;
  displayName: string;
  outputPort?: string;
  target: PreviewTarget;
  initialQuery?: Record<string, unknown>;
}

function basename(p: string): string {
  const trimmed = p.replace(/[\\/]+$/, "");
  const parts = trimmed.split(/[\\/]/);
  return parts[parts.length - 1] || trimmed;
}

export function deriveDisplayName(ref: string, dataItem: Record<string, unknown>): string {
  // 0. Backend-resolved canonical display name (#1812). The backend is now the
  // single precedence authority (`resolve_display_name`) and stamps the result
  // onto each item descriptor, so trust it when present. The metadata chain
  // below is a compatibility fallback for any descriptor that predates the
  // stamp or is built outside `register_output_payload`; new origins are added
  // in the backend resolver only, never here.
  const stamped = dataItem.display_name;
  if (typeof stamped === "string" && stamped) return stamped;
  const md = dataItem.metadata;
  if (md && typeof md === "object") {
    const mdRec = md as Record<string, unknown>;
    // 0b. Generic user-set display name (#1810 interim, #1812 convention). The
    // producer composes a user-facing label — e.g. "<file> — <sheet>" for an
    // .xlsx sheet — so same-file/different-sheet items don't collide. Preferred
    // over file-based heuristics because it is an explicit presentation choice.
    const user = mdRec.user;
    if (user && typeof user === "object") {
      const displayName = (user as Record<string, unknown>).display_name;
      if (typeof displayName === "string" && displayName) return displayName;
    }
    // 1. Typed source-file metadata. Imaging and spectroscopy loaders both
    // use this when the framework source is package provenance rather than a
    // user-facing filename.
    const directSourceFile = mdRec.source_file;
    if (typeof directSourceFile === "string" && directSourceFile) return basename(directSourceFile);
    const directFilePath = mdRec.file_path;
    if (typeof directFilePath === "string" && directFilePath) return basename(directFilePath);
    const meta = mdRec.meta;
    if (meta && typeof meta === "object") {
      const sourceFile = (meta as Record<string, unknown>).source_file;
      if (typeof sourceFile === "string" && sourceFile) return basename(sourceFile);
      const filePath = (meta as Record<string, unknown>).file_path;
      if (typeof filePath === "string" && filePath) return basename(filePath);
    }
    // 2. framework.source — set by IO loaders (LoadImage etc.). Package names
    // such as "scistudio-blocks-spectroscopy" are provenance, not filenames.
    const framework = mdRec.framework;
    if (framework && typeof framework === "object") {
      const src = (framework as Record<string, unknown>).source;
      if (typeof src === "string" && src && /[\\/]/.test(src)) return basename(src);
    }
  }
  // 3. Fallback: truncated ref (today's behavior)
  return ref.slice(0, 10);
}

function collectionItemType(
  record: Record<string, unknown>,
  items: Record<string, unknown>[],
): string {
  const explicit =
    record.item_type ?? record.item_type_name ?? record.collection_item_type ?? record.type_name;
  if (typeof explicit === "string" && explicit) return explicit;
  const firstType = items.find((item) => typeof item.type_name === "string")?.type_name;
  return typeof firstType === "string" && firstType ? firstType : "DataObject";
}

function normalizeCollectionItem(item: unknown): Record<string, unknown> | null {
  if (!item || typeof item !== "object") return null;
  const record = item as Record<string, unknown>;
  const ref = record.data_ref ?? record.ref;
  if (typeof ref !== "string" || !ref) return null;
  const out: Record<string, unknown> = { data_ref: ref };
  if (typeof record.type_name === "string") out.type_name = record.type_name;
  if (record.metadata && typeof record.metadata === "object") out.metadata = record.metadata;
  // Carry the backend-stamped canonical name (#1812) so the collection grid
  // reads the same resolved label as the pills instead of re-deriving.
  if (typeof record.display_name === "string" && record.display_name)
    out.display_name = record.display_name;
  return out;
}

function typeChainFor(typeName: string): string[] {
  if (!typeName || typeName === "DataObject") return ["DataObject"];
  return ["DataObject", typeName];
}

function displayNameForPath(path: string[], fallback: string): string {
  return path[path.length - 1] || fallback;
}

function visit(payload: unknown, path: string[]): RefEntry[] {
  if (!payload || typeof payload !== "object") {
    return [];
  }
  const record = payload as Record<string, unknown>;
  if (typeof record.data_ref === "string") {
    return [
      {
        id: record.data_ref,
        ref: record.data_ref,
        displayName: deriveDisplayName(record.data_ref, record),
        outputPort: path[0],
        target: { kind: "data_ref", ref: record.data_ref },
      },
    ];
  }
  if (record.kind === "collection" && Array.isArray(record.items)) {
    const items = record.items
      .map((item) => normalizeCollectionItem(item))
      .filter((item): item is Record<string, unknown> => item !== null);
    const itemType = collectionItemType(record, items);
    const ref =
      typeof record.collection_ref === "string" && record.collection_ref
        ? record.collection_ref
        : `collection:${path.join(".") || "root"}`;
    const displayName = displayNameForPath(path, "Collection");
    return [
      {
        id: ref,
        ref,
        displayName: `${displayName} (${record.count ?? items.length})`,
        outputPort: path[0],
        target: {
          kind: "collection_ref",
          ref,
          recorded_type: itemType,
          type_chain: typeChainFor(itemType),
          collection_item_type: itemType,
        },
        initialQuery: {
          _collection_items: items,
          _collection_count: typeof record.count === "number" ? record.count : items.length,
          _collection_item_type: itemType,
        },
      },
    ];
  }
  return Object.entries(record).flatMap(([key, value]) => visit(value, [...path, key]));
}

export function extractRefEntries(payload: unknown): RefEntry[] {
  return visit(payload, []);
}
