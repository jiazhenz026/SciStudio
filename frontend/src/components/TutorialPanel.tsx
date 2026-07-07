import { CheckCircle2, ChevronRight, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../lib/api";
import { useAppStore } from "../store";
import type { RunFirstWorkflowTutorialStep } from "../store/types";
import {
  findStep,
  hasTutorialBlock,
  hasTutorialPlot,
  NORMALIZE_FLUORESCENCE_BLOCK_SOURCE,
  NORMALIZED_ACTIVITY_PLOT_SOURCE,
  RUN_FIRST_WORKFLOW_INITIAL_STEP,
  normalizeOutputAvailable,
  RUN_FIRST_WORKFLOW_STEPS,
  workflowHasTutorialDatasetPath,
  workflowHasTutorialGraph,
} from "../tutorials/runFirstWorkflow/content";
import type { PlotListItem, WorkflowNode } from "../types/api";

interface TutorialPanelProps {
  onOpenFile: (path: string) => void;
  onReloadBlocks: () => Promise<void>;
  onSaveWorkflow: () => Promise<void>;
  onShowBlocks: () => void;
  onPaletteSearch: (search: string) => void;
}

function nextStep(step: RunFirstWorkflowTutorialStep): RunFirstWorkflowTutorialStep {
  const index = RUN_FIRST_WORKFLOW_STEPS.findIndex((candidate) => candidate.id === step);
  const fallbackIndex = RUN_FIRST_WORKFLOW_STEPS.length - 1;
  return (
    RUN_FIRST_WORKFLOW_STEPS[Math.min(index + 1, fallbackIndex)] ?? RUN_FIRST_WORKFLOW_INITIAL_STEP
  ).id;
}

function normalizeNode(nodes: WorkflowNode[], customBlockType: string): WorkflowNode | undefined {
  return nodes.find((node) => node.block_type === customBlockType);
}

export function TutorialPanel({
  onOpenFile,
  onReloadBlocks,
  onSaveWorkflow,
  onShowBlocks,
  onPaletteSearch,
}: TutorialPanelProps) {
  const currentProject = useAppStore((state) => state.currentProject);
  const workflowId = useAppStore((state) => state.workflowId);
  const blocks = useAppStore((state) => state.blocks);
  const workflowNodes = useAppStore((state) => state.workflowNodes);
  const workflowEdges = useAppStore((state) => state.workflowEdges);
  const blockOutputs = useAppStore((state) => state.blockOutputs);
  const bottomPanelCollapsed = useAppStore((state) => state.bottomPanelCollapsed);
  const toggleBottomPanel = useAppStore((state) => state.toggleBottomPanel);
  const setActiveBottomTab = useAppStore((state) => state.setActiveBottomTab);
  const setLastError = useAppStore((state) => state.setLastError);
  const active = useAppStore((state) => state.runFirstWorkflowTutorialActive);
  const stepId = useAppStore((state) => state.runFirstWorkflowTutorialStep);
  const instance = useAppStore((state) => state.runFirstWorkflowTutorialInstance);
  const setStep = useAppStore((state) => state.setRunFirstWorkflowTutorialStep);
  const exitTutorial = useAppStore((state) => state.exitRunFirstWorkflowTutorial);
  const completeTutorial = useAppStore((state) => state.completeRunFirstWorkflowTutorial);

  const [busy, setBusy] = useState(false);
  const [plots, setPlots] = useState<PlotListItem[]>([]);

  useEffect(() => {
    if (!active || !instance || !workflowId) return;
    let cancelled = false;
    void api
      .listPlots({ workflowId })
      .then((result) => {
        if (!cancelled) setPlots(result.plots);
      })
      .catch(() => {
        if (!cancelled) setPlots([]);
      });
    return () => {
      cancelled = true;
    };
  }, [active, instance, workflowId, stepId]);

  const complete = useMemo(() => {
    if (!instance) return false;
    if (stepId === "inspect-data") return true;
    if (stepId === "create-custom-block") return hasTutorialBlock(blocks, instance);
    if (stepId === "build-workflow")
      return workflowHasTutorialGraph(workflowNodes, workflowEdges, instance);
    if (stepId === "configure-controls")
      return workflowHasTutorialDatasetPath(workflowNodes, instance);
    if (stepId === "run-workflow")
      return normalizeOutputAvailable(blockOutputs, workflowNodes, instance);
    if (stepId === "create-plot-card") return hasTutorialPlot(plots, instance);
    if (stepId === "view-history") return true;
    return true;
  }, [blockOutputs, blocks, instance, plots, stepId, workflowEdges, workflowNodes]);

  if (!active || !instance || !currentProject || currentProject.id !== instance.projectId) {
    return null;
  }

  const step = findStep(stepId);
  const currentIndex = RUN_FIRST_WORKFLOW_STEPS.findIndex((candidate) => candidate.id === stepId);

  async function runAction() {
    if (!instance || !currentProject) return;
    setBusy(true);
    setLastError(null);
    try {
      if (stepId === "inspect-data") {
        onOpenFile(instance.datasetPath);
        setStep("create-custom-block");
      } else if (stepId === "create-custom-block") {
        await api.putProjectFile(
          currentProject.id,
          instance.customBlockPath,
          NORMALIZE_FLUORESCENCE_BLOCK_SOURCE,
          { createParentDirs: true },
        );
        await onReloadBlocks();
        onShowBlocks();
        onPaletteSearch(instance.customBlockName);
        onOpenFile(instance.customBlockPath);
        setStep("build-workflow");
      } else if (stepId === "create-plot-card") {
        await onSaveWorkflow();
        const node = normalizeNode(workflowNodes, instance.customBlockType);
        if (!node) {
          setLastError("Add Normalize Fluorescence to the workflow before creating the plot card.");
          return;
        }
        const targets = await api.listPlotTargets({
          workflowId: workflowId ?? instance.workflowId,
          nodeId: node.id,
          outputPort: "normalized",
          includeUnavailable: false,
        });
        const target = targets.targets[0];
        if (!target) {
          setLastError(
            "Run the workflow first so the normalized output is available for plotting.",
          );
          return;
        }
        const created = await api.createPlot({
          plot_id: instance.plotId,
          target_id: target.target_id,
          title: instance.plotTitle,
          language: "python",
          overwrite: true,
        });
        await api.putProjectFile(
          currentProject.id,
          created.script_path,
          NORMALIZED_ACTIVITY_PLOT_SOURCE,
        );
        const list = await api.listPlots({ workflowId: workflowId ?? instance.workflowId });
        setPlots(list.plots);
        if (bottomPanelCollapsed) toggleBottomPanel();
        setActiveBottomTab("plots");
        setStep("view-history");
      } else if (stepId === "view-history") {
        if (bottomPanelCollapsed) toggleBottomPanel();
        setActiveBottomTab("lineage");
        setStep("finish");
      } else if (stepId === "finish") {
        completeTutorial();
      }
    } catch (error) {
      setLastError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  function advance() {
    if (stepId === "finish") {
      completeTutorial();
      return;
    }
    setStep(nextStep(stepId));
  }

  return (
    <aside className="fixed bottom-5 right-5 z-40 w-[24rem] rounded-lg border border-stone-200 bg-white p-4 shadow-panel">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[0.65rem] uppercase tracking-[0.22em] text-stone-400">
            Run Your First SciStudio Workflow
          </p>
          <h2 className="mt-1 text-base font-semibold text-ink">{step.title}</h2>
        </div>
        <button
          aria-label="Exit tutorial"
          className="inline-flex h-7 w-7 items-center justify-center rounded-full text-stone-400 hover:bg-stone-100 hover:text-ink"
          onClick={exitTutorial}
          type="button"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <p className="mt-3 text-sm leading-6 text-stone-600">{step.body}</p>

      {stepId === "finish" ? (
        <div className="mt-3 rounded-lg bg-stone-50 p-3 text-xs leading-5 text-stone-600">
          Next, try using AI to explain results, suggest workflow changes, or draft a new custom
          block from your scientific question. SciStudio keeps workflows, artifacts, and history
          traceable so you can review what changed and why.
        </div>
      ) : null}

      <div className="mt-4 flex items-center justify-between gap-3">
        <span className="text-xs text-stone-500">
          Step {currentIndex + 1} of {RUN_FIRST_WORKFLOW_STEPS.length}
        </span>
        <div className="flex items-center gap-2">
          {complete && stepId !== "finish" ? (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-pine">
              <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
              Ready
            </span>
          ) : null}
          {step.actionLabel ? (
            <button
              className="inline-flex items-center gap-1 rounded-full bg-ink px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
              disabled={busy}
              onClick={() => void runAction()}
              type="button"
            >
              {busy ? "Working" : step.actionLabel}
              <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          ) : (
            <button
              className="inline-flex items-center gap-1 rounded-full bg-ink px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
              disabled={!complete}
              onClick={advance}
              type="button"
            >
              Continue
              <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
