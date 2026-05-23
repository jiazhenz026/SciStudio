/**
 * Dropdown menu body for BranchPicker. Extracted in #1413 so the parent
 * component fits under the 150-line function limit.
 */
import { Check, CornerUpRight, GitMerge, Plus, Trash2 } from "lucide-react";

import {
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

interface BranchInfo {
  name: string;
  is_current: boolean;
}

export interface BranchMenuContentProps {
  branches: BranchInfo[] | null;
  onSwitch: (name: string) => void;
  onDelete: (name: string) => void;
  onCreate: () => void;
  onMergeRequested?: (sourceBranch: string) => void;
  onCherryPickRequested?: () => void;
}

function BranchListItems({
  branches,
  onSwitch,
  onDelete,
}: {
  branches: BranchInfo[];
  onSwitch: (name: string) => void;
  onDelete: (name: string) => void;
}) {
  return (
    <>
      {branches.map((b) => (
        <DropdownMenuItem
          key={b.name}
          data-testid={`branch-picker-item-${b.name}`}
          disabled={b.is_current}
          aria-current={b.is_current ? "true" : undefined}
          onSelect={(e) => {
            if (b.is_current) {
              e.preventDefault();
              return;
            }
            onSwitch(b.name);
          }}
        >
          <span data-testid="branch-picker-item-check" className="inline-block w-4">
            {b.is_current ? <Check className="size-3.5 text-pine" /> : null}
          </span>
          <span className="flex-1">{b.name}</span>
          {!b.is_current && (
            <button
              type="button"
              aria-label={`Delete branch ${b.name}`}
              className="ml-2 rounded p-0.5 opacity-60 hover:bg-red-100 hover:opacity-100"
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
                onDelete(b.name);
              }}
            >
              <Trash2 className="size-3 text-red-600" />
            </button>
          )}
        </DropdownMenuItem>
      ))}
    </>
  );
}

export function BranchMenuContent({
  branches,
  onSwitch,
  onDelete,
  onCreate,
  onMergeRequested,
  onCherryPickRequested,
}: BranchMenuContentProps) {
  const nonCurrent = (branches ?? []).filter((b) => !b.is_current);
  return (
    <DropdownMenuContent data-testid="branch-picker-menu" align="start" className="min-w-[14rem]">
      <DropdownMenuLabel>Switch to branch</DropdownMenuLabel>
      {branches === null ? (
        <DropdownMenuItem disabled>
          <span className="text-stone-400">Loading branches…</span>
        </DropdownMenuItem>
      ) : branches.length === 0 ? (
        <DropdownMenuItem disabled>
          <span className="text-stone-400">No local branches</span>
        </DropdownMenuItem>
      ) : (
        <BranchListItems branches={branches} onSwitch={onSwitch} onDelete={onDelete} />
      )}
      <DropdownMenuSeparator />
      <DropdownMenuItem data-testid="branch-picker-create" onSelect={onCreate}>
        <Plus className="size-3.5" />+ Create branch…
      </DropdownMenuItem>

      {nonCurrent.length > 0 && (
        <>
          <DropdownMenuSeparator />
          <DropdownMenuLabel data-testid="branch-picker-merge-sub">
            Merge into current
          </DropdownMenuLabel>
          {nonCurrent.map((b) => (
            <DropdownMenuItem
              key={`merge-${b.name}`}
              data-testid={`branch-picker-merge-${b.name}`}
              onSelect={() => onMergeRequested?.(b.name)}
            >
              <GitMerge className="size-3.5" />
              {b.name}
            </DropdownMenuItem>
          ))}
        </>
      )}

      <DropdownMenuSeparator />
      <DropdownMenuItem
        data-testid="branch-picker-cherry-pick"
        onSelect={() => onCherryPickRequested?.()}
      >
        <CornerUpRight className="size-3.5" />
        Cherry-pick…
      </DropdownMenuItem>
    </DropdownMenuContent>
  );
}
