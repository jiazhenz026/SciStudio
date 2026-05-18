"""Shared pydantic primitive types for the QA schemas package."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

RepoRelativePath = Annotated[str, Field(min_length=1, pattern=r"^[^/](?:.*[^/])?$")]
PathGlob = Annotated[str, Field(min_length=1)]
DottedModulePath = Annotated[
    str,
    Field(pattern=r"^[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*$"),
]
FunctionOrClassPath = Annotated[
    str,
    Field(pattern=r"^[a-z_][a-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$"),
]
GitHandle = Annotated[str, Field(pattern=r"^@[A-Za-z0-9][A-Za-z0-9_-]*$")]
AssistedByLine = Annotated[
    str,
    Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*:[A-Za-z0-9._-]+(?: \[.+\])?$"),
]
LocaleCode = Annotated[str, Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")]
ADRRef = Annotated[int, Field(ge=1, le=9999)]
IssueRef = Annotated[int, Field(ge=1)]

__all__ = [
    "ADRRef",
    "AssistedByLine",
    "DottedModulePath",
    "FunctionOrClassPath",
    "GitHandle",
    "IssueRef",
    "LocaleCode",
    "PathGlob",
    "RepoRelativePath",
]
