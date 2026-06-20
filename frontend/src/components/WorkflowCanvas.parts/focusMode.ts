/**
 * Focus mode — pure focus-set computation (ADR-050 §3.1, FR-017..FR-019).
 *
 * Focus mode is a frontend-only VIEW state. Nothing in this module mutates
 * workflow nodes, edges, config, layout, or runtime state (FR-018). It only
 * reads the current selection + workflow edges and returns which node/edge ids
 * should be visible, dimmed, or hidden so `WorkflowCanvas` can post-process the
 * ReactFlow node array (dispatch checklist §4.3).
 *
 * The default focus set is the entire weakly-connected component of the
 * selection:
 *   - the selected node(s);
 *   - every block reachable from them along edges (the whole chain);
 *   - all edges between blocks in that component.
 *
 * `depth` optionally narrows this to a BFS neighborhood: a finite `depth = N`
 * keeps only nodes within N undirected hops (`depth = 0` = selection only,
 * `depth = 1` = immediate neighbors). Omitting `depth` (the default) expands
 * the BFS to the component boundary = the full chain.
 */
import type { WorkflowEdge } from "../../types/api";

/** Extract the node id from a `"nodeId:port"` edge endpoint reference. */
export function nodeIdOfRef(ref: string): string {
  const idx = ref.indexOf(":");
  return idx === -1 ? ref : ref.slice(0, idx);
}

/** Stable `"source->target"` edge id, matching the canvas/edge-builder id. */
export function edgeId(edge: WorkflowEdge): string {
  return `${edge.source}->${edge.target}`;
}

export interface FocusInput {
  /** Currently selected node ids. Empty ⇒ focus mode is inert/disabled. */
  selectedIds: readonly string[];
  /** All node ids present in the workflow (so we can derive the hidden set). */
  allNodeIds: readonly string[];
  /** All workflow edges (`{source, target}` with `nodeId:port` refs). */
  edges: readonly WorkflowEdge[];
  /**
   * Optional BFS hop limit around the selection. Omit (default) to focus the
   * whole connected chain; `0` ⇒ selection only; `N` ⇒ within N undirected
   * hops.
   */
  depth?: number;
}

export interface FocusResult {
  /** True when a focus set could be computed (a non-empty selection). */
  active: boolean;
  /** Node ids that stay fully visible/emphasized (selection + neighbors). */
  visibleNodeIds: Set<string>;
  /** Node ids outside the focus set (rendered dimmed or hidden). */
  dimmedNodeIds: Set<string>;
  /** Edge ids with both endpoints inside the focus set. */
  visibleEdgeIds: Set<string>;
  /** Edge ids with at least one endpoint outside the focus set. */
  dimmedEdgeIds: Set<string>;
  /** Count of nodes outside the focus set (for the hidden-count affordance). */
  hiddenNodeCount: number;
  /** Count of edges outside the focus set (for the hidden-count affordance). */
  hiddenEdgeCount: number;
}

interface Adjacency {
  /** Undirected neighbor map: nodeId -> set of adjacent node ids. */
  neighbors: Map<string, Set<string>>;
}

function buildAdjacency(edges: readonly WorkflowEdge[]): Adjacency {
  const neighbors = new Map<string, Set<string>>();
  const link = (a: string, b: string): void => {
    let set = neighbors.get(a);
    if (!set) {
      set = new Set<string>();
      neighbors.set(a, set);
    }
    set.add(b);
  };
  for (const edge of edges) {
    const source = nodeIdOfRef(edge.source);
    const target = nodeIdOfRef(edge.target);
    if (source === target) continue;
    link(source, target);
    link(target, source);
  }
  return { neighbors };
}

/**
 * Compute the deterministic focus set from the current selection and graph
 * adjacency. Pure: no side effects, no workflow mutation (FR-018/FR-019).
 *
 * The result is stable for a given input regardless of selection or edge
 * order because membership is set-based.
 */
export function computeFocusSet(input: FocusInput): FocusResult {
  const { selectedIds, allNodeIds, edges } = input;
  // #bug — default focuses the WHOLE connected chain (entire weakly-connected
  // component of the selection): every block reachable along edges plus all
  // edges between those blocks. Previously the default was a single hop, which
  // lit only part of the chain and could highlight a shortcut edge between two
  // 1-hop neighbors that isn't on the selected chain. A finite `depth` still
  // narrows the neighborhood (used by tests / future UI); the BFS naturally
  // stops at the component boundary, so an unbounded depth = the full chain.
  const depth = input.depth ?? Number.POSITIVE_INFINITY;

  const allSet = new Set(allNodeIds);
  // Only honor selected ids that exist in the workflow.
  const seeds = selectedIds.filter((id) => allSet.has(id));

  if (seeds.length === 0) {
    // No usable selection ⇒ focus mode is inert; everything stays visible so
    // the caller can disable the control without hiding anything.
    return {
      active: false,
      visibleNodeIds: new Set(allSet),
      dimmedNodeIds: new Set<string>(),
      visibleEdgeIds: new Set(edges.map(edgeId)),
      dimmedEdgeIds: new Set<string>(),
      hiddenNodeCount: 0,
      hiddenEdgeCount: 0,
    };
  }

  const { neighbors } = buildAdjacency(edges);

  // BFS outward from the selection up to `depth` undirected hops.
  const visibleNodeIds = new Set<string>(seeds);
  let frontier = new Set<string>(seeds);
  for (let hop = 0; hop < Math.max(0, depth); hop += 1) {
    const next = new Set<string>();
    for (const nodeId of frontier) {
      const adj = neighbors.get(nodeId);
      if (!adj) continue;
      for (const neighbor of adj) {
        if (!visibleNodeIds.has(neighbor)) {
          visibleNodeIds.add(neighbor);
          next.add(neighbor);
        }
      }
    }
    if (next.size === 0) break;
    frontier = next;
  }

  const dimmedNodeIds = new Set<string>();
  for (const id of allSet) {
    if (!visibleNodeIds.has(id)) dimmedNodeIds.add(id);
  }

  const visibleEdgeIds = new Set<string>();
  const dimmedEdgeIds = new Set<string>();
  for (const edge of edges) {
    const source = nodeIdOfRef(edge.source);
    const target = nodeIdOfRef(edge.target);
    const id = edgeId(edge);
    // An edge belongs to the focus set when BOTH endpoints are in focus. An
    // edge touching the boundary (one endpoint dimmed) is itself dimmed so the
    // focused subgraph reads cleanly (ADR-050 §3.1).
    if (visibleNodeIds.has(source) && visibleNodeIds.has(target)) {
      visibleEdgeIds.add(id);
    } else {
      dimmedEdgeIds.add(id);
    }
  }

  return {
    active: true,
    visibleNodeIds,
    dimmedNodeIds,
    visibleEdgeIds,
    dimmedEdgeIds,
    hiddenNodeCount: dimmedNodeIds.size,
    hiddenEdgeCount: dimmedEdgeIds.size,
  };
}
