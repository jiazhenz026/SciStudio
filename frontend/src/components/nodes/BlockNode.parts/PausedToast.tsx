// Extracted from BlockNode.tsx as part of the #1422 god-file split.
// PausedToast — shown in the BlockNode footer when an AppBlock enters the
// PAUSED state. Surfaces the configured output directory and a "Copy" button
// so the user can paste the path into a terminal / file explorer to drop the
// expected output files for the block to resume.

import { useRef, useState } from "react";

export function PausedToast({ outputDir }: { outputDir: string }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = () => {
    if (outputDir) void navigator.clipboard.writeText(outputDir);
    setCopied(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="mt-1 flex items-center gap-1 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] text-amber-700">
      <span className="min-w-0 flex-1 truncate" title={outputDir}>
        Save outputs to: {outputDir || "(exchange dir)"}
      </span>
      {outputDir && (
        <button
          type="button"
          className="nodrag shrink-0 rounded border border-amber-300 bg-white px-1 py-0.5 text-[10px] text-amber-700 hover:bg-amber-50"
          title="Copy output path"
          onClick={handleCopy}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      )}
    </div>
  );
}
