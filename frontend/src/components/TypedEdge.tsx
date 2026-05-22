import { BaseEdge, getBezierPath, type EdgeProps } from "@xyflow/react";

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
  const [path] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  return (
    <BaseEdge
      id={id}
      path={path}
      style={{
        stroke: (data as { color?: string } | undefined)?.color ?? style?.stroke ?? "#2d7891",
        strokeWidth: 2.2,
        strokeDasharray: undefined,
      }}
    />
  );
}
