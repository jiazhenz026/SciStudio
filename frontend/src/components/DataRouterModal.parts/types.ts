/**
 * Shared types for DataRouterModal and its parts.
 *
 * Extracted in #1413 so the panel sub-components can live in their own
 * files without circular imports.
 */
export interface ItemDescriptor {
  index: number;
  port: string;
  ref: string;
  name: string;
  type: string;
}

// Row colors for visual grouping.
export const ROW_COLORS = [
  "bg-blue-50 border-blue-200",
  "bg-green-50 border-green-200",
  "bg-purple-50 border-purple-200",
  "bg-amber-50 border-amber-200",
  "bg-rose-50 border-rose-200",
  "bg-cyan-50 border-cyan-200",
  "bg-indigo-50 border-indigo-200",
  "bg-lime-50 border-lime-200",
];
