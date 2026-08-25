// The Previewers tab (#2113) — tier-grouped cards over the #2095 listing with
// the #2049 per-type choice controls, plus reload and the surfaces nothing
// else shows (registry diagnostics, stale choices).

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as DataApi from "../../lib/api/data";
import { useAppStore } from "../../store";
import { resetPreviewerCatalogLoader } from "../../store/usePreviewerCatalog";
import { resetAppStore } from "../../testUtils";
import type { PreviewerChoice, PreviewerSpecSummary } from "../../types/api";
import { PreviewerPalette } from "../PreviewerPalette";

const listPreviewers = vi.fn();
const listPreviewerChoices = vi.fn();
const reloadPreviewers = vi.fn();
const setPreviewerChoice = vi.fn();
const clearPreviewerChoice = vi.fn();
vi.mock("../../lib/api/data", async (importOriginal) => {
  const actual = await importOriginal<typeof DataApi>();
  return {
    ...actual,
    dataApi: {
      ...actual.dataApi,
      listPreviewers: (...args: unknown[]) => listPreviewers(...args),
      listPreviewerChoices: () => listPreviewerChoices(),
      reloadPreviewers: () => reloadPreviewers(),
      setPreviewerChoice: (...args: unknown[]) => setPreviewerChoice(...args),
      clearPreviewerChoice: (...args: unknown[]) => clearPreviewerChoice(...args),
    },
  };
});

function makePreviewer(overrides: Partial<PreviewerSpecSummary> = {}): PreviewerSpecSummary {
  return {
    previewer_id: "core.table",
    owner_kind: "core",
    owner_name: "scistudio",
    target_type: "DataObject",
    supports_collection: false,
    priority: 0,
    capabilities: [],
    backend_provider: null,
    frontend_manifest: null,
    api_version: "1",
    ...overrides,
  };
}

const projectViewer = makePreviewer({
  previewer_id: "project.spectrum.view",
  owner_kind: "project",
  owner_name: "demo",
  target_type: "Spectrum",
});
const userViewer = makePreviewer({
  previewer_id: "user.spectrum.view",
  owner_kind: "user",
  owner_name: "library",
  target_type: "Spectrum",
});
const packageViewer = makePreviewer({
  previewer_id: "pkg.image.view",
  owner_kind: "package",
  owner_name: "scistudio-blocks-imaging",
  target_type: "Image",
});
const coreViewer = makePreviewer();

const CATALOGUE = [projectViewer, userViewer, packageViewer, coreViewer];

