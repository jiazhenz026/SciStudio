/**
 * File operations group (New / Import / Save / Save-As dropdown) in the
 * Toolbar. Extracted in #1413.
 *
 * ADR-053 additions:
 *   - "New data type" joins the New menu (FR-032), beside "New custom block";
 *     both run the same destination-aware flow (FR-029 – FR-033).
 *   - Entry point E1 — "Move to My Library" sits beside Save whenever the
 *     active editor tab is a project-level drop-in (§6.2). It is the shared
 *     `PromoteToLibraryAction`, not a toolbar-local reimplementation (FR-025),
 *     and it renders nothing at all for anything else (FR-019).
 */
import {
  ChartLine,
  ChevronDown,
  FileCode2,
  FilePlus2,
  FileText,
  Import,
  PackagePlus,
  Save,
  SaveAll,
  Shapes,
  Workflow,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import type { ProjectResponse } from "../../types/api";
import { PromoteToLibraryAction } from "../promotion/PromoteToLibraryAction";
import { useEditorPromotable } from "../promotion/useEditorPromotable";
import { ToolbarButton } from "./ToolbarButton";

export interface FileOperationsGroupProps {
  currentProject: ProjectResponse | null;
  isFileTab: boolean;
  onNewWorkflow: () => void;
  onNewCustomBlock?: () => void;
  /** ADR-053 FR-032 — "New data type". */
  onNewDataType?: () => void;
  onNewNote?: () => void;
  onNewPlot?: () => void;
  onInstallPackage: () => void;
  onImport: () => void;
  onSave: () => void;
  onSaveAs: () => void;
}

export function FileOperationsGroup({
  currentProject,
  isFileTab,
  onNewWorkflow,
  onNewCustomBlock,
  onNewDataType,
  onNewNote,
  onNewPlot,
  onInstallPackage,
  onImport,
  onSave,
  onSaveAs,
}: FileOperationsGroupProps) {
  // E1 resolves what the editor is showing; the action itself is shared with
  // the canvas node and the palette popovers.
  const editorItem = useEditorPromotable();

  return (
    <div className="flex shrink-0 items-center gap-1">
      {/*
       * ADR-036 §3.7 / §3.12 (I36c) — "New" is a constrained project-authoring
       * menu. No "New arbitrary file" entry.
       */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="toolbar"
            size="toolbar"
            disabled={!currentProject}
            type="button"
            aria-label="New"
          >
            <FilePlus2 className="size-3.5" />
            <span className="hidden xl:inline">New</span>
            <ChevronDown className="size-3" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={onNewWorkflow} disabled={!currentProject}>
            <Workflow className="size-4" />
            New workflow
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={onNewCustomBlock}
            disabled={!currentProject || !onNewCustomBlock}
          >
            <FileCode2 className="size-4" />
            New custom block
          </DropdownMenuItem>
          {/* ADR-053 FR-032 — the type-side twin of "New custom block".
           * Both entries call the same flow with one argument different
           * (FR-033), and both ask where the file goes first (FR-029). */}
          <DropdownMenuItem onClick={onNewDataType} disabled={!currentProject || !onNewDataType}>
            <Shapes className="size-4" />
            New data type
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onNewNote} disabled={!currentProject || !onNewNote}>
            <FileText className="size-4" />
            New note
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onNewPlot} disabled={!currentProject || !onNewPlot}>
            <ChartLine className="size-4" />
            New plot
          </DropdownMenuItem>
          {/* Live hotfix batch: "Install package" folded into the New menu.
           * Disabled without a project, consistent with the other entries. */}
          <DropdownMenuItem onClick={onInstallPackage} disabled={!currentProject}>
            <PackagePlus className="size-4" />
            New package
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ToolbarButton icon={Import} label="Import" disabled={!currentProject} onClick={onImport} />
      <ToolbarButton
        icon={Save}
        label="Save"
        shortcut="Ctrl+S"
        disabled={!currentProject}
        onClick={onSave}
      />
      {/* ADR-053 §6.2 E1 — beside the save affordance, hidden unless the open
       * file is a project-level drop-in (FR-019). */}
      <PromoteToLibraryAction entryPoint="E1" item={editorItem} variant="toolbar" />
      {/*
       * Save-As dropdown: only meaningful for workflow tabs in v1. File
       * tabs save to a fixed path; hide for file tabs.
       */}
      {!isFileTab && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="toolbar"
              size="toolbar"
              disabled={!currentProject}
              type="button"
              className="px-1"
            >
              <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem onClick={onSave}>
              <Save className="size-4" />
              Save
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onSaveAs}>
              <SaveAll className="size-4" />
              Save As...
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}
