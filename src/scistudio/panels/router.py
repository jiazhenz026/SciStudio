"""PreviewRouter — ADR-048 §3 / FR-003 / FR-004 / FR-005 resolution.

Resolves a :class:`PreviewTarget` to exactly one :class:`PanelSpec` or a
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
(FR-004). A project explicit default panel resolves a project-tier tie
(FR-005).

The ladder is table-driven (:data:`_EXACT_TIERS` / :data:`_PARENT_TIERS`)
rather than hand-expanded branches: adding the user tier (#2017, precedence
project > user > package per the owner decision recorded there) cost one
tuple entry instead of four more branches, and the next tier costs the same.

**ADR-054 spec 1 adds one thing and changes nothing else** (FR-016, FR-048,
A-006). Every request now states the capability it requires, and the candidate
set is filtered to the panels that can serve it *before* the ladder and the
person's choice see them. The ladder itself, the tier precedence, the
specificity walk, the priority tie-break, and the FR-005 project default are
all carried over untouched.

The filter comes first rather than last because a filter applied afterwards is
not a filter: it would let a person's displaying default for a type win the
choice short-circuit and then be discarded, leaving a session unable to produce
from that type at all even though a producing panel was installed. A producing
request that finds no producing panel falls back to the *displaying* resolution
and is mounted with no outbound path (FR-049) - the data is still shown, and
nothing is granted that was not declared.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from scistudio.core.panels import PanelCapability
from scistudio.panels.models import (
    OwnerKind,
    PanelSpec,
    PreviewTarget,
    RoutingAmbiguityError,
    UnknownTargetError,
)
from scistudio.panels.registry import PanelRegistry
from scistudio.stability import internal

logger = logging.getLogger(__name__)

#: Tier precedence for exact-type matches (FR-003): project > user > package.
_EXACT_TIERS: tuple[OwnerKind, ...] = (OwnerKind.PROJECT, OwnerKind.USER, OwnerKind.PACKAGE)

#: Tier precedence for parent (ancestor) matches (FR-003): project > user > package.
_PARENT_TIERS: tuple[OwnerKind, ...] = (OwnerKind.PROJECT, OwnerKind.USER, OwnerKind.PACKAGE)


@internal()
@dataclass(frozen=True)
class PanelResolution:
    """What one capability-aware request resolved to (FR-048, FR-049).

    ``granted_capability`` is what the host may grant this mount, which is not
    always what the panel declares: a producing panel opened from the preview
    surface is granted display only, and a producing request that found no
    producing panel is granted display as well. ``fell_back_to_display`` is what
    tells a caller the second case apart from the first, because a session that
    asked to produce and got a display mount has to say so rather than offer a
    control that cannot work.
    """

    spec: PanelSpec
    """The panel the request resolved to."""
    required_capability: PanelCapability
    """What the request asked for."""
    granted_capability: PanelCapability
    """What this mount may do."""
    fell_back_to_display: bool = False
    """True when a producing request found no producing panel for the type."""


@internal()
class PreviewRouter:
    """Deterministic panel resolver over a :class:`PanelRegistry`."""

    def __init__(self, registry: PanelRegistry) -> None:
        self._registry = registry

    def resolve_request(
        self,
        target: PreviewTarget,
        capability: PanelCapability = PanelCapability.DISPLAYING,
    ) -> PanelResolution:
        """Resolve *target* for a request that requires *capability* (FR-048).

        The candidates are filtered to the panels declaring at least
        *capability* before the ladder and the person's choice apply; a
        producing panel satisfies a displaying request (FR-006). A producing
        request with no producing panel for the type falls back to the
        displaying resolution and is granted no outbound path (FR-049).

        Raises:
            RoutingAmbiguityError: On an unresolved priority tie.
            UnknownTargetError: When nothing matches even after the fallback.
        """
        try:
            spec = self._resolve(target, capability)
        except UnknownTargetError:
            if capability is PanelCapability.DISPLAYING:
                raise
            return PanelResolution(
                spec=self._resolve(target, PanelCapability.DISPLAYING),
                required_capability=capability,
                granted_capability=PanelCapability.DISPLAYING,
                fell_back_to_display=True,
            )
        return PanelResolution(
            spec=spec,
            required_capability=capability,
            granted_capability=capability,
        )

    def resolve(self, target: PreviewTarget) -> PanelSpec:
        """Return the single best panel spec for *target* (FR-003).

        A person's own choice for the target's type wins outright (#2049,
        FR-034); everything below it is the unchanged FR-003 ladder, which also
        serves as the fallback whenever no usable choice applies.

        Raises :class:`RoutingAmbiguityError` on an unresolved priority tie
        within a tier+specificity and :class:`UnknownTargetError` when nothing
        matches (not even a core fallback).

        This is the displaying request, which is what every caller written
        before ADR-054 spec 1 was asking for; :meth:`resolve_request` is the
        capability-aware entry point.
        """
        return self._resolve(target, PanelCapability.DISPLAYING)

    def _resolve(self, target: PreviewTarget, capability: PanelCapability) -> PanelSpec:
        """Run the FR-003 ladder over the candidates that can serve *capability*."""
        specs = [spec for spec in self._registry.all_specs() if spec.capability.satisfies(capability)]
        is_collection = target.is_collection
        # Type chain ordered specific -> general for "closest parent wins".
        chain = self._specificity_chain(target)
        most_specific = chain[0] if chain else ""

        # ---- 0: the person's own choice for this exact type (#2049) ----
        # A short circuit, not a new tier: when it applies nothing below runs,
        # and when it does not the ladder is entered exactly as before. That is
        # what makes this purely additive — a session with no choice recorded
        # routes today's answer, unchanged.
        chosen = self._chosen_spec(most_specific, chain, want_collection=is_collection, capability=capability)
        if chosen is not None:
            return chosen

        # A collection target must only resolve to collection-capable panels
        # before reaching the core collection fallback (ADR-048 FR-003 / US4):
        # never select a want_collection=False (single-item / base) panel for
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
            f"No panel matched target type {most_specific or target.recorded_type or '<unknown>'!r}",
            detail={"target": target.to_dict()},
        )

    # -- internals ----------------------------------------------------------

    def _chosen_spec(
        self,
        type_name: str,
        chain: list[str],
        *,
        want_collection: bool,
        capability: PanelCapability = PanelCapability.DISPLAYING,
    ) -> PanelSpec | None:
        """Return the spec the person chose for *type_name*, if it is usable.

        Four things can make a recorded choice not apply, and all four fall
        through to the ladder rather than raising. A preference is not a
        constraint: failing to honour one must never be able to stop a preview
        from rendering.

        * **No choice for this type.** The common case.
        * **The chosen panel is gone** — a package uninstalled, a drop-in
          deleted or renamed. The choice stays on disk, because the person may
          reinstall, and takes effect again the moment its panel does.
        * **The chosen panel does not claim this type or any ancestor of
          it.** Choosing an ancestor's panel is legitimate and expected —
          picking core's plain ``Series`` view for a ``Spectrum`` is exactly
          the kind of preference this exists to serve — but a panel for an
          unrelated type would render nothing meaningful. Restricting the
          choice to ``chain`` bounds it to the same candidate set the ladder
          below considers, so a choice can reorder that set but never widen it.
        * **The choice cannot serve this target.** A panel that does not
          declare ``supports_collection`` must not be handed a collection, the
          same rule FR-003/US4 enforces down the ladder: a single-item viewer
          given a whole collection is a broken view, not an honoured
          preference.
        """
        if not type_name:
            return None
        previewer_id = self._registry.choice_for(type_name, capability)
        if previewer_id is None:
            return None
        spec = self._registry.get(previewer_id)
        if spec is None:
            logger.debug("chosen panel %r for %r is not registered; falling back", previewer_id, type_name)
            return None
        if not set(spec.target_type_names) & set(chain):
            logger.debug(
                "chosen panel %r targets %r, none of which is in the type chain for %r; falling back",
                previewer_id,
                spec.target_type_names,
                type_name,
            )
            return None
        if want_collection and not spec.supports_collection:
            logger.debug("chosen panel %r cannot render a collection of %r; falling back", previewer_id, type_name)
            return None
        if not spec.capability.satisfies(capability):
            # A fifth way a recorded choice can fail to apply, and it falls
            # through like the other four: a preference is not a constraint, so
            # a choice that cannot serve the capability the request needs must
            # never be able to stop the panel from being found (FR-048/FR-049).
            logger.debug(
                "chosen panel %r declares %s and cannot serve a %s request; falling back",
                previewer_id,
                spec.capability.value,
                capability.value,
            )
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
        specs: list[PanelSpec],
        owner_kind: OwnerKind,
        type_name: str,
        *,
        want_collection: bool,
        target: PreviewTarget,
    ) -> PanelSpec | None:
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
            and type_name in s.target_type_names
            and bool(s.supports_collection) == want_collection
        ]
        return self._resolve_candidates(candidates, owner_kind, type_name, target)

    def _pick_core_fallback(
        self,
        specs: list[PanelSpec],
        *,
        want_collection: bool,
        target: PreviewTarget,
    ) -> PanelSpec | None:
        """Pick the generic core collection/base fallback (tiers 7 / 8 catch-all).

        Core fallbacks declare a sentinel ``target_type`` of ``"Collection"``
        (collection fallback) or ``"DataObject"`` (universal base fallback).
        """
        sentinel = "Collection" if want_collection else "DataObject"
        candidates = [
            s
            for s in specs
            if s.owner_kind is OwnerKind.CORE
            and sentinel in s.target_type_names
            and bool(s.supports_collection) == want_collection
        ]
        return self._resolve_candidates(candidates, OwnerKind.CORE, sentinel, target)

    def _resolve_candidates(
        self,
        candidates: list[PanelSpec],
        owner_kind: OwnerKind,
        type_name: str,
        target: PreviewTarget,
    ) -> PanelSpec | None:
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
            f"{len(top)} panels tie for {owner_kind.value} type {type_name!r} at priority {top_priority}",
            detail={
                "type": type_name,
                "owner_kind": owner_kind.value,
                "candidates": [s.previewer_id for s in top],
                "target": target.to_dict(),
            },
        )


__all__ = ["PanelResolution", "PreviewRouter"]
