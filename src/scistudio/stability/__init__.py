"""Public-API stability decorators for SciStudio."""
# Maintainer context (kept outside generated API documentation):
# Public-API stability decorators for SciStudio (ADR-052 §5).
#
# Every public symbol in core and in a package carries two facts an author needs
# and cannot infer from the code: how much they may rely on it (its *tier*), and
# when it first became public (its ``Since`` version). ADR-052 §5 records both
# **on the symbol** via a small set of decorators, rather than in a separate
# hand-maintained table that would drift the moment a symbol changed.
#
# The three tiers:
#
# * ``stable`` — supported. Will not change incompatibly within a major version;
#   removal or a breaking change requires deprecation first.
# * ``provisional`` — usable but still settling. May change in a minor release,
#   with a changelog note.
# * ``internal`` — no promise. May change or vanish in any release. Excluded from
#   the generated reference; the tier exists so a symbol that must stay importable
#   for compatibility can still be labelled honestly.
#
# The decorators are **no-ops at runtime**: each attaches a :class:`StabilityInfo`
# to the symbol and returns it unchanged, so they add no runtime cost and change
# no behaviour. :func:`get_stability` reads the metadata back — the single read
# path shared by the contract validator, the API-surface freeze test, and the
# ``griffe`` reference generator (ADR-052 §7, §15), so all three agree.
#
# ``Since`` records the version a symbol first became public on *its own* surface:
# core's version line for core symbols (baseline ``0.3.1``), the package's version
# line for package symbols (ADR-052 §4.3, §13.1).
#
# This module is **decorators only** — not a re-export façade (ADR-052 §5). It is
# the foundational mechanism; decorating core's own public surface, generating the
# reference, and the surface freeze test are tracked separately under #1817.
#
# Usage::
#
#     from scistudio.stability import provisional, stable
#
#     @stable(since="0.3.1")
#     class Series(DataObject):
#         ...
#
#     @provisional(since="0.3.1")
#     def new_helper(...):
#         ...
#
# For a classmethod, apply ``@classmethod`` *outermost* so the marker lands on the
# underlying function::
#
#     class Spectrum(Series):
#         @classmethod
#         @stable(since="0.1.0")
#         def from_arrays(cls, ...):
#             ...
#
# :func:`get_stability` transparently unwraps classmethods, staticmethods, bound
# methods, and properties (reading the marker off ``fget`` / ``fset`` / ``fdel``),
# so the marker is found regardless of how the symbol is reached.
#
# Deprecation is orthogonal to the tier (ADR-052 §5 deprecation policy, #2426).
# A deprecated symbol keeps the tier it had -- its reliance promise holds until
# the removal release -- so deprecation is a separate composable marker,
# :func:`deprecated`, rather than a fourth tier. It records the version the
# deprecation starts, the version the symbol is removed in, and the replacement.
# :func:`get_deprecation` is its single read path. Like the tier markers it is a
# runtime no-op: warnings, where practical, come from the code path that uses the
# deprecated form, never from the marker. A module can carry the marker too,
# declaring its whole public surface deprecated; that is how a root's
# non-markable constants and type aliases are covered::
#
#     _deprecated = deprecated(since="0.3.5", removed_in="0.6.0", replacement="...")
#
#     @_deprecated
#     @provisional(since="0.3.1")
#     class OldThing: ...
#
#     _deprecated(sys.modules[__name__])
# Development references: #1817, #2426, ADR-052.

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeVar

__all__ = [
    "DeprecationInfo",
    "StabilityInfo",
    "Tier",
    "deprecated",
    "get_deprecation",
    "get_stability",
    "internal",
    "provisional",
    "stable",
]

#: The stability tiers an author may rely on, in descending order of promise.
Tier = Literal["stable", "provisional", "internal"]

#: Attribute under which :class:`StabilityInfo` is stashed on a decorated symbol.
#: Namespaced to avoid colliding with author attributes; always read it through
#: :func:`get_stability`, never directly.
_STABILITY_ATTR = "__scistudio_stability__"

#: Attribute under which :class:`DeprecationInfo` is stashed on a deprecated
#: symbol or module. Always read it through :func:`get_deprecation`.
_DEPRECATION_ATTR = "__scistudio_deprecation__"

_T = TypeVar("_T")


@dataclass(frozen=True)
class StabilityInfo:
    """The stability facts attached to one public symbol.

    ``tier`` is the reliance promise; ``since`` is the version the symbol first
    became public on its surface (``None`` only for ``internal`` symbols, which
    carry no promise and need no version).
    """

    # Development references: ADR-052.

    tier: Tier
    since: str | None = None


@dataclass(frozen=True)
class DeprecationInfo:
    """The deprecation facts attached to one public symbol or module.

    ``since`` is the version the deprecation starts in, ``removed_in`` the
    version the symbol is removed in (it stays supported in every release
    before that), and ``replacement`` names what to use instead.
    """

    # Development references: ADR-052, #2426.

    since: str
    removed_in: str
    replacement: str


