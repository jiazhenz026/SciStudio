/**
 * ADR-036 §3.1 — Monaco-backed code editor for file tabs.
 *
 * SKELETON (S36): renders a placeholder div. The Monaco import is
 * intentionally NOT wired up yet — Phase 2B (I36b) does that. The
 * placeholder still satisfies the type-check + render contract so
 * App.tsx can route to this component once the kind-switch lands.
 *
 * Implementation plan (per ADR-036 §3.1, mirror xterm pattern at
 *   ``frontend/src/components/AIChat/TerminalView.tsx:76-88``):
 *   1. Lazy-load `@monaco-editor/react` inside a `useEffect` so the
 *      ~600 KB chunk does not enter the workflow-canvas cold start.
 *      DO NOT use a static `import` — the bundle MUST stay
 *      out of the main chunk.
 *   2. Mount the editor on `containerRef.current`, dispose on unmount
 *      (mirror TerminalView's cancellation flag pattern).
 *   3. Wire props:
 *        - tab.content              → editor model value
 *        - tab.language             → editor language
 *        - tab.readOnly             → editor.updateOptions({readOnly})
 *        - onContentChange(value)   → debounce 600 ms → POST
 *                                     /api/lint/python (when language ===
 *                                     "python") → setModelMarkers(...)
 *        - onSave()                 → Ctrl+S inside the editor + the
 *                                     800 ms idle auto-save in App.tsx
 *
 * Edge cases:
 *   - Container unmount mid-load: bail with the cancelled flag.
 *   - tab.readOnly flips at runtime: re-call updateOptions.
 *   - Language flip: editor.setModelLanguage on the existing model.
 *
 * Test plan (vitest, must be added by I36b):
 *   - renders without crashing for a python tab
 *   - mocks `@monaco-editor/react` and asserts onChange wires through
 *   - lint debounce: 5 rapid edits → exactly 1 POST after 600 ms
 *   - read-only flag passed through to editor options
 *   - Ctrl+S triggers onSave
 *
 * References: ADR-036 §3.1, §3.3 (lint debounce), §3.7 (Ctrl+S);
 * existing lazy-import pattern at TerminalView.tsx:76-88.
 */

import { useRef } from "react";

import type { FileTab } from "../store/types";

export interface CodeEditorProps {
  tab: FileTab;
  /** Called on every content change. Phase 2B debounces lint + save here. */
  onContentChange: (content: string) => void;
  /** Called when the user invokes save (Ctrl+S, or auto-save timer fires). */
  onSave: () => void;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function CodeEditor({ tab, onContentChange, onSave }: CodeEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // TODO(ADR-036 I36b): lazy-import @monaco-editor/react here, mount the
  // editor on containerRef, wire onContentChange + onSave + lint debounce.
  // See the comment block at the top of this file for the full plan.

  return (
    <div
      ref={containerRef}
      className="flex h-full w-full items-center justify-center text-xs text-stone-400"
      data-testid="code-editor-skeleton"
    >
      {/* Skeleton placeholder — Phase 2B replaces this with the Monaco mount. */}
      Code editor placeholder ({tab.filePath}). Monaco wiring lands in Phase 2B.
    </div>
  );
}

export default CodeEditor;
