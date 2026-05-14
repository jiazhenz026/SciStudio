import type { Node } from "@xyflow/react";

import type { BlockPortResponse, BlockSchemaResponse, BlockSummary } from "./api";

export type BottomTab = "ai" | "config" | "logs" | "lineage" | "jobs";

export interface BlockNodeData extends Record<string, unknown> {
  label: string;
  blockType: string;
  category: string;
  summary?: BlockSummary;
  schema?: BlockSchemaResponse;
  config?: Record<string, unknown>;
  inputPorts: BlockPortResponse[];
  outputPorts: BlockPortResponse[];
  status?: string;
  /** Short error message populated when status is 'error'. Sourced from the
   *  BLOCK_ERROR WebSocket event's \`data.error\` field. */
  errorMessage?: string;
  /** Concise summary extracted from the error traceback (last line, max 120 chars).
   *  Preferred over errorMessage for inline display on the block node. */
  errorSummary?: string;
  outputPreviewLabel?: string;
  selected?: boolean;
  onRun?: () => void;
  onRestart?: () => void;
  onDelete?: () => void;
  onUpdateConfig?: (patch: Record<string, unknown>) => void;
  onErrorClick?: () => void;
}

export type BlockCanvasNode = Node<BlockNodeData>;

/** Data carried by an _annotation node on the canvas. */
export interface AnnotationNodeData extends Record<string, unknown> {
  text: string;
  onUpdateText?: (text: string) => void;
}

/** Data carried by a _group frame node on the canvas. */
export interface GroupNodeData extends Record<string, unknown> {
  title: string;
  note: string;
  color: string;
  onUpdateTitle?: (title: string) => void;
  onUpdateNote?: (note: string) => void;
}
