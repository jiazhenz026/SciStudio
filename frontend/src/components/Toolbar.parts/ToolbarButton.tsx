/**
 * Tooltip-wrapped toolbar button used by Toolbar groups. Extracted in
 * #1413.
 */
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export interface ToolbarButtonProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  shortcut?: string;
  disabled?: boolean;
  variant?: "toolbar" | "toolbar-dark";
  iconClassName?: string;
  onClick: () => void;
  /**
   * ADR-053 (#2057) — tutorial highlight target id, forwarded to the rendered
   * button as `data-tutorial-target`.
   *
   * An explicit prop rather than a rest spread: this component destructures a
   * closed prop list, so an attribute written on `<ToolbarButton>` would be
   * dropped without a word and the highlight would silently point at nothing.
   * Naming it makes the one button that needs it typed and greppable.
   */
  dataTutorialTarget?: string;
}

export function ToolbarButton({
  icon: Icon,
  label,
  shortcut,
  disabled,
  variant = "toolbar",
  iconClassName,
  onClick,
  dataTutorialTarget,
}: ToolbarButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant={variant}
          size="toolbar"
          disabled={disabled}
          onClick={onClick}
          type="button"
          aria-label={label}
          data-tutorial-target={dataTutorialTarget}
        >
          <Icon className={iconClassName ? `size-3.5 ${iconClassName}` : "size-3.5"} />
          <span className="hidden xl:inline">{label}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        <p>
          {label}
          {shortcut ? <span className="ml-2 text-xs opacity-70">{shortcut}</span> : null}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}
