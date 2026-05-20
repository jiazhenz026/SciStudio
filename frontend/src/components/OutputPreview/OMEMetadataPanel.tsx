// ---------------------------------------------------------------------------
// ADR-043 FR-013 — OME metadata browser panel
//
// Renders an `OME` tree (loaded by `getOMEMetadata` from
// `frontend/src/api/capabilities.ts`) as a navigable tree with
// copy-to-clipboard support on every leaf field. Behaviour per spec §3
// FR-013 + §4.3 T-022:
//   - Top sections are images / pixels (physical_size_x/y/z, size_x/y/z) /
//     channels (name, color, emission_wavelength) / annotations
//     (StructuredAnnotations). The OME tree is dynamic per IO handler so
//     this component does NOT hard-code those keys: it renders whatever
//     keys are present, with the spec-named ones highlighted at the top
//     when they exist.
//   - Each leaf field has a copy-to-clipboard button next to the value.
//   - When `ome` is null/empty, render a placeholder "No OME metadata"
//     message so the panel can sit in the output preview without flicker.
//
// The component is fully presentational. Callers fetch the OME tree (via
// `getOMEMetadata` or by extracting from an already-loaded metadata
// payload via `extractOMEFromMetadata`) and pass it via props.
// ---------------------------------------------------------------------------

import { useCallback, useState } from "react";

import type { OMETree } from "../../api/capabilities";

export interface OMEMetadataPanelProps {
  ome: OMETree | null;
  /**
   * Optional close handler — when provided, renders a close button in the
   * header so the panel can be used as a side-sheet inside DataPreview.
   * When omitted, the panel renders without chrome and assumes the parent
   * owns the open/close affordance.
   */
  onClose?: () => void;
  /**
   * Optional override for the clipboard implementation so unit tests can
   * assert the copied value without depending on the (jsdom-restricted)
   * `navigator.clipboard` API.
   */
  copyToClipboard?: (text: string) => Promise<void> | void;
}

type Path = readonly (string | number)[];

function pathLabel(path: Path): string {
  return path
    .map((segment) =>
      typeof segment === "number" ? `[${segment}]` : String(segment),
    )
    .join(".");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isLeaf(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  const t = typeof value;
  if (t === "string" || t === "number" || t === "boolean") return true;
  return false;
}

function formatLeaf(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

/**
 * Resolve a default clipboard writer. Avoids hitting the (jsdom-restricted)
 * `navigator.clipboard.writeText` during unit tests by checking once.
 */
function defaultCopy(text: string): Promise<void> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text);
  }
  // Last-ditch fallback for non-clipboard environments. We don't throw
  // because the panel should remain usable; the parent can still see the
  // value on screen.
  return Promise.resolve();
}

function LeafRow({
  path,
  value,
  onCopy,
}: {
  path: Path;
  value: unknown;
  onCopy: (text: string) => void;
}) {
  const label = pathLabel(path);
  const display = formatLeaf(value);
  return (
    <div
      className="flex items-baseline justify-between gap-2 py-[2px]"
      data-testid="ome-leaf"
    >
      <span className="min-w-0 flex-1 truncate text-stone-500" title={label}>
        {path[path.length - 1] ?? label}
      </span>
      <span
        className="min-w-0 flex-1 truncate font-mono text-ink"
        title={display}
      >
        {display}
      </span>
      <button
        type="button"
        aria-label={`Copy ${label}`}
        className="shrink-0 rounded border border-stone-200 bg-white px-1.5 py-[1px] text-[10px] text-stone-500 hover:bg-stone-50 hover:text-ink"
        onClick={() => onCopy(display)}
      >
        Copy
      </button>
    </div>
  );
}

