/*
 * frontend/src/components/Lineage/BlockExecutionCard.tsx — ADR-038 §3.8 per-block
 * ===============================================================================
 *
 * SKELETON ONLY. Function body throws `new Error("TODO: D38-2.4c — ...")`.
 *
 * Purpose
 * -------
 * Expandable card representing one row from `block_executions` JOIN block_io
 * JOIN data_objects (the result of the SQL in ADR-038 §3.7 Q4b). Collapsed
 * by default — shows block_id, type, version, duration, termination. When
 * expanded shows resolved params (block_config_resolved) + inputs + outputs.
 *
 * Props
 * -----
 *
 *   interface BlockExecutionCardProps {
 *     execution: LineageBlockExecution;
 *   }
 *
 * State consumed from store
 * -------------------------
 *   - expandedBlockExecutionIds (string[]) — to decide collapsed/expanded
 *   - toggleBlockExecutionExpanded(id)
 *
 * Layout markup pseudocode (vitest selectors)
 * -------------------------------------------
 *
 *   <article
 *     className="rounded-2xl border border-stone-200 bg-white"
 *     data-testid={`block-execution-card-${exec.block_execution_id}`}
 *   >
 *     <button
 *       type="button"
 *       className="flex w-full items-center gap-3 px-4 py-3 text-left"
 *       aria-expanded={expanded}
 *       aria-controls={`block-card-body-${exec.block_execution_id}`}
 *       data-testid={`block-execution-card-toggle-${exec.block_execution_id}`}
 *       onClick={() => toggleBlockExecutionExpanded(exec.block_execution_id)}
 *     >
 *       <TerminationIcon termination={exec.termination} />
 *       <span className="font-medium text-ink">{exec.block_id}</span>
 *       <span className="text-xs text-stone-500">
 *         {exec.block_type} · v{exec.block_version}
 *       </span>
 *       <span className="ml-auto text-xs text-stone-500">
 *         {formatDuration(exec)}
 *       </span>
 *     </button>
 *
 *     {expanded && (
 *       <div
 *         className="border-t border-stone-200 px-4 py-3"
 *         id={`block-card-body-${exec.block_execution_id}`}
 *         data-testid={`block-execution-card-body-${exec.block_execution_id}`}
 *       >
 *         <section data-testid="block-card-params">
 *           <h5 className="text-xs font-semibold uppercase tracking-wide text-stone-500">
 *             Resolved parameters
 *           </h5>
 *           <pre className="mt-1 max-h-[160px] overflow-auto rounded bg-stone-50 p-2 text-[11px]">
 *             {JSON.stringify(exec.block_config_resolved, null, 2)}
 *           </pre>
 *         </section>
 *
 *         <section className="mt-3" data-testid="block-card-inputs">
 *           <h5 className="...">Inputs ({exec.inputs.length})</h5>
 *           {exec.inputs.length === 0 ? (
 *             <p className="text-xs text-stone-500">(none)</p>
 *           ) : (
 *             <ul>
 *               {exec.inputs.map((io) => (
 *                 <li key={`${io.port_name}-${io.position}-${io.object_id}`}
 *                     data-testid={`block-card-input-${io.object_id}`}>
 *                   <code>{io.port_name}[{io.position}]</code>
 *                   <span>{io.type_name}</span>
 *                   <code className="text-stone-500">{io.object_id.slice(0,8)}</code>
 *                   {io.storage_path && <span className="text-stone-500">{io.storage_path}</span>}
 *                 </li>
 *               ))}
 *             </ul>
 *           )}
 *         </section>
 *
 *         <section className="mt-3" data-testid="block-card-outputs">
 *           <h5>Outputs ({exec.outputs.length})</h5>
 *           ... (same as inputs, with data-testid="block-card-output-...") ...
 *         </section>
 *
 *         {exec.termination === "error" && exec.termination_detail && (
 *           <section className="mt-3 rounded bg-rose-50 p-2"
 *                    data-testid="block-card-error">
 *             <h5 className="text-xs font-semibold text-rose-700">Error</h5>
 *             <p className="text-xs text-rose-700">{exec.termination_detail}</p>
 *           </section>
 *         )}
 *       </div>
 *     )}
 *   </article>
 *
 * TerminationIcon mapping
 * -----------------------
 *   completed → "✓" (text-emerald-600)
 *   error     → "✗" (text-rose-600)
 *   cancelled → "⊘" (text-stone-500)
 *   skipped   → "—" (text-stone-400)
 *
 *   Same accessibility pattern as RunsList's StatusIcon (aria-hidden +
 *   sr-only sibling).
 *
 * Skipped block special-case (ADR-038 §3.6a)
 * ------------------------------------------
 * "Run from here" creates a new run whose execute_from_block_id is the
 * resume block. Per §3.6a, blocks the engine actually skipped (upstream of
 * resume block) get NO row in block_executions. So this component never
 * sees them. The greyed-out treatment for skipped blocks lives in the
 * canvas DAG renderer, not here.
 *
 * However, if a future schema iteration adds termination="skipped" rows
 * (e.g. conditional branches), the mapping above still works.
 *
 * Copy strings (English, freeze)
 * ------------------------------
 *   "Resolved parameters"
 *   "Inputs (N)" / "Outputs (N)"
 *   "(none)" — when inputs.length === 0 OR outputs.length === 0
 *   "Error" — heading above termination_detail
 *
 * Accessibility
 * -------------
 *   - aria-expanded on the toggle button
 *   - aria-controls pointing to the body div's id
 *   - the body div has matching id
 *   - Enter / Space already work for a <button> (no extra keyboard handler)
 *   - When error, the rose-50 section is NOT a live region — it's static
 *     content. No aria-live needed (the user clicked to reveal it).
 *
 * Edge cases
 * ----------
 *   1. block_config_resolved === {}: render "{}" pre block, NOT "(none)" —
 *      empty config is a valid state, not missing data.
 *   2. block_version === "unknown": ADR §3.3 says registration fails loudly
 *      on missing version, so this should never appear. If it does (e.g.
 *      a pre-#934 run from a stale DB), render version="unknown" verbatim.
 *   3. exec.outputs has a Collection port: each item is one row (ADR §3.1
 *      Collection unrolling). position increments 0,1,2,... Display them
 *      as separate rows; the IMPL agent may optionally render a "+N more"
 *      collapse for collections >10 items, but v1 ships flat.
 *   4. storage_path is null OR empty string: omit it from the row.
 *   5. finished_at is null (block still running OR cancelled mid-flight):
 *      duration shows as "—".
 *
 * Test plan (no dedicated test file — covered via RunDetail.test.tsx)
 * ------------------------------------------------------------------
 * The dispatch only requires LineageTab, RunsList, RunDetail tests +
 * lineageSlice test. BlockExecutionCard's behavior is exercised through
 * RunDetail.test.tsx (which renders a card and toggles its expanded state).
 */

