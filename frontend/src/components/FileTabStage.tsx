/**
 * The centre stage for an open file tab (#2361).
 *
 * Every file gets Monaco. A markdown file gets Monaco *and* a live preview
 * beside it, because a `.md` tab is the one case where the raw text on screen
 * is not what the file says. `tabHelpers` already classifies `.md` as
 * `language: "markdown"`, so no new signal is needed to tell the two apart.
 *
 * The preview reads `tab.content`, which `CodeEditor` writes into the store on
 * every keystroke, so it follows typing with nothing else wired up.
 *
 * The split can be closed. That choice is a persisted UI-store flag rather than
 * local state so it survives a tab switch and a reload, and while it is closed
 * the editor carries a Preview button — a Hide with no way back would be a bug,
 * not a preference.
 */

import { useAppStore } from "../store";
import type { FileTab } from "../store/types";
import { PanelRightOpen } from "lucide-react";

import { CodeEditor } from "./CodeEditor";
import { MarkdownPane } from "./CodeEditor.parts/MarkdownPane";
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "./ui/resizable";

export interface FileTabStageProps {
  tab: FileTab;
  onContentChange: (content: string) => void;
  onSave: () => void;
}

export function FileTabStage({ tab, onContentChange, onSave }: FileTabStageProps) {
  const markdownPreviewVisible = useAppStore((state) => state.markdownPreviewVisible);
  const toggleMarkdownPreview = useAppStore((state) => state.toggleMarkdownPreview);

  const editor = <CodeEditor tab={tab} onContentChange={onContentChange} onSave={onSave} />;

  if (tab.language !== "markdown") return editor;

  /*
   * The editor keeps the same ancestor chain whether the preview is shown or
   * hidden: group > panel > CodeEditor. Only the preview panel is conditional.
   * If the toggle swapped the stage root between a <div> and the group, React
   * would remount CodeEditor, and @monaco-editor/react disposes the model on
   * unmount (keepCurrentModel defaults to false) — the undo stack and view
   * state would go with it for what is only a layout change.
   */
  return (
    <div className="relative h-full w-full" data-testid="file-tab-stage">
      <ResizablePanelGroup className="h-full w-full min-h-0" orientation="horizontal">
        <ResizablePanel defaultSize="50%" minSize="20%">
          {editor}
        </ResizablePanel>
        {markdownPreviewVisible && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize="50%" minSize="20%">
              {/*
               * Keyed by tab so a switch between two markdown files starts the
               * preview on the new file rather than holding the old one on screen
               * for the length of one debounce.
               */}
              <MarkdownPane key={tab.id} onHide={toggleMarkdownPreview} source={tab.content} />
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>
      {!markdownPreviewVisible && (
        <button
          aria-label="Show the markdown preview"
          className="absolute right-3 top-2 z-10 flex items-center gap-1 rounded-full border border-stone-600 bg-stone-800/90 px-2 py-0.5 text-xs text-stone-300 transition hover:border-stone-400 hover:text-white"
          data-testid="markdown-preview-show"
          onClick={toggleMarkdownPreview}
          title="Show the markdown preview"
          type="button"
        >
          <PanelRightOpen className="h-3 w-3" />
          Preview
        </button>
      )}
    </div>
  );
}

export default FileTabStage;
