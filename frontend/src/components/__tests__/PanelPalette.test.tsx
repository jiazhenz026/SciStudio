// The Panels tab (#2113) — tier-grouped cards over the #2095 listing with
// the #2049 per-type choice controls, plus reload and the surfaces nothing
// else shows (registry diagnostics, stale choices).

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as DataApi from "../../lib/api/data";
import { useAppStore } from "../../store";
import { resetPanelCatalogLoader } from "../../store/usePanelCatalog";
import { resetAppStore } from "../../testUtils";
import type { PanelChoice, PanelSpecSummary } from "../../types/api";
import { PanelPalette } from "../PanelPalette";

const listPanels = vi.fn();
const listPanelChoices = vi.fn();
const reloadPanels = vi.fn();
const setPanelChoice = vi.fn();
const clearPanelChoice = vi.fn();
vi.mock("../../lib/api/data", async (importOriginal) => {
  const actual = await importOriginal<typeof DataApi>();
  return {
    ...actual,
    dataApi: {
      ...actual.dataApi,
      listPanels: (...args: unknown[]) => listPanels(...args),
      listPanelChoices: () => listPanelChoices(),
      reloadPanels: () => reloadPanels(),
      setPanelChoice: (...args: unknown[]) => setPanelChoice(...args),
      clearPanelChoice: (...args: unknown[]) => clearPanelChoice(...args),
    },
  };
});

function makePanel(overrides: Partial<PanelSpecSummary> = {}): PanelSpecSummary {
  return {
    panel_id: "core.table",
    display_name: "core.table",
    owner_kind: "core",
    owner_name: "scistudio",
    target_type: "DataObject",
    target_types: ["DataObject"],
    supports_collection: false,
    priority: 0,
    features: [],
    capability: "displaying",
    backend_provider: null,
    frontend_manifest: null,
    api_version: "1",
    tier: "core",
    shadows: null,
    ...overrides,
  };
}

const projectViewer = makePanel({
  panel_id: "project.spectrum.view",
  owner_kind: "project",
  owner_name: "demo",
  target_type: "Spectrum",
});
const userViewer = makePanel({
  panel_id: "user.spectrum.view",
  owner_kind: "user",
  owner_name: "library",
  target_type: "Spectrum",
});
const packageViewer = makePanel({
  panel_id: "pkg.image.view",
  owner_kind: "package",
  owner_name: "scistudio-blocks-imaging",
  target_type: "Image",
});
const coreViewer = makePanel();

const CATALOGUE = [projectViewer, userViewer, packageViewer, coreViewer];

function makeChoice(overrides: Partial<PanelChoice> = {}): PanelChoice {
  return {
    target_type: "Spectrum",
    panel_id: "user.spectrum.view",
    capability: "displaying",
    scope: "user",
    available: true,
    ...overrides,
  };
}

/** Render the tab with the listing and choices already in the store. Setting
 *  the store BEFORE render matters: the pane's mount effect otherwise starts
 *  a catalogue fetch whose resolution would overwrite the fixture state.
 *
 *  A preloaded store also means the #2151 mount auto-rescan fires (a revisit
 *  over a cached catalogue), so the listing mock answers with the same
 *  fixture and the helper waits for that rescan to settle before returning —
 *  a test that sets choices afterwards must not have them overwritten by a
 *  late fetch landing mid-assertion. */
async function renderPalette(panels: PanelSpecSummary[] = CATALOGUE) {
  listPanels.mockResolvedValue({ panels: panels, diagnostics: [] });
  act(() => {
    useAppStore.getState().setPanels(panels, []);
    useAppStore.getState().setPanelChoices([]);
  });
  const result = render(<PanelPalette />);
  await act(async () => {});
  return result;
}

function card(id: string): HTMLElement {
  return screen.getByTestId(`panel-card-${id}`);
}