import type { ReactElement } from "react";

import { useAppStore } from "../../store";
import type {
  LineageBlockExecution,
  LineageBlockTermination,
} from "../../store/lineageSlice";

export interface BlockExecutionCardProps {
  execution: LineageBlockExecution;
}

const TERMINATION_GLYPH: Record<LineageBlockTermination, string> = {
  completed: "✓",
  error: "✗",
  cancelled: "⊘",
  skipped: "—",
};

const TERMINATION_COLOR: Record<LineageBlockTermination, string> = {
  completed: "text-emerald-600",
  error: "text-rose-600",
  cancelled: "text-stone-500",
  skipped: "text-stone-400",
};

function TerminationIcon({
  termination,
}: {
  termination: LineageBlockTermination;
}): ReactElement {
  return (
    <>
      <span aria-hidden="true" className={TERMINATION_COLOR[termination]}>
        {TERMINATION_GLYPH[termination]}
      </span>
      <span className="sr-only">{termination}</span>
    </>
  );
}

function formatDuration(exec: LineageBlockExecution): string {
  const ms = exec.duration_ms;
  if (ms === null) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const totalSeconds = Math.floor(ms / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}m ${s}s`;
}

export function BlockExecutionCard({
  execution: exec,
}: BlockExecutionCardProps): ReactElement {
  const expanded = useAppStore((s) =>
    s.expandedBlockExecutionIds.includes(exec.block_execution_id),
  );
  const toggle = useAppStore((s) => s.toggleBlockExecutionExpanded);
  const bodyId = `block-card-body-${exec.block_execution_id}`;

  return (
    <article
      className="rounded-2xl border border-stone-200 bg-white"
      data-testid={`block-execution-card-${exec.block_execution_id}`}
    >
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        aria-expanded={expanded}
        aria-controls={bodyId}
        data-testid={`block-execution-card-toggle-${exec.block_execution_id}`}
        onClick={() => toggle(exec.block_execution_id)}
      >
        <TerminationIcon termination={exec.termination} />
        <span className="font-medium text-ink">{exec.block_id}</span>
        <span className="text-xs text-stone-500">
          {exec.block_type} · v{exec.block_version}
        </span>
        <span className="ml-auto text-xs text-stone-500">
          {formatDuration(exec)}
        </span>
      </button>

      {expanded && (
        <div
          className="border-t border-stone-200 px-4 py-3"
          id={bodyId}
          data-testid={`block-execution-card-body-${exec.block_execution_id}`}
        >
          <section data-testid="block-card-params">
            <h5 className="text-xs font-semibold uppercase tracking-wide text-stone-500">
              Resolved parameters
            </h5>
            <pre className="mt-1 max-h-[160px] overflow-auto rounded bg-stone-50 p-2 text-[11px]">
              {JSON.stringify(exec.block_config_resolved, null, 2)}
            </pre>
          </section>

          <section className="mt-3" data-testid="block-card-inputs">
            <h5 className="text-xs font-semibold uppercase tracking-wide text-stone-500">
              Inputs ({exec.inputs.length})
            </h5>
            {exec.inputs.length === 0 ? (
              <p className="text-xs text-stone-500">(none)</p>
            ) : (
              <ul className="mt-1 space-y-1 text-xs">
                {exec.inputs.map((io) => (
                  <li
                    key={`${io.port_name}-${io.position}-${io.object_id}`}
                    className="flex items-center gap-2"
                    data-testid={`block-card-input-${io.object_id}`}
                  >
                    <code className="text-stone-700">
                      {io.port_name}[{io.position}]
                    </code>
                    <span className="text-stone-500">{io.type_name}</span>
                    <code className="text-stone-500">
                      {io.object_id.slice(0, 8)}
                    </code>
                    {io.storage_path && (
                      <span className="ml-auto text-stone-500">
                        {io.storage_path}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mt-3" data-testid="block-card-outputs">
            <h5 className="text-xs font-semibold uppercase tracking-wide text-stone-500">
              Outputs ({exec.outputs.length})
            </h5>
            {exec.outputs.length === 0 ? (
              <p className="text-xs text-stone-500">(none)</p>
            ) : (
              <ul className="mt-1 space-y-1 text-xs">
                {exec.outputs.map((io) => (
                  <li
                    key={`${io.port_name}-${io.position}-${io.object_id}`}
                    className="flex items-center gap-2"
                    data-testid={`block-card-output-${io.object_id}`}
                  >
                    <code className="text-stone-700">
                      {io.port_name}[{io.position}]
                    </code>
                    <span className="text-stone-500">{io.type_name}</span>
                    <code className="text-stone-500">
                      {io.object_id.slice(0, 8)}
                    </code>
                    {io.storage_path && (
                      <span className="ml-auto text-stone-500">
                        {io.storage_path}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {exec.termination === "error" && exec.termination_detail && (
            <section
              className="mt-3 rounded bg-rose-50 p-2"
              data-testid="block-card-error"
            >
              <h5 className="text-xs font-semibold text-rose-700">Error</h5>
              <p className="text-xs text-rose-700">{exec.termination_detail}</p>
            </section>
          )}
        </div>
      )}
    </article>
  );
}
