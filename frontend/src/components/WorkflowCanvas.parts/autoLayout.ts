/**
 * Auto-layout adapter (ADR-050 §3.2, FR-020..FR-023).
 *
 * Wraps `elkjs` layered layout behind a small deterministic adapter. The
 * adapter takes workflow nodes + edges + node dimensions + an optional scope
 * and returns `{ [nodeId]: { x, y } }` positions laid out left-to-right by
 * data flow.
 *
 * Determinism (SC-006): node and edge inputs are sorted by id before being
 * handed to ELK, and ELK is configured without randomized seeds. The same
 * graph input therefore produces the same positions across repeated runs.
 *
 * Robustness: cycles and disconnected components are passed straight to ELK's
 * layered algorithm, which handles back-edges and multiple components without
 * throwing. Nodes with no layout result fall back to a deterministic grid.
 *
 * The `elk.bundled.js` entry runs ELK in-process (no Web Worker / worker URL),
 * which keeps the adapter usable in both the browser and jsdom unit tests.
 */
// elk.bundled ships its own type via lib/main.d.ts; import the bundled JS so
// no worker URL is required.
import ELK from "elkjs/lib/elk.bundled.js";
import type { ElkNode, LayoutOptions } from "elkjs/lib/elk-api";

import type { WorkflowEdge, WorkflowNode } from "../../types/api";
import {
  COMPONENT_GAP,
  HIGH_DEGREE_CLEARANCE,
  LAYER_GAP,
  NODE_SIZE,
  SIBLING_GAP,
} from "./layoutConstants";

export interface XY {
  x: number;
  y: number;
}

export type LayoutPositions = Record<string, XY>;

export interface AutoLayoutInput {
  nodes: readonly WorkflowNode[];
  edges: readonly WorkflowEdge[];
  /** Square node body size; defaults to `NODE_SIZE` (ADR-050 §2.1). */
  nodeSize?: number;
  /**
   * Optional scope limiting layout to a subset of node ids (e.g. the focus
   * set). Nodes outside the scope are excluded from both the layout request
   * and the result, so their persisted layout is left untouched (ADR-050 §3.2
   * focus-scoped tidy). When omitted, the whole graph is laid out.
   */
  scopeNodeIds?: ReadonlySet<string>;
}

/** Extract the node id from a `"nodeId:port"` edge endpoint reference. */
function nodeIdOfRef(ref: string): string {
  const idx = ref.indexOf(":");
  return idx === -1 ? ref : ref.slice(0, idx);
}

function layoutOptions(): LayoutOptions {
  return {
    "elk.algorithm": "layered",
    // Left-to-right by data flow (ADR-050 §3.2).
    "elk.direction": "RIGHT",
    "elk.layered.spacing.nodeNodeBetweenLayers": String(LAYER_GAP),
    "elk.spacing.nodeNode": String(SIBLING_GAP),
    // Keep disconnected blocks from packing tight enough that their port
    // glyphs overlap after a tidy (ADR-050 §3.2).
    "elk.spacing.componentComponent": String(COMPONENT_GAP),
    "elk.spacing.edgeNode": String(HIGH_DEGREE_CLEARANCE),
    "elk.layered.spacing.edgeNodeBetweenLayers": String(HIGH_DEGREE_CLEARANCE),
    // Deterministic crossing minimization + node placement so repeated runs on
    // the same input are stable (SC-006). NETWORK_SIMPLEX is deterministic; the
    // default crossing minimizer can randomize, so pin it.
    "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
    "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
    "elk.layered.cycleBreaking.strategy": "GREEDY",
    "elk.layered.mergeEdges": "true",
  };
}

/**
 * Deterministic grid fallback used when ELK returns no coordinate for a node
 * (should not normally happen) so callers always receive a position for every
 * in-scope node.
 */
function gridFallback(index: number, nodeSize: number): XY {
  const cols = 4;
  return {
    x: (index % cols) * (nodeSize + LAYER_GAP),
    y: Math.floor(index / cols) * (nodeSize + SIBLING_GAP),
  };
}

/**
 * Compute deterministic left-to-right positions for the (optionally scoped)
 * workflow graph. Returns a `{ [nodeId]: {x, y} }` map containing only the
 * nodes that were laid out.
 */
export async function computeAutoLayout(input: AutoLayoutInput): Promise<LayoutPositions> {
  const nodeSize = input.nodeSize ?? NODE_SIZE;
  const scope = input.scopeNodeIds;

  // Annotation notes (`block_type === "_annotation"`) are free-floating canvas
  // pseudo-nodes with no ports or edges. ELK would treat each as a disconnected
  // component and reflow it into the layered grid, tearing the note away from
  // the block it describes (#1954). Tidy lays out real workflow nodes only and
  // leaves annotation positions untouched.
  //
  // Filter + sort nodes by id for a stable ELK input order (SC-006).
  const scopedNodes = input.nodes
    .filter((node) => node.block_type !== "_annotation")
    .filter((node) => (scope ? scope.has(node.id) : true))
    .slice()
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));

  if (scopedNodes.length === 0) return {};

  const scopedIds = new Set(scopedNodes.map((node) => node.id));

  // Keep only edges whose BOTH endpoints are in scope, de-duplicate, and sort
  // for a stable order. Self-loops are dropped (ELK rejects degenerate edges
  // and they carry no layout signal).
  const seenEdges = new Set<string>();
  const scopedEdges = input.edges
    .map((edge) => ({
      source: nodeIdOfRef(edge.source),
      target: nodeIdOfRef(edge.target),
    }))
    .filter((edge) => {
      if (edge.source === edge.target) return false;
      if (!scopedIds.has(edge.source) || !scopedIds.has(edge.target)) return false;
      const key = `${edge.source}->${edge.target}`;
      if (seenEdges.has(key)) return false;
      seenEdges.add(key);
      return true;
    })
    .sort((a, b) => {
      const ka = `${a.source}->${a.target}`;
      const kb = `${b.source}->${b.target}`;
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });

  const graph: ElkNode = {
    id: "root",
    layoutOptions: layoutOptions(),
    children: scopedNodes.map((node) => ({
      id: node.id,
      width: nodeSize,
      height: nodeSize,
    })),
    edges: scopedEdges.map((edge, index) => ({
      id: `e${index}`,
      sources: [edge.source],
      targets: [edge.target],
    })),
  };

  const elk = new ELK();
  const result = await elk.layout(graph);

  const positions: LayoutPositions = {};
  const children = result.children ?? [];
  scopedNodes.forEach((node, index) => {
    const laidOut = children.find((child) => child.id === node.id);
    if (laidOut && typeof laidOut.x === "number" && typeof laidOut.y === "number") {
      // Round to whole pixels so layout output is byte-stable across runs and
      // does not introduce floating-point jitter into persisted positions.
      positions[node.id] = { x: Math.round(laidOut.x), y: Math.round(laidOut.y) };
    } else {
      positions[node.id] = gridFallback(index, nodeSize);
    }
  });

  return positions;
}
