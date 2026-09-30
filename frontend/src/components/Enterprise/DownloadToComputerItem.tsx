/**
 * ADR-055 Spec 4 FR-005 — "Download to this computer" for one project file.
 *
 * A context-menu item that appears only when the `transfer` capability is on
 * and the item is a file. It sends the browser to the edition's download
 * route: the capability's template with `{path}` replaced by the URL-encoded
 * project-relative path, resolved under the service prefix. The open-source
 * edition implements no download route; it only follows the one declared.
 */

import { getCapabilities } from "../../lib/capabilities";
import { buildDownloadUrl, triggerDownload } from "./enterpriseApi";

export interface DownloadableItem {
  /** File name, used as the saved file's suggested name. */
  name: string;
  /** Project-relative path, `/`-separated. */
  path: string;
  type: "file" | "directory";
}

export function DownloadToComputerItem({
  item,
  onDone,
}: {
  item: DownloadableItem;
  onDone: () => void;
}) {
  const { transfer } = getCapabilities();
  if (transfer === null || item.type !== "file") return null;
  return (
    <button
      className="w-full px-4 py-1.5 text-left text-xs text-stone-700 hover:bg-stone-100"
      data-testid="enterprise-download"
      onClick={() => {
        triggerDownload(buildDownloadUrl(transfer, item.path), item.name);
        onDone();
      }}
      type="button"
    >
      Download to this computer
    </button>
  );
}
