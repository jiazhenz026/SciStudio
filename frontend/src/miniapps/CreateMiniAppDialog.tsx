/**
 * ADR-054 Phase D (#2354) - New MiniApp (FR-023, FR-024, FR-025).
 *
 * ONE dialog, three ways in: the MiniApps tab, the toolbar New menu, and a
 * block's context menu on the canvas. They differ only in whether the data is
 * already decided - `presetTarget` - and that is the whole reason the dialog is
 * one component rather than three. A user who right-clicked a block has already
 * said which output they mean; a user who pressed New from the toolbar has not.
 * Everything after that question is identical, and a second implementation of
 * "what do you want to see or do, and which agent writes it" would drift from
 * this one the first time either half changed.
 *
 * It asks for exactly two things and offers two more:
 *
 *   the data    - a block output in the open project (FR-023).
 *   the request - what the user wants to see or do, in their own words. It
 *                 becomes the MiniApp's `description` and the agent's brief
 *                 (FR-024), so it is prose, not a name.
 *   the agent   - provider and permission mode, AS "Bring in my work" DOES.
 *                 Not "like": the same two components, through the same
 *                 availability payload and the same helpers. See below.
 *
 * WHY THE AGENT CONTROLS ARE IMPORTED RATHER THAN REWRITTEN. FR-023 says the
 * dialog offers the provider and permission mode as "Bring in my work" does,
 * and ADR-053 FR-042 already settled what that means for the work-import
 * dialog: provider selection and permission semantics belong to ADR-034, and a
 * second copy drifts the moment a provider joins the registry. This dialog is
 * the third surface to start an agent session, so it consumes the same
 * `useAgentAvailability` probe, the same `isUsable` / `resolveSelectedProvider`
 * rules, and the same `AgentSetup` / `AvailabilityGuidance` pair. Nothing about
 * agents is decided in this file.
 *
 * WHY THE PROBE RUNS ON OPEN. FR-024 makes the ORDER normative on the backend:
 * `POST /api/panels/miniapps` probes availability first and creates nothing
 * when the chosen provider cannot start a session. A first graded probe is a
 * live call per provider and can take seconds, so the dialog fetches it when it
 * opens - while the user is still typing - and the submit does not wait on it.
 * The backend still probes; this is not a substitute for the server's check,
 * which is why a 409 `agent_unavailable` is rendered here verbatim rather than
 * being treated as impossible.
 */
import { X } from "lucide-react";
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
import type { MiniAppTarget } from "./types";

/** The ceiling `POST /api/panels/miniapps` puts on `request`. */
export const REQUEST_MAX_LENGTH = 4000;

export const CREATE_TITLE = "New MiniApp";
export const CREATE_EYEBROW = "MiniApp";
export const REQUEST_LABEL = "Instructions";
export const REQUEST_HELP = "Describe what to display and which controls you need.";
export const REQUEST_PLACEHOLDER =
  "Show the image with a threshold slider. Update the mask as I adjust the threshold.";
export const DATA_LABEL = "Data source";
export const DATA_HELP = "Select an output from a completed block.";
export const NO_OUTPUTS =
  "No block in the project has produced an output yet. Run a block first, then come back.";
export const NO_PROJECT = "Open a project first.";
export const PROBING = "Checking which agents can run this...";

/** One choosable block output of the open workflow. */
export interface OutputChoice {
  target: MiniAppTarget;
  /** `<block> - <port>`, with the declared type when the schema names one. */
  label: string;
}

const EMPTY_OUTPUT_CHOICES: OutputChoice[] = [];

function targetKey(target: MiniAppTarget): string {
  return `${target.workflow_id} ${target.block_id} ${target.port}`;
}

export interface CreateMiniAppResult {
  panel_id: string;
  name: string;
  target: MiniAppTarget;
  session_tab_id: string | null;
}

