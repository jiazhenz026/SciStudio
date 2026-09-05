/**
 * ADR-054 spec 4 (T-014) — the dependency graph as a secondary view (FR-032).
 *
 * The tab's centre shows either the panel host or this view. It draws the
 * *version* graph: one node per variable version — a name as one cell changed
 * it — with the edges the analysis reports and the origin of each.
 *
 * **The graph library is the canvas's.** `@xyflow/react` draws it and `elkjs`
 * lays it out, which is the pair `WorkflowCanvas` and
 * `WorkflowCanvas.parts/autoLayout.ts` already use. A-008 asks for exactly
 * that and nothing new is introduced: the version graph is a second consumer
 * of a dependency already in the bundle, not a reason for a third.
 *
 * **The version graph is derived, and only from the runtime's own facts.**
 * `GET /api/explore/sessions/{id}/graph` sends the *cell*-level edges plus the
 * changed set of every cell; the backend's own `_version_edges` in
 * `src/scistudio/explore/dependency_analysis.py` derives the version edges
 * from exactly those two, and `buildVersionGraph` below performs that same
 * derivation. Nothing here decides what depends on what — every edge, every
 * origin and every mark is copied — but the derivation *is* duplicated, and
 * that duplication is registered as a follow-up rather than hidden (F-A4-001).
 *
 * **Selection highlights and does nothing else.** Clicking a node selects its
 * whole weakly-connected region, which is what FR-032's "a connected region
 * selectable" asks for. ADR-054 §4.5's subgraph operation belongs to a later
 * spec (A-009), so there is no callback out of this module, no store write,
 * and no hook left behind for one: a consumer arrives with that spec.
 *
 * TODO(#2253): the version-edge derivation is duplicated from the backend's
 *   `_version_edges`, because `GraphResponse` publishes the cell-level edges
 *   and the changed sets but not the version edges themselves.
 *   Out of scope per the ADR-054 assembly dispatch: the route is
 *   `src/scistudio/api/routes/explore.py`, and no agent here writes
 *   `src/scistudio/**`.
 *   Followup: docs/planning/adr-054-assembly-followups.md, `F-A4-001`.
 */

