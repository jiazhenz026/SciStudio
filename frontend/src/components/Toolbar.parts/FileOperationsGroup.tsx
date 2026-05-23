/**
 * File operations group (New / Import / Save / Save-As dropdown) in the
 * Toolbar. Extracted in #1413.
 */
import {
  ChevronDown,
  FileCode2,
  FilePlus2,
  FileText,
  Import,
  Save,
  SaveAll,
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
import { ToolbarButton } from "./ToolbarButton";

export interface FileOperationsGroupProps {
  currentProject: ProjectResponse | null;
  isFileTab: boolean;
  onNewWorkflow: () => void;
  onNewCustomBlock?: () => void;
  onNewNote?: () => void;
  onImport: () => void;
  onSave: () => void;
  onSaveAs: () => void;
}

export function FileOperationsGroup({
  currentProject,
  isFileTab,
  onNewWorkflow,
  onNewCustomBlock,
  onNewNote,
  onImport,
  onSave,
  onSaveAs,
}: FileOperationsGroupProps) {
  return (
    <div className="flex items-center gap-1">
      {/*
       * ADR-036 §3.7 / §3.12 (I36c) — "New" is a constrained three-item
       * menu: workflow / custom block / note. No "New arbitrary file" entry.
       */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="toolbar" size="toolbar" disabled={!currentProject} type="button">
            <FilePlus2 className="size-3.5" />
            New
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
          <DropdownMenuItem onClick={onNewNote} disabled={!currentProject || !onNewNote}>
            <FileText className="size-4" />
            New note
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
