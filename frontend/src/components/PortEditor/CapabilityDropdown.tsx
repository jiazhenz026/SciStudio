// ---------------------------------------------------------------------------
// ADR-043 FR-012 — Capability dropdown for the port editor
//
// Renders a per-port capability picker that lists every ADR-043
// `FormatCapability` matching `(direction, dataType, extension)`. Behaviour
// per spec §3 FR-012 + §4.3 T-021:
//   - On mount + when `(direction, dataType, extension)` change, fetch
//     matching capabilities via `listCapabilities`.
//   - If exactly one capability matches, auto-select it (calling `onChange`
//     only when the new selection differs from the existing value).
//   - If zero or >1 match, surface the picker and a placeholder option
//     prompting the user to choose. Disabled while loading and when the
//     extension is empty (no useful filter yet).
//   - Each option shows label, format_id, and a metadata-fidelity badge
//     ("pixel_only" / "typed_meta" / "format_specific" / "lossless"). The
//     badge is colour-coded so the worst-case (`pixel_only` save) is
//     visible at a glance, matching the warning chip used in BlockNode.tsx.
//
// Persistence: the parent persists the selected `capability_id` on the
// port's port-config object (e.g. `port.capability_id`). The component is
// fully controlled and never persists anything itself.
// ---------------------------------------------------------------------------

import { useEffect, useRef, useState } from "react";

import { listCapabilities, type CapabilityDirection } from "../../api/capabilities";
import type {
  FormatCapabilityResponse,
  MetadataFidelityLevel,
  TypeHierarchyEntry,
} from "../../types/api";

export interface CapabilityDropdownProps {
  /** ADR-043 boundary IO (inverted at the block boundary): "save" for input
   *  ports (SciStudio writes a file for the external app), "load" for output
   *  ports (the external app writes a file SciStudio reads back). */
  direction: CapabilityDirection;
  /** DataObject subclass name. Empty string skips the type filter. */
  dataType: string;
  /** File extension (case-insensitive, leading dot OK). Empty string
   *  disables the dropdown until the user picks one. */
  extension: string;
  /** Currently-selected capability_id, or null for none. */
  value: string | null;
  /** Called with the new capability_id whenever the user picks an option
   *  OR the auto-select rule fires. Never called with the existing value. */
  onChange: (capabilityId: string) => void;
  /**
   * Optional injection for tests + storybook. When provided, replaces the
   * real `listCapabilities` API call. The signature mirrors the real
   * function so unit tests can pass a sync stub returning a static list.
   */
  loadCapabilities?: typeof listCapabilities;
  /** Optional disabled flag (e.g. when the port row is read-only). */
  disabled?: boolean;
  /** Optional id for accessibility / test selectors. */
  id?: string;
  /**
   * Optional `BlockSchemaResponse.type_hierarchy` slice — when supplied,
   * the dropdown's API filter walks the supertype chain so capabilities
   * declared on a base type (e.g. `DataObject`) match subtype requests
   * (Codex P2, PR #1299). When omitted, only the universal `DataObject`
   * base is treated as polymorphic — still a strict improvement over
   * exact-equality matching.
   */
  typeHierarchy?: TypeHierarchyEntry[];
}

const FIDELITY_BADGE: Record<MetadataFidelityLevel, { label: string; cls: string }> = {
  pixel_only: {
    // Display label only; the backend MetadataFidelityLevel value stays
    // "pixel_only". "payload only" reads better for non-image data too.
    label: "payload only",
    cls: "bg-red-50 text-red-700 border border-red-200",
  },
  typed_meta: {
    label: "typed_meta",
    cls: "bg-amber-50 text-amber-700 border border-amber-200",
  },
  format_specific: {
    label: "format_specific",
    cls: "bg-sky-50 text-sky-700 border border-sky-200",
  },
  lossless: {
    label: "lossless",
    cls: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  },
};

