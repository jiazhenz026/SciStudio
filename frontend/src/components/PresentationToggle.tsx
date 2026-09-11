import { ArrowLeftRight } from "lucide-react";

import { isDesktopShell, setPresentation, usePresentation } from "../lib/presentation";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

export function PresentationToggle() {
  const isAi = usePresentation() === "ai";
  if (isDesktopShell()) return null;
  const label = isAi ? "Switch to full workbench" : "Switch to AI host layout";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={label}
          aria-pressed={isAi}
          data-testid="presentation-toggle"
          className="inline-flex shrink-0 items-center gap-2 rounded-full border border-stone-300 bg-white px-3 py-1.5 text-xs font-medium text-stone-600 hover:bg-stone-100"
          onClick={() => setPresentation(isAi ? "workbench" : "ai")}
        >
          <ArrowLeftRight className="size-4" aria-hidden="true" />
          <span className="hidden md:inline">{isAi ? "AI layout" : "Workbench"}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
