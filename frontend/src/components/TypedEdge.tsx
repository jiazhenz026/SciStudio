import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from "@xyflow/react";

interface TypedEdgeData {
  color?: string;
  dashed?: boolean;
  invalid?: boolean;
  invalidReason?: string;
}

export function TypedEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  data,
}: EdgeProps) {
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const typed = data as TypedEdgeData | undefined;
  const dashed = typed?.dashed ?? false;
  const invalid = typed?.invalid ?? false;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{
          stroke: typed?.color ?? style?.stroke ?? "#2d7891",
          strokeWidth: invalid ? 2.6 : 2.2,
          strokeDasharray: dashed ? "6 4" : undefined,
        }}
      />
      {invalid && typed?.invalidReason ? (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan absolute -translate-x-1/2 -translate-y-1/2 rounded-full bg-red-600 px-2 py-0.5 text-[10px] font-medium text-white shadow"
            style={{ left: labelX, top: labelY }}
            title={typed.invalidReason}
          >
            ! type mismatch
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}