def _stamp(attr: str, info: object) -> Callable[[_T], _T]:
    """Build a decorator that stamps ``info`` under ``attr`` and returns the symbol."""

    def decorate(symbol: _T) -> _T:
        # classmethod/staticmethod wrappers reject attribute assignment, so when
        # the marker is applied outside one, stamp the function it wraps instead;
        # get_stability unwraps the same way on read.
        target: object = symbol.__func__ if isinstance(symbol, (classmethod, staticmethod)) else symbol
        # A few objects (builtins, some C/slotted types) can't carry the marker;
        # the validator then reads "undecorated", the honest result for a symbol
        # that cannot be marked.
        with contextlib.suppress(AttributeError, TypeError):
            setattr(target, attr, info)
        return symbol

    return decorate


def _marker(info: StabilityInfo) -> Callable[[_T], _T]:
    """Build a decorator that stamps ``info`` onto a symbol and returns it."""
    return _stamp(_STABILITY_ATTR, info)


def stable(*, since: str) -> Callable[[_T], _T]:
    """Mark a public symbol ``stable`` as of ``since``."""
    # Development references: ADR-052.
    return _marker(StabilityInfo(tier="stable", since=since))


def provisional(*, since: str) -> Callable[[_T], _T]:
    """Mark a public symbol ``provisional`` as of ``since``."""
    # Development references: ADR-052.
    return _marker(StabilityInfo(tier="provisional", since=since))


def internal(*, since: str | None = None) -> Callable[[_T], _T]:
    """Mark a symbol ``internal`` — importable but carrying no promise."""
    # Development references: ADR-052.
    return _marker(StabilityInfo(tier="internal", since=since))


def deprecated(*, since: str, removed_in: str, replacement: str) -> Callable[[_T], _T]:
    """Mark a public symbol, or a whole module, deprecated.

    The marker composes with the tier markers in either order and does not
    change the tier: a deprecated ``provisional`` symbol is still
    ``provisional`` until ``removed_in``. Applied to a module object it declares
    every name in that module's ``__all__`` deprecated, which also covers
    constants and type aliases that cannot carry a marker of their own. The
    marker changes no behaviour and emits no warning.
    """
    # Development references: ADR-052, #2426.
    return _stamp(_DEPRECATION_ATTR, DeprecationInfo(since=since, removed_in=removed_in, replacement=replacement))


def _read(symbol: object, attr: str, kind: type[_T], *, inherit: bool = True) -> _T | None:
    """Read ``attr`` off ``symbol``, unwrapping methods and property accessors.

    With ``inherit=False`` a class answers only for itself, so a subclass of a
    marked class does not read the base class's marker.
    """
    if isinstance(symbol, property):
        for accessor in (symbol.fget, symbol.fset, symbol.fdel):
            info = getattr(accessor, attr, None)
            if isinstance(info, kind):
                return info
        return None
    target = getattr(symbol, "__func__", symbol)
    own_only = not inherit and isinstance(target, type)
    info = vars(target).get(attr) if own_only else getattr(target, attr, None)
    return info if isinstance(info, kind) else None


def get_deprecation(symbol: object) -> DeprecationInfo | None:
    """Return the :class:`DeprecationInfo` stamped on ``symbol``, or ``None``.

    Unwraps methods and properties the same way :func:`get_stability` does.
    ``symbol`` may be a module, in which case the module-wide deprecation is
    returned. Neither a subclass of a deprecated class nor a symbol of a
    deprecated module inherits the marker through this call; a reader that wants
    the effective status checks the symbol first and its canonical module
    second.
    """
    # Development references: ADR-052, #2426.
    return _read(symbol, _DEPRECATION_ATTR, DeprecationInfo, inherit=False)


def get_stability(symbol: object) -> StabilityInfo | None:
    """Return the :class:`StabilityInfo` stamped on ``symbol``, or ``None``.

    Transparently unwraps ``classmethod`` / ``staticmethod`` / bound-method
    access and ``property`` objects so a symbol marked on its underlying
    function (or accessor) is found regardless of how it is reached. A property
    is read from its getter first, then its setter, then its deleter — matching
    the normal ``@property`` / ``@stable`` order, where the marker lands on
    ``fget``. This is the single read path for the contract validator, the
    API-surface freeze test, and the generated reference.
    """
    # Maintainer context:
    # Transparently unwraps ``classmethod`` / ``staticmethod`` / bound-method
    # access and ``property`` objects so a symbol marked on its underlying
    # function (or accessor) is found regardless of how it is reached. A property
    # is read from its getter first, then its setter, then its deleter — matching
    # the normal ``@property`` / ``@stable`` order, where the marker lands on
    # ``fget``. This is the single read path for the contract validator, the
    # API-surface freeze test, and the generated reference (§15).
    # Development references: ADR-052.
    return _read(symbol, _STABILITY_ATTR, StabilityInfo)
