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
import { useCallback, useEffect, useMemo, useState } from "react";

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
export const REQUEST_LABEL = "What do you want to see or do?";
export const REQUEST_HELP =
  "Describe it the way you would to a colleague. The agent writes the MiniApp from this, and it stays on the MiniApp as its description.";
export const REQUEST_PLACEHOLDER =
  "Let me drag a threshold across the stack and see the mask update.";
export const DATA_LABEL = "Which data?";
export const DATA_HELP =
  "An output of a block that has run. The MiniApp opens on it, and takes its type from it.";
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

/**
 * The outputs the user may choose from.
 *
 * `blockOutputs` is the canvas's own record of what the latest run produced,
 * keyed by node id and then by output port - the same source the preview column
 * and the canvas context menu read. A port is offered because data exists at
 * it, never because a schema declares it: a block that has not run has nothing
 * to open a MiniApp on.
 *
 * Cached outputs seed the picker while the project-wide source list loads.
 */
export function outputChoices(
  workflowId: string | null,
  nodes: { id: string; block_type: string }[],
  blockOutputs: Record<string, Record<string, unknown>>,
  labelOf: (nodeId: string) => string,
  typeOf: (nodeId: string, port: string) => string | null,
): OutputChoice[] {
  if (!workflowId) return [];
  const choices: OutputChoice[] = [];
  for (const node of nodes) {
    const outputs = blockOutputs[node.id];
    if (!outputs) continue;
    for (const port of Object.keys(outputs)) {
      const declared = typeOf(node.id, port);
      choices.push({
        target: { workflow_id: workflowId, block_id: node.id, port },
        label: `${labelOf(node.id)} - ${port}${declared ? ` (${declared})` : ""}`,
      });
    }
  }
  return choices;
}

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
  if (!props.open) return null;
  return <CreateMiniAppDialogBody {...props} />;
}

function CreateMiniAppDialogBody({
  onOpenChange,
  presetTarget,
  onCreated,
  fetchAvailability,
  create = miniAppsApi.create,
}: CreateMiniAppDialogProps) {
  const projectOpen = useAppStore((s) => s.currentProject !== null);
  const workflowId = useAppStore((s) => s.workflowId);
  const nodes = useAppStore((s) => s.workflowNodes);
  const blockOutputs = useAppStore((s) => s.blockOutputs);
  const blocks = useAppStore((s) => s.blocks);
  const schemas = useAppStore((s) => s.blockSchemas);

  const cachedChoices = useMemo(() => {
    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    const labelOf = (nodeId: string) => {
      const node = nodeById.get(nodeId);
      if (!node) return nodeId;
      const summary = blocks.find((b) => b.type_name === node.block_type);
      return summary?.name ?? schemas[node.block_type]?.name ?? node.block_type;
    };
    const typeOf = (nodeId: string, port: string) => {
      const node = nodeById.get(nodeId);
      const schema = node ? schemas[node.block_type] : undefined;
      const spec = schema?.output_ports?.find((p) => p.name === port);
      return spec?.accepted_types?.[0] ?? null;
    };
    return outputChoices(workflowId, nodes, blockOutputs, labelOf, typeOf);
  }, [blockOutputs, blocks, nodes, schemas, workflowId]);

  const [projectChoices, setProjectChoices] = useState<OutputChoice[] | null>(null);
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
              label: `${source.workflow_name} / ${source.block_name} - ${source.port} (${source.type})`,
            })),
          );
      })
      .catch(() => {
        /* Keep the known canvas outputs available if discovery fails. */
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const choices = projectChoices ?? cachedChoices;

  /*
   * The preset is offered even when it is not in `choices` - it came from a
   * block the user just right-clicked, and a dialog that silently dropped it
   * would send the user hunting for the row they had already chosen.
   */
  const options = useMemo(() => {
    if (!presetTarget) return choices;
    if (choices.some((c) => targetKey(c.target) === targetKey(presetTarget))) return choices;
    return [
      { target: presetTarget, label: `${presetTarget.block_id} - ${presetTarget.port}` },
      ...choices,
    ];
  }, [choices, presetTarget]);

  const [selectedKey, setSelectedKey] = useState<string>(() =>
    presetTarget ? targetKey(presetTarget) : options[0] ? targetKey(options[0].target) : "",
  );
  useEffect(() => {
    if (!selectedKey && options[0]) setSelectedKey(targetKey(options[0].target));
  }, [options, selectedKey]);
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
            className="rounded-full border border-stone-300 px-3 py-1 text-sm"
            onClick={close}
            type="button"
            data-testid="miniapp-create-close"
          >
            Cancel
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
