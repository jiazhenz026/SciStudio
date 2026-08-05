import { beforeEach, describe, expect, it } from "vitest";

import { useAppStore } from "./index";
import type { RunFirstWorkflowTutorialInstance } from "./types";

const INSTANCE: RunFirstWorkflowTutorialInstance = {
  tutorialId: "run-first-scistudio-workflow",
  projectId: "proj-1",
  datasetPath: "data/raw/fluorescence.csv",
  workflowId: "wf-1",
  customBlockPath: "blocks/normalize_fluorescence.py",
  customBlockType: "normalize_fluorescence",
  customBlockName: "Normalize Fluorescence",
  plotId: "plot-1",
  plotTitle: "Normalized fluorescence",
  negativeControl: "blank",
  positiveControl: "max",
};

function resetTutorialState(): void {
  useAppStore.setState({
    runFirstWorkflowTutorialActive: false,
    runFirstWorkflowTutorialStep: "inspect-data",
    runFirstWorkflowTutorialInstance: null,
    runFirstWorkflowTutorialPrefs: {},
  });
}

describe("tutorial slice prefs", () => {
  beforeEach(resetTutorialState);

  it("keeps an existing suppression when the tutorial is started again (#1986)", () => {
    useAppStore.getState().suppressRunFirstWorkflowTutorialPrompt();
    useAppStore.getState().startRunFirstWorkflowTutorial(INSTANCE);

    const state = useAppStore.getState();
    expect(state.runFirstWorkflowTutorialActive).toBe(true);
    expect(state.runFirstWorkflowTutorialInstance).toEqual(INSTANCE);
    expect(state.runFirstWorkflowTutorialPrefs.suppressAutoStart).toBe(true);
  });

  it("keeps a recorded completion when the tutorial is started again (#1986)", () => {
    useAppStore.getState().completeRunFirstWorkflowTutorial();
    const completedAt = useAppStore.getState().runFirstWorkflowTutorialPrefs.completedAt;
    expect(completedAt).toBeTruthy();

    useAppStore.getState().startRunFirstWorkflowTutorial(INSTANCE);

    expect(useAppStore.getState().runFirstWorkflowTutorialPrefs.completedAt).toBe(completedAt);
  });

  it("survives start then exit, so the welcome prompt stays suppressed (#1986)", () => {
    useAppStore.getState().suppressRunFirstWorkflowTutorialPrompt();
    useAppStore.getState().startRunFirstWorkflowTutorial(INSTANCE);
    useAppStore.getState().exitRunFirstWorkflowTutorial();

    const state = useAppStore.getState();
    expect(state.runFirstWorkflowTutorialActive).toBe(false);
    expect(state.runFirstWorkflowTutorialPrefs.suppressAutoStart).toBe(true);
  });

  it("records completion without discarding an earlier suppression", () => {
    useAppStore.getState().suppressRunFirstWorkflowTutorialPrompt();
    useAppStore.getState().completeRunFirstWorkflowTutorial();

    const prefs = useAppStore.getState().runFirstWorkflowTutorialPrefs;
    expect(prefs.suppressAutoStart).toBe(true);
    expect(prefs.completedAt).toBeTruthy();
    expect(useAppStore.getState().runFirstWorkflowTutorialStep).toBe("finish");
  });
});
