"""Shared pydantic primitive types for the QA schemas package."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

RepoRelativePath = Annotated[str, Field(min_length=1, pattern=r"^[^/](?:.*[^/])?$")]
FunctionOrClassPath = Annotated[
    str,
    Field(pattern=r"^[a-z_][a-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$"),
]
ADRRef = Annotated[int, Field(ge=1, le=9999)]

__all__ = ["ADRRef", "FunctionOrClassPath", "RepoRelativePath"]