function TreeNode({
  label,
  value,
  path,
  depth,
  onCopy,
  defaultOpen,
}: {
  label: string;
  value: unknown;
  path: Path;
  depth: number;
  onCopy: (text: string) => void;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState<boolean>(defaultOpen ?? depth < 2);

  if (isLeaf(value)) {
    return <LeafRow path={path} value={value} onCopy={onCopy} />;
  }

  const entries: [string | number, unknown][] = Array.isArray(value)
    ? value.map((item, idx) => [idx, item])
    : Object.entries(value as Record<string, unknown>);

  return (
    <div className="border-l border-stone-200 pl-2">
      <button
        type="button"
        className="flex w-full items-center gap-1 text-left text-[11px] font-medium text-ink hover:text-ember"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
      >
        <span className="inline-block w-3 text-stone-400">
          {open ? "▾" : "▸"}
        </span>
        <span className="truncate">{label}</span>
        <span className="ml-1 text-[10px] text-stone-400">
          ({Array.isArray(value) ? `${entries.length} items` : `${entries.length} fields`})
        </span>
      </button>
      {open ? (
        <div className="ml-2 mt-1">
          {entries.map(([key, child]) => {
            const childPath: Path = [...path, key];
            const childLabel = String(key);
            if (isLeaf(child)) {
              return <LeafRow key={childLabel} path={childPath} value={child} onCopy={onCopy} />;
            }
            return (
              <TreeNode
                key={childLabel}
                label={childLabel}
                value={child}
                path={childPath}
                depth={depth + 1}
                onCopy={onCopy}
              />
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

// Per FR-013, surface these spec-named subtrees first so the panel reads
// the way a microscopist expects (images → pixels → channels →
// annotations). Anything else falls through to a generic "Other fields"
// block at the bottom.
const TOP_KEYS_ORDER = ["images", "pixels", "channels", "annotations", "structured_annotations"];

export function OMEMetadataPanel({
  ome,
  onClose,
  copyToClipboard,
}: OMEMetadataPanelProps) {
  const copy = useCallback(
    (text: string) => {
      const fn = copyToClipboard ?? defaultCopy;
      void Promise.resolve(fn(text)).catch(() => {
        // Swallow clipboard errors — the value is still visible on screen.
      });
    },
    [copyToClipboard],
  );

  if (!ome || Object.keys(ome).length === 0) {
    return (
      <section
        aria-label="OME metadata"
        className="rounded-2xl border border-stone-200 bg-white p-3 text-sm text-stone-500"
        data-testid="ome-panel-empty"
      >
        {onClose ? (
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">OME metadata</h3>
            <button
              type="button"
              aria-label="Close OME metadata"
              className="rounded text-stone-400 hover:text-ink"
              onClick={onClose}
            >
              ×
            </button>
          </div>
        ) : null}
        No OME metadata attached to this output.
      </section>
    );
  }

  const entries = Object.entries(ome);
  const ordered = [
    ...entries.filter(([k]) => TOP_KEYS_ORDER.includes(k)),
    ...entries.filter(([k]) => !TOP_KEYS_ORDER.includes(k)),
  ];

  return (
    <section
      aria-label="OME metadata"
      className="rounded-2xl border border-stone-200 bg-white p-3 text-xs"
      data-testid="ome-panel"
    >
      {onClose ? (
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-ink">OME metadata</h3>
          <button
            type="button"
            aria-label="Close OME metadata"
            className="rounded text-stone-400 hover:text-ink"
            onClick={onClose}
          >
            ×
          </button>
        </div>
      ) : (
        <h3 className="mb-2 text-sm font-semibold text-ink">OME metadata</h3>
      )}
      <div className="space-y-2">
        {ordered.map(([key, value]) => (
          <TreeNode
            key={key}
            label={key}
            value={value}
            path={[key]}
            depth={0}
            onCopy={copy}
            defaultOpen={TOP_KEYS_ORDER.includes(key)}
          />
        ))}
      </div>
    </section>
  );
}

/**
 * Convenience helper — true when an OME tree has any rendered content, so
 * callers can hide the "OME metadata" button when there is nothing to
 * show. Mirrors the same null/empty check the panel itself does so the
 * two stay in lockstep.
 */
export function hasOMEContent(ome: OMETree | null | undefined): boolean {
  if (!ome) return false;
  if (!isRecord(ome)) return false;
  return Object.keys(ome).length > 0;
}
