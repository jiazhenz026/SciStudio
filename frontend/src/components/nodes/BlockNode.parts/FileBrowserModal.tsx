// Extracted from BlockNode.tsx as part of the #1422 god-file split.
// FileBrowserModal — lazy-loading filesystem picker used as the fallback
// path-picker when the native OS dialog is unavailable. Opened by
// `InlineTextInputField` via the "..." Browse button for fields whose
// `ui_widget` is "file_browser" or "directory_browser".

import { useCallback, useEffect, useState } from "react";

import { api } from "../../../lib/api";
import type { FilesystemEntry } from "../../../types/api";

type BrowserMode = "file_browser" | "directory_browser";

function formatSize(size: number | null | undefined): string {
  if (size === null || size === undefined) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function navigateBreadcrumb(currentPath: string, index: number): string {
  const parts = currentPath.replace(/\\/g, "/").split("/").filter(Boolean);
  // On Windows paths like "C:/" we need to preserve the drive letter.
  const isWindows = currentPath.includes("\\") || /^[A-Z]:/.test(currentPath);
  if (isWindows) {
    let newPath = parts.slice(0, index + 1).join("\\");
    if (/^[A-Z]:$/.test(newPath)) newPath += "\\";
    return newPath;
  }
  return "/" + parts.slice(0, index + 1).join("/");
}

interface EntryRowProps {
  entry: FilesystemEntry;
  isSelected: boolean;
  mode: BrowserMode;
  currentPath: string;
  onToggleSelect: (name: string) => void;
  onNavigate: (dirName: string) => void;
  onSelectFile: (path: string) => void;
}

function EntryRow({
  entry,
  isSelected,
  mode,
  currentPath,
  onToggleSelect,
  onNavigate,
  onSelectFile,
}: EntryRowProps) {
  const isDir = entry.type === "directory";
  const isSelectable = mode === "directory_browser" ? isDir : true;
  const sep = currentPath.includes("\\") ? "\\" : "/";
  return (
    <div
      className={`flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-xs ${
        isSelected ? "bg-blue-50 text-sea" : "text-ink hover:bg-stone-50"
      } ${!isSelectable && mode === "file_browser" && !isDir ? "opacity-50" : ""}`}
      onClick={() => {
        if (isDir && mode === "directory_browser") {
          onToggleSelect(entry.name);
        } else if (!isDir && mode === "file_browser") {
          onToggleSelect(entry.name);
        }
      }}
      onDoubleClick={() => {
        if (isDir) {
          onNavigate(entry.name);
        } else if (mode === "file_browser") {
          onSelectFile(`${currentPath}${sep}${entry.name}`);
        }
      }}
    >
      <span className="shrink-0 text-sm">{isDir ? "📁" : "📄"}</span>
      <span className="min-w-0 flex-1 truncate">{entry.name}</span>
      {!isDir && entry.size !== null && entry.size !== undefined && (
        <span className="shrink-0 text-stone-400">{formatSize(entry.size)}</span>
      )}
    </div>
  );
}

interface EntryListProps {
  loading: boolean;
  error: string | null;
  entries: FilesystemEntry[];
  selectedEntry: string | null;
  mode: BrowserMode;
  currentPath: string;
  onToggleSelect: (name: string) => void;
  onNavigate: (dirName: string) => void;
  onSelectFile: (path: string) => void;
}

function EntryList(props: EntryListProps) {
  const {
    loading,
    error,
    entries,
    selectedEntry,
    mode,
    currentPath,
    onToggleSelect,
    onNavigate,
    onSelectFile,
  } = props;
  if (loading) return <p className="py-4 text-center text-xs text-stone-400">Loading...</p>;
  if (error) return <p className="py-4 text-center text-xs text-red-500">{error}</p>;
  if (entries.length === 0) {
    return <p className="py-4 text-center text-xs text-stone-400">Empty directory</p>;
  }
  return (
    <>
      {entries.map((entry) => (
        <EntryRow
          key={entry.name}
          entry={entry}
          isSelected={selectedEntry === entry.name}
          mode={mode}
          currentPath={currentPath}
          onToggleSelect={onToggleSelect}
          onNavigate={onNavigate}
          onSelectFile={onSelectFile}
        />
      ))}
    </>
  );
}

interface BreadcrumbsProps {
  currentPath: string;
  onClick: (index: number) => void;
}

function Breadcrumbs({ currentPath, onClick }: BreadcrumbsProps) {
  const parts = currentPath ? currentPath.replace(/\\/g, "/").split("/").filter(Boolean) : [];
  // Build per-row keys from the cumulative path prefix so duplicate segment
  // names (e.g. nested ``foo/foo``) still yield stable, non-index-based keys.
  const breadcrumbs = parts.map((part, i) => ({
    part,
    index: i,
    key: parts.slice(0, i + 1).join("/"),
  }));
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-stone-500">
      <button type="button" className="hover:text-sea" onClick={() => onClick(-1)}>
        Root
      </button>
      {breadcrumbs.map(({ part, index, key }) => (
        <span key={key} className="flex items-center gap-1">
          <span>/</span>
          <button type="button" className="hover:text-sea" onClick={() => onClick(index)}>
            {part}
          </button>
        </span>
      ))}
    </div>
  );
}

