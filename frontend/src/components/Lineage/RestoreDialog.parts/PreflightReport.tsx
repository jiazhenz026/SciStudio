/**
 * Preflight report for `RestoreDialog` — ADR-038 §3.6 checks as rendered.
 *
 * Successor to `ValidationWarnings` (#2033). The cards are unchanged; the
 * states around them are the point of the rewrite. The old component knew two
 * states, "warnings" and "clean", and fell into "clean" whenever the warning
 * arrays were empty — including the case where no check had been performed,
 * which was every case, because the endpoint did not exist.
 *
 * There are four distinct states here and they must stay distinct:
 *
 * - **failed** — the preflight request errored. Nothing is known.
 * - **unknown** — no run is recorded at this commit (a manual commit, or an
 *   `auto: pre-restore` one). There is nothing to compare against.
 * - **warnings** — a run was found and something moved.
 * - **clean** — a run was found and nothing moved. Only this one is green.
 *
 * When several workflows ran at the commit, every one of them was checked
 * (#2425); the report names them and labels each input change with the
 * workflow that read the file.
 */
import type { RestorePreflight } from "../../../types/lineage";

export interface PreflightReportProps {
  preflight: RestorePreflight | null;
  error: string | null;
}

function InputWarningsCard({
  warnings,
  showWorkflow,
}: {
  warnings: RestorePreflight["input_warnings"];
  showWorkflow: boolean;
}) {
  if (warnings.length === 0) return null;
  return (
    <div className="rounded bg-amber-50 p-3" data-testid="restore-dialog-input-warnings">
      <h4 className="text-sm font-semibold text-amber-800">
        Input file changes ({warnings.length})
      </h4>
      <ul className="mt-1 list-disc pl-5 text-xs text-amber-700">
        {warnings.map((w, i) => (
          <li key={`${w.path}-${i}`}>
            <code>{w.path}</code> — {w.reason}
            {showWorkflow && w.workflow_id ? (
              <span data-testid="restore-dialog-input-warning-workflow">
                {" "}
                (workflow <code>{w.workflow_id}</code>)
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function EnvWarningsCard({ warnings }: { warnings: RestorePreflight["env_warnings"] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="rounded bg-amber-50 p-3" data-testid="restore-dialog-env-warnings">
      <h4 className="text-sm font-semibold text-amber-800">
        Environment drift ({warnings.length})
      </h4>
      <ul className="mt-1 list-disc pl-5 text-xs text-amber-700">
        {warnings.map((w, i) => (
          <li key={`${w.package}-${i}`}>
            <code>{w.package}</code>: {w.old} → {w.new}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-amber-700">
        Restore does not roll these back — SciStudio, its packages, and your Python environment live
        outside the project folder. If the run failed because of one of these, restoring the files
        will not fix it.
      </p>
    </div>
  );
}

export function PreflightReport({ preflight, error }: PreflightReportProps) {
  if (error) {
    return (
      <section className="mt-4" data-testid="restore-dialog-preflight-failed">
        <p className="rounded bg-stone-100 p-3 text-sm text-stone-700">
          Could not check this version against your inputs and environment ({error}). The restore
          can still proceed.
        </p>
      </section>
    );
  }
  if (!preflight) return null;

  if (preflight.run_id === null) {
    return (
      <section className="mt-4" data-testid="restore-dialog-preflight-unknown">
        <p className="rounded bg-stone-100 p-3 text-sm text-stone-700">
          No run was recorded at this version, so there is nothing to compare your inputs and
          environment against. This is normal for a manually saved version.
        </p>
      </section>
    );
  }

  const workflows = (preflight.runs ?? []).map((run) => run.workflow_id);
  const multiWorkflow = workflows.length > 1;
  const clean = preflight.input_warnings.length === 0 && preflight.env_warnings.length === 0;
  return (
    <section className="mt-4 space-y-3" data-testid="restore-dialog-preflight">
      {multiWorkflow ? (
        <p className="text-xs text-stone-600" data-testid="restore-dialog-preflight-workflows">
          Checked the latest run of each of the {workflows.length} workflows recorded at this
          version: {workflows.join(", ")}.
        </p>
      ) : null}
      {clean ? (
        <p
          className="rounded bg-emerald-50 p-3 text-sm text-emerald-700"
          data-testid="restore-dialog-preflight-clean"
        >
          {multiWorkflow
            ? "Your input files and environment match the runs recorded at this version."
            : "Your input files and environment match the run that produced this version."}
        </p>
      ) : (
        <>
          <InputWarningsCard warnings={preflight.input_warnings} showWorkflow={multiWorkflow} />
          <EnvWarningsCard warnings={preflight.env_warnings} />
          <p className="text-xs text-stone-600">These are advisory. You can still restore.</p>
        </>
      )}
    </section>
  );
}
