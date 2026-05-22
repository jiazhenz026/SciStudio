/**
 * #898 — derive human-friendly pill labels from output payloads.
 *
 * Every output dict in ``blockOutputs[block_id]`` already carries
 * ``metadata.framework.source`` (full source file path stamped by
 * LoadImage and other IO blocks). Walk the payload and pair each
 * ``data_ref`` with a display name so the pill labels read e.g.
 * ``beads.tif`` instead of ``data-873de``.
 *
 * Mirror of `LossySaveWarning.extractRefEntries` shape — keep in sync.
 */

export interface RefEntry {
  ref: string;
  displayName: string;
}

function basename(p: string): string {
  const trimmed = p.replace(/[\\/]+$/, "");
  const parts = trimmed.split(/[\\/]/);
  return parts[parts.length - 1] || trimmed;
}

function deriveDisplayName(ref: string, dataItem: Record<string, unknown>): string {
  const md = dataItem.metadata;
  if (md && typeof md === "object") {
    const mdRec = md as Record<string, unknown>;
    // 1. framework.source — set by IO loaders (LoadImage etc.)
    const framework = mdRec.framework;
    if (framework && typeof framework === "object") {
      const src = (framework as Record<string, unknown>).source;
      if (typeof src === "string" && src) return basename(src);
    }
    // 2. meta.source_file — typed Image.Meta
    const meta = mdRec.meta;
    if (meta && typeof meta === "object") {
      const sourceFile = (meta as Record<string, unknown>).source_file;
      if (typeof sourceFile === "string" && sourceFile) return basename(sourceFile);
      // 3. meta.file_path — Artifact
      const filePath = (meta as Record<string, unknown>).file_path;
      if (typeof filePath === "string" && filePath) return basename(filePath);
    }
  }
  // 4. Fallback: truncated ref (today's behavior)
  return ref.slice(0, 10);
}

export function extractRefEntries(payload: unknown): RefEntry[] {
  if (!payload || typeof payload !== "object") {
    return [];
  }
  const record = payload as Record<string, unknown>;
  if (typeof record.data_ref === "string") {
    return [{ ref: record.data_ref, displayName: deriveDisplayName(record.data_ref, record) }];
  }
  if (record.kind === "collection" && Array.isArray(record.items)) {
    return record.items.flatMap((item) => extractRefEntries(item));
  }
  return Object.values(record).flatMap((value) => extractRefEntries(value));
}
