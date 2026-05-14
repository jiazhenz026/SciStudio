export interface Position {
  x: number;
  y: number;
}

export interface WorkflowNode {
  id: string;
  block_type: string;
  config: Record<string, unknown>;
  execution_mode?: string | null;
  layout?: Position | null;
}

export interface WorkflowEdge {
  source: string;
  target: string;
}

export interface WorkflowResponse {
  id: string;
  version: string;
  description: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  metadata: Record<string, unknown>;
}

export interface WorkflowExecutionResponse {
  workflow_id: string;
  status: string;
  message: string;
}

export interface ExecuteFromResponse extends WorkflowExecutionResponse {
  reused_blocks: string[];
  reset_blocks: string[];
}

export interface ProjectResponse {
  id: string;
  name: string;
  description: string;
  path: string;
  last_opened?: string | null;
  workflow_count: number;
  workflows: string[];
  current_workflow_id?: string | null;
}

export interface BlockPortResponse {
  name: string;
  direction: string;
  accepted_types: string[];
  required: boolean;
  description: string;
  constraint_description: string;
  is_collection: boolean;
}

export interface BlockSummary {
  name: string;
  type_name: string;
  // #588: base_category is always one of 6 base types (io, process, code,
  // app, ai, subworkflow).  subcategory is the optional palette grouping label.
  base_category: string;
  subcategory: string;
  description: string;
  version: string;
  input_ports: BlockPortResponse[];
  output_ports: BlockPortResponse[];
  direction?: string | null;
  source?: string;
  package_name?: string;
  /** ADR-029 D8: true when this block supports user-configurable input port count. */
  variadic_inputs?: boolean;
  /** ADR-029 D8: true when this block supports user-configurable output port count. */
  variadic_outputs?: boolean;
}

export interface TypeHierarchyEntry {
  name: string;
  base_type: string;
  description: string;
  ui_ring_color?: string | null;
}

/**
 * Declarative dynamic-port descriptor for blocks whose port types depend on
 * a config field selection (e.g. ``LoadData``'s ``core_type`` dropdown).
 *
 * Mirrors the backend ``Block.dynamic_ports`` ClassVar shape defined in
 * ADR-028 Addendum 1 §D2'. The mapping is strictly two-level:
 *
 *     {port_name: {enum_value: [type_name, ...]}}
 *
 * The frontend consumes this descriptor via ``computeEffectivePorts()`` to
 * resolve the per-instance ``accepted_types`` for each port without making a
 * backend round-trip when the user changes the driving config field.
 *
 * Per ADR-028 Addendum 1 D4 / D8, this descriptor is delivered to the
 * frontend on ``BlockSchemaResponse.dynamic_ports`` (set to ``null`` for
 * static blocks).
 */
export interface DynamicPortsConfig {
  /** Name of the config field whose value drives the port-type mapping. */
  source_config_key: string;
  /** Per-output-port enum-value to type-name list mapping. */
  output_port_mapping?: Record<string, Record<string, string[]>>;
  /** Per-input-port enum-value to type-name list mapping. */
  input_port_mapping?: Record<string, Record<string, string[]>>;
}

export interface BlockSchemaResponse extends BlockSummary {
  config_schema: {
    type?: string;
    properties?: Record<string, Record<string, unknown>>;
    required?: string[];
  };
  type_hierarchy: TypeHierarchyEntry[];
  /**
   * Enum-driven dynamic-port descriptor (ADR-028 Addendum 1 D4).
   *
   * ``null`` (or ``undefined``) for static blocks. Populated by the
   * backend from ``cls.dynamic_ports`` at registry scan time. Consumed
   * by ``computeEffectivePorts()`` in the frontend.
   */
  dynamic_ports?: DynamicPortsConfig | null;
  /**
   * IO direction (ADR-028 Addendum 1 D8). One of ``"input"`` or
   * ``"output"`` for IO blocks; ``null`` (or ``undefined``) for
   * non-IO blocks. Populated by the backend from ``cls.direction`` so
   * the frontend can render IO-specific UI (e.g. file-vs-directory
   * picker on the Browse button) without hardcoding
   * ``blockType === "io_block"`` checks.
   */
  direction?: string | null;
  /**
   * ADR-029 D11: type names accepted by variadic input ports.
   * Frontend uses this to populate the type dropdown in the port editor.
   * Empty array means "any DataObject subclass".
   */
  allowed_input_types?: string[];
  /**
   * ADR-029 D11: type names accepted by variadic output ports.
   * Empty array means "any DataObject subclass".
   */
  allowed_output_types?: string[];
  /**
   * ADR-029 Addendum 1: minimum number of variadic input ports.
   * null/undefined means no minimum.
   */
  min_input_ports?: number | null;
  /**
   * ADR-029 Addendum 1: maximum number of variadic input ports.
   * null/undefined means no maximum.
   */
  max_input_ports?: number | null;
  /**
   * ADR-029 Addendum 1: minimum number of variadic output ports.
   * null/undefined means no minimum.
   */
  min_output_ports?: number | null;
  /**
   * ADR-029 Addendum 1: maximum number of variadic output ports.
   * null/undefined means no maximum.
   */
  max_output_ports?: number | null;
}

export interface BlockListResponse {
  blocks: BlockSummary[];
}

export interface ConnectionValidationResponse {
  compatible: boolean;
  reason: string;
}

export interface DataUploadResponse {
  ref: string;
  type_name: string;
  metadata: Record<string, unknown>;
}

export interface DataMetadataResponse {
  ref: string;
  type_name: string;
  metadata: Record<string, unknown>;
}

export interface DataPreviewResponse {
  ref: string;
  type_name: string;
  preview: Record<string, unknown>;
}

export interface CancelPropagationResponse {
  cancelled_blocks: string[];
  skipped_blocks: string[];
  skip_reasons: Record<string, string>;
}

export interface WorkflowEventMessage {
  type: string;
  block_id?: string | null;
  workflow_id?: string | null;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  workflow_id?: string | null;
  block_id?: string | null;
}

export interface FilesystemEntry {
  name: string;
  type: "file" | "directory";
  size?: number | null;
}

export interface FilesystemBrowseResponse {
  path: string;
  entries: FilesystemEntry[];
}

export interface TreeEntry {
  name: string;
  type: "file" | "directory";
  size?: number | null;
}

export interface TreeResponse {
  entries: TreeEntry[];
}
