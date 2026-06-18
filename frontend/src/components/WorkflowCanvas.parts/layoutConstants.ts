/**
 * Canvas layout constants for ADR-050 §2.1 / §3.2 (tidy auto-layout).
 *
 * FE-2 owns these spacing constants. They are intentionally DECOUPLED from
 * FE-1's `nodes/BlockNode.parts/nodeGeometry.ts` so each worktree type-checks
 * alone (see the dispatch checklist §4.1). The square-node size declared here
 * MUST equal `nodeGeometry.NODE_SIZE` (ADR-050 §2.1) — do NOT cross-import
 * between the two files. The unit test in `__tests__/layoutConstants.test.ts`
 * asserts the `104` invariant so the two declarations cannot silently drift.
 */

/**
 * Square node body size in CSS px. MUST equal `nodeGeometry.NODE_SIZE`
 * (ADR-050 §2.1). The default density is `104 x 104`.
 */
export const NODE_SIZE = 104;

/**
 * Minimum horizontal gap between adjacent layers in a left-to-right data-flow
 * layout (ADR-050 §3.2). Drives `elk.layered.spacing.nodeNodeBetweenLayers`.
 */
export const LAYER_GAP = 96;

/**
 * Minimum vertical gap between sibling nodes within the same layer
 * (ADR-050 §3.2). Drives `elk.spacing.nodeNode`.
 */
export const SIBLING_GAP = 48;

/**
 * Extra clearance reserved around high-degree nodes so dense fan-in/fan-out
 * regions do not crowd edges (ADR-050 §3.2). Drives
 * `elk.spacing.edgeNode` / `elk.layered.spacing.edgeNodeBetweenLayers`.
 */
export const HIGH_DEGREE_CLEARANCE = 32;
