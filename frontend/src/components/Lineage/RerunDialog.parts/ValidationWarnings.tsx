/**
 * Drift / validation warning section for RerunDialog. Extracted in #1413.
 */
import type { LineageRerunValidation } from "../../../types/lineage";

export interface ValidationWarningsProps {
  validation: LineageRerunValidation;
}

function InputWarningsCard({ warnings }: { warnings: LineageRerunValidation["input_warnings"] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="rounded bg-amber-50 p-3" data-testid="rerun-dialog-input-warnings">
      <h4 className="text-sm font-semibold text-amber-800">
        Input file changes ({warnings.length})
      </h4>
      <ul className="mt-1 list-disc pl-5 text-xs text-amber-700">
        {warnings.map((w, i) => (
          <li key={`${w.path}-${i}`}>
            <code>{w.path}</code> — {w.reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

function EnvWarningsCard({ warnings }: { warnings: LineageRerunValidation["env_warnings"] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="rounded bg-amber-50 p-3" data-testid="rerun-dialog-env-warnings">
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
    </div>
  );
}

export function ValidationWarnings({ validation }: ValidationWarningsProps) {
  const hasNoWarnings =
    validation.input_warnings.length === 0 && validation.env_warnings.length === 0;
  return (
    <section className="mt-4 space-y-3" data-testid="rerun-dialog-warnings">
      {hasNoWarnings ? (
        <p
          className="rounded bg-emerald-50 p-3 text-sm text-emerald-700"
          data-testid="rerun-dialog-warnings-clean"
        >
          No drift detected. Re-running will reproduce the original results as closely as the
          current environment allows.
        </p>
      ) : (
        <>
          <InputWarningsCard warnings={validation.input_warnings} />
          <EnvWarningsCard warnings={validation.env_warnings} />
          <p className="text-xs text-stone-600">
            These warnings are advisory only. You can still proceed.
          </p>
        </>
      )}
    </section>
  );
}
