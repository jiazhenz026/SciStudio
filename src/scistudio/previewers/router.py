"""PreviewRouter — ADR-048 §3 / FR-003 / FR-004 / FR-005 resolution.

Resolves a :class:`PreviewTarget` to exactly one :class:`PreviewerSpec` or a
typed routing error.

The precedence order (highest first) is exactly ADR-048 §3 / spec FR-003:

1. project exact ``Collection[T]``
2. project exact ``T``
3. package exact ``Collection[T]``
4. package exact ``T``
5. project parent (walk the type chain general-ward, project tier)
6. package parent (walk the type chain general-ward, package tier)
7. core collection fallback
8. core base fallback
9. unknown / error

Specificity is driven by the target's ``type_chain`` (ordered general ->
specific). "Exact" means the spec's ``target_type`` equals the most specific
recorded type; "parent" means it equals an ancestor in the chain, with closer
ancestors preferred. Within one tier + specificity, the highest ``priority``
wins; an unresolved priority tie raises :class:`RoutingAmbiguityError`
(FR-004). A project explicit default previewer resolves a project-tier tie
(FR-005).
"""

from __future__ import annotations

import logging

from scistudio.previewers.models import (
    OwnerKind,
    PreviewerSpec,
    PreviewTarget,
    RoutingAmbiguityError,
    UnknownTargetError,
)
from scistudio.previewers.registry import PreviewerRegistry

logger = logging.getLogger(__name__)


