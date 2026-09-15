/**
 * ADR-055 Spec 4 — the capability-gated controls in the toolbar
 * (`docs/specs/adr-055-enterprise-support.md`, FR-004, FR-005, FR-007, FR-015).
 *
 * The open-source frontend carries the enterprise UI itself, inert by default:
 * each control renders only when the backend declared its capability, and with
 * none declared this renders nothing at all. They sit outside the toolbar's
 * scrolling area so the signed-in user stays visible on a narrow window.
 */

import { getCapabilities } from "../../lib/capabilities";
import { IdentityChrome } from "./IdentityChrome";
import { TransferUpload } from "./TransferUpload";
import { UpdateNotice } from "./UpdateNotice";

export function EnterpriseToolbarControls({ projectOpen }: { projectOpen: boolean }) {
  const { identity, transfer, update } = getCapabilities();
  if (identity === null && transfer === null && update === null) return null;
  return (
    <div className="flex shrink-0 items-center gap-2" data-testid="enterprise-toolbar">
      {update !== null ? <UpdateNotice update={update} /> : null}
      {transfer !== null ? <TransferUpload projectOpen={projectOpen} /> : null}
      {identity !== null ? <IdentityChrome identity={identity} /> : null}
    </div>
  );
}
