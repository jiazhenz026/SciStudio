/**
 * ADR-054 Phase D (#2354) — the New MiniApp dialog (FR-023, FR-024, FR-025).
 *
 * US1 acceptance 1 and 4 live here: a dialog reached from a block's context
 * menu opens with that block's output pre-filled, and a route that refuses
 * because the chosen agent cannot start shows the backend's reason verbatim.
 *
 * The create route is supplied through the component's own seam: it does not
 * exist in the frozen OpenAPI snapshot. The agent controls are AI Chat's own
 * (#2454), so `GET /api/ai/status` is faked with the shared fixture, which also
 * fails any request to the removed `/api/ai/availability` endpoint.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CODEX_STATUS,
  mockAgentStatus,
  providerStatus,
  type AgentStatusMock,
} from "../components/AIChat/__tests__/agentStatusFixture";
import { ApiError } from "../lib/api/core";
import { useAppStore } from "../store";
import { resetAppStore } from "../testUtils";
import type { BlockSchemaResponse, WorkflowNode } from "../types/api";

import { CreateMiniAppDialog, type CreateMiniAppResult } from "./CreateMiniAppDialog";
import { miniAppsApi } from "./api";
import type { MiniAppSource, MiniAppTarget } from "./types";

function schema(name: string, ports: { name: string; types: string[] }[]): BlockSchemaResponse {
  return {
    name,
    type_name: name,
    base_category: "process",
    subcategory: "",
    description: "",
    version: "1.0",
    input_ports: [],
    output_ports: ports.map((p) => ({
      name: p.name,
      direction: "output",
      accepted_types: p.types,
      required: true,
      description: "",
      constraint_description: "",
      is_collection: false,
    })),
    config_schema: { type: "object", properties: {} },
    type_hierarchy: [],
    dynamic_ports: null,
    direction: null,
  };
}

const NODES: WorkflowNode[] = [
  { id: "segment1", block_type: "segment", config: { params: {} } },
  { id: "table1", block_type: "tabulate", config: { params: {} } },
];

const PRESET: MiniAppTarget = { workflow_id: "main", block_id: "segment1", port: "mask" };

function created(overrides: Partial<CreateMiniAppResult> = {}) {
  return {
    panel_id: "miniapp_1",
    name: "Threshold explorer",
    source: PRESET,
    session_tab_id: "tab-1",
    directory: "/p/panels/miniapp_1",
    ...overrides,
  };
}

interface Harness {
  create: ReturnType<typeof vi.fn>;
  onCreated: ReturnType<typeof vi.fn>;
  onOpenChange: ReturnType<typeof vi.fn>;
  status: AgentStatusMock;
}

function renderDialog(
  options: {
    presetTarget?: MiniAppTarget | null;
    create?: Harness["create"];
    providers?: Parameters<typeof mockAgentStatus>[0];
  } = {},
): Harness {
  const status = mockAgentStatus(options.providers);
  const create = options.create ?? vi.fn(async () => created());
  const onCreated = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <CreateMiniAppDialog
      create={create as never}
      onCreated={onCreated}
      onOpenChange={onOpenChange}
      open
      presetTarget={options.presetTarget ?? null}
    />,
  );
  return { create, onCreated, onOpenChange, status };
}

/** Wait for `/api/ai/status` to arrive, so the provider options exist. */
async function settled(provider = "claude-code"): Promise<void> {
  await screen.findByTestId(`setup-provider-option-${provider}`);
  await waitFor(() => expect(screen.getByTestId("setup-provider-select")).not.toBeDisabled());
}

/** Choose a provider and a permission mode through the UI, as AI Chat asks for. */
async function chooseAgent(provider = "claude-code"): Promise<void> {
  await settled(provider);
  fireEvent.change(screen.getByTestId("setup-provider-select"), {
    target: { value: provider },
  });
  fireEvent.click(screen.getByTestId("setup-permission-safe"));
}

const SOURCES: MiniAppSource[] = [
  { ...PRESET, workflow_name: "Main", block_name: "Segment", type: "Mask" },
  {
    workflow_id: "main",
    workflow_name: "Main",
    block_id: "table1",
    block_name: "Table",
    port: "table",
    type: "DataFrame",
  },
];

