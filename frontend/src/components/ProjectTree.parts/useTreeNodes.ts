/**
 * Tree-state hook for ProjectTree (lazy-loaded children, expand/collapse,
 * refresh wiring). Extracted in #1413 so the parent function stays small.
 */
import { useCallback, useEffect, useState } from "react";

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

export interface UseTreeNodesResult {
  rootNodes: TreeNodeData[];
  loading: boolean;
  refresh: () => Promise<void>;
  handleToggle: (node: TreeNodeData) => Promise<void>;
}

export function useTreeNodes(projectId: string): UseTreeNodesResult {
  const [rootNodes, setRootNodes] = useState<TreeNodeData[]>([]);
  const [loading, setLoading] = useState(false);

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
