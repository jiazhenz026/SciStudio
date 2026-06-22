/**
 * Tree-state hook for ProjectTree (lazy-loaded children, expand/collapse,
 * refresh wiring). Extracted in #1413 so the parent function stays small.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../lib/api";
import { useAppStore } from "../../store";
import type { TreeNodeData } from "./types";

function updateNode(
  nodes: TreeNodeData[],
  targetPath: string,
  updater: (n: TreeNodeData) => TreeNodeData,
): TreeNodeData[] {
  return nodes.map((node) => {
    if (node.path === targetPath) return updater(node);
    if (node.children && targetPath.startsWith(node.path + "/")) {
      return { ...node, children: updateNode(node.children, targetPath, updater) };
    }
    return node;
  });
}

/**
 * Collect the paths of currently-expanded directories in shallow→deep order
 * (a parent always precedes its descendants). Used by `refresh()` to restore
 * expansion state after a watcher-driven reload instead of wiping it (#1751).
 */
function collectExpandedPaths(nodes: TreeNodeData[]): string[] {
  const out: string[] = [];
  const walk = (ns: TreeNodeData[]) => {
    for (const node of ns) {
      if (node.type === "directory" && node.expanded) {
        out.push(node.path);
        if (node.children) walk(node.children);
      }
    }
  };
  walk(nodes);
  return out;
}

export interface UseTreeNodesResult {
  rootNodes: TreeNodeData[];
  loading: boolean;
  refresh: () => Promise<void>;
  handleToggle: (node: TreeNodeData) => Promise<void>;
}

export function useTreeNodes(projectId: string): UseTreeNodesResult {
  const [rootNodes, setRootNodes] = useState<TreeNodeData[]>([]);
  const [loading, setLoading] = useState(false);
  // Mirror the latest tree so `refresh()` (a stable callback) can read the
  // current expansion state without depending on `rootNodes` and re-running.
  const rootNodesRef = useRef<TreeNodeData[]>([]);
  useEffect(() => {
    rootNodesRef.current = rootNodes;
  }, [rootNodes]);

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
      // Reload the root, then re-open the directories that were expanded before
      // the refresh so the watcher tick (ADR-034) does not collapse the tree on
      // every run (#1751). Paths are shallow→deep, so each parent's children are
      // loaded before a descendant is merged into them; folders that vanished
      // since the last load are skipped and simply stay collapsed.
      const expandedPaths = collectExpandedPaths(rootNodesRef.current);
      let tree = await loadChildren("");
      for (const path of expandedPaths) {
        try {
          const children = await loadChildren(path);
          tree = updateNode(tree, path, (n) => ({ ...n, expanded: true, loaded: true, children }));
        } catch {
          // directory removed or unreadable since last load -- leave collapsed
        }
      }
      setRootNodes(tree);
    } catch {
      // silently ignore -- project may not be ready
    } finally {
      setLoading(false);
    }
  }, [loadChildren]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // ADR-034: auto-refresh on filesystem watcher tick.
  const refreshCounter = useAppStore((s) => s.projectTreeRefreshCounter);
  useEffect(() => {
    if (refreshCounter === 0) return;
    void refresh();
  }, [refreshCounter, refresh]);

  const handleToggle = useCallback(
    async (node: TreeNodeData) => {
      if (node.type !== "directory") return;

      if (node.expanded) {
        setRootNodes((prev) => updateNode(prev, node.path, (n) => ({ ...n, expanded: false })));
        return;
      }

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
        setRootNodes((prev) => updateNode(prev, node.path, (n) => ({ ...n, expanded: true })));
      }
    },
    [loadChildren],
  );

  return { rootNodes, loading, refresh, handleToggle };
}
