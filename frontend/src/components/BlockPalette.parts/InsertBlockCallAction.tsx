/**
 * ADR-054 spec 4 (T-015) — the palette card's insert-call action (FR-031).
 *
 * Mounts in the same action row as ADR-053's "Promote to My Library"
 * (`BlockDetailPopover`'s `actions`), and follows the same rule that entry
 * point set: **hidden, not disabled**. With no Explore tab active there is no
 * notebook to write into, and a control that is only ever greyed out would be
 * a worse card for every user who never opens one — so the action returns
 * `null` and the card is byte-identical to today's.
 *
 * The insert goes through `POST /api/explore/sessions/{id}/cells` with
 * `after` set to the session's current cell, which is FR-031's "after the
 * current cell". The cells the response carries are what the slice is then
 * written from; nothing here guesses where the new cell landed.
 */

import { useCallback, useState } from "react";

import { exploreApi } from "../../lib/api/explore";
import { useAppStore } from "../../store";
import type { BlockSummary } from "../../types/api";

import { activeExploreCurrentCell, activeExploreSessionId, blockCallSource } from "./exploreCall";

export interface InsertBlockCallActionProps {
  block: BlockSummary;
}

export function InsertBlockCallAction({ block }: InsertBlockCallActionProps) {
  const sessionId = useAppStore(activeExploreSessionId);
  const currentCell = useAppStore(activeExploreCurrentCell);
  const applyExploreCells = useAppStore((state) => state.applyExploreCells);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const insert = useCallback(async () => {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const response = await exploreApi.insertExploreCell(
        sessionId,
        blockCallSource(block),
        currentCell,
      );
      applyExploreCells(sessionId, response.cells);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }, [applyExploreCells, block, currentCell, sessionId]);

  if (!sessionId) return null;

  return (
    <span className="flex flex-col gap-1">
      <button
        className="toolbar-button w-full text-left"
        data-testid="palette-insert-block-call"
        disabled={busy}
        onClick={() => void insert()}
        type="button"
      >
        {busy ? "Inserting…" : "Insert call into notebook"}
      </button>
      {error ? (
        <span className="text-[11px] text-red-700" data-testid="palette-insert-block-call-error">
          {error}
        </span>
      ) : null}
    </span>
  );
}
