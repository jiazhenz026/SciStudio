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
}

export function ToolbarButton({
  icon: Icon,
  label,
  shortcut,
  disabled,
  variant = "toolbar",
  iconClassName,
  onClick,
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
        >
          <Icon className={iconClassName ? `size-3.5 ${iconClassName}` : "size-3.5"} />
          {label}
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
