/**
 * ADR-054 Phase D (#2354) - Convert to interactive block (FR-036, US8).
 *
 * The scientist has finished exploring. They dragged the threshold until the
 * mask looked right, and now they want the workflow to ask for that threshold
 * on every run. That is an ADR-051 interactive block, and the only thing the
 * agent cannot infer from the MiniApp is what the block should PRODUCE: a
 * MiniApp shows things, a block outputs them, and the page never had to name a
 * port or a type. So this dialog asks exactly that, plus a note for anything
 * the outputs do not say.
 *
 * IT WRITES NOTHING AND CHANGES NOTHING. FR-036 is explicit that the MiniApp is
 * left unchanged: the route starts an agent session whose brief names the
 * MiniApp directory, the `scistudio-write-block` skill, the ADR-051 contract,
 * and these outputs. The user keeps the MiniApp they were using while the block
 * is being written, and a conversion they abandon costs them nothing.
 *
 * The agent controls are the same ones the create dialog offers, for the same
 * reason (ADR-053 FR-042): this is the second surface in this feature to start
 * a session, and a session that cannot start should say so here rather than
 * failing inside the route.
 */
import { Plus } from "lucide-react";

import { useCallback, useEffect, useState } from "react";

import type { PermissionMode } from "../components/AIChat/SetupScreen.parts/types";
import { AgentSetup } from "../components/BringInMyWorkDialog.parts/AgentSetup";
import { AvailabilityGuidance } from "../components/BringInMyWorkDialog.parts/AvailabilityGuidance";
import {
  hasUsableProvider,
  resolveSelectedProvider,
} from "../components/BringInMyWorkDialog.parts/availability";
import {
  useAgentAvailability,
  type AvailabilityFetcher,
} from "../components/BringInMyWorkDialog.parts/useAgentAvailability";
import { fromBackendPermissionMode, toBackendPermissionMode } from "../lib/api/workImport";
import { useAppStore } from "../store";

import { miniAppsApi } from "./api";

export const CONVERT_TITLE = "Convert to interactive block";
export const CONVERT_EYEBROW = "MiniApp";
export const OUTPUTS_LABEL = "Outputs";
export const NOTE_LABEL = "Instructions";
export const NOTE_PLACEHOLDER = "Use the current threshold as the default.";
export const PROBING = "Checking which agents can run this...";

/** One requested output port of the block being written. */
export interface OutputRow {
  /** Stable across edits and removals, so a row keeps its identity in React. */
  id: string;
  name: string;
  type: string;
  port: string;
}

let nextRowId = 0;

export function emptyRow(): OutputRow {
  nextRowId += 1;
  return { id: `output-${nextRowId}`, name: "", type: "", port: "" };
}