import { Background, Controls, ReactFlow, ReactFlowProvider } from "@xyflow/react";
import type { Edge, Node, NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import ELK from "elkjs/lib/elk.bundled.js";
import type { ElkNode } from "elkjs/lib/elk-api";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { CellView, ExploreGraphState } from "../store/types";
import type { ExploreCellMarkKind } from "../types/ui";

import type { ExploreRegionProps } from "./regions/ExploreRegions";

/** The node type name registered with `ReactFlow`. */
export const VERSION_NODE_TYPE = "exploreVersion";

/** Node box, in the units both the fallback grid and ELK lay out in. */
const NODE_WIDTH = 168;
const NODE_HEIGHT = 44;
const COLUMN_GAP = 96;
const ROW_GAP = 24;

/** The two marks that highlight a version node (FR-032). */
const HIGHLIGHT_MARKS: readonly ExploreCellMarkKind[] = ["stale", "out_of_order"];

/**
 * One version node's payload.
 *
 * `name` is `null` for the sink a reading cell that changes nothing becomes.
 * The backend keeps that reader in its version graph the same way — a display
 * cell is a sink but must still appear — so dropping it here would lose the
 * one node the person is most likely looking for.
 */
export interface VersionNodeData extends Record<string, unknown> {
  cellId: string;
  name: string | null;
  /** Copied from the runtime's marks on the cell; never computed here. */
  marks: ExploreCellMarkKind[];
  /** `true` when the cell carries a stale or out-of-order mark (FR-032). */
  highlighted: boolean;
  /** Position of the cell in the graph's written order; the layout column. */
  column: number;
  /** Position of this version among the cell's versions; the layout row. */
  row: number;
}

/** One version edge, carrying the origin the analysis gave it. */
export interface VersionEdgeModel {
  id: string;
  source: string;
  target: string;
  /** The name read across this edge. */
  name: string;
  /** `static_assignment`, `observed_change` or `unknown_binding`. */
  origin: string;
}

export interface VersionGraphModel {
  nodes: { id: string; data: VersionNodeData }[];
  edges: VersionEdgeModel[];
}

/** The id of one version node. Stable, so a re-fetch does not move selection. */
export function versionNodeId(cellId: string, name: string | null): string {
  return name === null ? `${cellId}::` : `${cellId}::${name}`;
}

/** The label a version node shows: the name, or the cell for a sink. */
export function versionNodeLabel(data: VersionNodeData): string {
  return data.name ?? data.cellId;
}

/**
 * Derive the version graph from one `GraphResponse` and the session's cells.
 *
 * Mirrors `_version_edges` in `scistudio/explore/dependency_analysis.py`: for
 * each cell-level edge, the source is the version `(definer, name)` and the
 * targets are the versions the *reader* changes — or, when the reader changes
 * nothing, the reader itself as a sink.
 *
 * Deterministic: cells keep the graph's written order and names are sorted
 * inside a cell, so the same response always builds the same model and the
 * layout below does not jitter between two identical fetches.
 */
export function buildVersionGraph(
  graph: ExploreGraphState,
  cells: readonly CellView[],
): VersionGraphModel {
  const marksByCell = new Map<string, ExploreCellMarkKind[]>(
    cells.map((cell) => [cell.cellId, cell.marks]),
  );
  const column = new Map<string, number>();
  graph.cells.forEach((cellId, index) => column.set(cellId, index));

  const nodes = new Map<string, { id: string; data: VersionNodeData }>();
  const rowsUsed = new Map<string, number>();

  const put = (cellId: string, name: string | null) => {
    const id = versionNodeId(cellId, name);
    const held = nodes.get(id);
    if (held) return held;
    const marks = marksByCell.get(cellId) ?? [];
    const row = rowsUsed.get(cellId) ?? 0;
    rowsUsed.set(cellId, row + 1);
    const created = {
      id,
      data: {
        cellId,
        name,
        marks,
        // Copied, not computed: `stale` and `out_of_order` are the runtime's
        // marks on the cell, and this only asks whether it carries one.
        highlighted: marks.some((mark) => HIGHLIGHT_MARKS.includes(mark)),
        column: column.get(cellId) ?? graph.cells.length,
        row,
      } satisfies VersionNodeData,
    };
    nodes.set(id, created);
    return created;
  };

  // Every version the analysis knows of, in the notebook's own order, so a
  // cell that changes a name nothing reads is still on screen.
  for (const cellId of graph.cells) {
    for (const name of [...(graph.changedSets[cellId] ?? [])].sort()) {
      put(cellId, name);
    }
  }

  const edges: VersionEdgeModel[] = [];
  for (const edge of graph.edges) {
    const source = put(edge.definer, edge.name);
    const readerVersions = [...(graph.changedSets[edge.reader] ?? [])].sort();
    const targets =
      readerVersions.length === 0
        ? [put(edge.reader, null)]
        : readerVersions.map((name) => put(edge.reader, name));
    for (const target of targets) {
      const id = `${source.id}->${target.id}:${edge.name}`;
      // The same (definer, name) can reach one reader version through two
      // cell-level edges; keying by the triple keeps one drawn edge per pair.
      if (edges.some((existing) => existing.id === id)) continue;
      edges.push({
        id,
        source: source.id,
        target: target.id,
        name: edge.name,
        origin: edge.origin,
      });
    }
  }

  return { nodes: [...nodes.values()], edges };
}

/**
 * Every node reachable from `nodeId` when the edges are read as undirected.
 *
 * FR-032's "a connected region selectable". Undirected because the region a
 * person means when they click a variable is everything that version is part
 * of, upstream and down, not just what it feeds.
 */
export function connectedRegion(model: VersionGraphModel, nodeId: string): Set<string> {
  const neighbours = new Map<string, string[]>();
  const link = (from: string, to: string) => {
    const held = neighbours.get(from);
    if (held) held.push(to);
    else neighbours.set(from, [to]);
  };
  for (const edge of model.edges) {
    link(edge.source, edge.target);
    link(edge.target, edge.source);
  }
  const seen = new Set<string>();
  const queue = [nodeId];
  while (queue.length > 0) {
    const current = queue.pop() as string;
    if (seen.has(current)) continue;
    seen.add(current);
    for (const next of neighbours.get(current) ?? []) {
      if (!seen.has(next)) queue.push(next);
    }
  }
  return seen;
}

/** Deterministic positions used before — and instead of — an ELK result. */
function fallbackPositions(model: VersionGraphModel): Record<string, { x: number; y: number }> {
  const positions: Record<string, { x: number; y: number }> = {};
  for (const node of model.nodes) {
    positions[node.id] = {
      x: node.data.column * (NODE_WIDTH + COLUMN_GAP),
      y: node.data.row * (NODE_HEIGHT + ROW_GAP),
    };
  }
  return positions;
}

/** Lay the version graph out left to right, as `autoLayout.ts` lays the canvas out. */
async function elkPositions(
  model: VersionGraphModel,
): Promise<Record<string, { x: number; y: number }>> {
  const graph: ElkNode = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.layered.spacing.nodeNodeBetweenLayers": String(COLUMN_GAP),
      "elk.spacing.nodeNode": String(ROW_GAP),
      // The same deterministic strategies the canvas pins, for the same
      // reason: an identical graph must lay out identically twice.
      "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
      "elk.layered.cycleBreaking.strategy": "GREEDY",
    },
    children: model.nodes.map((node) => ({ id: node.id, width: NODE_WIDTH, height: NODE_HEIGHT })),
    edges: model.edges
      // ELK rejects a self-loop, and a cell that reads a name it also changes
      // produces one; it carries no layout signal, so it is dropped here and
      // still drawn by `ReactFlow`.
      .filter((edge) => edge.source !== edge.target)
      .map((edge) => ({ id: edge.id, sources: [edge.source], targets: [edge.target] })),
  };
  const result = await new ELK().layout(graph);
  const positions: Record<string, { x: number; y: number }> = {};
  for (const child of result.children ?? []) {
    if (typeof child.x === "number" && typeof child.y === "number") {
      positions[child.id] = { x: Math.round(child.x), y: Math.round(child.y) };
    }
  }
  return positions;
}

