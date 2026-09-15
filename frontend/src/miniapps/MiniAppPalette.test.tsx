// The MiniApps tab (ADR-054 FR-031/FR-032/FR-039) — User Story 5, scenarios 1
// and 2.
//
// Scenario 3 ("All Previewers replaces the preview inside the column") is a
// property of the preview column rather than of this pane, and is tested where
// it lives: `components/__tests__/DataPreviewAllPreviewers.test.tsx`.

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetDialogChannel, showPromotionResult } from "../components/promotion/dialogChannel";
import type { PromotableItem } from "../components/promotion/promotable";
import type { PromotionOutcome } from "../components/promotion/promoteToUserLibrary";

import { blocksApi } from "../lib/api/blocks";
import { useAppStore } from "../store";
import { resetAppStore } from "../testUtils";
import { useMiniAppCatalog } from "./useMiniAppCatalog";

import { MiniAppPalette } from "./MiniAppPalette";
import type { MiniAppSummary } from "./types";

const list = vi.fn();
vi.mock("./api", () => ({
  miniAppsApi: {
    list: () => list(),
    sources: vi.fn(),
    create: vi.fn(),
    convert: vi.fn(),
    promote: vi.fn(),
  },
}));

const runPromotion = vi.fn();
vi.mock("../components/promotion/runPromotion", () => ({
  runPromotion: (item: PromotableItem) => runPromotion(item),
}));

function makeMiniApp(overrides: Partial<MiniAppSummary> = {}): MiniAppSummary {
  return {
    panel_id: "threshold-explorer",
    name: "Threshold explorer",
    description: "Sweep the threshold and watch the mask.",
    type: "Image",
    tier: "project",
    directory: "/projects/demo/panels/threshold-explorer",
    has_python: true,
    ...overrides,
  };
}

const projectApp = makeMiniApp();
const userApp = makeMiniApp({
  panel_id: "spectra-compare",
  name: "Spectra compare",
  description: "Overlay two spectra.",
  type: "Spectrum",
  tier: "user",
  directory: "/home/me/.scistudio/panels/spectra-compare",
});
const packageApp = makeMiniApp({
  panel_id: "peak-picker",
  name: "Peak picker",
  type: "Chromatogram",
  tier: "package",
  directory: "/site-packages/scistudio_blocks_lcms/panels/peak-picker",
});

function outcome(item: PromotableItem): PromotionOutcome {
  return {
    status: "promoted",
    item,
    promoted: {
      kind: "miniapp",
      label: item.label,
      filename: "threshold-explorer",
      path: "/home/me/.scistudio/panels/threshold-explorer",
      overwritten: false,
      movedFrom: "panels/threshold-explorer",
      moveError: null,
    },
    promotedDependencies: [],
    declinedDependencies: [],
    secondLevel: [],
    warnings: [],
  };
}

async function renderPalette(miniapps: MiniAppSummary[], onOpen = vi.fn(), onCreate = vi.fn()) {
  list.mockResolvedValue(miniapps);
  render(<MiniAppPalette onCreate={onCreate} onOpen={onOpen} />);
  await screen.findByTestId("miniapp-palette-content");
  await waitFor(() => expect(list).toHaveBeenCalled());
  return { onOpen, onCreate };
}

function card(panelId: string): HTMLElement {
  return screen.getByTestId(`miniapp-card-${panelId}`);
}

