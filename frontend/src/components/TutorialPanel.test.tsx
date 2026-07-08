import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// TutorialPanel and the shared store read named methods off the `api` object;
// mock the ones this surface touches and keep the rest intact.
const putProjectFile = vi.fn();
const listPlots = vi.fn();
vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  const actualApi = (actual.api ?? {}) as Record<string, unknown>;
  return {
    ...actual,
    api: {
      ...actualApi,
      putProjectFile: (...a: unknown[]) => putProjectFile(...a),
      listPlots: (...a: unknown[]) => listPlots(...a),
    },
  };
});

import { useAppStore } from "../store";
import type { RunFirstWorkflowTutorialInstance } from "../store/types";
import type { ProjectResponse } from "../types/api";
import { resetAppStore } from "../testUtils";

import { TutorialPanel } from "./TutorialPanel";

const PROJECT_ID = "proj-1";

function makeInstance(): RunFirstWorkflowTutorialInstance {
  return {
    tutorialId: "run-first-scistudio-workflow",
    projectId: PROJECT_ID,
    datasetPath: "data/raw/cell_viability_fluorescence.csv",
    workflowId: "main",
    customBlockPath: "blocks/normalize_fluorescence.py",
    customBlockType: "normalize_fluorescence",
    customBlockName: "Normalize Fluorescence",
    plotId: "normalized-activity",
    plotTitle: "Normalized cell activity",
    negativeControl: "neg_control",
    positiveControl: "pos_control",
  };
}

function makeProject(): ProjectResponse {
  return {
    id: PROJECT_ID,
    name: "Demo",
    description: "",
    path: "/tmp/proj-1",
    workflow_count: 1,
    workflows: ["main"],
    current_workflow_id: "main",
  };
}

function makeProps() {
  return {
    onOpenFile: vi.fn(),
    onReloadBlocks: vi.fn().mockResolvedValue(undefined),
    onSaveWorkflow: vi.fn().mockResolvedValue(undefined),
    onShowBlocks: vi.fn(),
  };
}

beforeEach(() => {
  putProjectFile.mockReset().mockResolvedValue(undefined);
  listPlots.mockReset().mockResolvedValue({ plots: [] });
  resetAppStore();
  useAppStore.setState({
    currentProject: makeProject(),
    runFirstWorkflowTutorialActive: true,
    runFirstWorkflowTutorialStep: "create-custom-block",
    runFirstWorkflowTutorialInstance: makeInstance(),
    paletteSearch: "",
  });
});

afterEach(() => {
  cleanup();
});

describe("TutorialPanel create-custom-block step", () => {
  it("does not pre-fill the block palette search (Load must stay findable, #1929)", async () => {
    const props = makeProps();
    render(<TutorialPanel {...props} />);

    fireEvent.click(screen.getByRole("button", { name: /create block/i }));

    // The create-block action creates the tutorial block, shows the palette,
    // opens the block file, and advances to the build-workflow step.
    await waitFor(() => {
      expect(useAppStore.getState().runFirstWorkflowTutorialStep).toBe("build-workflow");
    });
    expect(putProjectFile).toHaveBeenCalledWith(
      PROJECT_ID,
      "blocks/normalize_fluorescence.py",
      expect.stringContaining("NormalizeFluorescenceBlock"),
      { createParentDirs: true },
    );
    expect(props.onShowBlocks).toHaveBeenCalled();
    expect(props.onOpenFile).toHaveBeenCalledWith("blocks/normalize_fluorescence.py");

    // Regression guard: the tutorial must never seed the palette search. A
    // lingering "Normalize Fluorescence" filter hid the Load block in the next
    // step and forced users to clear the field by hand.
    expect(useAppStore.getState().paletteSearch).toBe("");
  });
});
