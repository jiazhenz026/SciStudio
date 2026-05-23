/**
 * Projects dropdown (Group 1) in the Toolbar. Extracted in #1413.
 */
import { ChevronDown, FolderOpen, Plus, Save, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import type { ProjectResponse } from "../../types/api";

export interface ProjectsDropdownProps {
  currentProject: ProjectResponse | null;
  recentProjects: ProjectResponse[];
  onNewProject: () => void;
  onOpenProject: () => void;
  onSave: () => void;
  onOpenRecent: (project: ProjectResponse) => void;
  onCloseProject: () => void;
}

export function ProjectsDropdown({
  currentProject,
  recentProjects,
  onNewProject,
  onOpenProject,
  onSave,
  onOpenRecent,
  onCloseProject,
}: ProjectsDropdownProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="toolbar" size="toolbar" type="button">
          <FolderOpen className="size-3.5" />
          Projects
          <ChevronDown className="size-3" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-96 w-56 overflow-y-auto">
        <DropdownMenuItem onClick={onNewProject}>
          <Plus className="size-4" />
          New Project...
        </DropdownMenuItem>
        <DropdownMenuItem onClick={onOpenProject}>
          <FolderOpen className="size-4" />
          Open Project...
        </DropdownMenuItem>
        <DropdownMenuItem disabled={!currentProject} onClick={onSave}>
          <Save className="size-4" />
          Save Workflow
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Recent Projects</DropdownMenuLabel>
        {recentProjects.length > 0 ? (
          recentProjects.slice(0, 5).map((project) => (
            <DropdownMenuItem key={project.id} onClick={() => onOpenRecent(project)}>
              <span className="truncate">{project.name}</span>
            </DropdownMenuItem>
          ))
        ) : (
          <DropdownMenuItem disabled>
            <span className="text-stone-400">No recent projects</span>
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={!currentProject} onClick={onCloseProject}>
          <X className="size-4" />
          Close Project
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
