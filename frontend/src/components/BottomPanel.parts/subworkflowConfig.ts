import type { WorkflowNode } from "../../types/api";

/**
 * ADR-044 FR-011 (US5) — true when the selected node is a SubWorkflowBlock
 * authoring container (`subworkflow_block`) or its broken-ref placeholder
 * (`subworkflow_broken`). `ConfigPanel` routes these to `SubworkflowConfigEditor`
 * instead of the generic field renderer.
 *
 * The SubWorkflowBlock `config_schema` declares a NESTED `ref.path`
 * (ui_widget `subworkflow_picker`); the generic top-level renderer cannot edit
 * a nested object field, so the special-case editor owns the picker the same
 * way `isCodeBlockConfigTarget` routes Code Block to `CodeBlockConfigEditor`.
 */
export function isSubworkflowConfigTarget(selectedNode: WorkflowNode | null): boolean {
  const blockType = selectedNode?.block_type;
  return blockType === "subworkflow_block" || blockType === "subworkflow_broken";
}

/** Read the persisted `config.ref.path` (top-level, NOT under params) for a
 *  subworkflow node, or `null` when unset. */
export function subworkflowRefPath(selectedNode: WorkflowNode | null): string | null {
  const ref = selectedNode?.config.ref as { path?: string } | undefined;
  const path = ref?.path;
  return typeof path === "string" && path.trim() ? path : null;
}
