// Extracted from App.tsx as part of the #1422 god-file split.
//
// AppLevelMergeFlow — app-level MergeFlow mount (ADR-039 §3.5, issue #975).
//
// Wraps the gitSlice subscription so the App component itself does not
// re-render on every `mergeFlowSource` change. Driven by
// `gitSlice.mergeFlowSource` + `gitSlice.mergeFlowProjectId`. Mounted
// outside the `{currentProject ? (...)}` ternary so the modal's
// close-guard survives project-switch and project-close events during
// mid-conflict resolution.
//
// Visibility gate (#975 Codex P1 on PR #980): the modal renders only
// when the active project ID matches the one stamped at modal-open
// time. If the user switches to a different project mid-conflict, the
// modal hides (state preserved) so MergeFlow's Complete/Abort actions
// cannot be routed to the wrong backend project context. Switching
// back to the original project re-shows the modal in its in-flight
// state. Closing the modal (via Abort) clears `mergeFlowProjectId`
// along with `mergeFlowSource` via the slice setter.

import { MergeFlow } from "../components/Git/MergeFlow";
import { useAppStore } from "../store";

export function AppLevelMergeFlow() {
  const mergeFlowSource = useAppStore((s) => s.mergeFlowSource);
  const mergeFlowProjectId = useAppStore((s) => s.mergeFlowProjectId);
  const currentProject = useAppStore((s) => s.currentProject);
  const setMergeFlowSource = useAppStore((s) => s.setMergeFlowSource);
  const openFileTab = useAppStore((s) => s.openFileTab);
  // Only render when the active project matches the one that opened
  // the modal. Different project → hide (state preserved). Same
  // project (or modal closed) → render normally.
  const projectMatches = mergeFlowProjectId === null || mergeFlowProjectId === currentProject?.id;
  return (
    <MergeFlow
      sourceBranch={mergeFlowSource ?? ""}
      isOpen={mergeFlowSource !== null && projectMatches}
      onClose={() => setMergeFlowSource(null)}
      onOpenFile={(path) => {
        openFileTab(path);
      }}
    />
  );
}
