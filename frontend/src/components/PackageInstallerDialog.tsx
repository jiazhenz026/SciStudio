import { FolderOpen, PackagePlus } from "lucide-react";
import { startTransition, useState } from "react";

import { api } from "../lib/api";
import type { LocalPackageInstallResponse } from "../types/api";
import { useAppStore } from "../store";

interface PackageInstallerDialogProps {
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

export function PackageInstallerDialog({ open, onClose }: PackageInstallerDialogProps) {
  const setBlocks = useAppStore((state) => state.setBlocks);
  const setBlockSchema = useAppStore((state) => state.setBlockSchema);
  const [path, setPath] = useState("");
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LocalPackageInstallResponse | null>(null);

  if (!open) return null;

  async function choosePath(mode: "file" | "directory") {
    setError(null);
    try {
      const response = await api.openNativeDialog(mode, parentDirectory(path));
      if (response.paths.length > 0) {
        setPath(response.paths[0]);
        setResult(null);
      }
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
    setResult(null);
    try {
      const installed = await api.installLocalPackage(selected);
      setResult(installed);
      await refreshBlocks();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setInstalling(false);
    }
  }

  async function refreshBlocks() {
    const payload = await api.listBlocks();
    startTransition(() => setBlocks(payload.blocks));
    const schemas = await Promise.all(
      payload.blocks.map((block) => api.getBlockSchema(block.type_name)),
    );
    startTransition(() => {
      schemas.forEach((schema) => setBlockSchema(schema));
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-950/55 p-4 backdrop-blur-sm">
      <div
        aria-modal="true"
        role="dialog"
        className="w-full max-w-xl rounded-xl border border-stone-200 bg-stone-50 p-6 shadow-panel"
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-stone-500">Packages</p>
            <h2 className="mt-2 font-display text-2xl text-ink">Install local package</h2>
          </div>
          <button
            className="rounded-full border border-stone-300 px-3 py-1 text-sm"
            onClick={onClose}
            type="button"
          >
            Close
          </button>
        </div>

        <label className="block text-sm font-medium text-stone-700">
          Local path
          <div className="mt-1 flex flex-col gap-2 sm:flex-row">
            <input
              autoFocus
              className="min-w-0 flex-1 rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-ink"
              onChange={(event) => {
                setPath(event.currentTarget.value);
                setResult(null);
              }}
              placeholder="C:\\path\\to\\scistudio-blocks-example.whl"
              value={path}
            />
            <button
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-stone-300 px-3 py-2 text-sm hover:bg-white sm:w-auto"
              onClick={() => void choosePath("file")}
              type="button"
            >
              <PackagePlus className="size-4" />
              File
            </button>
            <button
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-stone-300 px-3 py-2 text-sm hover:bg-white sm:w-auto"
              onClick={() => void choosePath("directory")}
              type="button"
            >
              <FolderOpen className="size-4" />
              Folder
            </button>
          </div>
        </label>

        {result ? (
          <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            Installed {result.package_name} {result.version}. Registered {result.blocks_count} block
            {result.blocks_count === 1 ? "" : "s"}.
          </div>
        ) : null}

        {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}

        <div className="mt-6 flex justify-end gap-3">
          <button
            className="rounded-full border border-stone-300 px-4 py-2 text-sm"
            onClick={onClose}
            type="button"
          >
            Cancel
          </button>
          <button
            className="rounded-full bg-ink px-5 py-2 text-sm font-medium text-stone-50 transition hover:bg-pine disabled:opacity-50"
            disabled={installing}
            onClick={() => void installPackage()}
            type="button"
          >
            {installing ? "Installing..." : "Install"}
          </button>
        </div>
      </div>
    </div>
  );
}
