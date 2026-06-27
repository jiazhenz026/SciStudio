// #1799 — readable plot-target labels.
//
// The plot link/relink picker used to show a block by its opaque `node_id`
// (`<block_type>-<timestamp>`), which users could not map back to a block on
// the canvas. These helpers render a target the same way the canvas labels a
// block — the registry display name — plus a stable disambiguating index when
// two blocks share that name, so the picker rows read like the canvas.

import type { BlockSchemaResponse, BlockSummary, PlotTargetItem } from "../types/api";

/** Registry display name for a block type, mirroring the canvas `resolveLabel`. */
export function blockDisplayName(
  blockType: string,
  blocks: BlockSummary[],
  schemas: Record<string, BlockSchemaResponse>,
): string {
  const summary = blocks.find((block) => block.type_name === blockType);
  return summary?.name ?? schemas[blockType]?.name ?? blockType;
}

/**
 * Human label for a target's block: prefer an explicit user label
 * (`node.config.label`, surfaced as `node_label`) when present, otherwise the
 * registry display name. Never the opaque `node_id`.
 */
export function targetBlockLabel(
  target: PlotTargetItem,
  blocks: BlockSummary[],
  schemas: Record<string, BlockSchemaResponse>,
): string {
  const explicit = target.node_label?.trim();
  return explicit || blockDisplayName(target.block_type, blocks, schemas);
}

export interface ReadableTarget {
  /** Block label plus a `#n` suffix when its display name is shared. */
  blockLabel: string;
  /** Primary row text: "<blockLabel> · <output_port>". */
  primary: string;
  /** Output core type (e.g. "Spectrum"); empty when unknown. */
  outputType: string;
  /** True when the bound output has no materialized run output yet. */
  pending: boolean;
}

/**
 * Build readable descriptors keyed by `target_id`. The disambiguating index is
 * assigned per distinct `node_id` within a shared-name group, ordered by
 * `node_id` so the index is stable regardless of the picker's display sort
 * (which can move the selected node to the top). The index is only a textual
 * hint — the precise disambiguator is the hover → canvas highlight.
 */
export function describeReadableTargets(
  targets: PlotTargetItem[],
  blocks: BlockSummary[],
  schemas: Record<string, BlockSchemaResponse>,
): Map<string, ReadableTarget> {
  const labelByNode = new Map<string, string>();
  const nodesByLabel = new Map<string, Set<string>>();
  for (const target of targets) {
    if (labelByNode.has(target.node_id)) continue;
    const label = targetBlockLabel(target, blocks, schemas);
    labelByNode.set(target.node_id, label);
    const group = nodesByLabel.get(label) ?? new Set<string>();
    group.add(target.node_id);
    nodesByLabel.set(label, group);
  }

  const indexByNode = new Map<string, number>();
  for (const nodeIds of nodesByLabel.values()) {
    if (nodeIds.size < 2) continue;
    [...nodeIds].sort().forEach((nodeId, i) => indexByNode.set(nodeId, i + 1));
  }

  const result = new Map<string, ReadableTarget>();
  for (const target of targets) {
    const base = labelByNode.get(target.node_id) ?? target.block_type;
    const index = indexByNode.get(target.node_id);
    const blockLabel = index ? `${base} #${index}` : base;
    result.set(target.target_id, {
      blockLabel,
      primary: `${blockLabel} · ${target.output_port}`,
      outputType: target.output_type ?? "",
      pending: !target.latest_output_available,
    });
  }
  return result;
}
