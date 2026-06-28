"""Signatures/shape of the spec-flagged new and changed members.

Spec: §10 (ergonomic accessors exist), §11 (large-data methods + signatures),
§3.1 owner opt-A (de-underscored reconstruction hooks), §16 cleanup (removed
``metadata`` property + ``metadata=`` kwarg), §3.x keyword-only constructors.

These probe structure (member presence, parameter kinds), not behavior; the
round-trip values are exercised in test_ergonomic_accessors.

EXPECTED TO FAIL in the pre-implementation tree: the accessors and public hook
names do not exist yet, the underscore hooks are still present, and the metadata
shim is not yet deleted. Written correct-by-spec, not weakened to pass.
"""

from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from _spec_data import (
    CONSTRUCTOR_SPECS,
    DEUNDERSCORED_HOOKS,
    ERGONOMIC_ACCESSORS,
    LARGE_DATA_METHODS,
    REMOVED_PROPERTIES,
)
from conftest import import_root


def _get_class(root: str, cls_name: str):
    module = import_root(root)
    assert module is not None, f"{root} failed to import"
    cls = getattr(module, cls_name, None)
    assert cls is not None, f"{cls_name} not importable from {root}"
    return cls


# --------------------------------------------------------------------------- #
# §10 ergonomic accessors exist and are zero-extra-arg readers.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("root", "cls_name", "method", "kind"), ERGONOMIC_ACCESSORS)
def test_ergonomic_accessor_present(root: str, cls_name: str, method: str, kind: str) -> None:
    cls = _get_class(root, cls_name)
    fn = getattr(cls, method, None)
    assert fn is not None, f"{cls_name}.{method}() missing (ADR-052 §3.1 / spec §10)"
    assert callable(fn), f"{cls_name}.{method} must be callable"
    params = [
        p
        for p in inspect.signature(fn).parameters.values()
        if p.name != "self" and p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)
        and p.default is p.empty
    ]
    assert not params, (
        f"{cls_name}.{method}() must read with no required args (wraps to_memory); "
        f"got required {[p.name for p in params]}"
    )


# --------------------------------------------------------------------------- #
# §11 large-data surface present with the documented parameter shape.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("root", "cls_name", "method", "required", "var_kind"), LARGE_DATA_METHODS
)
def test_large_data_method_signature(
    root: str, cls_name: str, method: str, required: tuple[str, ...], var_kind: str | None
) -> None:
    cls = _get_class(root, cls_name)
    fn = getattr(cls, method, None)
    assert fn is not None, f"{cls_name}.{method} missing (ADR-052 §3.2 / spec §11)"
    sig = inspect.signature(fn)
    names = set(sig.parameters)
    for want in required:
        assert want in names, f"{cls_name}.{method} must accept {want!r}; sig={sig}"
    if var_kind == "VAR_KEYWORD":
        assert any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values()), (
            f"{cls_name}.{method} must accept **axes (VAR_KEYWORD); sig={sig}"
        )
    elif var_kind == "VAR_POSITIONAL":
        assert any(p.kind is p.VAR_POSITIONAL for p in sig.parameters.values()), (
            f"{cls_name}.{method} must accept *args (VAR_POSITIONAL); sig={sig}"
        )


# --------------------------------------------------------------------------- #
# §3.1 owner opt-A: reconstruction hooks de-underscored (public name in, private
# name out).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("public_name", "private_name"), DEUNDERSCORED_HOOKS)
def test_reconstruction_hook_deunderscored(public_name: str, private_name: str) -> None:
    cls = _get_class("scistudio.core.types", "DataObject")
    assert hasattr(cls, public_name), (
        f"DataObject.{public_name} (de-underscored hook) missing (spec §3.1 opt-A)"
    )
    assert not hasattr(cls, private_name), (
        f"DataObject.{private_name} must be removed once {public_name} is published"
    )


# --------------------------------------------------------------------------- #
# §16 cleanup: the deprecated metadata shim is deleted.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("cls_name", "prop"), REMOVED_PROPERTIES)
def test_metadata_property_removed(cls_name: str, prop: str) -> None:
    cls = _get_class("scistudio.core.types", cls_name)
    attr = inspect.getattr_static(cls, prop, None)
    assert not isinstance(attr, property), (
        f"{cls_name}.{prop} property must be deleted (spec §16 Phase-11 cleanup)"
    )


# --------------------------------------------------------------------------- #
# §3.x keyword-only constructor payloads + removed metadata= kwarg.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("cls_name", "kw_only", "forbidden", "positional"), CONSTRUCTOR_SPECS
)
def test_constructor_param_kinds(
    cls_name: str,
    kw_only: tuple[str, ...],
    forbidden: tuple[str, ...],
    positional: tuple[str, ...],
) -> None:
    cls = _get_class("scistudio.core.types", cls_name)
    sig = inspect.signature(cls.__init__)
    params = sig.parameters

    for name in forbidden:
        assert name not in params, (
            f"{cls_name}.__init__ must not accept {name!r} (spec §3 / §16); sig={sig}"
        )
    for name in kw_only:
        assert name in params, f"{cls_name}.__init__ must accept {name!r}; sig={sig}"
        assert params[name].kind is params[name].KEYWORD_ONLY, (
            f"{cls_name}.__init__ param {name!r} must be keyword-only (spec §3); "
            f"got {params[name].kind}"
        )
    for name in positional:
        assert name in params, f"{cls_name}.__init__ must accept {name!r}; sig={sig}"
        assert params[name].kind in (
            params[name].POSITIONAL_OR_KEYWORD,
            params[name].POSITIONAL_ONLY,
        ), (
            f"{cls_name}.__init__ param {name!r} must be positional (spec §3.8), "
            f"not keyword-only; got {params[name].kind}"
        )