function FidelityBadge({ level }: { level: MetadataFidelityLevel }) {
  const entry = FIDELITY_BADGE[level] ?? FIDELITY_BADGE.pixel_only;
  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1.5 text-xs font-medium ${entry.cls}`}
      data-testid="fidelity-badge"
    >
      {entry.label}
    </span>
  );
}

function describeOption(cap: FormatCapabilityResponse): string {
  // The native <option> element does not render React children, so we
  // build a plain-text label that surfaces label + format_id + fidelity.
  // The badge below the select shows the rich version for the currently
  // selected option.
  return `${cap.label} — ${cap.format_id} [${cap.metadata_fidelity.level}]`;
}

interface PlaceholderArgs {
  showEmpty: boolean;
  loading: boolean;
  hasCapabilities: boolean;
}

function placeholderLabel({ showEmpty, loading, hasCapabilities }: PlaceholderArgs): string {
  if (showEmpty) return "Enter extension to pick a capability";
  if (loading) return "Loading capabilities...";
  if (!hasCapabilities) return "No matching capability";
  return "Select a capability...";
}

interface HintProps {
  error: string | null;
  ambiguous: boolean;
  ambiguousCount: number;
  /** User-facing term for the handler: "Saver" (input) or "Loader" (output). */
  term: string;
}

function CapabilityHint({ error, ambiguous, ambiguousCount, term }: HintProps) {
  if (error) {
    return (
      <span className="text-[11px] text-red-600" role="alert">
        {error}
      </span>
    );
  }
  if (ambiguous) {
    return (
      <span className="text-[11px] text-amber-700">
        {ambiguousCount} {term.toLowerCase()}s match — pick one.
      </span>
    );
  }
  // Metadata fidelity (incl. the payload-only / pixel_only case) is conveyed by
  // the FidelityBadge pill next to the select, not a sentence.
  return null;
}

export function CapabilityDropdown({
  direction,
  dataType,
  extension,
  value,
  onChange,
  loadCapabilities,
  disabled,
  id,
  typeHierarchy,
}: CapabilityDropdownProps) {
  const [capabilities, setCapabilities] = useState<FormatCapabilityResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Avoid stale-fetch races: if the user edits the extension three times
  // quickly we only render the latest response. requestId is incremented
  // on every fetch; only the matching response is allowed to call
  // setCapabilities.
  const requestIdRef = useRef(0);

  // Track the last value we auto-selected so we don't fight the parent if
  // it deliberately clears the selection.
  const lastAutoSelectRef = useRef<string | null>(null);

  useEffect(() => {
    const fetcher = loadCapabilities ?? listCapabilities;
    const myRequest = ++requestIdRef.current;
    setLoading(true);
    setError(null);

    Promise.resolve(
      fetcher({
        direction,
        dataType: dataType || undefined,
        extension: extension || undefined,
        typeHierarchy,
      }),
    )
      .then((next) => {
        if (myRequest !== requestIdRef.current) return;
        setCapabilities(next);
        setLoading(false);

        // Auto-select rule (FR-012): if exactly one capability matches AND
        // the parent has no value (or the value is not in the new list),
        // adopt the single match. Only fire once per resolved id so the
        // parent doesn't get a render-loop if it echoes the value back
        // through props.
        if (next.length === 1) {
          const only = next[0];
          const valueInList = value && next.some((c) => c.id === value);
          if (!valueInList && lastAutoSelectRef.current !== only.id) {
            lastAutoSelectRef.current = only.id;
            onChange(only.id);
          }
        }
      })
      .catch((err: unknown) => {
        if (myRequest !== requestIdRef.current) return;
        setError(err instanceof Error ? err.message : "Failed to load capabilities");
        setCapabilities([]);
        setLoading(false);
      });
    // value is intentionally not a dep: we only react to filter changes
    // for fetch; the auto-select rule reads value at fetch-time.
    // typeHierarchy is included so subtype-compatible matching refreshes
    // when a schema arrives or the user switches blocks (Codex P2).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [direction, dataType, extension, loadCapabilities, typeHierarchy]);

  const selected = capabilities.find((c) => c.id === value) ?? null;
  const ambiguous = capabilities.length > 1 && !selected;
  const showEmpty = !extension;
  // ADR-043 boundary IO: input ports are written by a SAVER, output ports read
  // by a LOADER. This is the user-facing term (was the dev jargon "Capability").
  const term = direction === "save" ? "Saver" : "Loader";

  if (error) {
    return (
      <div className="flex flex-col gap-1 text-xs" data-testid="capability-dropdown">
        <span className="text-[11px] text-red-600" role="alert">
          {error}
        </span>
      </div>
    );
  }

  // Only surface the picker when there is a real choice (>1 match). With 0 or 1
  // match the (type, extension) tuple already determines the handler, so the
  // field would just duplicate Data type + Extension. We still warn when a
  // single lossy saver is auto-selected, or when nothing matches at all.
  if (capabilities.length <= 1) {
    const noMatch = !showEmpty && !loading && capabilities.length === 0;
    if (noMatch) {
      return (
        <div className="flex flex-col gap-1 text-xs" data-testid="capability-dropdown">
          <span className="text-[11px] text-amber-700">
            No {term.toLowerCase()} for {dataType || "this type"} + {extension || "?"}.
          </span>
        </div>
      );
    }
    // Single match: the picker (handler choice) is redundant with Data type +
    // Extension and stays hidden, but Metadata Completeness is useful info, so
    // surface the resolved capability's level as a labelled pill.
    if (selected) {
      return (
        // Single line (label + pill) — shows how completely the handler
        // preserves metadata, not a handler choice, so it is labelled "Metadata
        // Completeness" (not Saver/Loader).
        <div className="flex items-center gap-2 text-sm" data-testid="capability-dropdown">
          <span className="font-medium text-stone-700">Metadata Completeness</span>
          <FidelityBadge level={selected.metadata_fidelity.level} />
        </div>
      );
    }
    return null;
  }

  return (
    <div className="flex flex-col gap-1 text-xs" data-testid="capability-dropdown">
      <label className="flex items-center gap-2">
        <span className="shrink-0 text-stone-500">{term}</span>
        <select
          aria-label={
            id
              ? `${id} ${term.toLowerCase()}`
              : `${direction} ${term.toLowerCase()} for ${dataType || "any type"}`
          }
          className="min-w-0 flex-1 rounded-xl border border-stone-300 bg-white px-3 py-1.5 text-xs disabled:cursor-not-allowed disabled:bg-stone-50"
          disabled={disabled || loading || showEmpty || capabilities.length === 0}
          value={value ?? ""}
          onChange={(event) => {
            const nextId = event.target.value;
            if (!nextId || nextId === value) return;
            onChange(nextId);
          }}
        >
          {(showEmpty || capabilities.length !== 1 || !value) && (
            <option value="">
              {placeholderLabel({
                showEmpty,
                loading,
                hasCapabilities: capabilities.length > 0,
              })}
            </option>
          )}
          {capabilities.map((cap) => (
            <option key={cap.id} value={cap.id}>
              {describeOption(cap)}
            </option>
          ))}
        </select>
        {selected ? <FidelityBadge level={selected.metadata_fidelity.level} /> : null}
      </label>
      <CapabilityHint
        error={error}
        ambiguous={ambiguous}
        ambiguousCount={capabilities.length}
        term={term}
      />
    </div>
  );
}
