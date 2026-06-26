import { FolderOpen, PackagePlus, RotateCcw, Trash2 } from "lucide-react";
import { startTransition, useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../lib/api";
import type { InstalledPackage, PackageUpdateStatus } from "../types/api";
import { useAppStore } from "../store";

interface PackageManagerDialogProps {
  open: boolean;
  onClose: () => void;
}

function parentDirectory(path: string): string | undefined {
  const trimmed = path.trim();
  if (!trimmed) return undefined;
  const normalized = trimmed.replace(/\\/g, "/");
  const index = normalized.lastIndexOf("/");
  return index > 0 ? trimmed.slice(0, index) : undefined;
}

/**
 * #1784 — in-app Package Manager. Opened from the toolbar Packages button as an
 * app-modal (the "open project" dialog pattern). Lists installed packages with
 * their available OTA updates and supports install / update / rollback /
 * delete. Update, rollback, and delete change package code on disk; applying it
 * needs a fresh interpreter, so the dialog prompts a relaunch.
 */
export function PackageManagerDialog({ open, onClose }: PackageManagerDialogProps) {
  const setBlocks = useAppStore((state) => state.setBlocks);
  const setBlockSchema = useAppStore((state) => state.setBlockSchema);

  const [installed, setInstalled] = useState<InstalledPackage[]>([]);
  const [updates, setUpdates] = useState<PackageUpdateStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyPackage, setBusyPackage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [relaunchPrompt, setRelaunchPrompt] = useState<string | null>(null);

  const [path, setPath] = useState("");
  const [installing, setInstalling] = useState(false);

  const updateByName = useMemo(() => {
    const map = new Map<string, PackageUpdateStatus>();
    for (const status of updates) map.set(status.package_name, status);
    return map;
  }, [updates]);

  const refreshBlocks = useCallback(async () => {
    const payload = await api.listBlocks();
    startTransition(() => setBlocks(payload.blocks));
    const schemas = await Promise.all(
      payload.blocks.map((block) => api.getBlockSchema(block.type_name)),
    );
    startTransition(() => {
      schemas.forEach((schema) => setBlockSchema(schema));
    });
  }, [setBlocks, setBlockSchema]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await api.listInstalledPackages();
      setInstalled(list.packages);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
    // The update check hits the network per package; never let it block the list.
    try {
      const checked = await api.checkPackageUpdates();
      setUpdates(checked.statuses);
    } catch {
      setUpdates([]);
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  if (!open) return null;

  async function choosePath(mode: "file" | "directory") {
    setError(null);
    try {
      const response = await api.openNativeDialog(mode, parentDirectory(path));
      if (response.paths.length > 0) setPath(response.paths[0]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function installPackage() {
    const selected = path.trim();
    if (!selected) {
      setError("Choose a local package path first.");
      return;
    }
    setInstalling(true);
    setError(null);
    try {
      await api.installLocalPackage(selected);
      setPath("");
      await refreshBlocks();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setInstalling(false);
    }
  }

  async function runAction(
    packageName: string,
    action: () => Promise<{ needs_relaunch: boolean }>,
    relaunchMessage: string,
  ) {
    setBusyPackage(packageName);
    setError(null);
    try {
      const result = await action();
      await refreshBlocks();
      await load();
      if (result.needs_relaunch) setRelaunchPrompt(relaunchMessage);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyPackage(null);
    }
  }

  function relaunch() {
    void window.scistudioDesktop?.relaunch();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-950/55 p-4 backdrop-blur-sm">
      <div
        aria-modal="true"
        role="dialog"
        className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-xl border border-stone-200 bg-stone-50 p-6 shadow-panel"
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-stone-500">Packages</p>
            <h2 className="mt-2 font-display text-2xl text-ink">Package Manager</h2>
          </div>
          <button
            className="rounded-full border border-stone-300 px-3 py-1 text-sm"
            onClick={onClose}
            type="button"
          >
            Close
          </button>
        </div>

        {relaunchPrompt ? (
          <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            <span>{relaunchPrompt}</span>
            <button
              className="shrink-0 rounded-full bg-amber-600 px-3 py-1 text-xs font-medium text-white hover:bg-amber-700"
              onClick={relaunch}
              type="button"
            >
              Restart now
            </button>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto">
          <h3 className="mb-2 text-sm font-semibold text-stone-700">Installed packages</h3>
          {loading ? (
            <p className="text-sm text-stone-500">Loading…</p>
          ) : installed.length === 0 ? (
            <p className="text-sm text-stone-500">No packages installed yet.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {installed.map((pkg) => {
                const status = updateByName.get(pkg.package_name);
                const busy = busyPackage === pkg.package_name;
                return (
                  <li
                    key={pkg.package_name}
                    className="rounded-lg border border-stone-200 bg-white px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-ink">{pkg.package_name}</p>
                        <p className="text-xs text-stone-500">
                          v{pkg.version}
                          {status?.update_available ? (
                            <span className="ml-2 rounded-full bg-pine/15 px-2 py-0.5 text-pine">
                              → v{status.available_version}
                            </span>
                          ) : null}
                          {status?.status === "incompatible" ? (
                            <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-amber-700">
                              needs core ≥ {status.min_core_base}
                            </span>
                          ) : null}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {status?.update_available ? (
                          <button
                            className="rounded-full bg-ink px-3 py-1 text-xs font-medium text-stone-50 hover:bg-pine disabled:opacity-50"
                            disabled={busy}
                            onClick={() =>
                              void runAction(
                                pkg.package_name,
                                () => api.updatePackage(pkg.package_name),
                                `Updated ${pkg.package_name}. Restart to apply.`,
                              )
                            }
                            type="button"
                          >
                            {busy ? "Updating…" : "Update"}
                          </button>
                        ) : null}
                        {pkg.has_backup ? (
                          <button
                            className="inline-flex items-center gap-1 rounded-full border border-stone-300 px-3 py-1 text-xs hover:bg-stone-100 disabled:opacity-50"
                            disabled={busy}
                            onClick={() =>
                              void runAction(
                                pkg.package_name,
                                () => api.rollbackPackage(pkg.package_name),
                                `Rolled back ${pkg.package_name}. Restart to apply.`,
                              )
                            }
                            title={`Roll back to v${pkg.backup_version}`}
                            type="button"
                          >
                            <RotateCcw className="size-3" />
                            Rollback
                          </button>
                        ) : null}
                        <button
                          className="inline-flex items-center gap-1 rounded-full border border-red-200 px-3 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
                          disabled={busy}
                          onClick={() =>
                            void runAction(
                              pkg.package_name,
                              () => api.deletePackage(pkg.package_name),
                              `Removed ${pkg.package_name}. Restart to finish.`,
                            )
                          }
                          type="button"
                        >
                          <Trash2 className="size-3" />
                          Delete
                        </button>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <h3 className="mb-2 mt-6 text-sm font-semibold text-stone-700">
            Install a local package
          </h3>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              className="min-w-0 flex-1 rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-ink"
              onChange={(event) => setPath(event.currentTarget.value)}
              placeholder="/path/to/scistudio-blocks-example.whl"
              value={path}
            />
            <button
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-stone-300 px-3 py-2 text-sm hover:bg-white"
              onClick={() => void choosePath("file")}
              type="button"
            >
              <PackagePlus className="size-4" />
              File
            </button>
            <button
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-stone-300 px-3 py-2 text-sm hover:bg-white"
              onClick={() => void choosePath("directory")}
              type="button"
            >
              <FolderOpen className="size-4" />
              Folder
            </button>
            <button
              className="rounded-lg bg-ink px-5 py-2 text-sm font-medium text-stone-50 transition hover:bg-pine disabled:opacity-50"
              disabled={installing}
              onClick={() => void installPackage()}
              type="button"
            >
              {installing ? "Installing…" : "Install"}
            </button>
          </div>
        </div>

        {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}
      </div>
    </div>
  );
}
