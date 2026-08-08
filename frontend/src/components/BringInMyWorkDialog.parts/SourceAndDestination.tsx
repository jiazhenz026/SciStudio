/**
 * ADR-053 spec 2 (#2001) — where the work is and where the results go
 * (FR-008 – FR-011).
 */
import { FolderOpen } from "lucide-react";

import {
  DESTINATION_LABEL,
  DESTINATION_OPTIONS,
  NO_CODEBASE_HELP,
  NO_CODEBASE_LABEL,
  SOURCE_BROWSE_LABEL,
  SOURCE_LABEL,
  SOURCE_PLACEHOLDER,
} from "./copy";
import type { WorkImportFormState } from "./formState";
import { sourceFieldDisabled } from "./formState";

export interface SourceAndDestinationProps {
  state: WorkImportFormState;
  onChange: (patch: Partial<WorkImportFormState>) => void;
  onBrowse: () => void;
  browsing: boolean;
}

export function SourceAndDestination({
  state,
  onChange,
  onBrowse,
  browsing,
}: SourceAndDestinationProps) {
  const disabled = sourceFieldDisabled(state);

  return (
    <div className="grid gap-4">
      <div className="grid gap-2">
        {/*
         * Label, box, button. No help line: the label asks the question, the
         * placeholder says a folder, and the button says Browse (owner,
         * 2026-08-08 — page one was padded).
         */}
        <label className="text-sm font-medium text-ink" htmlFor="work-import-source">
          {SOURCE_LABEL}
        </label>
        <div className="flex gap-2">
          <input
            id="work-import-source"
            type="text"
            className="min-w-0 flex-1 rounded-2xl border border-stone-300 px-3 py-2 text-sm text-ink disabled:bg-stone-100 disabled:text-stone-400"
            data-testid="work-import-source-input"
            placeholder={SOURCE_PLACEHOLDER}
            value={state.sourceLocation}
            disabled={disabled}
            onChange={(event) => onChange({ sourceLocation: event.target.value })}
          />
          {/*
           * FR-008 — the browse control opens a DIRECTORY picker, not a file
           * picker. A user's analysis is a folder; a picker that only accepts a
           * file cannot express the thing the question asks for.
           */}
          <button
            type="button"
            className="inline-flex shrink-0 items-center gap-1 rounded-2xl border border-stone-300 px-3 py-2 text-sm text-ink hover:bg-stone-100 disabled:text-stone-400"
            data-testid="work-import-source-browse"
            disabled={disabled || browsing}
            onClick={onBrowse}
          >
            <FolderOpen className="size-4" />
            {SOURCE_BROWSE_LABEL}
          </button>
        </div>

        {/*
         * FR-009 / FR-010 — spreadsheet and GUI-application users are a
         * first-class path, not a degraded one. Ticking this takes the source
         * field out of play and leaves every other field in effect.
         */}
        <label className="flex items-start gap-2 text-sm text-ink">
          <input
            type="checkbox"
            className="mt-1"
            data-testid="work-import-no-codebase"
            checked={state.hasNoCodebase}
            onChange={(event) => onChange({ hasNoCodebase: event.target.checked })}
          />
          <span>
            <span className="font-medium">{NO_CODEBASE_LABEL}</span>
            <span className="block text-xs text-stone-500">{NO_CODEBASE_HELP}</span>
          </span>
        </label>
      </div>

      <fieldset className="grid gap-2" data-testid="work-import-destination-group">
        <legend className="text-sm font-medium text-ink">{DESTINATION_LABEL}</legend>
        {DESTINATION_OPTIONS.map((option) => (
          <label
            key={option.value}
            className="flex items-start gap-2 rounded-2xl border border-stone-300 px-3 py-2 text-sm text-ink hover:bg-stone-50"
          >
            <input
              type="radio"
              name="work-import-destination"
              className="mt-1"
              value={option.value}
              data-testid={`work-import-destination-${option.value}`}
              checked={state.destinationTier === option.value}
              onChange={() => onChange({ destinationTier: option.value })}
            />
            <span>
              <span className="font-medium">{option.label}</span>
              <span className="block text-xs text-stone-500">{option.help}</span>
            </span>
          </label>
        ))}
      </fieldset>
    </div>
  );
}
