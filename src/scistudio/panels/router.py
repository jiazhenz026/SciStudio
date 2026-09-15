"""The one data-to-panel routing ladder, over panels and legacy previewers alike."""
# Maintainer context (kept outside generated API documentation):
# ADR-054 §2 / FR-006 / FR-007 and ADR-048 §3 / FR-003..FR-005. This module is
# the only implementation of the routing ladder. Panel descriptors and the
# deprecated Python previewers compete as one candidate set: a panel claim is
# adapted into a :class:`PreviewerSpec` (``PanelDescriptor.candidates``) and a
# legacy previewer is its own spec, so "a project Image previewer beats a
# package Image panel" and "a same-tier panel shadows a same-id legacy
# previewer" are both answered here, once. When a legacy candidate wins, the
# panel service hands the session to the legacy renderer; the ladder does not
# care which renderer a candidate uses.
#
# Precedence (highest first):
#
# 0. the person's own choice for the most specific type (#2049), when usable
# 1-6. exact type, tier order project > user > package
# 7-9. parent types, nearest ancestor first, same tier order
# 10. core ``Collection`` sentinel (collection targets)
# 11. core base: closest type in the chain, then the ``DataObject`` sentinel
# 12. unknown target
#
# Within one bucket the highest priority wins; a tie is broken by the project
# default declaration (FR-005) or raised as ambiguity (FR-004). A collection
# target only ever resolves to a collection-capable candidate.
# Development references: #2017, #2049, #2465, ADR-048, ADR-054.

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from scistudio.panels.descriptor import PanelDescriptor
from scistudio.panels.registry import TIER_ORDER
from scistudio.previewers.models import (
    OwnerKind,
    PreviewerSpec,
    PreviewTarget,
    RoutingAmbiguityError,
    UnknownPreviewerError,
    UnknownTargetError,
)
from scistudio.stability import internal

logger = logging.getLogger(__name__)

_LADDER_TIERS: tuple[OwnerKind, ...] = (OwnerKind.PROJECT, OwnerKind.USER, OwnerKind.PACKAGE)


def claim_parts(claim: str) -> tuple[str, bool]:
    """Split a declared type claim into ``(type name, is collection)``."""
    if claim.startswith("Collection[") and claim.endswith("]"):
        return claim[11:-1], True
    return claim, claim == "Collection"


def spec_claim(spec: PreviewerSpec) -> str:
    """The type claim a routing candidate answers, in ``panel.json`` spelling."""
    if spec.supports_collection and spec.target_type != "Collection":
        return f"Collection[{spec.target_type}]"
    return spec.target_type


def panel_catalog_spec(panel: PanelDescriptor) -> PreviewerSpec:
    """One catalog card for a panel, whether or not it can route."""
    candidates = panel.candidates()
    if candidates:
        return candidates[0]
    return PreviewerSpec(
        previewer_id=panel.id,
        owner_kind=panel.owner_kind,
        owner_name=panel.owner_name,
        target_type="",
        priority=panel.priority,
        api_version=panel.api_version,
        panel=panel.to_dict(),
    )


