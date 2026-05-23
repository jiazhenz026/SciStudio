/**
 * Hook that registers / disposes ConflictMarkerDecoration on the Monaco
 * editor whenever the editing tab enters / leaves a git-merge conflict
 * state (ADR-039 §3.5a).
 *
 * Extracted in #1413 so the main CodeEditor function stays under 150 lines.
 */
import { useEffect } from "react";

import { registerConflictDecorations, resolveRegionText } from "../Git/ConflictMarkerDecoration";

export interface UseConflictDecorationsOpts {
  isInConflict: boolean;
  editorReady: boolean;
  filePath: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  editorRef: React.MutableRefObject<any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  monacoRef: React.MutableRefObject<any>;
}

export function useConflictDecorations({
  isInConflict,
  editorReady,
  filePath,
  editorRef,
  monacoRef,
}: UseConflictDecorationsOpts) {
  useEffect(() => {
    if (!isInConflict) return;
    // Codex P1 (PR #945): re-run after Monaco mounts. `editorReady` is
    // set inside `handleEditorMount`, which guarantees both refs are
    // populated by the time this branch is reached.
    if (!editorReady) return;
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;
    let dispose: (() => void) | null = null;
    try {
      dispose = registerConflictDecorations(editor, monaco, (action, region) => {
        // D39-2.4b: splice the chosen text into the Monaco model. Uses
        // `pushEditOperations` so the change participates in Monaco's
        // undo stack — the user can Ctrl+Z to revert a misclicked
        // "Accept Both" without losing the conflict markers.
        try {
          const model = editor.getModel();
          if (!model) return;
          const fullText = model.getValue();
          const next = resolveRegionText(fullText, region, action);
          if (next === fullText) return;
          const fullRange = model.getFullModelRange();
          editor.executeEdits("conflict-resolution", [
            {
              range: fullRange,
              text: next,
              forceMoveMarkers: true,
            },
          ]);
        } catch (err) {
          console.warn("ConflictMarkerDecoration: failed to apply action", err);
        }
      });
    } catch (err) {
      console.warn("ConflictMarkerDecoration failed to register:", err);
    }
    return () => {
      if (dispose) {
        try {
          dispose();
        } catch {
          /* ignore */
        }
      }
    };
  }, [isInConflict, filePath, editorReady, editorRef, monacoRef]);
}
