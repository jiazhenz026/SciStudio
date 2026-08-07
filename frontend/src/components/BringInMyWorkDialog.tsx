/**
 * ADR-053 spec 2 (#2001) — the Bring In My Work framing dialog.
 *
 * Spec: `docs/specs/adr-053-work-import.md`, FR-003 – FR-021 and FR-037 – FR-044.
 *
 * A scientist who already has a working way of doing their analysis is the user
 * with the most to gain from SciStudio and the highest cost of entry. This
 * dialog is everything the product does before handing that user to an agent:
 * it collects where their work is, where the results should go, which agent
 * runs, how much that agent may do without asking, and four questions about
 * their own world. Then it says plainly that the result is not verified, and
 * starts an ordinary chat session (FR-025) with all of it already loaded.
 *
 * Two constraints shape every question in here, and both are easy to erode:
 *
 *   FR-006 — no question may require SciStudio knowledge.
 *   FR-007 — no question may require software-development knowledge.
 *
 * The dialog asks only about the user's own world. The wording that makes that
 * true lives in `BringInMyWorkDialog.parts/copy.ts`, together with the note on
 * why questions 3 and 4 are also a discovery surface.
 */
import { useCallback, useEffect, useState } from "react";

import { api } from "../lib/api";
import {
  fromBackendPermissionMode,
  startWorkImportSession,
  validateWorkImportRequest,
  type WorkImportSessionRequest,
} from "../lib/api/workImport";
import { useAppStore } from "../store";

import { AgentSetup } from "./BringInMyWorkDialog.parts/AgentSetup";
import { AvailabilityGuidance } from "./BringInMyWorkDialog.parts/AvailabilityGuidance";
import { CorrectnessCaveat } from "./BringInMyWorkDialog.parts/CorrectnessCaveat";
import { DataKindsQuestion } from "./BringInMyWorkDialog.parts/DataKindsQuestion";
import { FreeTextQuestion } from "./BringInMyWorkDialog.parts/FreeTextQuestion";
import { SourceAndDestination } from "./BringInMyWorkDialog.parts/SourceAndDestination";
import {
  hasUsableProvider,
  resolveSelectedProvider,
} from "./BringInMyWorkDialog.parts/availability";
import {
  AVAILABILITY_PROBING,
  CANCEL_LABEL,
  DIALOG_EYEBROW,
  DIALOG_LEAD,
  DIALOG_TITLE,
  Q2_HELP_NO_CODEBASE,
  Q2_HELP_WITH_SOURCE,
  Q2_LABEL,
  Q2_PLACEHOLDER_NO_CODEBASE,
  Q2_PLACEHOLDER_WITH_SOURCE,
  Q3_HELP,
  Q3_LABEL,
  Q3_PLACEHOLDER,
  Q4_HELP,
  Q4_LABEL,
  Q4_PLACEHOLDER,
  START_HELP,
  START_LABEL,
  STARTING_LABEL,
} from "./BringInMyWorkDialog.parts/copy";
import {
  blockingReasons,
  buildRequest,
  canStart,
  INITIAL_FORM_STATE,
  workflowDescriptionRequired,
  type WorkImportFormState,
} from "./BringInMyWorkDialog.parts/formState";
import {
  useAgentAvailability,
  type AvailabilityFetcher,
} from "./BringInMyWorkDialog.parts/useAgentAvailability";

export interface BringInMyWorkDialogProps {
  onClose: () => void;
  /**
   * Test seam for contract C1. Production passes nothing and the hook uses
   * `fetchAgentAvailability` from the availability track's client module.
   */
  fetchAvailability?: AvailabilityFetcher;
  /** Test seam for the request itself; production posts to `POST /api/work-import/sessions`. */
  startSession?: (request: WorkImportSessionRequest) => Promise<{
    tab_id: string;
    title: string;
    brief_path: string;
    provider: string;
    permission_mode: "safe" | "bypass";
  }>;
}

function parentDirectory(path: string): string | undefined {
  const trimmed = path.trim();
  if (!trimmed) return undefined;
  const normalized = trimmed.replace(/\\/g, "/");
  const index = normalized.lastIndexOf("/");
  return index > 0 ? trimmed.slice(0, index) : undefined;
}

