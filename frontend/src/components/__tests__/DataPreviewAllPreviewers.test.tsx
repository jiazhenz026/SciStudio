// ADR-054 FR-033 — All Previewers, and User Story 5 scenario 3: "the list the
// Previewers tab showed replaces the preview inside the column, with its
// reload action, diagnostics, and per-type choice controls, and a control
// returns to the preview".

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { mockBackend, type MockBackend } from "../../__tests__/contract/mockBackend";
import { useAppStore } from "../../store";
import { resetPreviewerCatalogLoader } from "../../store/usePreviewerCatalog";
import { resetAppStore } from "../../testUtils";
import type { PreviewerSpecSummary } from "../../types/api";
import { DataPreview, openAllPreviewers, resetAllPreviewersRequests } from "../DataPreview";

let backend: MockBackend;

const coreViewer: PreviewerSpecSummary = {
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
};

function renderPreview() {
  return render(
    <DataPreview blockOutputs={{}} selectedNodeId={null} selectedNodeLabel="Threshold" />,
  );
}

beforeEach(() => {
  resetAppStore();
  resetPreviewerCatalogLoader();
  resetAllPreviewersRequests();
  backend = mockBackend({
    "GET /api/previews/previewers": { previewers: [coreViewer], diagnostics: [] },
    "GET /api/previews/choices": { choices: [] },
    "POST /api/previews/reload": { reloaded: 0, added: [], removed: [], diagnostics: [] },
  });
});

afterEach(() => {
  cleanup();
  backend.restore();
});

describe("All Previewers (FR-033)", () => {
  it("shows the preview until the button is pressed", () => {
    renderPreview();
    expect(
      screen.getByText("Pick a block to inspect its latest outputs and cached previews."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("all-previewers-open")).toBeInTheDocument();
    expect(screen.queryByTestId("all-previewers-pane")).toBeNull();
  });

  it("replaces the preview with the previewer list, inside the column and with no dialog", async () => {
    renderPreview();
    fireEvent.click(screen.getByTestId("all-previewers-open"));

    const pane = await screen.findByTestId("all-previewers-pane");
    // The same component: its own heading, its reload action, and — once the
    // listing lands — its per-type choice controls.
    expect(screen.getByText("Previewers")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
    expect(screen.getByTestId("previewer-palette-content")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("previewer-card-core.table")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("previewer-choice-segments")).toBeInTheDocument();
    // Inside the preview column, not in an overlay beside it.
    expect(screen.getByTestId("data-preview-column")).toContainElement(pane);
    expect(document.querySelector("[role='dialog']")).toBeNull();
    // And the preview itself is gone while the list is up.
    expect(
      screen.queryByText("Pick a block to inspect its latest outputs and cached previews."),
    ).toBeNull();
  });

  it("surfaces the registry diagnostics nothing else shows", async () => {
    renderPreview();
    fireEvent.click(screen.getByTestId("all-previewers-open"));
    await screen.findByTestId("all-previewers-pane");

    act(() => {
      useAppStore.getState().setPreviewers([coreViewer], ["duplicate previewer id 'x'"]);
    });

    expect(screen.getByTestId("previewer-diagnostics")).toHaveTextContent(
      "duplicate previewer id 'x'",
    );
  });

  it("returns to the preview", async () => {
    renderPreview();
    fireEvent.click(screen.getByTestId("all-previewers-open"));
    await screen.findByTestId("all-previewers-pane");

    fireEvent.click(screen.getByTestId("all-previewers-back"));

    expect(
      screen.getByText("Pick a block to inspect its latest outputs and cached previews."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("all-previewers-back")).toBeNull();
    expect(screen.getByTestId("all-previewers-open")).toBeInTheDocument();
  });

  it("does not rescan the previewer registries on every open", async () => {
    // #2151's mount rescan is right for a section switch and wrong for a
    // control the user toggles: re-mounting the pane on each open would POST a
    // registry reload every time. The pane is kept mounted instead.
    act(() => {
      useAppStore.getState().setPreviewers([coreViewer], []);
    });
    renderPreview();

    fireEvent.click(screen.getByTestId("all-previewers-open"));
    await screen.findByTestId("all-previewers-pane");
    await waitFor(() => expect(backend.callsTo("POST /api/previews/reload")).toHaveLength(1));

    fireEvent.click(screen.getByTestId("all-previewers-back"));
    fireEvent.click(screen.getByTestId("all-previewers-open"));
    fireEvent.click(screen.getByTestId("all-previewers-back"));
    fireEvent.click(screen.getByTestId("all-previewers-open"));
    await act(async () => {});

    expect(backend.callsTo("POST /api/previews/reload")).toHaveLength(1);
  });

  it("opens from outside the column, for the tutorial route (FR-040)", async () => {
    renderPreview();
    expect(screen.queryByTestId("all-previewers-pane")).toBeNull();

    act(() => {
      openAllPreviewers();
    });

    expect(await screen.findByTestId("all-previewers-pane")).toBeInTheDocument();
    expect(screen.getByTestId("previewer-palette-content")).toBeInTheDocument();
  });

  it("expands a collapsed column before showing the list (FR-033)", () => {
    // The tutorial route can reach the list while the column is collapsed, and
    // a list rendered into a zero-width column teaches nothing.
    act(() => {
      useAppStore.setState({ previewCollapsed: true });
    });
    renderPreview();

    act(() => {
      openAllPreviewers();
    });

    expect(useAppStore.getState().previewCollapsed).toBe(false);
  });
});
