import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../lib/api";
import type { TreeEntry } from "../types/api";

interface TreeNodeData extends TreeEntry {
  path: string;
  children?: TreeNodeData[];
  loaded: boolean;
  expanded: boolean;
}

interface ProjectTreeProps {
  projectId: string;
  projectPath: string;
  /**
   * #796: callback receives both the backend workflow id (filename stem) AND
   * the user-facing display name. The display name acts as a fallback when the
   * workflow YAML has an empty/missing `id:` field (e.g. on macOS where some
   * older or hand-edited YAMLs omit it, leaving the tab + title blank).
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

interface ContextMenuState {
  x: number;
  y: number;
  node: TreeNodeData;
}

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
      className="flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-xs hover:bg-stone-100"
      onClick={() => {
        if (node.type === "directory") onToggle(node);
      }}
      onContextMenu={(e) => onContextMenu(e, node)}
      onDoubleClick={() => onDoubleClick(node)}
      style={{ paddingLeft: `${depth * 16 + 4}px` }}
      type="button"
    >
      {node.type === "directory" ? (
        <span className="w-3 text-[10px] text-stone-400">{node.expanded ? "\u25BC" : "\u25B6"}</span>
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

export function ProjectTree({
  projectId,
  projectPath,
  onLoadWorkflow,
  onReloadBlocks,
}: ProjectTreeProps) {
  const [rootNodes, setRootNodes] = useState<TreeNodeData[]>([]);
  const [loading, setLoading] = useState(false);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const contextMenuRef = useRef<HTMLDivElement>(null);

  const loadChildren = useCallback(
    async (parentPath: string): Promise<TreeNodeData[]> => {
      const response = await api.getProjectTree(projectId, parentPath);
      return response.entries.map((entry) => ({
        ...entry,
        path: parentPath ? `${parentPath}/${entry.name}` : entry.name,
        children: entry.type === "directory" ? [] : undefined,
        loaded: false,
        expanded: false,
      }));
    },
    [projectId],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const children = await loadChildren("");
      setRootNodes(children);
    } catch {
      // silently ignore -- project may not be ready
    } finally {
      setLoading(false);
    }
  }, [loadChildren]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Close context menu on outside click
  useEffect(() => {
    if (!contextMenu) return undefined;
    const handler = (e: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    };
    window.addEventListener("mousedown", handler);
    return () => window.removeEventListener("mousedown", handler);
  }, [contextMenu]);

  const updateNode = useCallback(
    (nodes: TreeNodeData[], targetPath: string, updater: (n: TreeNodeData) => TreeNodeData): TreeNodeData[] => {
      return nodes.map((node) => {
        if (node.path === targetPath) {
          return updater(node);
        }
        if (node.children && targetPath.startsWith(node.path + "/")) {
          return { ...node, children: updateNode(node.children, targetPath, updater) };
        }
        return node;
      });
    },
    [],
  );

  const handleToggle = useCallback(
    async (node: TreeNodeData) => {
      if (node.type !== "directory") return;

      if (node.expanded) {
        // Collapse
        setRootNodes((prev) =>
          updateNode(prev, node.path, (n) => ({ ...n, expanded: false })),
        );
        return;
      }

      // Expand: load children if not loaded
      if (!node.loaded) {
        try {
          const children = await loadChildren(node.path);
          setRootNodes((prev) =>
            updateNode(prev, node.path, (n) => ({
              ...n,
              expanded: true,
              loaded: true,
              children,
            })),
          );
        } catch {
          // ignore
        }
      } else {
        setRootNodes((prev) =>
          updateNode(prev, node.path, (n) => ({ ...n, expanded: true })),
        );
      }
    },
    [loadChildren, updateNode],
  );

  const handleDoubleClick = useCallback(
    (node: TreeNodeData) => {
      if (node.type === "directory") return;
      const ext = node.name.split(".").pop()?.toLowerCase() ?? "";

      // Double-click .yaml in workflows/ -> load workflow.
      // #796: derive both the backend workflow id (filename stem) and a
      // non-empty display-name fallback. node.name is the literal filename as
      // reported by the backend FS scan, which is always non-empty for an
      // entry returned by the project-tree API.
      if ((ext === "yaml" || ext === "yml") && node.path.startsWith("workflows/")) {
        const workflowId = node.name.replace(/\.(yaml|yml)$/, "");
        // Fall back to the raw filename if the stem somehow ends up empty
        // (e.g. a file literally named ".yaml" — unusual but defensible).
        const displayName = workflowId || node.name;
        onLoadWorkflow(workflowId, displayName);
        return;
      }

      // Double-click .py in blocks/ -> hot-reload blocks
      if (ext === "py" && node.path.startsWith("blocks/")) {
        onReloadBlocks();
      }
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
        <button
          className="toolbar-button"
          disabled={loading}
          onClick={() => void refresh()}
          type="button"
        >
          {loading ? "..." : "Refresh"}
        </button>
      </div>

      <div className="mt-4 min-h-0 flex-1 overflow-y-auto pb-6 scrollbar-thin">
        {rootNodes.length === 0 && !loading ? (
          <p className="text-xs text-stone-400">No files found</p>
        ) : null}
        {renderNodes(rootNodes, 0)}
      </div>

      {contextMenu ? (
        <div
          ref={contextMenuRef}
          className="fixed z-50 rounded-lg border border-stone-200 bg-white py-1 shadow-lg"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            className="w-full px-4 py-1.5 text-left text-xs text-stone-700 hover:bg-stone-100"
            onClick={() => copyToClipboard(contextMenu.node.name)}
            type="button"
          >
            Copy Name
          </button>
          <button
            className="w-full px-4 py-1.5 text-left text-xs text-stone-700 hover:bg-stone-100"
            onClick={() => copyToClipboard(contextMenu.node.path)}
            type="button"
          >
            Copy Path
          </button>
          <button
            className="w-full px-4 py-1.5 text-left text-xs text-stone-700 hover:bg-stone-100"
            onClick={() => handleReveal(contextMenu.node)}
            type="button"
          >
            Reveal in Explorer
          </button>
        </div>
      ) : null}
    </aside>
  );
}