/** One version node: the name, the cell that changed it, and its marks. */
function VersionNode({ data, selected }: NodeProps<Node<VersionNodeData>>) {
  const label = versionNodeLabel(data);
  return (
    <div
      className={`rounded border px-2 py-1 text-[11px] shadow-sm ${
        data.highlighted ? "border-ember bg-amber-50 text-ink" : "border-stone-300 bg-white"
      } ${selected ? "ring-2 ring-ember" : ""}`}
      data-cell-id={data.cellId}
      data-highlighted={data.highlighted ? "true" : "false"}
      data-marks={data.marks.join(" ")}
      data-selected={selected ? "true" : "false"}
      data-testid={`explore-graph-node-${versionNodeId(data.cellId, data.name)}`}
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT }}
    >
      <p className="truncate font-mono font-semibold text-ink">{label}</p>
      <p className="truncate text-[10px] text-stone-500">
        {data.name === null ? "reads only" : data.cellId}
        {data.marks.length > 0 ? ` · ${data.marks.join(", ")}` : ""}
      </p>
    </div>
  );
}

const NODE_TYPES = { [VERSION_NODE_TYPE]: VersionNode };

/**
 * The secondary view itself.
 *
 * Takes the region props so `GraphViewRegion` can hand it the tab and the
 * session unchanged; only the session is read, because a graph is a property
 * of the session rather than of the tab showing it.
 */
export function GraphView({ session }: ExploreRegionProps) {
  const graph = session?.graph ?? null;
  const cells = useMemo(() => session?.cells ?? [], [session?.cells]);

  const model = useMemo(
    () => (graph ? buildVersionGraph(graph, cells) : { nodes: [], edges: [] }),
    [graph, cells],
  );

  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [selection, setSelection] = useState<ReadonlySet<string>>(new Set<string>());

  // A model change invalidates both: a version that is gone cannot stay
  // selected, and a position from the previous graph would place the wrong box.
  useEffect(() => {
    setSelection(new Set<string>());
    setPositions(fallbackPositions(model));
    if (model.nodes.length === 0) return;
    let cancelled = false;
    void elkPositions(model)
      .then((laid) => {
        if (!cancelled) setPositions((held) => ({ ...held, ...laid }));
      })
      .catch(() => {
        // The deterministic grid is already on screen; a layout that failed
        // is a worse drawing, not a broken view.
      });
    return () => {
      cancelled = true;
    };
  }, [model]);

  const flowNodes: Node<VersionNodeData>[] = useMemo(
    () =>
      model.nodes.map((node) => ({
        id: node.id,
        type: VERSION_NODE_TYPE,
        position: positions[node.id] ?? { x: 0, y: 0 },
        data: node.data,
        selected: selection.has(node.id),
        draggable: false,
      })),
    [model.nodes, positions, selection],
  );

  const flowEdges: Edge[] = useMemo(
    () =>
      model.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        // FR-032 wants the origin on the edge, so it is the label rather than
        // a tooltip: "why does this edge exist" is the question the origin
        // was computed to answer.
        label: `${edge.name} · ${edge.origin}`,
        data: { origin: edge.origin, name: edge.name },
        selected: selection.has(edge.source) && selection.has(edge.target),
      })),
    [model.edges, selection],
  );

  const onNodeClick = useCallback(
    (_event: unknown, node: Node) => setSelection(connectedRegion(model, node.id)),
    [model],
  );
  const onPaneClick = useCallback(() => setSelection(new Set<string>()), []);

  return (
    <div
      className="flex h-full min-h-0 flex-col rounded border border-stone-200 bg-white"
      data-testid="explore-graph-view"
    >
      <div className="flex items-center gap-3 border-b border-stone-200 px-3 py-1.5 text-[11px] text-stone-500">
        <span className="font-medium text-stone-600">Dependency graph</span>
        <span data-testid="explore-graph-counts">
          {model.nodes.length} versions · {model.edges.length} dependencies
        </span>
        {selection.size > 0 ? (
          <span data-testid="explore-graph-selection-count">{selection.size} selected</span>
        ) : null}
        {graph === null ? (
          <span data-testid="explore-graph-empty">No analysis has been reported yet.</span>
        ) : null}
      </div>
      <div className="min-h-0 flex-1">
        <ReactFlowProvider>
          <ReactFlow
            edges={flowEdges}
            nodeTypes={NODE_TYPES}
            nodes={flowNodes}
            nodesConnectable={false}
            nodesDraggable={false}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            proOptions={{ hideAttribution: true }}
          >
            <Background />
            <Controls showInteractive={false} />
          </ReactFlow>
        </ReactFlowProvider>
      </div>
    </div>
  );
}
