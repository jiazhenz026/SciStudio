/**
 * ADR-044 — run-view helpers for `subworkflow_block` nodes.
 *
 * At run start the parser inline-flattens every subworkflow reference, so the
 * scheduler emits status/output events keyed by PREFIXED inner ids of the form
 * `<subworkflowNodeId>__<innerNodeId>` (recursively, for nested subworkflows).
 * The collapsed `subworkflow` node on the parent canvas (id `<subworkflowNodeId>`)
 * and the expanded child canvas (inner ids without the prefix) therefore never
 * match the raw event keys, so neither shows run status nor preview data.
 *
 * These pure helpers bridge that gap:
 *   - `aggregateSubworkflowStatus` rolls every inner block's state up into one
 *     status glyph for the collapsed node.
 *   - `buildScopedBlockOutputs` produces an outputs map addressable by the ids a
 *     canvas actually renders: child nodes aliased to their prefixed run outputs
 *     (so an expanded child canvas previews live data) and each subworkflow node
 *     mapped from its exposed-output surface to the inner block outputs.
 */
import type { ResolvedSubworkflowPort, WorkflowNode } from "../../types/api";

/** Block-state values the reducer derives from `block_<type>` events. */
const ERROR_STATES = new Set(["error", "fail", "failed", "failure"]);
const RUNNING_STATES = new Set(["running", "started"]);
const DONE_STATES = new Set(["done", "success", "succeeded", "completed", "skipped"]);

/** Block types rendered as a collapsed subworkflow container (mirror of
 *  `useFlowNodes.SUBWORKFLOW_BLOCK_TYPES`, duplicated here to keep this module
 *  dependency-free and unit-testable). */
const SUBWORKFLOW_TYPES = new Set(["subworkflow_block", "subworkflow_broken"]);

/**
 * Roll the flattened inner blocks' states up into a single status for a
 * collapsed subworkflow node. *prefix* is the full inner-key prefix for the
 * node, i.e. `${runScopePrefix}${nodeId}__`.
 *
 * Priority: error > running (incl. partial progress) > cancelled > done > idle.
 * "Partial progress" (some inner done, none currently running) still reads as
 * running so the glyph keeps spinning until every observed inner block settles.
 */
export function aggregateSubworkflowStatus(
  blockStates: Record<string, string>,
  prefix: string,
): string {
  const values: string[] = [];
  for (const [key, value] of Object.entries(blockStates)) {
    if (key.startsWith(prefix)) values.push(value);
  }
  if (values.length === 0) return "idle";
  if (values.some((v) => ERROR_STATES.has(v))) return "error";
  if (values.some((v) => RUNNING_STATES.has(v))) return "running";
  if (values.some((v) => v === "cancelled")) return "cancelled";
  if (values.every((v) => DONE_STATES.has(v))) return "done";
  return "running";
}

/** Split an exposed-port name of the auto-derived dot form `"<inner>.<port>"`.
 *  Returns null when the name is not in that form (e.g. a hand-authored exposed
 *  name), in which case the preview mapping for that port is skipped.
 *
 *  TODO(#890): hand-authored `exposed_ports` may name a port arbitrarily while
 *    its `internal` ref still points at `<inner>.<port>`. Carrying `internal`
 *    through the resolved-port surface would map those too; auto-derived ports
 *    (the import default) already encode `<inner>.<port>` in the name.
 */
function splitExposedName(name: string): { inner: string; port: string } | null {
  const dot = name.indexOf(".");
  if (dot <= 0 || dot >= name.length - 1) return null;
  return { inner: name.slice(0, dot), port: name.slice(dot + 1) };
}

type OutputsMap = Record<string, Record<string, unknown>>;

/**
 * Build an outputs map addressable by the node ids a canvas renders, given the
 * raw run outputs (keyed by flattened `<...>__<id>` ids) and the canvas's
 * `runScopePrefix` (`""` for a top-level workflow, `"<sw>__"` for a child
 * canvas opened from a subworkflow node).
 *
 * For every node on the canvas:
 *   - a subworkflow container is keyed by its node id and its value maps each
 *     exposed output `name` to the matching inner block output value;
 *   - any other node is aliased to its prefixed run outputs so an expanded
 *     child canvas previews live data under the child's own node id.
 *
 * The raw map is spread through first so a top-level canvas (empty prefix, no
 * subworkflow selected) is unchanged.
 */
export function buildScopedBlockOutputs(
  nodes: WorkflowNode[],
  blockOutputs: OutputsMap,
  runScopePrefix: string,
): OutputsMap {
  const scoped: OutputsMap = { ...blockOutputs };
  for (const node of nodes) {
    if (SUBWORKFLOW_TYPES.has(node.block_type)) {
      const exposed = node.resolved_ports?.outputs ?? [];
      const mapped = mapExposedOutputs(exposed, blockOutputs, `${runScopePrefix}${node.id}__`);
      if (Object.keys(mapped).length > 0) scoped[node.id] = mapped;
      continue;
    }
    const runOutputs = blockOutputs[`${runScopePrefix}${node.id}`];
    if (runOutputs) scoped[node.id] = runOutputs;
  }
  return scoped;
}

function mapExposedOutputs(
  exposed: ResolvedSubworkflowPort[],
  blockOutputs: OutputsMap,
  innerPrefix: string,
): Record<string, unknown> {
  const mapped: Record<string, unknown> = {};
  for (const port of exposed) {
    const split = splitExposedName(port.name);
    if (!split) continue;
    const innerOutputs = blockOutputs[`${innerPrefix}${split.inner}`];
    if (innerOutputs && split.port in innerOutputs) {
      mapped[port.name] = innerOutputs[split.port];
    }
  }
  return mapped;
}
