"""PreviewRouter — ADR-048 §3 / FR-003 / FR-004 / FR-005 resolution.

Resolves a :class:`PreviewTarget` to exactly one :class:`PreviewerSpec` or a
typed routing error.

The precedence order (highest first) is exactly ADR-048 §3 / spec FR-003:

1. project exact ``Collection[T]``
2. project exact ``T``
3. user exact ``Collection[T]``
4. user exact ``T``
5. package exact ``Collection[T]``
6. package exact ``T``
7. project parent (walk the type chain general-ward, project tier)
8. user parent (walk the type chain general-ward, user tier)
9. package parent (walk the type chain general-ward, package tier)
10. core collection fallback
11. core base fallback
12. unknown / error

Specificity is driven by the target's ``type_chain`` (ordered general ->
specific). "Exact" means the spec's ``target_type`` equals the most specific
recorded type; "parent" means it equals an ancestor in the chain, with closer
ancestors preferred. Within one tier + specificity, the highest ``priority``
wins; an unresolved priority tie raises :class:`RoutingAmbiguityError`
(FR-004). A project explicit default previewer resolves a project-tier tie
(FR-005).

The ladder is table-driven (:data:`_EXACT_TIERS` / :data:`_PARENT_TIERS`)
rather than hand-expanded branches: adding the user tier (#2017, precedence
project > user > package per the owner decision recorded there) cost one
tuple entry instead of four more branches, and the next tier costs the same.
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
from scistudio.stability import internal

logger = logging.getLogger(__name__)

#: Tier precedence for exact-type matches (FR-003): project > user > package.
_EXACT_TIERS: tuple[OwnerKind, ...] = (OwnerKind.PROJECT, OwnerKind.USER, OwnerKind.PACKAGE)

#: Tier precedence for parent (ancestor) matches (FR-003): project > user > package.
_PARENT_TIERS: tuple[OwnerKind, ...] = (OwnerKind.PROJECT, OwnerKind.USER, OwnerKind.PACKAGE)


@internal()
class PreviewRouter:
    """Deterministic previewer resolver over a :class:`PreviewerRegistry`."""

    def __init__(self, registry: PreviewerRegistry) -> None:
        self._registry = registry

    def resolve(self, target: PreviewTarget) -> PreviewerSpec:
        """Return the single best previewer spec for *target* (FR-003).

        A person's own choice for the target's type wins outright (#2049,
        FR-034); everything below it is the unchanged FR-003 ladder, which also
        serves as the fallback whenever no usable choice applies.

        Raises :class:`RoutingAmbiguityError` on an unresolved priority tie
        within a tier+specificity and :class:`UnknownTargetError` when nothing
        matches (not even a core fallback).
        """
        specs = self._registry.all_specs()
        is_collection = target.is_collection
        # Type chain ordered specific -> general for "closest parent wins".
        chain = self._specificity_chain(target)
        most_specific = chain[0] if chain else ""

        # ---- 0: the person's own choice for this exact type (#2049) ----
        # A short circuit, not a new tier: when it applies nothing below runs,
        # and when it does not the ladder is entered exactly as before. That is
        # what makes this purely additive — a session with no choice recorded
        # routes today's answer, unchanged.
        chosen = self._chosen_spec(most_specific, chain, want_collection=is_collection)
        if chosen is not None:
            return chosen

        # A collection target must only resolve to collection-capable previewers
        # before reaching the core collection fallback (ADR-048 FR-003 / US4):
        # never select a want_collection=False (single-item / base) previewer for
        # a collection, otherwise e.g. Collection[Image] with the imaging package
        # installed would mis-route to the single-image viewer at the exact/parent
        # tiers before the core collection fallback.

        # ---- 1-6: exact matches, tier order project > user > package ----
        for owner_kind in _EXACT_TIERS:
            winner = self._pick(specs, owner_kind, most_specific, want_collection=is_collection, target=target)
            if winner is not None:
                return winner

        # ---- 7-9: parent matches (closest ancestor first), same tier order ----
        for owner_kind in _PARENT_TIERS:
            for parent in chain[1:]:
                winner = self._pick(specs, owner_kind, parent, want_collection=is_collection, target=target)
                if winner is not None:
                    return winner

        # ---- 10: core collection fallback ----
        if is_collection:
            winner = self._pick_core_fallback(specs, want_collection=True, target=target)
            if winner is not None:
                return winner

        # ---- 11: core base fallback (closest matching base in chain) — items only ----
        if not is_collection:
            for type_name in chain:
                winner = self._pick(specs, OwnerKind.CORE, type_name, want_collection=False, target=target)
                if winner is not None:
                    return winner
            winner = self._pick_core_fallback(specs, want_collection=False, target=target)
            if winner is not None:
                return winner

        # ---- 12: unknown / error ----
        raise UnknownTargetError(
            f"No previewer matched target type {most_specific or target.recorded_type or '<unknown>'!r}",
            detail={"target": target.to_dict()},
        )

    # -- internals ----------------------------------------------------------

    def _chosen_spec(self, type_name: str, chain: list[str], *, want_collection: bool) -> PreviewerSpec | None:
        """Return the spec the person chose for *type_name*, if it is usable.

        Four things can make a recorded choice not apply, and all four fall
        through to the ladder rather than raising. A preference is not a
        constraint: failing to honour one must never be able to stop a preview
        from rendering.

        * **No choice for this type.** The common case.
        * **The chosen previewer is gone** — a package uninstalled, a drop-in
          deleted or renamed. The choice stays on disk, because the person may
          reinstall, and takes effect again the moment its previewer does.
        * **The chosen previewer does not claim this type or any ancestor of
          it.** Choosing an ancestor's previewer is legitimate and expected —
          picking core's plain ``Series`` view for a ``Spectrum`` is exactly
          the kind of preference this exists to serve — but a previewer for an
          unrelated type would render nothing meaningful. Restricting the
          choice to ``chain`` bounds it to the same candidate set the ladder
          below considers, so a choice can reorder that set but never widen it.
        * **The choice cannot serve this target.** A previewer that does not
          declare ``supports_collection`` must not be handed a collection, the
          same rule FR-003/US4 enforces down the ladder: a single-item viewer
          given a whole collection is a broken view, not an honoured
          preference.
        """
        if not type_name:
            return None
        previewer_id = self._registry.choice_for(type_name)
        if previewer_id is None:
            return None
        spec = self._registry.get(previewer_id)
        if spec is None:
            logger.debug("chosen previewer %r for %r is not registered; falling back", previewer_id, type_name)
            return None
        if spec.target_type not in chain:
            logger.debug(
                "chosen previewer %r targets %r, which is not in the type chain for %r; falling back",
                previewer_id,
                spec.target_type,
                type_name,
            )
            return None
        if want_collection and not spec.supports_collection:
            logger.debug("chosen previewer %r cannot render a collection of %r; falling back", previewer_id, type_name)
            return None
        return spec

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
