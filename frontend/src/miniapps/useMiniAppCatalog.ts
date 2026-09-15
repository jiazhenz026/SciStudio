import { useCallback, useEffect, useState } from "react";

import { useDialogChannel } from "../components/promotion/dialogChannel";
import { blocksApi } from "../lib/api/blocks";
import { useAppStore } from "../store";

import { miniAppsApi } from "./api";
import type { MiniAppSummary } from "./types";

/** Both the sidebar and canvas read the backend again when its registry changes. */
export function useMiniAppCatalog() {
  const project = useAppStore((state) => state.currentProject);
  const registryRevision = useAppStore((state) => state.blockCatalogRefreshCounter);
  const { notice } = useDialogChannel();
  const promotion =
    notice?.item.kind === "miniapp" && (notice.status === "promoted" || notice.status === "partial")
      ? notice
      : null;
  const [listing, setListing] = useState<{
    project: typeof project;
    items: MiniAppSummary[];
    error: string | null;
  } | null>(null);
  const [reloading, setReloading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    miniAppsApi.list().then(
      (items) => {
        if (!cancelled && useAppStore.getState().currentProject === project)
          setListing({ project, items, error: null });
      },
      (error: unknown) => {
        if (!cancelled && useAppStore.getState().currentProject === project)
          setListing({
            project,
            items: [],
            error: String(error instanceof Error ? error.message : error),
          });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [project, registryRevision, promotion]);

  const reload = useCallback(async () => {
    setReloading(true);
    try {
      // This existing endpoint rebuilds all registries, including panels.
      await blocksApi.reloadBlocks();
      if (useAppStore.getState().currentProject === project)
        useAppStore.getState().bumpBlockCatalogRefresh();
    } catch (error) {
      if (useAppStore.getState().currentProject === project)
        setListing((previous) => ({
          project,
          items: previous?.project === project ? previous.items : [],
          error: error instanceof Error ? error.message : String(error),
        }));
    } finally {
      setReloading(false);
    }
  }, [project]);

  const current = listing?.project === project ? listing : null;
  return {
    miniapps: current?.items ?? [],
    loaded: current !== null,
    error: current?.error ?? null,
    reloading,
    reload,
  };
}
