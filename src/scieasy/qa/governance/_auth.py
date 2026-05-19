"""Authorization helpers for ADR-042 governance guards."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from scieasy.qa.governance.local_gate import ActorPermission, PullRequestMetadata

AUTHORIZED_PERMISSIONS = {"write", "maintain", "admin"}
ADMIN_PERMISSIONS = {"maintain", "admin"}


def has_label(pr: PullRequestMetadata | None, label: str) -> bool:
    return pr is not None and label in pr.labels


def has_authorized_actor(pr: PullRequestMetadata | None, *, admin_only: bool = False) -> bool:
    if pr is None:
        return False
    allowed = ADMIN_PERMISSIONS if admin_only else AUTHORIZED_PERMISSIONS
    return any(actor.permission in allowed for actor in pr.actors)


def has_authorized_signal(
    pr: PullRequestMetadata | None,
    *,
    operation: str,
    name: str | None = None,
    signal_type: str | None = None,
    admin_only: bool = False,
) -> bool:
    if pr is None:
        return False
    allowed = ADMIN_PERMISSIONS if admin_only else AUTHORIZED_PERMISSIONS
    for signal in pr.authorization_signals:
        if signal.operation != operation or not signal.valid:
            continue
        if name is not None and signal.name != name:
            continue
        if signal_type is not None and signal.signal_type != signal_type:
            continue
        if signal.actor_permission.permission in allowed:
            return True
    return False


def review_authorized(reviews: Sequence[Mapping[str, object]], *, admin_only: bool = False) -> bool:
    allowed = ADMIN_PERMISSIONS if admin_only else AUTHORIZED_PERMISSIONS
    for review in reviews:
        permission = str(review.get("actor_permission") or review.get("permission") or "")
        state = str(review.get("state") or "").upper()
        if permission in allowed and state in {"APPROVED", "COMMENTED"}:
            return True
    return False


def actor_authorized(actor: ActorPermission, *, admin_only: bool = False) -> bool:
    allowed = ADMIN_PERMISSIONS if admin_only else AUTHORIZED_PERMISSIONS
    return actor.permission in allowed