@internal()
@dataclass(frozen=True)
class CandidateSet:
    """Panels and legacy previewers merged into one namespace.

    ``routable`` holds every candidate the ladder considers. ``by_id`` holds the
    namespace winner of each id (a panel card or a legacy spec). ``panels`` holds
    the panels that won their id, which are the only panels a context may open;
    ``shadowed_panels`` and ``shadowed_specs`` hold the losers for the catalogs.
    """

    routable: tuple[PreviewerSpec, ...] = ()
    by_id: Mapping[str, PreviewerSpec] = field(default_factory=dict)
    panels: Mapping[str, PanelDescriptor] = field(default_factory=dict)
    shadowed_panels: tuple[PanelDescriptor, ...] = ()
    shadowed_specs: tuple[PreviewerSpec, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def catalog_specs(self) -> list[tuple[PreviewerSpec, bool]]:
        """Every card, winners first, with whether it is shadowed."""
        return (
            [(spec, False) for spec in self.by_id.values()]
            + [(spec, True) for spec in self.shadowed_specs]
            + [(panel_catalog_spec(panel), True) for panel in self.shadowed_panels]
        )


def merge_candidates(
    *,
    panels: Mapping[str, PanelDescriptor],
    shadowed_panels: Iterable[PanelDescriptor] = (),
    panel_diagnostics: Iterable[str] = (),
    legacy_specs: Iterable[PreviewerSpec] = (),
    legacy_shadowed: Iterable[PreviewerSpec] = (),
    legacy_diagnostics: Iterable[str] = (),
) -> CandidateSet:
    """Merge panel winners with legacy winners into one namespace.

    A panel and a legacy previewer with the same id: the higher tier wins, and
    at the same tier the panel wins. Neither input is mutated.
    """
    by_id: dict[str, PreviewerSpec] = {spec.previewer_id: spec for spec in legacy_specs}
    legacy_winner_ids = set(by_id)
    shadowed_specs = list(legacy_shadowed)
    lost_panels: list[PanelDescriptor] = list(shadowed_panels)
    diagnostics = [*legacy_diagnostics, *panel_diagnostics]
    winners: dict[str, PanelDescriptor] = {}
    for panel in panels.values():
        previous = by_id.get(panel.id) if panel.id in legacy_winner_ids else None
        if previous is not None and TIER_ORDER[previous.owner_kind] < TIER_ORDER[panel.owner_kind]:
            lost_panels.append(panel)
            diagnostics.append(f"panel {panel.id!r} shadowed by legacy {previous.owner_kind.value}")
            continue
        if previous is not None:
            shadowed_specs.append(previous)
            legacy_winner_ids.discard(panel.id)
            diagnostics.append(f"legacy previewer {panel.id!r} shadowed by panel {panel.owner_kind.value}")
        winners[panel.id] = panel
        by_id[panel.id] = panel_catalog_spec(panel)
    routable: list[PreviewerSpec] = []
    for previewer_id, spec in by_id.items():
        if previewer_id in winners:
            routable.extend(winners[previewer_id].candidates())
        else:
            routable.append(spec)
    return CandidateSet(
        routable=tuple(routable),
        by_id=by_id,
        panels=winners,
        shadowed_panels=tuple(lost_panels),
        shadowed_specs=tuple(shadowed_specs),
        diagnostics=tuple(diagnostics),
    )


@internal()
class PanelRouter:
    """Deterministic resolver over one candidate set."""

    def __init__(
        self,
        candidates: Sequence[PreviewerSpec],
        *,
        choices: Mapping[str, str] | None = None,
        project_default: Callable[[str], str | None] | None = None,
    ) -> None:
        self._candidates = tuple(candidates)
        self._choices = dict(choices or {})
        self._project_default = project_default or (lambda _type: None)

    @classmethod
    def over_registry(cls, registry: Any) -> PanelRouter:
        """A router over a legacy previewer registry's own specs and choices."""
        return cls(
            registry.all_specs(),
            choices=registry.previewer_choices(),
            project_default=registry.project_default_for,
        )

    @property
    def candidates(self) -> tuple[PreviewerSpec, ...]:
        return self._candidates

    def select(self, target: PreviewTarget, query: Mapping[str, Any] | None = None) -> PreviewerSpec:
        """Resolve *target* honouring the ``core_only`` and ``panel_id`` query keys."""
        query = query or {}
        if query.get("core_only") is True:
            core = [spec for spec in self._candidates if spec.owner_kind is OwnerKind.CORE]
            return PanelRouter(core).resolve(target)
        requested = query.get("panel_id")
        if requested:
            return self.requested(target, str(requested))
        return self.resolve(target)

    def requested(self, target: PreviewTarget, previewer_id: str) -> PreviewerSpec:
        """The candidate named *previewer_id* that serves *target*, or raise."""
        chain = specificity_chain(target)
        for spec in self._candidates:
            if spec.previewer_id != previewer_id or bool(spec.supports_collection) != target.is_collection:
                continue
            # An item-type candidate must claim a type in the item chain. The
            # ``Collection`` sentinel is not an item type; it serves any collection.
            if spec.target_type in chain or (target.is_collection and spec.target_type == "Collection"):
                return spec
        raise UnknownPreviewerError(f"Previewer {previewer_id!r} does not serve this target")

    def resolve(self, target: PreviewTarget) -> PreviewerSpec:
        """Return the single best candidate for *target* or raise a routing error."""
        specs = self._candidates
        is_collection = target.is_collection
        chain = specificity_chain(target)
        most_specific = chain[0] if chain else ""

        chosen = self._chosen(most_specific, chain, want_collection=is_collection)
        if chosen is not None:
            return chosen
        for owner_kind in _LADDER_TIERS:
            winner = self._pick(specs, owner_kind, most_specific, want_collection=is_collection, target=target)
            if winner is not None:
                return winner
        for owner_kind in _LADDER_TIERS:
            for parent in chain[1:]:
                winner = self._pick(specs, owner_kind, parent, want_collection=is_collection, target=target)
                if winner is not None:
                    return winner
        if is_collection:
            winner = self._pick(specs, OwnerKind.CORE, "Collection", want_collection=True, target=target)
            if winner is not None:
                return winner
        else:
            for type_name in chain:
                winner = self._pick(specs, OwnerKind.CORE, type_name, want_collection=False, target=target)
                if winner is not None:
                    return winner
            winner = self._pick(specs, OwnerKind.CORE, "DataObject", want_collection=False, target=target)
            if winner is not None:
                return winner
        raise UnknownTargetError(
            f"No previewer matched target type {most_specific or target.recorded_type or '<unknown>'!r}",
            detail={"target": target.to_dict()},
        )

    def _chosen(self, type_name: str, chain: list[str], *, want_collection: bool) -> PreviewerSpec | None:
        # A recorded choice applies only when its previewer is registered, claims
        # this type or an ancestor, and can serve this target's collection-ness;
        # otherwise the ladder answers. A preference never stops a preview.
        if not type_name:
            return None
        previewer_id = self._choices.get(type_name)
        if previewer_id is None:
            return None
        for spec in self._candidates:
            if (
                spec.previewer_id == previewer_id
                and spec.target_type in chain
                and bool(spec.supports_collection) == want_collection
            ):
                return spec
        logger.debug("chosen previewer %r for %r cannot serve this target; falling back", previewer_id, type_name)
        return None

    def _pick(
        self,
        specs: Sequence[PreviewerSpec],
        owner_kind: OwnerKind,
        type_name: str,
        *,
        want_collection: bool,
        target: PreviewTarget,
    ) -> PreviewerSpec | None:
        if not type_name:
            return None
        candidates = sorted(
            (
                spec
                for spec in specs
                if spec.owner_kind is owner_kind
                and spec.target_type == type_name
                and bool(spec.supports_collection) == want_collection
            ),
            key=lambda spec: (-spec.priority, spec.previewer_id),
        )
        if not candidates:
            return None
        top = [spec for spec in candidates if spec.priority == candidates[0].priority]
        if len(top) == 1:
            return top[0]
        default_id = self._project_default(type_name)
        for spec in top:
            if default_id is not None and spec.previewer_id == default_id:
                return spec
        raise RoutingAmbiguityError(
            f"{len(top)} previewers tie for {owner_kind.value} type {type_name!r} at priority {top[0].priority}",
            detail={
                "type": type_name,
                "owner_kind": owner_kind.value,
                "candidates": [spec.previewer_id for spec in top],
                "target": target.to_dict(),
            },
        )


def specificity_chain(target: PreviewTarget) -> list[str]:
    """Candidate type names ordered specific to general.

    A collection target routes on its item type chain, so ``Collection[Image]``
    resolves against ``Image``, then ``Array``, and so on.
    """
    ordered: list[str] = []
    if target.is_collection and target.collection_item_type:
        ordered.append(target.collection_item_type)
    if target.type_chain:
        for name in reversed(target.type_chain):
            if name and name not in ordered:
                ordered.append(name)
    elif not target.is_collection and target.recorded_type:
        ordered.append(target.recorded_type)
    return ordered


__all__ = [
    "CandidateSet",
    "PanelRouter",
    "claim_parts",
    "merge_candidates",
    "panel_catalog_spec",
    "spec_claim",
]