class PreviewRouter:
    """Deterministic previewer resolver over a :class:`PreviewerRegistry`."""

    def __init__(self, registry: PreviewerRegistry) -> None:
        self._registry = registry

    def resolve(self, target: PreviewTarget) -> PreviewerSpec:
        """Return the single best previewer spec for *target* (FR-003).

        Raises :class:`RoutingAmbiguityError` on an unresolved priority tie
        within a tier+specificity and :class:`UnknownTargetError` when nothing
        matches (not even a core fallback).
        """
        specs = self._registry.all_specs()
        is_collection = target.is_collection
        # Type chain ordered specific -> general for "closest parent wins".
        chain = self._specificity_chain(target)
        most_specific = chain[0] if chain else ""

        # Tiers in precedence order. Each entry is (owner_kind, require_collection,
        # match_mode, type_to_match_resolver). We evaluate them top to bottom and
        # return the first non-empty winner.
        # ---- 1 & 2: project exact (collection then item) ----
        if is_collection:
            winner = self._pick(specs, OwnerKind.PROJECT, most_specific, want_collection=True, target=target)
            if winner is not None:
                return winner
        winner = self._pick(specs, OwnerKind.PROJECT, most_specific, want_collection=False, target=target)
        if winner is not None:
            return winner

        # ---- 3 & 4: package exact (collection then item) ----
        if is_collection:
            winner = self._pick(specs, OwnerKind.PACKAGE, most_specific, want_collection=True, target=target)
            if winner is not None:
                return winner
        winner = self._pick(specs, OwnerKind.PACKAGE, most_specific, want_collection=False, target=target)
        if winner is not None:
            return winner

        # ---- 5: project parent (closest ancestor first) ----
        for parent in chain[1:]:
            if is_collection:
                winner = self._pick(specs, OwnerKind.PROJECT, parent, want_collection=True, target=target)
                if winner is not None:
                    return winner
            winner = self._pick(specs, OwnerKind.PROJECT, parent, want_collection=False, target=target)
            if winner is not None:
                return winner

        # ---- 6: package parent (closest ancestor first) ----
        for parent in chain[1:]:
            if is_collection:
                winner = self._pick(specs, OwnerKind.PACKAGE, parent, want_collection=True, target=target)
                if winner is not None:
                    return winner
            winner = self._pick(specs, OwnerKind.PACKAGE, parent, want_collection=False, target=target)
            if winner is not None:
                return winner

        # ---- 7: core collection fallback ----
        if is_collection:
            winner = self._pick_core_fallback(specs, want_collection=True, target=target)
            if winner is not None:
                return winner

        # ---- 8: core base fallback (closest matching base in chain) ----
        for type_name in chain:
            winner = self._pick(specs, OwnerKind.CORE, type_name, want_collection=False, target=target)
            if winner is not None:
                return winner
        winner = self._pick_core_fallback(specs, want_collection=False, target=target)
        if winner is not None:
            return winner

        # ---- 9: unknown / error ----
        raise UnknownTargetError(
            f"No previewer matched target type {most_specific or target.recorded_type or '<unknown>'!r}",
            detail={"target": target.to_dict()},
        )

    # -- internals ----------------------------------------------------------

    def _specificity_chain(self, target: PreviewTarget) -> list[str]:
        """Return candidate type names ordered specific -> general.

        For a collection target we route on the *item* type chain so
        ``Collection[Image]`` resolves against ``Image`` -> ``Array`` -> ...
        """
        if target.is_collection:
            item = target.collection_item_type
            chain = list(reversed(target.type_chain)) if target.type_chain else []
            ordered = [item] if item else []
            for name in chain:
                if name and name not in ordered:
                    ordered.append(name)
            return [n for n in ordered if n]
        if target.type_chain:
            seen: list[str] = []
            for name in reversed(target.type_chain):
                if name and name not in seen:
                    seen.append(name)
            return seen
        return [target.recorded_type] if target.recorded_type else []

    def _pick(
        self,
        specs: list[PreviewerSpec],
        owner_kind: OwnerKind,
        type_name: str,
        *,
        want_collection: bool,
        target: PreviewTarget,
    ) -> PreviewerSpec | None:
        """Pick the winning spec for one (tier, type, collection) bucket.

        Highest priority wins; an unresolved priority tie raises ambiguity
        unless a project default resolves it (FR-004/FR-005).
        """
        if not type_name:
            return None
        candidates = [
            s
            for s in specs
            if s.owner_kind is owner_kind
            and s.target_type == type_name
            and bool(s.supports_collection) == want_collection
        ]
        return self._resolve_candidates(candidates, owner_kind, type_name, target)

    def _pick_core_fallback(
        self,
        specs: list[PreviewerSpec],
        *,
        want_collection: bool,
        target: PreviewTarget,
    ) -> PreviewerSpec | None:
        """Pick the generic core collection/base fallback (tiers 7 / 8 catch-all).

        Core fallbacks declare a sentinel ``target_type`` of ``"Collection"``
        (collection fallback) or ``"DataObject"`` (universal base fallback).
        """
        sentinel = "Collection" if want_collection else "DataObject"
        candidates = [
            s
            for s in specs
            if s.owner_kind is OwnerKind.CORE
            and s.target_type == sentinel
            and bool(s.supports_collection) == want_collection
        ]
        return self._resolve_candidates(candidates, OwnerKind.CORE, sentinel, target)

    def _resolve_candidates(
        self,
        candidates: list[PreviewerSpec],
        owner_kind: OwnerKind,
        type_name: str,
        target: PreviewTarget,
    ) -> PreviewerSpec | None:
        if not candidates:
            return None
        candidates = sorted(candidates, key=lambda s: (-s.priority, s.previewer_id))
        top_priority = candidates[0].priority
        top = [s for s in candidates if s.priority == top_priority]
        if len(top) == 1:
            return top[0]

        # Priority tie. A project default declaration breaks the tie (FR-005).
        default_id = self._registry.project_default_for(type_name)
        if default_id is not None:
            for s in top:
                if s.previewer_id == default_id:
                    return s
        raise RoutingAmbiguityError(
            f"{len(top)} previewers tie for {owner_kind.value} type {type_name!r} at priority {top_priority}",
            detail={
                "type": type_name,
                "owner_kind": owner_kind.value,
                "candidates": [s.previewer_id for s in top],
                "target": target.to_dict(),
            },
        )


__all__ = ["PreviewRouter"]
