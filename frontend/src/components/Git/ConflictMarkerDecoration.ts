/**
 * ADR-039 §3.5a / §6 Phase 3 — Monaco decoration provider for git
 * conflict markers.
 *
 * ============================================================================
 * STRUCTURE (post-#1422 split)
 * ============================================================================
 *
 * This file is the orchestrator. The four collaborating modules under
 * `ConflictMarkerDecoration.parts/` hold the heavy lifting and let each
 * file stay below the 500-LOC ceiling enforced by `frontend/eslint.config.js`:
 *
 *   - `parts/types.ts`       — `ConflictRegion`, `ConflictAction` shapes
 *   - `parts/parser.ts`      — `parseConflictRegions`, `resolveRegionText`
 *   - `parts/widget.ts`      — inline action widget DOM factory
 *   - `parts/decorations.ts` — Monaco decoration descriptor builder
 *
 * Existing consumers continue to `import { parseConflictRegions, ... }
 * from "./ConflictMarkerDecoration"` — every public symbol is re-exported
 * below so no downstream file needed updates.
 *
 * ============================================================================
 * PURPOSE
 * ============================================================================
 *
 * When a git merge produces conflicts, git writes the conflicting files
 * in-place with the textual markers:
 *
 *   <<<<<<< HEAD
 *   ... current branch's version ...
 *   =======
 *   ... incoming branch's version ...
 *   >>>>>>> source-branch-name
 *
 * (Optionally, with `merge.conflictStyle=diff3`, a third section between
 *  `<<<<<<<` and `=======`:
 *
 *   <<<<<<< HEAD
 *   ... current ...
 *   ||||||| merged common ancestors
 *   ... base ...
 *   =======
 *   ... incoming ...
 *   >>>>>>> source
 *
 *  SciStudio does NOT enable diff3 by default in v1; we handle it
 *  gracefully if the user's git config is set this way.)
 *
 * This module registers Monaco decorations to:
 *
 *   1. Highlight the "current" section with a subtle green background.
 *   2. Highlight the "incoming" section with a subtle blue background.
 *   3. Render inline glyph-margin action buttons above each conflict:
 *        [Accept Current] [Accept Incoming] [Accept Both] [Manual edit]
 *   4. Number conflicts ("1 of 3", "2 of 3") in the glyph margin so the
 *      user can navigate.
 *
 * VS Code itself shipped with this exact UX for years before adding the
 * dedicated 3-way merge editor in 2022. We adopt the same model per
 * ADR-039 §3.5a "no new editor; no third-party 3-way merge component".
 *
 * ============================================================================
 * MONACO INTEGRATION CONTRACT
 * ============================================================================
 *
 * Monaco is loaded lazily by `CodeEditor.tsx` (see ADR-036 §3.1). This
 * module exposes:
 *
 *   registerConflictDecorations(
 *     editor:   monaco.editor.IStandaloneCodeEditor,
 *     monaco:   typeof import("monaco-editor"),
 *     onAction: (action: ConflictAction, region: ConflictRegion) => void,
 *   ): () => void                                // dispose function
 *
 * The caller (`CodeEditor.tsx`) invokes this AFTER the editor is mounted
 * AND `mergeInProgress?.conflicted_files.includes(activeFile)` is true.
 * The returned dispose function unregisters listeners + clears decorations
 * when the file leaves conflict state.
 *
 * ============================================================================
 * INTEGRATION
 * ============================================================================
 *
 *   - `CodeEditor.tsx`: registers on mount IF
 *     `gitSlice.mergeInProgress?.conflicted_files.includes(filePath)`.
 *     The dispose function is called on unmount or when the file leaves
 *     conflict state.
 *
 *   - `ConflictResolveView.tsx`: receives `ConflictAction` events via the
 *     `onAction` callback and dispatches `gitMergeStageFile(file)` on
 *     "Mark Resolved" after all regions are handled.
 *
 * ============================================================================
 */

