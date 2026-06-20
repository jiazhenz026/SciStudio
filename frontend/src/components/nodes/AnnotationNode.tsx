import { type Node, type NodeProps, NodeResizer } from "@xyflow/react";
import { Pencil } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { AnnotationNodeData } from "../../types/ui";

/**
 * A lightweight, resizable text annotation node for the canvas.
 *
 * - No ports, no block header/border.
 * - Semi-transparent background for readability.
 * - Resizable via ReactFlow NodeResizer; the size is persisted in config.style.
 * - Double-click (or the pencil button shown when selected) enters edit mode;
 *   blur/Enter saves, Escape cancels.
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

  const startEdit = useCallback(() => {
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
      className={`group relative h-full w-full rounded-lg px-3 py-2 text-sm leading-relaxed transition-shadow ${
        selected ? "ring-2 ring-blue-400/60" : ""
      }`}
      style={{ backgroundColor: "rgba(255, 251, 235, 0.6)" }}
      onDoubleClick={startEdit}
      data-testid="annotation-node"
    >
      <NodeResizer
        minWidth={120}
        minHeight={60}
        isVisible={selected ?? false}
        lineClassName="!border-blue-400"
        handleClassName="!h-3 !w-3 !rounded-full !border-2 !border-blue-400 !bg-white"
      />

      {/* Edit affordance: a pencil button surfaces on select/hover so the
       * double-click-to-edit interaction is discoverable. It floats ABOVE the
       * note so it never overlaps the NodeResizer corner handles. */}
      {!editing ? (
        <button
          type="button"
          aria-label="Edit note"
          title="Edit note"
          onClick={startEdit}
          className={`nodrag absolute -top-7 right-0 rounded-md border border-stone-200 bg-white p-1 text-stone-500 shadow-sm transition-opacity hover:text-ink ${
            selected ? "opacity-100" : "opacity-0 group-hover:opacity-100"
          }`}
          data-testid="annotation-edit-button"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
      ) : null}

      {editing ? (
        <textarea
          ref={textareaRef}
          className="nodrag nowheel h-full w-full resize-none rounded border border-stone-200 bg-white px-1 py-0.5 text-sm text-ink focus:border-blue-400 focus:outline-none"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitEdit}
          onKeyDown={handleKeyDown}
          data-testid="annotation-textarea"
        />
      ) : (
        <p
          className="h-full overflow-auto whitespace-pre-wrap text-stone-700"
          data-testid="annotation-text"
        >
          {data.text || "Double-click to edit"}
        </p>
      )}
    </div>
  );
}
