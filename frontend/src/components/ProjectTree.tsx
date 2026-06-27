import { useCallback, useState } from "react";

import { useReloadFlash } from "../hooks/useReloadFlash";
import { api } from "../lib/api";
import { useAppStore } from "../store";
import type { TreeEntry } from "../types/api";
import { ContextMenu } from "./ProjectTree.parts/ContextMenu";
import type { ContextMenuState, TreeNodeData } from "./ProjectTree.parts/types";
import { useTreeNodes } from "./ProjectTree.parts/useTreeNodes";

interface ProjectTreeProps {
  projectId: string;
  projectPath: string;
  /**
   * #796: callback receives both the backend workflow id (filename stem) AND
   * the user-facing display name. The display name acts as a fallback when the
   * workflow YAML has an empty/missing `id:` field.
   */
  onLoadWorkflow: (filePath: string, displayName: string) => void;
  onReloadBlocks: () => void;
}

function fileIcon(entry: TreeEntry): string {
  if (entry.type === "directory") return "\u{1F4C1}";
  const ext = entry.name.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "yaml" || ext === "yml") return "\u{1F4C4}";
  if (ext === "py") return "\u{1F40D}";
  if (ext === "json") return "\u{1F4CB}";
  if (ext === "csv" || ext === "parquet") return "\u{1F4CA}";
  if (ext === "tif" || ext === "tiff" || ext === "png" || ext === "jpg" || ext === "jpeg")
    return "\u{1F5BC}";
  return "\u{1F4C3}";
}

function formatSize(size: number | null | undefined): string {
  if (size == null) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

// ADR-036 §3.5 (Phase 2C / I36c): file extensions the embedded Monaco editor
// knows how to render. Anything outside this set is ignored on double-click.
const EDITABLE_EXTENSIONS: readonly string[] = ["py", "r", "txt", "md", "json", "csv"];

function TreeNodeRow({
  node,
  depth,
  onToggle,
  onDoubleClick,
  onContextMenu,
}: {
  node: TreeNodeData;
  depth: number;
  onToggle: (node: TreeNodeData) => void;
  onDoubleClick: (node: TreeNodeData) => void;
  onContextMenu: (event: React.MouseEvent, node: TreeNodeData) => void;
}) {
  return (
    <button
      className="flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-sm hover:bg-stone-100"
      onClick={() => {
        if (node.type === "directory") onToggle(node);
      }}
      onContextMenu={(e) => onContextMenu(e, node)}
      onDoubleClick={() => onDoubleClick(node)}
      style={{ paddingLeft: `${depth * 16 + 4}px` }}
      type="button"
    >
      {node.type === "directory" ? (
        <span className="w-3 text-[10px] text-stone-400">{node.expanded ? "▼" : "▶"}</span>
      ) : (
        <span className="w-3" />
      )}
      <span className="shrink-0 text-[11px]">{fileIcon(node)}</span>
      <span className="min-w-0 flex-1 truncate text-stone-700">{node.name}</span>
      {node.type === "file" && node.size != null ? (
        <span className="shrink-0 text-[10px] text-stone-400">{formatSize(node.size)}</span>
      ) : null}
    </button>
  );
}

function handleDoubleClickRoute(
  node: TreeNodeData,
  onLoadWorkflow: (filePath: string, displayName: string) => void,
  onReloadBlocks: () => void,
): void {
  if (node.type === "directory") return;
  const ext = node.name.split(".").pop()?.toLowerCase() ?? "";

  // Double-click .yaml in workflows/ -> load workflow (#796).
  if ((ext === "yaml" || ext === "yml") && node.path.startsWith("workflows/")) {
    const workflowId = node.name.replace(/\.(yaml|yml)$/, "");
    const displayName = workflowId || node.name;
    onLoadWorkflow(workflowId, displayName);
    return;
  }

  // ADR-036 §3.5 (I36c): .py under blocks/ refreshes the palette AND opens
  // the file in the Monaco editor.
  if (ext === "py" && node.path.startsWith("blocks/")) {
    onReloadBlocks();
    useAppStore.getState().openFileTab(node.path);
    return;
  }

  // Editable extensions anywhere in the project open in the Monaco editor.
  if (EDITABLE_EXTENSIONS.includes(ext)) {
    useAppStore.getState().openFileTab(node.path);
    return;
  }
}

export function ProjectTree({
  projectId,
  projectPath,
  onLoadWorkflow,
  onReloadBlocks,
}: ProjectTreeProps) {
  const { rootNodes, loading, refresh, handleToggle } = useTreeNodes(projectId);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  // Blink the tree once a Refresh actually lands (same feedback as the palette).
  const { ref: treeRef, trigger: triggerFlash } = useReloadFlash<HTMLDivElement, TreeNodeData[]>(
    rootNodes,
  );

  const handleRefresh = useCallback(() => {
    triggerFlash();
    void refresh();
  }, [refresh, triggerFlash]);

  const handleDoubleClick = useCallback(
    (node: TreeNodeData) => {
      handleDoubleClickRoute(node, onLoadWorkflow, onReloadBlocks);
    },
    [onLoadWorkflow, onReloadBlocks],
  );

  const handleContextMenu = useCallback((event: React.MouseEvent, node: TreeNodeData) => {
    event.preventDefault();
    setContextMenu({ x: event.clientX, y: event.clientY, node });
  }, []);

  const copyToClipboard = useCallback((text: string) => {
    void navigator.clipboard.writeText(text);
    setContextMenu(null);
  }, []);

  const handleReveal = useCallback(
    (node: TreeNodeData) => {
      const fullPath = `${projectPath}/${node.path}`.replace(/\//g, "/");
      void api.revealInExplorer(fullPath);
      setContextMenu(null);
    },
    [projectPath],
  );

  const renderNodes = (nodes: TreeNodeData[], depth: number): React.ReactNode => {
    return nodes.map((node) => (
      <div key={node.path}>
        <TreeNodeRow
          depth={depth}
          node={node}
          onContextMenu={handleContextMenu}
          onDoubleClick={handleDoubleClick}
          onToggle={handleToggle}
        />
        {node.expanded && node.children ? renderNodes(node.children, depth + 1) : null}
      </div>
    ));
  };

  return (
    <aside className="flex h-full flex-col overflow-hidden border-r border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))] p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="font-display text-xl text-ink">Project</p>
        <button className="toolbar-button" disabled={loading} onClick={handleRefresh} type="button">
          {loading ? "..." : "Refresh"}
        </button>
      </div>

      <div className="mt-4 min-h-0 flex-1 overflow-y-auto pb-6 scrollbar-thin" ref={treeRef}>
        {rootNodes.length === 0 && !loading ? (
          <p className="text-xs text-stone-400">No files found</p>
        ) : null}
        {renderNodes(rootNodes, 0)}
      </div>

      <ContextMenu
        contextMenu={contextMenu}
        onClose={() => setContextMenu(null)}
        onCopyName={copyToClipboard}
        onCopyPath={copyToClipboard}
        onReveal={handleReveal}
      />
    </aside>
  );
}