import { buildDecorations } from "./ConflictMarkerDecoration.parts/decorations";
import { parseConflictRegions } from "./ConflictMarkerDecoration.parts/parser";
import type { ConflictAction, ConflictRegion } from "./ConflictMarkerDecoration.parts/types";
import { buildWidget } from "./ConflictMarkerDecoration.parts/widget";

// Re-exports preserve the pre-split public surface so every existing
// `import ... from "./ConflictMarkerDecoration"` site keeps compiling.
// `parseConflictRegions` is also imported locally above to drive
// `registerConflictDecorations`; `resolveRegionText` is consumed only
// by callers via this re-export.
export type { ConflictAction, ConflictRegion } from "./ConflictMarkerDecoration.parts/types";
export { parseConflictRegions, resolveRegionText } from "./ConflictMarkerDecoration.parts/parser";

/**
 * Register conflict-marker decorations + glyph-margin action widgets on
 * a Monaco editor instance.
 *
 * Layered behavior:
 *   1. Highlight the current section (green) + incoming section (blue)
 *      via `editor.deltaDecorations`.
 *   2. Mount one `IContentWidget` above each region with four buttons:
 *      Accept Current / Accept Incoming / Accept Both / Manual edit.
 *   3. On the editor's content-change event, re-parse and re-apply.
 *   4. The returned dispose function clears decorations + widgets + the
 *      change listener.
 *
 * The Monaco types are kept loose (`any`) to preserve the lazy-load
 * boundary from ADR-036 §3.1 (we cannot statically import `monaco-editor`
 * without breaking the bundle split).
 *
 * @param editor   - The Monaco IStandaloneCodeEditor (typed loose so we
 *                   stay behind the lazy-load boundary).
 * @param monaco   - The Monaco namespace, also typed loose.
 * @param onAction - Callback fired when the user clicks an inline
 *                   action button. The dispatcher (likely
 *                   `ConflictResolveView.tsx`) applies the text mutation
 *                   to the model.
 * @returns A dispose function that removes all decorations + listeners.
 */
export function registerConflictDecorations(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  editor: any,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  monaco: any,
  onAction: (action: ConflictAction, region: ConflictRegion) => void,
): () => void {
  if (!editor || !monaco) {
    return () => {};
  }
  const model = editor.getModel?.();
  if (!model) {
    return () => {};
  }

  let decorationIds: string[] = [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const widgets: any[] = [];

  function clearWidgets() {
    for (const w of widgets) {
      try {
        editor.removeContentWidget(w);
      } catch {
        /* ignore */
      }
    }
    widgets.length = 0;
  }

  function clearDecorations() {
    try {
      decorationIds = editor.deltaDecorations(decorationIds, []);
    } catch {
      decorationIds = [];
    }
  }

  function refresh() {
    clearWidgets();
    const text = model.getValue();
    const regions = parseConflictRegions(text);

    if (regions.length === 0) {
      clearDecorations();
      return;
    }

    const decorations = buildDecorations(regions, monaco);
    try {
      decorationIds = editor.deltaDecorations(decorationIds, decorations);
    } catch (err) {
      console.warn("ConflictMarkerDecoration: failed to set decorations", err);
    }

    regions.forEach((region, i) => {
      const widget = buildWidget(region, `${i + 1} of ${regions.length}`, monaco, onAction);
      try {
        editor.addContentWidget(widget);
        widgets.push(widget);
      } catch (err) {
        console.warn("ConflictMarkerDecoration: failed to add widget", err);
      }
    });
  }

  // Listen for content changes so the decorations follow user edits.
  let disposable: { dispose: () => void } | null = null;
  try {
    disposable = model.onDidChangeContent(() => {
      refresh();
    });
  } catch {
    disposable = null;
  }

  refresh();

  return function dispose() {
    try {
      disposable?.dispose();
    } catch {
      /* ignore */
    }
    clearWidgets();
    clearDecorations();
  };
}