/** Generate stable, unique Python-style port names from display names. */
export function completeRows(rows: OutputRow[]): { name: string; type: string; port: string }[] {
  const used = new Set<string>();
  return rows.map((row) => {
    const name = row.name.trim();
    const stem =
      name
        .normalize("NFKD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9_]+/g, "_")
        .replace(/^_+|_+$/g, "") || "output";
    const base = /^[a-z_]/.test(stem) ? stem : `output_${stem}`;
    let port = base;
    let suffix = 2;
    while (used.has(port)) port = `${base}_${suffix++}`;
    used.add(port);
    return { name, type: row.type.trim(), port };
  });
}

export interface ConvertToBlockDialogProps {
  open: boolean;
  onOpenChange(open: boolean): void;
  panelId: string;
  panelName?: string;
  onStarted(sessionTabId: string | null): void;
  /** Test seam for the graded availability probe. */
  fetchAvailability?: AvailabilityFetcher;
  /** Test seam for `POST /api/panels/miniapps/{panel_id}/convert`. */
  convert?: typeof miniAppsApi.convert;
}

/** Mounted only while open, so the availability probe fires on open. */
export function ConvertToBlockDialog(props: ConvertToBlockDialogProps) {
  if (!props.open) return null;
  return <ConvertToBlockDialogBody {...props} />;
}

function ConvertToBlockDialogBody({
  onOpenChange,
  panelId,
  panelName,
  onStarted,
  fetchAvailability,
  convert = miniAppsApi.convert,
}: ConvertToBlockDialogProps) {
  const types = useAppStore((s) => s.types);

  const [rows, setRows] = useState<OutputRow[]>([emptyRow()]);
  const [note, setNote] = useState("");
  const [provider, setProvider] = useState<string | null>(null);
  const [permissionMode, setPermissionMode] = useState<PermissionMode>("safe");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const {
    loading: probing,
    availability,
    probeError,
    retry,
    retrying,
  } = useAgentAvailability(fetchAvailability);
  const agentUsable = hasUsableProvider(availability);

  useEffect(() => {
    setProvider((prev) => resolveSelectedProvider(availability, prev));
  }, [availability]);

  const close = useCallback(() => onOpenChange(false), [onOpenChange]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [close]);

  const outputs = completeRows(rows);
  const duplicateNames =
    new Set(outputs.map((output) => output.name.toLowerCase())).size !== outputs.length;
  const complete =
    outputs.length > 0 &&
    outputs.every(
      (output) => output.name !== "" && types.some((type) => type.name === output.type),
    );
  const rowError =
    duplicateNames && outputs.every((output) => output.name)
      ? "Give each output a different name."
      : null;
  const submittable = complete && !rowError && !submitting && !probing && agentUsable;

  const patchRow = (id: string, patch: Partial<OutputRow>) => {
    setRows((prev) => prev.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  };

  const submit = useCallback(async () => {
    if (!submittable) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await convert(panelId, {
        outputs,
        note: note.trim() || null,
        provider,
        permission_mode: toBackendPermissionMode(permissionMode),
      });
      const sessionProvider = response.provider ?? provider;
      if (response.session_tab_id && sessionProvider) {
        useAppStore.getState().addWorkImportTerminalTab({
          tabId: response.session_tab_id,
          title: "Convert MiniApp",
          provider: sessionProvider,
          permissionMode: fromBackendPermissionMode(
            response.permission_mode ?? toBackendPermissionMode(permissionMode),
          ),
        });
        useAppStore.getState().openBottomTab("ai");
      }
      onStarted(response.session_tab_id);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }, [
    convert,
    note,
    onOpenChange,
    onStarted,
    outputs,
    panelId,
    permissionMode,
    provider,
    submittable,
  ]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4">
      <div
        aria-modal="true"
        role="dialog"
        aria-labelledby="miniapp-convert-title"
        data-testid="miniapp-convert-dialog"
        className="flex max-h-[88vh] w-full max-w-2xl flex-col rounded-xl border border-stone-200 bg-stone-50 p-6 shadow-panel"
      >
        <div className="mb-3 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-stone-500">{CONVERT_EYEBROW}</p>
            <h2 className="mt-2 font-display text-2xl text-ink" id="miniapp-convert-title">
              {CONVERT_TITLE}
            </h2>
            <p className="mt-2 text-sm text-stone-600">
              Use <strong>{panelName || panelId}</strong> as an interactive step in your workflow.
              Choose which results it should send to the next blocks.
            </p>
            <p className="mt-1 text-sm text-stone-600">Your MiniApp will remain available.</p>
          </div>
          <button
            className="rounded-full border border-stone-300 px-3 py-1 text-sm"
            data-testid="miniapp-convert-close"
            onClick={close}
            type="button"
          >
            Cancel
          </button>
        </div>

        <div className="grid min-h-0 flex-1 content-start gap-5 overflow-y-auto pr-1">
          <div className="grid gap-1.5">
            <p className="text-sm font-medium text-ink">{OUTPUTS_LABEL}</p>
            <div className="grid gap-2">
              {rows.map((row, index) => (
                <div className="flex items-end gap-2" key={row.id}>
                  <div className="grid min-w-0 flex-1 gap-1">
                    <label className="text-xs text-stone-600" htmlFor={`${row.id}-name`}>
                      Name
                    </label>
                    <input
                      id={`${row.id}-name`}
                      aria-label={`Output ${index + 1} name`}
                      className="min-w-0 rounded-2xl border border-stone-300 bg-white px-3 py-2 text-sm text-ink"
                      data-testid={`miniapp-convert-name-${index}`}
                      onChange={(event) => patchRow(row.id, { name: event.target.value })}
                      value={row.name}
                    />
                  </div>
                  <div className="grid min-w-0 flex-1 gap-1">
                    <label className="text-xs text-stone-600" htmlFor={`${row.id}-type`}>
                      Data type
                    </label>
                    <select
                      id={`${row.id}-type`}
                      aria-label={`Output ${index + 1} data type`}
                      className="min-w-0 rounded-2xl border border-stone-300 bg-white px-3 py-2 text-sm text-ink"
                      data-testid={`miniapp-convert-type-${index}`}
                      onChange={(event) => patchRow(row.id, { type: event.target.value })}
                      value={row.type}
                    >
                      <option value="" disabled>
                        Select data type
                      </option>
                      {types.map((type) => (
                        <option key={type.name} value={type.name}>
                          {type.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  {rows.length > 1 ? (
                    <button
                      className="rounded-full border border-stone-300 px-3 py-1 text-xs"
                      data-testid={`miniapp-convert-remove-${index}`}
                      onClick={() => setRows((prev) => prev.filter((entry) => entry.id !== row.id))}
                      type="button"
                    >
                      Remove
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
            {rowError ? (
              <p className="text-sm text-red-700" role="alert">
                {rowError}
              </p>
            ) : null}
            <div>
              <button
                className="inline-flex items-center gap-1 rounded-full border border-stone-300 px-3 py-1 text-xs"
                data-testid="miniapp-convert-add-output"
                onClick={() => setRows((prev) => [...prev, emptyRow()])}
                type="button"
              >
                <Plus size={14} aria-hidden="true" />
                Add output
              </button>
            </div>
          </div>

          <div className="grid gap-1.5">
            <label className="text-sm font-medium text-ink" htmlFor="miniapp-convert-note">
              {NOTE_LABEL} <span className="ml-2 font-normal text-stone-500">Optional</span>
            </label>
            <textarea
              className="min-h-[4rem] rounded-2xl border border-stone-300 bg-white px-3 py-2 text-sm text-ink"
              data-testid="miniapp-convert-note"
              id="miniapp-convert-note"
              onChange={(event) => setNote(event.target.value)}
              placeholder={NOTE_PLACEHOLDER}
              value={note}
            />
          </div>

          {probing ? (
            <div className="grid gap-2">
              <p className="text-xs italic text-stone-500" data-testid="miniapp-convert-probing">
                {PROBING}
              </p>
              <AgentSetup
                availability={availability}
                probing
                provider={provider}
                permissionMode={permissionMode}
                onProviderChange={setProvider}
                onPermissionModeChange={setPermissionMode}
              />
            </div>
          ) : agentUsable ? (
            <AgentSetup
              availability={availability}
              probing={false}
              provider={provider}
              permissionMode={permissionMode}
              onProviderChange={setProvider}
              onPermissionModeChange={setPermissionMode}
            />
          ) : (
            <AvailabilityGuidance
              availability={availability}
              probeError={probeError}
              onRetry={retry}
              retrying={retrying}
            />
          )}
        </div>

        <div className="mt-4 grid gap-3 border-t border-stone-200 pt-4">
          {error ? (
            <div
              className="rounded bg-red-50 px-3 py-2 text-sm text-red-700"
              data-testid="miniapp-convert-error"
              role="alert"
              aria-live="assertive"
            >
              {error}
            </div>
          ) : null}
          <div className="flex justify-end">
            <button
              className="rounded-full bg-ink px-4 py-2 text-sm text-white disabled:opacity-40"
              data-testid="miniapp-convert-submit"
              disabled={!submittable}
              onClick={() => void submit()}
              type="button"
            >
              {submitting ? "Converting..." : "Convert"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