function makeChoice(overrides: Partial<PreviewerChoice> = {}): PreviewerChoice {
  return {
    target_type: "Spectrum",
    previewer_id: "user.spectrum.view",
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
async function renderPalette(previewers: PreviewerSpecSummary[] = CATALOGUE) {
  listPreviewers.mockResolvedValue({ previewers, diagnostics: [] });
  act(() => {
    useAppStore.getState().setPreviewers(previewers, []);
    useAppStore.getState().setPreviewerChoices([]);
  });
  const result = render(<PreviewerPalette />);
  await act(async () => {});
  return result;
}

function card(id: string): HTMLElement {
  return screen.getByTestId(`previewer-card-${id}`);
}

beforeEach(() => {
  resetAppStore();
  resetPreviewerCatalogLoader();
  listPreviewers.mockResolvedValue({ previewers: [], diagnostics: [] });
  listPreviewerChoices.mockResolvedValue({ choices: [] });
  reloadPreviewers.mockResolvedValue({ reloaded: 0, added: [], removed: [], diagnostics: [] });
  setPreviewerChoice.mockResolvedValue({ choices: [] });
  clearPreviewerChoice.mockResolvedValue({ choices: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Previewers tab — structure", () => {
  it("titles the panel `Previewers`, matching its activity-bar label", async () => {
    await renderPalette();
    expect(screen.getByText("Previewers")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search previewers")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it("groups cards by tier: This Project, My Library, Core, then packages A→Z", async () => {
    const { container } = await renderPalette();
    const sections = [...container.querySelectorAll("section[data-testid^='previewer-section-']")];
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
    expect(screen.getByTestId("previewer-palette-empty")).toHaveTextContent(
      "No previewers registered.",
    );
  });

  it("narrows the cards by search text", async () => {
    await renderPalette();
    fireEvent.change(screen.getByPlaceholderText("Search previewers"), {
      target: { value: "imaging" },
    });
    expect(screen.queryByTestId("previewer-card-pkg.image.view")).toBeTruthy();
    expect(screen.queryByTestId("previewer-card-core.table")).toBeNull();
  });
});

describe("Previewers tab — reload (#2095)", () => {
  it("Reload re-scans the registries before re-reading the listing", async () => {
    const calls: string[] = [];
    reloadPreviewers.mockImplementation(() => {
      calls.push("scan");
      return Promise.resolve({ reloaded: 0, added: [], removed: [], diagnostics: [] });
    });
    listPreviewers.mockImplementation(() => {
      calls.push("list");
      return Promise.resolve({ previewers: CATALOGUE, diagnostics: [] });
    });
    // A preloaded store makes the mount an auto-rescan revisit (#2151) — that
    // settle is the baseline the click adds to. (Not `renderPalette`: its
    // listing-mock default would replace the tracked implementations above.)
    act(() => {
      useAppStore.getState().setPreviewers(CATALOGUE, []);
      useAppStore.getState().setPreviewerChoices([]);
    });
    render(<PreviewerPalette />);
    await act(async () => {});
    expect(calls).toEqual(["scan", "list"]);
    calls.length = 0;

    fireEvent.click(screen.getByRole("button", { name: "Reload" }));

    await waitFor(() => expect(calls).toEqual(["scan", "list"]));
  });

  it("surfaces registry diagnostics the listing carried", () => {
    render(<PreviewerPalette />);
    act(() => {
      useAppStore
        .getState()
        .setPreviewers(CATALOGUE, ["duplicate previewer id 'x' from two packages"]);
    });
    expect(screen.getByTestId("previewer-diagnostics")).toHaveTextContent(
      "duplicate previewer id 'x'",
    );
  });
});

describe("Previewers tab — auto-reload on section switch (#2151)", () => {
  it("rescans once when the pane mounts over an already-loaded (possibly stale) catalogue", async () => {
    // The revisit: the store still holds the last listing, which is exactly
    // the cache a change outside the registry-refresh paths leaves stale.
    act(() => {
      useAppStore.getState().setPreviewers(CATALOGUE, []);
      useAppStore.getState().setPreviewerChoices([]);
    });
    listPreviewers.mockResolvedValue({ previewers: CATALOGUE, diagnostics: [] });
    render(<PreviewerPalette />);
    await act(async () => {});
    expect(reloadPreviewers).toHaveBeenCalledTimes(1);
    expect(listPreviewers).toHaveBeenCalledTimes(1);
  });

  it("does not rescan on the first ever mount — the plain load is already fetching", async () => {
    render(<PreviewerPalette />);
    await act(async () => {});
    expect(reloadPreviewers).not.toHaveBeenCalled();
    expect(listPreviewers).toHaveBeenCalledTimes(1);
  });
});

describe("Previewers tab — per-type choice (#2049, segmented control)", () => {
  it("highlights the chosen card's scope segment; every other card reads Auto", async () => {
    await renderPalette();
    act(() => {
      useAppStore.getState().setPreviewerChoices([makeChoice()]);
    });
    expect(within(card("user.spectrum.view")).getByTestId("previewer-seg-user")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(card("user.spectrum.view")).getByTestId("previewer-seg-auto")).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    // The competing card for the same type reads Auto — the choice is not its.
    expect(within(card("project.spectrum.view")).getByTestId("previewer-seg-auto")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("names the current choice on a competing card for the same type", async () => {
    await renderPalette();
    act(() => {
      useAppStore.getState().setPreviewerChoices([makeChoice()]);
    });
    expect(
      within(card("project.spectrum.view")).getByTestId("previewer-current-choice"),
    ).toHaveTextContent("user.spectrum.view");
  });

  it("writes a user-scope choice from the All projects segment and re-routes", async () => {
    await renderPalette();
    setPreviewerChoice.mockResolvedValue({ choices: [makeChoice()] });
    const versionBefore = useAppStore.getState().previewerChoiceVersion;

    fireEvent.click(within(card("user.spectrum.view")).getByTestId("previewer-seg-user"));

    await waitFor(() =>
      expect(setPreviewerChoice).toHaveBeenCalledWith("Spectrum", "user.spectrum.view", "user"),
    );
    await waitFor(() =>
      expect(useAppStore.getState().previewerChoices[0]?.previewer_id).toBe("user.spectrum.view"),
    );
    // The routing epoch bumped so an open preview re-creates its session
    // through the new choice instead of sitting on the old envelope.
    expect(useAppStore.getState().previewerChoiceVersion).toBe(versionBefore + 1);
  });

  it("writes a project-scope choice from the This project segment", async () => {
    await renderPalette();
    setPreviewerChoice.mockResolvedValue({
      choices: [makeChoice({ scope: "project", previewer_id: "project.spectrum.view" })],
    });

    fireEvent.click(within(card("project.spectrum.view")).getByTestId("previewer-seg-project"));

    await waitFor(() =>
      expect(setPreviewerChoice).toHaveBeenCalledWith(
        "Spectrum",
        "project.spectrum.view",
        "project",
      ),
    );
    await waitFor(() =>
      expect(
        within(card("project.spectrum.view")).getByTestId("previewer-seg-project"),
      ).toHaveAttribute("aria-pressed", "true"),
    );
  });

  it("clears BOTH layers from the chosen card's Auto segment, returning the type to the ladder", async () => {
    // Auto means "no preference anywhere": clearing only the project layer
    // would reveal a user-layer choice underneath (#2049 reveal semantics),
    // which is correct for a scoped clear and wrong for Auto. Both DELETEs
    // succeed even when a layer holds nothing.
    await renderPalette();
    clearPreviewerChoice.mockResolvedValue({ choices: [] });
    act(() => {
      useAppStore
        .getState()
        .setPreviewerChoices([
          makeChoice({ scope: "project", previewer_id: "user.spectrum.view" }),
        ]);
    });

    fireEvent.click(within(card("user.spectrum.view")).getByTestId("previewer-seg-auto"));

    await waitFor(() => expect(clearPreviewerChoice).toHaveBeenCalledWith("Spectrum", "project"));
    await waitFor(() => expect(clearPreviewerChoice).toHaveBeenCalledWith("Spectrum", "user"));
    await waitFor(() =>
      expect(within(card("user.spectrum.view")).getByTestId("previewer-seg-auto")).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
  });

  it("Auto on an unchosen card is a no-op — it must not clear another previewer's choice", async () => {
    await renderPalette();
    act(() => {
      useAppStore.getState().setPreviewerChoices([makeChoice()]);
    });

    fireEvent.click(within(card("project.spectrum.view")).getByTestId("previewer-seg-auto"));

    await Promise.resolve();
    expect(clearPreviewerChoice).not.toHaveBeenCalled();
  });

  it("shows a card-level error instead of losing the click when the write fails", async () => {
    await renderPalette();
    setPreviewerChoice.mockRejectedValue(new Error("Unknown previewer 'nope'"));

    fireEvent.click(within(card("user.spectrum.view")).getByTestId("previewer-seg-user"));

    await waitFor(() =>
      expect(within(card("user.spectrum.view")).getByRole("alert")).toHaveTextContent(
        "Unknown previewer 'nope'",
      ),
    );
  });

  it("renders the choice control as one pill-shaped segmented group with visible depth (owner review on #2119)", async () => {
    // Owner call: keep the pill shape (the toolbar-button design language);
    // the control reads as interactive through the container's border + shadow.
    await renderPalette();
    const segments = within(card("user.spectrum.view")).getByTestId("previewer-choice-segments");
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

describe("Previewers tab — stale choices", () => {
  it("lists a choice whose previewer is not registered and clears it in place", async () => {
    await renderPalette();
    act(() => {
      useAppStore
        .getState()
        .setPreviewerChoices([makeChoice({ previewer_id: "gone.view", available: false })]);
    });

    const strip = screen.getByTestId("previewer-stale-choices");
    expect(strip).toHaveTextContent("Spectrum → gone.view (user) — not registered");

    fireEvent.click(within(strip).getByTestId("previewer-stale-clear-Spectrum"));
    await waitFor(() => expect(clearPreviewerChoice).toHaveBeenCalledWith("Spectrum", "user"));
  });
});
