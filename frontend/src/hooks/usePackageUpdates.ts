/**
 * #1784 — background package update check.
 *
 * Runs once when the host component mounts (app startup) and exposes the set of
 * available package updates so the toolbar can show a non-blocking badge. The
 * check requires a bundled desktop run; in the browser/dev it 403s and is
 * silently treated as "no updates" so the UI never errors.
 */

import { useCallback, useEffect, useState } from "react";

import { api } from "../lib/api";
import type { PackageUpdateStatus } from "../types/api";

export interface PackageUpdatesState {
  statuses: PackageUpdateStatus[];
  updateCount: number;
  checking: boolean;
  refresh: () => Promise<void>;
}

export function usePackageUpdates(): PackageUpdatesState {
  const [statuses, setStatuses] = useState<PackageUpdateStatus[]>([]);
  const [checking, setChecking] = useState(false);

  const refresh = useCallback(async () => {
    setChecking(true);
    try {
      const response = await api.checkPackageUpdates();
      // Tolerate a missing/partial payload (e.g. mocked api in tests, or an
      // older backend): only an array of statuses is meaningful.
      setStatuses(Array.isArray(response?.statuses) ? response.statuses : []);
    } catch {
      // Non-bundled run, offline, or backend not ready — no badge, no error.
      setStatuses([]);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const updateCount = (statuses ?? []).filter((status) => status.update_available).length;
  return { statuses, updateCount, checking, refresh };
}