beforeEach(() => {
  vi.spyOn(miniAppsApi, "projectSources").mockResolvedValue(SOURCES);
  resetAppStore();
  useAppStore.setState({
    currentProject: {
      id: "p1",
      name: "Demo",
      description: "",
      path: "/projects/demo",
      created_at: "",
      updated_at: "",
    } as never,
    workflowId: "main",
    workflowNodes: NODES,
    blockOutputs: {
      segment1: { mask: { data_ref: "ref-mask" } },
      table1: { table: { data_ref: "ref-table" } },
    },
    blockSchemas: {
      segment: schema("segment", [{ name: "mask", types: ["Mask"] }]),
      tabulate: schema("tabulate", [{ name: "table", types: ["DataFrame"] }]),
    },
    typesLoaded: true,
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CreateMiniAppDialog (ADR-054 FR-023 / FR-024 / FR-025)", () => {
  it("closes from the icon-only header button without submitting", async () => {
    const harness = renderDialog({ presetTarget: PRESET });
    await settled();

    const close = screen.getByRole("button", { name: "Close" });
    expect(close.textContent).toBe("");
    fireEvent.click(close);

    expect(harness.onOpenChange).toHaveBeenCalledWith(false);
    expect(harness.create).not.toHaveBeenCalled();
  });

  it("opens pre-filled with the block output it was given", async () => {
    // US1 acceptance 1 — the context-menu route.
    const harness = renderDialog({ presetTarget: PRESET });
    await settled();

    expect(screen.getByLabelText("Data source")).toBeTruthy();
    expect(screen.getByLabelText("Instructions")).toHaveAttribute(
      "placeholder",
      "Show the image with a threshold slider. Update the mask as I adjust the threshold.",
    );
    const select = screen.getByTestId("miniapp-create-target") as HTMLSelectElement;
    expect(select.value).toBe("main segment1 mask");

    fireEvent.change(screen.getByTestId("miniapp-create-request"), {
      target: { value: "Let me drag a threshold across the stack." },
    });
    await chooseAgent();
    fireEvent.click(screen.getByTestId("miniapp-create-submit"));

    await waitFor(() => expect(harness.create).toHaveBeenCalledTimes(1));
    expect(harness.create.mock.calls[0][0]).toMatchObject({
      request: "Let me drag a threshold across the stack.",
      source: PRESET,
      permission_mode: "safe",
      provider: "claude-code",
    });
    expect(harness.status.availabilityCalls).toEqual([]);
  });

  it("sends the provider the user chose, not a default", async () => {
    const harness = renderDialog({ presetTarget: PRESET, providers: [CODEX_STATUS] });
    fireEvent.change(screen.getByTestId("miniapp-create-request"), {
      target: { value: "Threshold explorer please." },
    });
    await chooseAgent("codex");
    fireEvent.click(screen.getByTestId("miniapp-create-submit"));

    await waitFor(() => expect(harness.create).toHaveBeenCalledTimes(1));
    expect(harness.create.mock.calls[0][0]).toMatchObject({
      provider: "codex",
      permission_mode: "safe",
    });
  });

  it("offers the open workflow's outputs when it was opened without one", async () => {
    // The toolbar New menu and the MiniApps tab carry no data with them, so the
    // dialog has to ask (FR-023).
    renderDialog();
    await settled();
    await screen.findByTestId("miniapp-create-target");

    const options = screen
      .getAllByRole("option")
      .map((option) => (option as HTMLOptionElement).value);
    expect(options).toContain("main segment1 mask");
    expect(options).toContain("main table1 table");
  });

  it("hands the caller the panel and the target as soon as the route returns", async () => {
    // FR-025 — the tab opens before the agent has written anything, so nothing
    // in this dialog waits for the MiniApp to exist on disk.
    const harness = renderDialog({ presetTarget: PRESET });
    const previousRevision = useAppStore.getState().blockCatalogRefreshCounter;
    fireEvent.change(screen.getByTestId("miniapp-create-request"), {
      target: { value: "Threshold explorer please." },
    });
    await chooseAgent();
    fireEvent.click(screen.getByTestId("miniapp-create-submit"));

    await waitFor(() => expect(harness.onCreated).toHaveBeenCalledTimes(1));
    expect(useAppStore.getState().blockCatalogRefreshCounter).toBe(previousRevision + 1);
    expect(harness.onCreated).toHaveBeenCalledWith({
      panel_id: "miniapp_1",
      name: "Threshold explorer",
      target: PRESET,
      session_tab_id: "tab-1",
    });
    expect(harness.onOpenChange).toHaveBeenCalledWith(false);
    expect(useAppStore.getState().terminalTabs.some((tab) => tab.id === "tab-1")).toBe(true);
    expect(useAppStore.getState().activeBottomTab).toBe("ai");
  });

  it("shows the route's launch-check reason verbatim when the agent cannot start", async () => {
    // US1 acceptance 4 — nothing is created, and the user is told what is
    // wrong in the backend's own words rather than "request failed".
    const reason = "Claude Code is installed but not signed in. Run `claude login`.";
    const create = vi.fn(async () => {
      throw new ApiError(reason, 409);
    });
    const harness = renderDialog({ presetTarget: PRESET, create });
    fireEvent.change(screen.getByTestId("miniapp-create-request"), {
      target: { value: "Threshold explorer please." },
    });
    await chooseAgent();
    fireEvent.click(screen.getByTestId("miniapp-create-submit"));

    await waitFor(() =>
      expect(screen.getByTestId("miniapp-create-error")).toHaveTextContent(reason),
    );
    expect(harness.onCreated).not.toHaveBeenCalled();
    expect(harness.onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it("reads /api/ai/status when it opens, never the removed availability probe", async () => {
    const harness = renderDialog({ presetTarget: PRESET });
    await settled();
    expect(harness.status.statusCalls).toHaveLength(1);
    expect(harness.status.availabilityCalls).toEqual([]);
  });

  it("offers AI Chat's provider and permission controls", async () => {
    // FR-023 — the SAME controls, which is why these are the AI setup screen's
    // own test ids rather than ids of this dialog's own.
    renderDialog({ presetTarget: PRESET });
    await settled();

    expect(screen.getByTestId("agent-launch-setup")).toBeInTheDocument();
    expect(screen.getByTestId("setup-provider-select")).toBeInTheDocument();
    expect(screen.getByTestId("setup-permission-safe")).toBeInTheDocument();
    expect(screen.getByTestId("setup-permission-dangerous")).toBeInTheDocument();
  });

  it("refuses to submit an empty request", async () => {
    renderDialog({ presetTarget: PRESET });
    await chooseAgent();
    expect(screen.getByTestId("miniapp-create-submit")).toBeDisabled();
  });

  it("starts with no provider or permission mode chosen and waits for both", async () => {
    renderDialog({ presetTarget: PRESET });
    await settled();
    fireEvent.change(screen.getByTestId("miniapp-create-request"), {
      target: { value: "Threshold explorer please." },
    });
    const select = screen.getByTestId("setup-provider-select") as HTMLSelectElement;
    expect(select.value).toBe("");
    const submit = screen.getByTestId("miniapp-create-submit");
    expect(submit).toBeDisabled();

    fireEvent.change(select, { target: { value: "claude-code" } });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByTestId("setup-permission-safe"));
    expect(submit).not.toBeDisabled();
  });

  it("will not submit with a provider that is not installed", async () => {
    renderDialog({
      presetTarget: PRESET,
      providers: [providerStatus({ name: "claude-code", available: false })],
    });
    fireEvent.change(screen.getByTestId("miniapp-create-request"), {
      target: { value: "Threshold explorer please." },
    });
    await screen.findByTestId("setup-no-providers-notice");
    expect(screen.getByTestId("miniapp-create-submit")).toBeDisabled();
  });

  it("renders nothing while closed, so provider status is not read early", () => {
    const status = mockAgentStatus();
    render(<CreateMiniAppDialog onCreated={vi.fn()} onOpenChange={vi.fn()} open={false} />);
    expect(screen.queryByTestId("miniapp-create-dialog")).toBeNull();
    expect(status.statusCalls).toEqual([]);
    expect(status.availabilityCalls).toEqual([]);
  });
});

it("clears previous-project choices immediately and ignores a late source response", async () => {
  let resolveOld!: (sources: MiniAppSource[]) => void;
  vi.mocked(miniAppsApi.projectSources)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    )
    .mockResolvedValueOnce([]);
  const harness = renderDialog({ presetTarget: PRESET });
  await act(async () => {
    useAppStore.setState({
      currentProject: {
        ...useAppStore.getState().currentProject!,
        id: "p2",
        path: "/projects/empty",
      },
    });
  });
  await waitFor(() => expect(screen.getByTestId("miniapp-create-no-outputs")).toBeTruthy());
  await act(async () => {
    resolveOld(SOURCES);
  });
  expect(screen.queryByTestId("miniapp-create-target")).toBeNull();
  expect(screen.getByTestId("miniapp-create-submit")).toBeDisabled();
  expect(harness.create).not.toHaveBeenCalled();
});

it("does not fall back to cached canvas data when source discovery fails", async () => {
  vi.mocked(miniAppsApi.projectSources).mockRejectedValue(new Error("Cannot load project data"));
  renderDialog({ presetTarget: PRESET });
  expect(await screen.findByRole("alert")).toHaveTextContent("Cannot load project data");
  expect(screen.queryByTestId("miniapp-create-target")).toBeNull();
  expect(screen.getByTestId("miniapp-create-submit")).toBeDisabled();
});
