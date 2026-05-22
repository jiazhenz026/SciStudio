import { type Node, type NodeProps } from "@xyflow/react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { AnnotationNodeData } from "../../types/ui";

/**
 * A lightweight text annotation node for the canvas.
 *
 * - No ports, no block header/border.
 * - Semi-transparent background for readability.
 * - Double-click to enter edit mode (textarea); blur/Enter to save.
 * - When selected: subtle blue ring.
 */
export function AnnotationNode({ data, selected }: NodeProps<Node<AnnotationNodeData>>) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(data.text);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Sync draft when external data changes (e.g. undo/redo).
  useEffect(() => {
    if (!editing) {
      setDraft(data.text);
    }
  }, [data.text, editing]);

  const commitEdit = useCallback(() => {
    setEditing(false);
    const trimmed = draft.trim();
    if (trimmed !== data.text) {
      data.onUpdateText?.(trimmed || "Note");
    }
  }, [draft, data]);

  const handleDoubleClick = useCallback(() => {
    setEditing(true);
    // Focus the textarea on next tick after it renders.
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        commitEdit();
      }
      if (e.key === "Escape") {
        setDraft(data.text);
        setEditing(false);
      }
    },
    [commitEdit, data.text],
  );

  return (
    <div
      className={`max-w-[240px] rounded-lg px-3 py-2 text-sm leading-relaxed transition-shadow ${
        selected ? "ring-2 ring-blue-400/60" : ""
      }`}
      style={{ backgroundColor: "rgba(255, 251, 235, 0.6)" }}
      onDoubleClick={handleDoubleClick}
      data-testid="annotation-node"
    >
      {editing ? (
        <textarea
          ref={textareaRef}
          className="nodrag nowheel w-full resize-none rounded border border-stone-200 bg-white px-1 py-0.5 text-sm text-ink focus:border-blue-400 focus:outline-none"
          rows={3}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitEdit}
          onKeyDown={handleKeyDown}
          data-testid="annotation-textarea"
        />
      ) : (
        <p className="whitespace-pre-wrap text-stone-700" data-testid="annotation-text">
          {data.text || "Double-click to edit"}
        </p>
      )}
    </div>
  );
}
