import { type Node, type NodeProps, NodeResizer } from "@xyflow/react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { GroupNodeData } from "../../types/ui";

/**
 * A dashed-border group frame node for visually grouping blocks.
 *
 * - Dashed border rectangle with rounded corners.
 * - Editable title (double-click) at the top.
 * - Optional body note below the title.
 * - Semi-transparent background tint.
 * - Resizable via ReactFlow NodeResizer.
 * - Minimum size: 200x150.
 */
export function GroupNode({ data, selected }: NodeProps<Node<GroupNodeData>>) {
  const [editingTitle, setEditingTitle] = useState(false);
  const [editingNote, setEditingNote] = useState(false);
  const [titleDraft, setTitleDraft] = useState(data.title);
  const [noteDraft, setNoteDraft] = useState(data.note);
  const titleRef = useRef<HTMLInputElement>(null);
  const noteRef = useRef<HTMLTextAreaElement>(null);

  // Sync drafts when external data changes.
  useEffect(() => {
    if (!editingTitle) setTitleDraft(data.title);
  }, [data.title, editingTitle]);

  useEffect(() => {
    if (!editingNote) setNoteDraft(data.note);
  }, [data.note, editingNote]);

  const commitTitle = useCallback(() => {
    setEditingTitle(false);
    const trimmed = titleDraft.trim();
    if (trimmed !== data.title) {
      data.onUpdateTitle?.(trimmed || "Group");
    }
  }, [titleDraft, data]);

  const commitNote = useCallback(() => {
    setEditingNote(false);
    const trimmed = noteDraft.trim();
    if (trimmed !== data.note) {
      data.onUpdateNote?.(trimmed);
    }
  }, [noteDraft, data]);

  const borderColor = selected ? "rgba(59, 130, 246, 0.5)" : "rgba(168, 162, 158, 0.5)";

  return (
    <div
      className="relative h-full w-full rounded-xl"
      style={{
        backgroundColor: "rgba(241, 245, 249, 0.35)",
        border: `2px dashed ${borderColor}`,
        minWidth: 200,
        minHeight: 150,
      }}
      data-testid="group-node"
    >
      <NodeResizer
        minWidth={200}
        minHeight={150}
        isVisible={selected ?? false}
        lineClassName="!border-blue-400"
        handleClassName="!h-3 !w-3 !rounded-full !border-2 !border-blue-400 !bg-white"
      />

      {/* Title */}
      <div
        className="px-3 pt-2 pb-1"
        onDoubleClick={() => {
          setEditingTitle(true);
          requestAnimationFrame(() => titleRef.current?.focus());
        }}
      >
        {editingTitle ? (
          <input
            ref={titleRef}
            className="nodrag nowheel w-full rounded border border-stone-200 bg-white px-1 py-0.5 font-display text-sm font-semibold text-ink focus:border-blue-400 focus:outline-none"
            value={titleDraft}
            onChange={(e) => setTitleDraft(e.target.value)}
            onBlur={commitTitle}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                commitTitle();
              }
              if (e.key === "Escape") {
                setTitleDraft(data.title);
                setEditingTitle(false);
              }
            }}
            data-testid="group-title-input"
          />
        ) : (
          <p
            className="font-display text-sm font-semibold text-stone-600"
            data-testid="group-title"
          >
            {data.title || "Group"}
          </p>
        )}
      </div>

      {/* Note (optional body text) */}
      <div
        className="px-3 pb-2"
        onDoubleClick={() => {
          setEditingNote(true);
          requestAnimationFrame(() => noteRef.current?.focus());
        }}
      >
        {editingNote ? (
          <textarea
            ref={noteRef}
            className="nodrag nowheel w-full resize-none rounded border border-stone-200 bg-white px-1 py-0.5 text-xs text-stone-500 focus:border-blue-400 focus:outline-none"
            rows={2}
            value={noteDraft}
            onChange={(e) => setNoteDraft(e.target.value)}
            onBlur={commitNote}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                commitNote();
              }
              if (e.key === "Escape") {
                setNoteDraft(data.note);
                setEditingNote(false);
              }
            }}
            data-testid="group-note-textarea"
          />
        ) : data.note ? (
          <p className="text-xs text-stone-400" data-testid="group-note">
            {data.note}
          </p>
        ) : null}
      </div>
    </div>
  );
}
