import { usePresentation } from "../lib/presentation";

interface AIBlockPresentationNoticeProps {
  blockType?: string;
  compact?: boolean;
}

/** Explain the AI Block interaction surface without inferring backend capabilities. */
export function AIBlockPresentationNotice({
  blockType,
  compact = false,
}: AIBlockPresentationNoticeProps) {
  const presentation = usePresentation();
  if (presentation !== "ai" || blockType !== "ai.agent") return null;

  if (compact) {
    return <span className="text-[10px] text-amber-800">Use Workbench</span>;
  }

  return (
    <div className="my-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
      <p className="font-semibold">Use Workbench for AI Block</p>
      <p className="mt-1 leading-relaxed">
        This block starts a local agent in AI Chat. AI layout hides that terminal, including its
        prompts and permission requests. Switch to Workbench to run and interact with this block. It
        does not use the AI host you are chatting with.
      </p>
    </div>
  );
}
