import { GripVertical } from "lucide-react";
import { Group, Panel, Separator } from "react-resizable-panels";

import { cn } from "@/lib/utils";

const ResizablePanelGroup = ({ className, ...props }: React.ComponentProps<typeof Group>) => (
  <Group className={cn("flex h-full w-full", className)} {...props} />
);

const ResizablePanel = Panel;

const ResizableHandle = ({
  withHandle,
  className,
  ...props
}: React.ComponentProps<typeof Separator> & {
  withHandle?: boolean;
}) => (
  <Separator
    className={cn(
      // react-resizable-panels v4 exposes the handle line direction via
      // ``aria-orientation`` (not ``data-orientation``, which the original
      // shadcn template targeted and which never existed on this version's
      // separator role). Top/bottom panel groups produce handles with
      // ``aria-orientation="horizontal"`` — a horizontal line you drag up/
      // down — so the override below targets that. Without this fix the
      // bottom-panel handle falls through to the default ``w-3`` vertical-
      // strip styling and renders as a tiny 12×24px pill at the left edge.
      "relative flex w-3 items-center justify-center bg-transparent transition-colors hover:bg-stone-200/60 after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:bg-border focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-offset-1 [&[aria-orientation=horizontal]]:h-3 [&[aria-orientation=horizontal]]:w-full [&[aria-orientation=horizontal]]:after:left-0 [&[aria-orientation=horizontal]]:after:top-1/2 [&[aria-orientation=horizontal]]:after:h-px [&[aria-orientation=horizontal]]:after:w-full [&[aria-orientation=horizontal]]:after:-translate-y-1/2 [&[aria-orientation=horizontal]]:after:translate-x-0 [&[aria-orientation=horizontal]>div]:rotate-90",
      className,
    )}
    {...props}
  >
    {withHandle && (
      <div className="z-10 flex h-6 w-4 items-center justify-center rounded-sm border bg-border/80 opacity-60 transition-opacity hover:opacity-100">
        <GripVertical className="h-3 w-3 text-stone-500" />
      </div>
    )}
  </Separator>
);

export { ResizablePanelGroup, ResizablePanel, ResizableHandle };
