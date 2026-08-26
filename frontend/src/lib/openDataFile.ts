/**
 * Open a project data file in a preview tab, asking which type when the
 * extension is ambiguous (#2112).
 *
 * Shared by the Data tree's double-click and the preview tab's "Change" chip,
 * so both reach the same three decisions in the same order: a remembered
 * choice opens the file without asking, a single candidate needs no question,
 * and anything else raises the picker.
 */

import { api } from "./api";
import { isOpenAsDialogMounted, requestOpenAs } from "../components/OpenAsDialog.parts/request";
import { useAppStore } from "../store";

export interface OpenDataFileOptions {
  /** Ask even when a choice is remembered — the "Change" affordance. */
  forceAsk?: boolean;
}

/**
 * Register *path* with the data catalog and open it in a preview tab.
 *
 * Returns silently when the person cancels the picker: nothing is registered
 * and no tab opens, which is what "cancel" has to mean for an action whose
 * only product is the tab.
 *
 * Unchecking "remember" in the picker clears an existing remembered choice for
 * the extension. That is the reset path — it lives on the same control that
 * set the preference, so undoing it needs no separate screen to find.
 */
export async function openDataFileAsPreview(
  projectId: string,
  path: string,
  fallbackName: string,
  options: OpenDataFileOptions = {},
): Promise<void> {
  const info = await api.getOpenAsCandidates({ projectId, path });

  let typeName: string | undefined;
  let remember = false;
  const ambiguous = info.remembered === null && info.candidates.length > 1;

  if ((options.forceAsk === true || ambiguous) && isOpenAsDialogMounted()) {
    const answer = await requestOpenAs({
      displayName: fallbackName,
      extension: info.extension,
      candidates: info.candidates,
      remembered: info.remembered,
    });
    if (answer === null) return;
    typeName = answer.typeName;
    remember = answer.remember;
    if (!remember && info.remembered !== null) {
      await api.clearOpenAsType({ projectId, extension: info.extension });
    }
  }

  const result = await api.registerDataPath({ projectId, path, typeName, remember });
  useAppStore.getState().openPreviewTab(
    {
      kind: "data_ref",
      ref: result.ref,
      recorded_type: result.recorded_type,
      type_chain: result.type_chain,
    },
    result.display_name ?? fallbackName,
    undefined,
    {
      path,
      extension: result.extension,
      typeName: result.recorded_type,
      remembered: result.remembered,
    },
  );
}
