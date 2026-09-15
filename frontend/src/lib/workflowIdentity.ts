/**
 * #2394 — the workflow run identity the backend hands the editor.
 *
 * A workflow is identified by its FILE, not by the `id:` written inside the
 * YAML. `workflows/<stem>.yaml` is identified by `<stem>`; any other workflow
 * file (a subworkflow opened from a SubWorkflowBlock) by its project-relative
 * path in the single-segment "path form": `@` + the path components joined with
 * `@`, where `%` is written `%25` and `@` is written `%40` inside a component.
 * `subworkflows/qc.yaml` is `@subworkflows@qc.yaml`.
 *
 * The backend (`scistudio.workflow.identity`) owns the format; this module only
 * reads it, to label tabs and to keep path-form identities out of the project's
 * top-level workflow list. Save, run, cancel and events all use the identity
 * verbatim.
 */

const PATH_MARKER = "@";
const WORKFLOW_FILE = /\.(ya?ml)$/i;

function pathComponents(identity: string): string[] | null {
  if (!identity.startsWith(PATH_MARKER)) return null;
  const parts = identity
    .slice(PATH_MARKER.length)
    .split(PATH_MARKER)
    .map((part) =>
      part.replace(/%(25|40)/g, (_match, code: string) => (code === "25" ? "%" : "@")),
    );
  if (parts.some((part) => part === "" || part === "." || part === ".." || /[\\/]/.test(part))) {
    return null;
  }
  return WORKFLOW_FILE.test(parts[parts.length - 1]) ? parts : null;
}

/** Whether `identity` names a file outside `workflows/<stem>.yaml` (e.g. a subworkflow). */
export function isPathWorkflowIdentity(identity: string | null | undefined): boolean {
  return typeof identity === "string" && pathComponents(identity) !== null;
}

/**
 * A human label for a workflow identity: the stem itself, or for the path form
 * the file name without its `.yaml` / `.swf.yaml` suffix.
 */
export function workflowIdentityLabel(identity: string | null | undefined): string {
  if (!identity) return "";
  const parts = pathComponents(identity);
  if (parts === null) return identity;
  const base = parts[parts.length - 1];
  return base.replace(/\.(swf\.)?(ya?ml)$/i, "") || base;
}

/** The project-relative file a workflow identity names. */
export function workflowIdentityPath(identity: string): string {
  const parts = pathComponents(identity);
  return parts === null ? `workflows/${identity}.yaml` : parts.join("/");
}
