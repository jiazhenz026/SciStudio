"""User-facing API docstrings must not leak internal dev/agent text (#1723).

FastAPI renders model and endpoint docstrings into the public OpenAPI schema
(visible at ``/docs`` and ``/redoc``). Several of these previously carried the
internal ``Skeleton``/``SKELETON`` development marker and one referenced an
internal agent phase (``I36c``). These tests pin them clean so the markers
cannot creep back into a surface API consumers can see.
"""

from __future__ import annotations

import pytest

from scistudio.api.routes.blocks import BlockTemplateResponse, get_block_template
from scistudio.api.routes.lint import LintRequest, LintResponse
from scistudio.api.routes.projects import (
    FileReadResponse,
    FileWriteRequest,
    FileWriteResponse,
)

_INTERNAL_MARKERS = (
    "Skeleton",
    "SKELETON",
    "skeleton agent",
    "S36",
    "I36c",
    "dispatch prompt",
    "lockstep",
    "Implementation plan",
    "Test plan",
)

# Docstring owners that FastAPI surfaces in the OpenAPI schema.
_DOCSTRING_OWNERS = [
    BlockTemplateResponse,
    get_block_template,
    FileReadResponse,
    FileWriteRequest,
    FileWriteResponse,
    LintRequest,
    LintResponse,
]


@pytest.mark.parametrize("owner", _DOCSTRING_OWNERS, ids=lambda o: o.__name__)
def test_user_facing_docstring_has_no_internal_markers(owner: object) -> None:
    """No user-visible API docstring leaks an internal dev/agent marker (#1723)."""
    doc = owner.__doc__ or ""
    leaks = [marker for marker in _INTERNAL_MARKERS if marker in doc]
    assert not leaks, f"{owner.__name__} docstring leaks internal dev text: {leaks}"  # type: ignore[attr-defined]