export function BringInMyWorkDialog({
  onClose,
  fetchAvailability,
  startSession = startWorkImportSession,
}: BringInMyWorkDialogProps) {
  const projectDir = useAppStore((s) => s.currentProject?.path ?? null);
  const addWorkImportTerminalTab = useAppStore((s) => s.addWorkImportTerminalTab);
  const openBottomTab = useAppStore((s) => s.openBottomTab);

  const [state, setState] = useState<WorkImportFormState>(INITIAL_FORM_STATE);
  const [browsing, setBrowsing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // FR-035 — renders immediately; a hanging probe degrades to a reported state.
  const {
    loading: probing,
    availability,
    probeError,
    retry,
    retrying,
  } = useAgentAvailability(fetchAvailability);
  const agentUsable = hasUsableProvider(availability);

  // FR-043 — one usable provider is selected rather than offered as a choice.
  useEffect(() => {
    setState((prev) => {
      const next = resolveSelectedProvider(availability, prev.provider);
      return next === prev.provider ? prev : { ...prev, provider: next };
    });
  }, [availability]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const patch = useCallback((next: Partial<WorkImportFormState>) => {
    setState((prev) => ({ ...prev, ...next }));
  }, []);

  const toggleDataKind = useCallback((option: string) => {
    setState((prev) => ({
      ...prev,
      dataKinds: prev.dataKinds.includes(option)
        ? prev.dataKinds.filter((value) => value !== option)
        : [...prev.dataKinds, option],
    }));
  }, []);

  const handleBrowse = useCallback(async () => {
    setBrowsing(true);
    setError(null);
    try {
      // FR-008 — a DIRECTORY picker. The user's work is a folder.
      const response = await api.openNativeDialog(
        "directory",
        parentDirectory(state.sourceLocation),
        true,
      );
      if (response.paths.length > 0) patch({ sourceLocation: response.paths[0] });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBrowsing(false);
    }
  }, [patch, state.sourceLocation]);

  const handleStart = useCallback(async () => {
    if (!projectDir) return;
    setStarting(true);
    setError(null);
    const request = buildRequest(state, projectDir);
    /*
     * A2's `ImportSessionContext` rejects a body that breaks any of its rules,
     * and a 422 at this point is a dead end: the user has filled in a long form
     * and gets an HTTP status back. `blockingReasons` should already have made
     * every violation unreachable, so this is a backstop that turns a
     * regression in the form's own rules into a readable sentence instead of a
     * rejected request.
     */
    const problems = validateWorkImportRequest(request);
    if (problems.length > 0) {
      setError(problems.join(" "));
      setStarting(false);
      return;
    }
    try {
      const response = await startSession(request);
      // C3 — the backend has already written the brief and spawned the PTY, so
      // the tab goes straight to `running` and joins the existing session over
      // `WS /api/ai/pty/{tab_id}`. FR-025: from here it is an ordinary chat
      // session the user can talk to, redirect, and end like any other.
      addWorkImportTerminalTab({
        tabId: response.tab_id,
        title: response.title,
        provider: response.provider,
        permissionMode: fromBackendPermissionMode(response.permission_mode),
      });
      openBottomTab("ai");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStarting(false);
    }
  }, [addWorkImportTerminalTab, onClose, openBottomTab, projectDir, startSession, state]);

  const reasons = blockingReasons(state, { projectDir, agentUsable });
  const startable = canStart(state, { projectDir, agentUsable }) && !starting;
  const q2Required = workflowDescriptionRequired(state);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4">
      <div
        aria-modal="true"
        role="dialog"
        aria-labelledby="work-import-title"
        data-testid="work-import-dialog"
        className="flex max-h-[88vh] w-full max-w-2xl flex-col rounded-xl border border-stone-200 bg-stone-50 p-6 shadow-panel"
      >
        <div className="mb-3 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-stone-500">{DIALOG_EYEBROW}</p>
            <h2 className="mt-2 font-display text-2xl text-ink" id="work-import-title">
              {DIALOG_TITLE}
            </h2>
          </div>
          <button
            className="rounded-full border border-stone-300 px-3 py-1 text-sm"
            onClick={onClose}
            type="button"
            data-testid="work-import-close"
          >
            {CANCEL_LABEL}
          </button>
        </div>
        <p className="mb-4 text-sm text-stone-600">{DIALOG_LEAD}</p>

        <div className="grid min-h-0 flex-1 gap-6 overflow-y-auto pr-1">
          <SourceAndDestination
            state={state}
            onChange={patch}
            onBrowse={() => void handleBrowse()}
            browsing={browsing}
          />

          {/*
           * FR-005 — when NO agent is usable the guidance takes the picker's
           * place and no start action is rendered at all. When some are usable
           * the user proceeds with one of those; the rest are reported inside
           * `AgentSetup` without blocking.
           */}
          {probing ? (
            <div className="grid gap-2">
              <p className="text-xs italic text-stone-500" data-testid="work-import-probing">
                {AVAILABILITY_PROBING}
              </p>
              <AgentSetup
                availability={availability}
                probing
                provider={state.provider}
                permissionMode={state.permissionMode}
                onProviderChange={(provider) => patch({ provider })}
                onPermissionModeChange={(permissionMode) => patch({ permissionMode })}
              />
            </div>
          ) : agentUsable ? (
            <AgentSetup
              availability={availability}
              probing={false}
              provider={state.provider}
              permissionMode={state.permissionMode}
              onProviderChange={(provider) => patch({ provider })}
              onPermissionModeChange={(permissionMode) => patch({ permissionMode })}
            />
          ) : (
            <AvailabilityGuidance
              availability={availability}
              probeError={probeError}
              onRetry={retry}
              retrying={retrying}
            />
          )}

          <DataKindsQuestion
            selected={state.dataKinds}
            other={state.dataKindsOther}
            onToggle={toggleDataKind}
            onOtherChange={(dataKindsOther) => patch({ dataKindsOther })}
          />

          <FreeTextQuestion
            id="q2"
            label={Q2_LABEL}
            help={q2Required ? Q2_HELP_NO_CODEBASE : Q2_HELP_WITH_SOURCE}
            placeholder={q2Required ? Q2_PLACEHOLDER_NO_CODEBASE : Q2_PLACEHOLDER_WITH_SOURCE}
            value={state.workflowDescription}
            required={q2Required}
            onChange={(workflowDescription) => patch({ workflowDescription })}
          />

          <FreeTextQuestion
            id="q3"
            label={Q3_LABEL}
            help={Q3_HELP}
            placeholder={Q3_PLACEHOLDER}
            value={state.interactionWishes}
            onChange={(interactionWishes) => patch({ interactionWishes })}
          />

          <FreeTextQuestion
            id="q4"
            label={Q4_LABEL}
            help={Q4_HELP}
            placeholder={Q4_PLACEHOLDER}
            value={state.otherSoftware}
            onChange={(otherSoftware) => patch({ otherSoftware })}
          />
        </div>

        {/*
         * FR-038 — the caveat sits between the last question and the start
         * action, always expanded and never dismissible, so it is not possible
         * to reach the start action without having seen it.
         */}
        <div className="mt-4 grid gap-3 border-t border-stone-200 pt-4">
          <CorrectnessCaveat />

          {error ? (
            <p className="text-sm text-red-600" data-testid="work-import-error">
              {error}
            </p>
          ) : null}

          {agentUsable && reasons.length > 0 ? (
            <ul
              className="list-disc pl-5 text-xs text-stone-500"
              data-testid="work-import-blocking-reasons"
            >
              {reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-stone-500">{agentUsable ? START_HELP : ""}</p>
            {agentUsable ? (
              <button
                type="button"
                className="shrink-0 rounded-full bg-ink px-4 py-2 text-sm font-medium text-stone-50 hover:bg-pine disabled:opacity-50"
                data-testid="work-import-start"
                disabled={!startable}
                onClick={() => void handleStart()}
              >
                {starting ? STARTING_LABEL : START_LABEL}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