export interface CreateMiniAppDialogProps {
  open: boolean;
  onOpenChange(open: boolean): void;
  /** Pre-filled when the dialog was opened from a block's context menu (FR-023). */
  presetTarget?: MiniAppTarget | null;
  onCreated(result: CreateMiniAppResult): void;
  /** Test seam for the graded availability probe; production uses the shared client. */
  fetchAvailability?: AvailabilityFetcher;
  /** Test seam for `POST /api/panels/miniapps`. */
  create?: typeof miniAppsApi.create;
}

/**
 * Mounted only while `open`, so the availability probe fires when the dialog
 * opens rather than when its parent mounts (FR-024). A parent that keeps this
 * component mounted with `open: false` - which every call site does, because
 * that is how the pinned props read - would otherwise probe on workspace load
 * and serve a stale report to a dialog opened ten minutes later.
 */
export function CreateMiniAppDialog(props: CreateMiniAppDialogProps) {
  const projectPath = useAppStore((s) => s.currentProject?.path ?? "");
  if (!props.open) return null;
  return <CreateMiniAppDialogBody key={projectPath} {...props} />;
}

function CreateMiniAppDialogBody({
  onOpenChange,
  presetTarget,
  onCreated,
  fetchAvailability,
  create = miniAppsApi.create,
}: CreateMiniAppDialogProps) {
  const projectOpen = useAppStore((s) => s.currentProject !== null);
  const [projectChoices, setProjectChoices] = useState<OutputChoice[] | null>(null);
  const [sourceError, setSourceError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    miniAppsApi
      .projectSources()
      .then((sources) => {
        if (!cancelled)
          setProjectChoices(
            sources.map((source) => ({
              target: {
                workflow_id: source.workflow_id,
                block_id: source.block_id,
                port: source.port,
              },
              label: `${source.workflow_name} / ${source.block_name}${source.block_name !== source.block_id ? ` [${source.block_id}]` : ""} - ${source.port} (${source.type})`,
            })),
          );
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setSourceError(err instanceof Error ? err.message : String(err));
          setProjectChoices([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const options = projectChoices ?? EMPTY_OUTPUT_CHOICES;

  const [selectedKey, setSelectedKey] = useState<string>(() =>
    presetTarget ? targetKey(presetTarget) : options[0] ? targetKey(options[0].target) : "",
  );
  useEffect(() => {
    if (projectChoices === null) return;
    if (!options.some((option) => targetKey(option.target) === selectedKey)) {
      setSelectedKey(options[0] ? targetKey(options[0].target) : "");
    }
  }, [options, projectChoices, selectedKey]);
  const [request, setRequest] = useState("");
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

  // FR-043's rule, reused: one usable provider is selected, not offered.
  useEffect(() => {
    setProvider((prev) => resolveSelectedProvider(availability, prev));
  }, [availability]);

  const target = options.find((c) => targetKey(c.target) === selectedKey)?.target ?? null;
  const trimmed = request.trim();
  const submittable =
    projectOpen && target !== null && trimmed.length > 0 && !submitting && !probing && agentUsable;

  const close = useCallback(() => onOpenChange(false), [onOpenChange]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [close]);

  const submit = useCallback(async () => {
    if (!target || !trimmed) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await create({
        request: trimmed.slice(0, REQUEST_MAX_LENGTH),
        source: target,
        provider,
        permission_mode: toBackendPermissionMode(permissionMode),
      });
      useAppStore.getState().bumpBlockCatalogRefresh();
      // FR-025 - the caller opens the tab and shows the session NOW, before the
      // agent has written anything. The dialog then closes as the session opens.
      const sessionProvider = response.provider ?? provider;
      if (response.session_tab_id && sessionProvider) {
        useAppStore.getState().addWorkImportTerminalTab({
          tabId: response.session_tab_id,
          title: "Create MiniApp",
          provider: sessionProvider,
          permissionMode: fromBackendPermissionMode(
            response.permission_mode ?? toBackendPermissionMode(permissionMode),
          ),
        });
        useAppStore.getState().openBottomTab("ai");
      }
      onCreated({
        panel_id: response.panel_id,
        name: response.name,
        target: response.source,
        session_tab_id: response.session_tab_id,
      });
      onOpenChange(false);
    } catch (err) {
      /*
       * FR-024 / US1 acceptance 4 - when the route refuses with
       * `agent_unavailable` it carries the GRADED REASON, and that sentence is
       * the only thing that tells the user what to fix. `ApiError` keeps the
       * panels envelope's `message` and drops its `code`, so what is shown is
       * that message verbatim rather than a generic failure line of our own.
       */
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }, [create, onCreated, onOpenChange, permissionMode, provider, target, trimmed]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4">
      <div
        aria-modal="true"
        role="dialog"
        aria-labelledby="miniapp-create-title"
        data-testid="miniapp-create-dialog"
        className="flex max-h-[88vh] w-full max-w-2xl flex-col rounded-xl border border-stone-200 bg-stone-50 p-6 shadow-panel"
      >
        <div className="mb-3 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-stone-500">{CREATE_EYEBROW}</p>
            <h2 className="mt-2 font-display text-2xl text-ink" id="miniapp-create-title">
              {CREATE_TITLE}
            </h2>
          </div>
          <button
            aria-label="Close"
            title="Close"
            className="inline-flex size-8 shrink-0 items-center justify-center rounded-full text-stone-500 hover:bg-stone-100 hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-stone-500"
            onClick={close}
            type="button"
            data-testid="miniapp-create-close"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 content-start gap-5 overflow-y-auto pr-1">
          <div className="grid gap-1.5">
            <label className="text-sm font-medium text-ink" htmlFor="miniapp-create-target">
              {DATA_LABEL}
            </label>
            <p className="text-xs text-stone-500">{DATA_HELP}</p>
            {!projectOpen ? (
              <p className="text-sm text-stone-600" data-testid="miniapp-create-no-project">
                {NO_PROJECT}
              </p>
            ) : projectChoices === null ? (
              <p className="text-sm text-stone-600">Looking for project data...</p>
            ) : sourceError ? (
              <p className="text-sm text-red-700" role="alert">
                {sourceError}
              </p>
            ) : options.length === 0 ? (
              <p className="text-sm text-stone-600" data-testid="miniapp-create-no-outputs">
                {NO_OUTPUTS}
              </p>
            ) : (
              <select
                className="rounded-2xl border border-stone-300 bg-white px-3 py-2 text-sm text-ink"
                data-testid="miniapp-create-target"
                id="miniapp-create-target"
                onChange={(event) => setSelectedKey(event.target.value)}
                value={selectedKey}
              >
                {options.map((choice) => (
                  <option key={targetKey(choice.target)} value={targetKey(choice.target)}>
                    {choice.label}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="grid gap-1.5">
            <label className="text-sm font-medium text-ink" htmlFor="miniapp-create-request">
              {REQUEST_LABEL}
            </label>
            <p className="text-xs text-stone-500">{REQUEST_HELP}</p>
            <textarea
              className="min-h-[6rem] rounded-2xl border border-stone-300 bg-white px-3 py-2 text-sm text-ink"
              data-testid="miniapp-create-request"
              id="miniapp-create-request"
              maxLength={REQUEST_MAX_LENGTH}
              onChange={(event) => setRequest(event.target.value)}
              placeholder={REQUEST_PLACEHOLDER}
              value={request}
            />
          </div>

          {/* FR-023 - the agent half, exactly as "Bring in my work" offers it. */}
          {probing ? (
            <div className="grid gap-2">
              <p className="text-xs italic text-stone-500" data-testid="miniapp-create-probing">
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
              data-testid="miniapp-create-error"
              role="alert"
              aria-live="assertive"
            >
              {error}
            </div>
          ) : null}
          <div className="flex justify-end">
            <button
              className="rounded-full bg-ink px-4 py-2 text-sm text-white disabled:opacity-40"
              data-testid="miniapp-create-submit"
              disabled={!submittable}
              onClick={() => void submit()}
              type="button"
            >
              {submitting ? "Creating..." : "Create MiniApp"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