export function FileBrowserModal({
  mode,
  initialPath,
  onSelect,
  onCancel,
}: {
  mode: BrowserMode;
  initialPath: string;
  onSelect: (path: string) => void;
  onCancel: () => void;
}) {
  const [currentPath, setCurrentPath] = useState("");
  const [entries, setEntries] = useState<FilesystemEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<string | null>(null);

  const loadDirectory = useCallback(async (dirPath: string) => {
    setLoading(true);
    setError(null);
    setSelectedEntry(null);
    try {
      const resp = await api.browseFilesystem(dirPath);
      setCurrentPath(resp.path);
      setEntries(resp.entries);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to browse");
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Try to start from the current value's directory
    loadDirectory(initialPath || "");
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleNavigate = (dirName: string) => {
    const sep = currentPath.includes("\\") ? "\\" : "/";
    const newPath = currentPath ? `${currentPath}${sep}${dirName}` : dirName;
    loadDirectory(newPath);
  };

  const handleBreadcrumbClick = (index: number) => {
    if (index < 0) {
      loadDirectory("");
      return;
    }
    loadDirectory(navigateBreadcrumb(currentPath, index));
  };

  const handleToggleSelect = (name: string) =>
    setSelectedEntry((prev) => (prev === name ? null : name));

  const handleSelect = () => {
    if (mode === "directory_browser") {
      if (selectedEntry) {
        const sep = currentPath.includes("\\") ? "\\" : "/";
        onSelect(`${currentPath}${sep}${selectedEntry}`);
      } else {
        onSelect(currentPath);
      }
    } else if (selectedEntry) {
      const sep = currentPath.includes("\\") ? "\\" : "/";
      onSelect(`${currentPath}${sep}${selectedEntry}`);
    }
  };

  const canSelect =
    mode === "directory_browser"
      ? currentPath !== "" || selectedEntry !== null
      : selectedEntry !== null &&
        entries.some((e) => e.name === selectedEntry && e.type === "file");

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40"
      onClick={onCancel}
    >
      <div
        className="flex max-h-[70vh] w-[500px] flex-col rounded-xl border border-stone-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-b border-stone-100 px-4 py-3">
          <div className="text-sm font-semibold text-ink">
            {mode === "file_browser" ? "Select File" : "Select Directory"}
          </div>
          <Breadcrumbs currentPath={currentPath} onClick={handleBreadcrumbClick} />
        </div>

        {/* File list */}
        <div className="min-h-[200px] flex-1 overflow-y-auto px-2 py-1">
          <EntryList
            loading={loading}
            error={error}
            entries={entries}
            selectedEntry={selectedEntry}
            mode={mode}
            currentPath={currentPath}
            onToggleSelect={handleToggleSelect}
            onNavigate={handleNavigate}
            onSelectFile={onSelect}
          />
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-stone-100 px-4 py-2">
          <button
            type="button"
            className="rounded border border-stone-200 px-3 py-1.5 text-xs text-stone-600 hover:bg-stone-50"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded bg-blue-500 px-3 py-1.5 text-xs text-white hover:bg-blue-600 disabled:opacity-40"
            disabled={!canSelect}
            onClick={handleSelect}
          >
            Select
          </button>
        </div>
      </div>
    </div>
  );
}