beforeEach(() => {
  resetAppStore();
  resetPanelCatalogLoader();
  listPanels.mockResolvedValue({ panels: [], diagnostics: [] });
  listPanelChoices.mockResolvedValue({ choices: [] });
  reloadPanels.mockResolvedValue({ reloaded: 0, added: [], removed: [], diagnostics: [] });
  setPanelChoice.mockResolvedValue({ choices: [] });
  clearPanelChoice.mockResolvedValue({ choices: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Panels tab — structure", () => {
  it("titles the panel `Previewers`, matching its activity-bar label", async () => {
    await renderPalette();
    expect(screen.getByText("Previewers")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search previewers")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it("groups cards by tier: This Project, My Library, Core, then packages A→Z", async () => {
    const { container } = await renderPalette();
    const sections = [...container.querySelectorAll("section[data-testid^='panel-section-']")];
    const headings = sections.map(
      (node) => node.querySelector("button span:last-child, p")?.textContent,
    );
    expect(headings).toEqual(["This Project", "My Library", "Core", "scistudio-blocks-imaging"]);
    expect(within(card("project.spectrum.view")).getByText("project.spectrum.view")).toBeTruthy();
  });

  it("renders both drop-in tier sections with their teaching copy when empty", async () => {
    await renderPalette([coreViewer]);
    const hints = screen.getAllByTestId("palette-section-empty").map((node) => node.textContent);
    expect(hints).toHaveLength(2);
    expect(hints.some((hint) => hint?.includes("No previewers of your own yet"))).toBe(true);
    expect(hints.some((hint) => hint?.includes("No previewers in this project yet"))).toBe(true);
  });

  it("says so when nothing is registered at all", async () => {
    await renderPalette([]);
    expect(screen.getByTestId("panel-palette-empty")).toHaveTextContent(
      "No previewers registered.",
    );
  });

  it("narrows the cards by search text", async () => {
    await renderPalette();
    fireEvent.change(screen.getByPlaceholderText("Search previewers"), {
      target: { value: "imaging" },
    });
    expect(screen.queryByTestId("panel-card-pkg.image.view")).toBeTruthy();
    expect(screen.queryByTestId("panel-card-core.table")).toBeNull();
  });
});

describe("Panels tab — reload (#2095)", () => {
  it("Reload re-scans the registries before re-reading the listing", async () => {
    const calls: string[] = [];
    reloadPanels.mockImplementation(() => {
      calls.push("scan");
      return Promise.resolve({ reloaded: 0, added: [], removed: [], diagnostics: [] });
    });
    listPanels.mockImplementation(() => {
      calls.push("list");
      return Promise.resolve({ panels: CATALOGUE, diagnostics: [] });
    });
    // A preloaded store makes the mount an auto-rescan revisit (#2151) — that
    // settle is the baseline the click adds to. (Not `renderPalette`: its
    // listing-mock default would replace the tracked implementations above.)
    act(() => {
      useAppStore.getState().setPanels(CATALOGUE, []);
      useAppStore.getState().setPanelChoices([]);
    });
    render(<PanelPalette />);
    await act(async () => {});
    expect(calls).toEqual(["scan", "list"]);
    calls.length = 0;

    fireEvent.click(screen.getByRole("button", { name: "Reload" }));

    await waitFor(() => expect(calls).toEqual(["scan", "list"]));
  });

  it("surfaces registry diagnostics the listing carried", () => {
    render(<PanelPalette />);
    act(() => {
      useAppStore.getState().setPanels(CATALOGUE, ["duplicate panel id 'x' from two packages"]);
    });
    expect(screen.getByTestId("panel-diagnostics")).toHaveTextContent("duplicate panel id 'x'");
  });
});

describe("Panels tab — auto-reload on section switch (#2151)", () => {
  it("rescans once when the pane mounts over an already-loaded (possibly stale) catalogue", async () => {
    // The revisit: the store still holds the last listing, which is exactly
    // the cache a change outside the registry-refresh paths leaves stale.
    act(() => {
      useAppStore.getState().setPanels(CATALOGUE, []);
      useAppStore.getState().setPanelChoices([]);
    });
    listPanels.mockResolvedValue({ panels: CATALOGUE, diagnostics: [] });
    render(<PanelPalette />);
    await act(async () => {});
    expect(reloadPanels).toHaveBeenCalledTimes(1);
    expect(listPanels).toHaveBeenCalledTimes(1);
  });

  it("does not rescan on the first ever mount — the plain load is already fetching", async () => {
    render(<PanelPalette />);
    await act(async () => {});
    expect(reloadPanels).not.toHaveBeenCalled();
    expect(listPanels).toHaveBeenCalledTimes(1);
  });

  it("stays at one rescan under StrictMode's mount-effect replay (#2153 review)", async () => {
    act(() => {
      useAppStore.getState().setPanels(CATALOGUE, []);
      useAppStore.getState().setPanelChoices([]);
    });
    listPanels.mockResolvedValue({ panels: CATALOGUE, diagnostics: [] });
    render(
      <StrictMode>
        <PanelPalette />
      </StrictMode>,
    );
    await act(async () => {});
    expect(reloadPanels).toHaveBeenCalledTimes(1);
    expect(listPanels).toHaveBeenCalledTimes(1);
  });
});

describe("Panels tab — per-type choice (#2049, segmented control)", () => {
  it("highlights the chosen card's scope segment; every other card reads Auto", async () => {
    await renderPalette();
    act(() => {
      useAppStore.getState().setPanelChoices([makeChoice()]);
    });
    expect(within(card("user.spectrum.view")).getByTestId("panel-seg-user")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(card("user.spectrum.view")).getByTestId("panel-seg-auto")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    // The competing card for the same type reads Auto — the choice is not its.
    expect(within(card("project.spectrum.view")).getByTestId("panel-seg-auto")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("names the current choice on a competing card for the same type", async () => {
    await renderPalette();
    act(() => {
      useAppStore.getState().setPanelChoices([makeChoice()]);
    });
    expect(
      within(card("project.spectrum.view")).getByTestId("panel-current-choice"),
    ).toHaveTextContent("user.spectrum.view");
  });

  it("writes a user-scope choice from the All projects segment and re-routes", async () => {
    await renderPalette();
    setPanelChoice.mockResolvedValue({ choices: [makeChoice()] });
    const versionBefore = useAppStore.getState().panelChoiceVersion;

    fireEvent.click(within(card("user.spectrum.view")).getByTestId("panel-seg-user"));

    await waitFor(() =>
      expect(setPanelChoice).toHaveBeenCalledWith("Spectrum", "user.spectrum.view", "user"),
    );
    await waitFor(() =>
      expect(useAppStore.getState().panelChoices[0]?.panel_id).toBe("user.spectrum.view"),
    );
    // The routing epoch bumped so an open preview re-creates its session
    // through the new choice instead of sitting on the old envelope.
    expect(useAppStore.getState().panelChoiceVersion).toBe(versionBefore + 1);
  });

  it("writes a project-scope choice from the This project segment", async () => {
    await renderPalette();
    setPanelChoice.mockResolvedValue({
      choices: [makeChoice({ scope: "project", panel_id: "project.spectrum.view" })],
    });

    fireEvent.click(within(card("project.spectrum.view")).getByTestId("panel-seg-project"));

    await waitFor(() =>
      expect(setPanelChoice).toHaveBeenCalledWith("Spectrum", "project.spectrum.view", "project"),
    );
    await waitFor(() =>
      expect(
        within(card("project.spectrum.view")).getByTestId("panel-seg-project"),
      ).toHaveAttribute("aria-pressed", "true"),
    );
  });

  it("clears BOTH layers from the chosen card's Auto segment, returning the type to the ladder", async () => {
    // Auto means "no preference anywhere": clearing only the project layer
    // would reveal a user-layer choice underneath (#2049 reveal semantics),
    // which is correct for a scoped clear and wrong for Auto. Both DELETEs
    // succeed even when a layer holds nothing.
    await renderPalette();
    clearPanelChoice.mockResolvedValue({ choices: [] });
    act(() => {
      useAppStore
        .getState()
        .setPanelChoices([makeChoice({ scope: "project", panel_id: "user.spectrum.view" })]);
    });

    fireEvent.click(within(card("user.spectrum.view")).getByTestId("panel-seg-auto"));

    await waitFor(() => expect(clearPanelChoice).toHaveBeenCalledWith("Spectrum", "project"));
    await waitFor(() => expect(clearPanelChoice).toHaveBeenCalledWith("Spectrum", "user"));
    await waitFor(() =>
      expect(within(card("user.spectrum.view")).getByTestId("panel-seg-auto")).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
  });

  it("Auto on an unchosen card is a no-op — it must not clear another panel's choice", async () => {
    await renderPalette();
    act(() => {
      useAppStore.getState().setPanelChoices([makeChoice()]);
    });

    fireEvent.click(within(card("project.spectrum.view")).getByTestId("panel-seg-auto"));

    await Promise.resolve();
    expect(clearPanelChoice).not.toHaveBeenCalled();
  });

  it("shows a card-level error instead of losing the click when the write fails", async () => {
    await renderPalette();
    setPanelChoice.mockRejectedValue(new Error("Unknown panel 'nope'"));

    fireEvent.click(within(card("user.spectrum.view")).getByTestId("panel-seg-user"));

    await waitFor(() =>
      expect(within(card("user.spectrum.view")).getByRole("alert")).toHaveTextContent(
        "Unknown panel 'nope'",
      ),
    );
  });

  it("renders the choice control as one pill-shaped segmented group with visible depth (owner review on #2119)", async () => {
    // Owner call: keep the pill shape (the toolbar-button design language);
    // the control reads as interactive through the container's border + shadow.
    await renderPalette();
    const segments = within(card("user.spectrum.view")).getByTestId("panel-choice-segments");
    expect(segments.className).toContain("rounded-full");
    expect(segments.className).toContain("shadow-sm");
    expect(segments.className).toContain("border");
    expect(
      within(segments)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(["Auto", "This project", "All projects"]);
  });
});

describe("Panels tab — stale choices", () => {
  it("lists a choice whose panel is not registered and clears it in place", async () => {
    await renderPalette();
    act(() => {
      useAppStore
        .getState()
        .setPanelChoices([makeChoice({ panel_id: "gone.view", available: false })]);
    });

    const strip = screen.getByTestId("panel-stale-choices");
    expect(strip).toHaveTextContent("Spectrum → gone.view (user) — not registered");

    fireEvent.click(within(strip).getByTestId("panel-stale-clear-Spectrum"));
    await waitFor(() => expect(clearPanelChoice).toHaveBeenCalledWith("Spectrum", "user"));
  });
});

// ---------------------------------------------------------------------------
// ADR-054 T-010's host half — the card is where a panel is opened and reverted
// ---------------------------------------------------------------------------
//
// The audit found `PUT /api/panels/{id}/source` reachable only from `curl`,
// which left SC-004 -- "copy a built-in panel into a project, edit, save, and
// see the mounted panel redraw" -- with no affordance in the product. The Edit
// button is that affordance, and it is on every tier deliberately: FR-025
// forbids asking where a save goes, and FR-026 makes a save on a core panel the
// copy itself.

describe("Panels tab — editing a panel (FR-024, FR-029)", () => {
  it("opens a panel's source from its card, whichever tier it is in", async () => {
    const openPanelSourceTab = vi.fn();
    await renderPalette();
    act(() => {
      useAppStore.setState({ openPanelSourceTab });
    });

    fireEvent.click(within(card("core.table")).getByTestId("panel-edit"));

    expect(openPanelSourceTab).toHaveBeenCalledWith("core.table");
  });

  it("offers Edit on a core panel, because saving it is what copies it (SC-004)", async () => {
    await renderPalette();
    expect(within(card("core.table")).getByTestId("panel-edit")).toBeInTheDocument();
  });

  it("offers Revert only on a copy that shadows something (FR-029)", async () => {
    const shadowing = makePanel({
      panel_id: "shadow.view",
      owner_kind: "project",
      owner_name: "demo",
      target_type: "Image",
      tier: "project",
      shadows: "core",
    });
    await renderPalette([...CATALOGUE, shadowing]);

    expect(within(card("shadow.view")).getByTestId("panel-revert")).toHaveTextContent(
      "Revert to core",
    );
    expect(within(card("core.table")).queryByTestId("panel-revert")).toBeNull();
    expect(within(card("project.spectrum.view")).queryByTestId("panel-revert")).toBeNull();
  });
});