beforeEach(() => {
  resetAppStore();
  resetDialogChannel();
  list.mockResolvedValue([]);
  runPromotion.mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe("MiniApps tab — the listing (FR-031)", () => {
  it("groups MiniApps by tier, the way the Previewers tab grouped previewers", async () => {
    await renderPalette([packageApp, userApp, projectApp]);

    expect(
      within(await screen.findByTestId("miniapp-section-__this_project__")).getByTestId(
        "miniapp-card-threshold-explorer",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("miniapp-section-__user_library__")).getByTestId(
        "miniapp-card-spectra-compare",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("miniapp-section-Packages")).getByTestId(
        "miniapp-card-peak-picker",
      ),
    ).toBeInTheDocument();
  });

  it("shows the name and the declared type on the card", async () => {
    await renderPalette([projectApp]);
    const tile = await screen.findByTestId("miniapp-card-threshold-explorer");
    expect(tile).toHaveTextContent("Threshold explorer");
    expect(tile).toHaveTextContent("Image");
  });

  it("narrows the list through the search box", async () => {
    await renderPalette([projectApp, userApp]);
    await screen.findByTestId("miniapp-card-threshold-explorer");

    fireEvent.change(screen.getByPlaceholderText("Search MiniApps"), {
      target: { value: "spectra" },
    });

    expect(screen.queryByTestId("miniapp-card-threshold-explorer")).toBeNull();
    expect(screen.getByTestId("miniapp-card-spectra-compare")).toBeInTheDocument();
  });

  it("hands New MiniApp to the workspace, which owns the dialog", async () => {
    const { onCreate } = await renderPalette([]);
    expect(screen.getByTestId("miniapp-new").textContent).toBe("New");
    fireEvent.click(screen.getByTestId("miniapp-new"));
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  it("opens the MiniApp on a single click (the target picker is the workspace's)", async () => {
    const { onOpen } = await renderPalette([projectApp]);
    fireEvent.click(await screen.findByTestId("miniapp-card-threshold-explorer"));
    expect(onOpen).toHaveBeenCalledWith(projectApp);
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});

describe("MiniApps tab — US5 scenario 1: the hover popover (FR-032)", () => {
  it("shows the description, the declared type, the tier and the directory", async () => {
    await renderPalette([projectApp]);
    fireEvent.mouseEnter(card("threshold-explorer"));

    const popover = await screen.findByTestId("miniapp-detail-popover");
    expect(popover).toHaveTextContent("Sweep the threshold and watch the mask.");
    expect(popover).toHaveTextContent("Image");
    expect(popover).toHaveTextContent("This Project");
    expect(popover).toHaveTextContent("/projects/demo/panels/threshold-explorer");
  });

  it("offers Promote to My Library for a project MiniApp", async () => {
    await renderPalette([projectApp]);
    fireEvent.mouseEnter(card("threshold-explorer"));

    const popover = await screen.findByTestId("miniapp-detail-popover");
    expect(within(popover).getByTestId("promote-to-library-action")).toBeInTheDocument();
  });

  it.each([
    ["user", userApp],
    ["package", packageApp],
  ] as const)("hides Promote to My Library for a %s MiniApp", async (_tier, miniapp) => {
    await renderPalette([miniapp]);
    fireEvent.mouseEnter(card(miniapp.panel_id));

    const popover = await screen.findByTestId("miniapp-detail-popover");
    expect(within(popover).queryByTestId("promote-to-library-action")).toBeNull();
  });
});

describe("MiniApps tab — US5 scenario 2: promotion (FR-039)", () => {
  it("promotes the panel directory through the one shared promotion action", async () => {
    await renderPalette([projectApp]);
    fireEvent.mouseEnter(card("threshold-explorer"));
    const popover = await screen.findByTestId("miniapp-detail-popover");

    fireEvent.click(within(popover).getByTestId("promote-to-library-action"));

    await waitFor(() => expect(runPromotion).toHaveBeenCalledTimes(1));
    // The entry point's whole job: resolve what the user pointed at into one
    // `PromotableItem`. Everything else — the collision prompt, the move, the
    // confirmation — is the shared implementation's (ADR-053 FR-025).
    expect(runPromotion).toHaveBeenCalledWith({
      target: "panels",
      kind: "miniapp",
      label: "Threshold explorer",
      origin: "project",
      source: { from: "panelDirectory", panelId: "threshold-explorer" },
    });
  });

  it("still lists the MiniApp once it has moved, now under My Library", async () => {
    await renderPalette([projectApp]);
    await screen.findByTestId("miniapp-card-threshold-explorer");

    // The promotion landed: the backend moved the directory, so the next
    // listing reports the same MiniApp at the user tier.
    const promotedApp = makeMiniApp({
      tier: "user",
      directory: "/home/me/.scistudio/panels/threshold-explorer",
    });
    list.mockResolvedValue([promotedApp]);
    showPromotionResult(
      outcome({
        target: "panels",
        kind: "miniapp",
        label: "Threshold explorer",
        origin: "project",
        source: { from: "panelDirectory", panelId: "threshold-explorer" },
      }),
    );

    await waitFor(() =>
      expect(
        within(screen.getByTestId("miniapp-section-__user_library__")).getByTestId(
          "miniapp-card-threshold-explorer",
        ),
      ).toBeInTheDocument(),
    );
    expect(
      within(screen.getByTestId("miniapp-section-__this_project__")).queryByTestId(
        "miniapp-card-threshold-explorer",
      ),
    ).toBeNull();
  });
});

describe("MiniApp registry refresh", () => {
  function CompatibleActions() {
    const { miniapps } = useMiniAppCatalog();
    return <div data-testid="compatible-apps">{miniapps.map((app) => app.name).join(", ")}</div>;
  }

  it("Reload rescans the backend and refreshes both the sidebar and compatible actions", async () => {
    let completeScan!: () => void;
    const scan = vi.spyOn(blocksApi, "reloadBlocks").mockImplementation(
      () =>
        new Promise((resolve) => {
          completeScan = () => resolve({ reloaded: 1, added: [], removed: [] });
        }),
    );
    await renderPalette([projectApp]);
    render(<CompatibleActions />);
    await waitFor(() =>
      expect(screen.getByTestId("compatible-apps")).toHaveTextContent(projectApp.name),
    );
    const reads = list.mock.calls.length;
    list.mockResolvedValue([userApp]);
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    expect(scan).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Reload" })).toBeDisabled();
    // #2415 — the shared reload icon spins while the rescan is in flight.
    expect(
      within(screen.getByRole("button", { name: "Reload" })).getByTestId("section-reload-icon"),
    ).toHaveClass("animate-spin");
    expect(list).toHaveBeenCalledTimes(reads);
    await act(async () => completeScan());
    await screen.findByTestId(`miniapp-card-${userApp.panel_id}`);
    await waitFor(() =>
      expect(screen.getByTestId("compatible-apps")).toHaveTextContent(userApp.name),
    );
    expect(screen.queryByTestId(`miniapp-card-${projectApp.panel_id}`)).toBeNull();
  });

  it("updates compatible actions on registry invalidation without a project switch", async () => {
    await renderPalette([]);
    render(<CompatibleActions />);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    list.mockResolvedValue([projectApp]);
    act(() => useAppStore.getState().bumpBlockCatalogRefresh());
    await screen.findByTestId(`miniapp-card-${projectApp.panel_id}`);
    await waitFor(() =>
      expect(screen.getByTestId("compatible-apps")).toHaveTextContent(projectApp.name),
    );
  });

  it("keeps the listing and reports a failed rescan", async () => {
    vi.spyOn(blocksApi, "reloadBlocks").mockRejectedValue(new Error("Registry reload failed"));
    await renderPalette([projectApp]);
    await screen.findByTestId(`miniapp-card-${projectApp.panel_id}`);
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Registry reload failed");
    expect(card(projectApp.panel_id)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeEnabled();
  });

  it("ignores an old project's delayed listing after switching projects", async () => {
    let resolveOld!: (items: MiniAppSummary[]) => void;
    list.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    );
    render(<MiniAppPalette onCreate={vi.fn()} onOpen={vi.fn()} />);
    list.mockResolvedValue([userApp]);
    act(() =>
      useAppStore.setState({
        currentProject: { id: "new-project", path: "/projects/new" } as NonNullable<
          ReturnType<typeof useAppStore.getState>["currentProject"]
        >,
      }),
    );
    await screen.findByTestId(`miniapp-card-${userApp.panel_id}`);
    await act(async () => resolveOld([projectApp]));
    expect(screen.queryByTestId(`miniapp-card-${projectApp.panel_id}`)).toBeNull();
    expect(card(userApp.panel_id)).toBeInTheDocument();
  });
});
