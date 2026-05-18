"""Pydantic schema for libCST codemod metadata blocks (ADR-042 §20.3).

Each codemod under ``tools/codemods/adr-NNN-<slug>.py`` begins with a
metadata docstring of the form::

    \"\"\"
    ADR: 42
    Description: Rename scieasy.X.foo to scieasy.X.bar per ADR-042 §N
    Affects:
      - scieasy.X.foo (renamed to scieasy.X.bar)
    Tests:
      - tests/codemods/test_adr_042_rename.py
    \"\"\"

:class:`CodemodMeta` is the pydantic-validated structural shape of that
metadata. The audit tool :mod:`scieasy.qa.audit.codemod_lint` parses
codemod files into ``CodemodMeta`` (via ``parse_model``) and emits
findings on shape violations and on broken cross-references.

References
----------
ADR-042 §20.1 — codemod discipline statement.
ADR-042 §20.3 — metadata format (authoritative source for this file).
ADR-042 §20.4 — CI verification pattern.

Manager defaults
----------------
Per Phase 1 investigation SUMMARY Q1B.9.1, two parsing entry points are
provided: :func:`parse <scieasy.qa.audit.codemod_lint.parse>` returning
a plain ``dict[str, Any]`` (per the §20.3 stub literal) and the sibling
``parse_model`` returning a ``CodemodMeta``. Typed callers prefer the
latter; the dict form remains for ad-hoc inspection / JSON dumping.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from scieasy.qa.schemas._common import ADRRef, RepoRelativePath

__all__ = ["CodemodMeta"]


class CodemodMeta(BaseModel):
    """Structural shape of a codemod's metadata docstring block.

    The four fields mirror the §20.3 example verbatim:

    * ``adr`` — numeric ADR reference (1-9999) introducing the contract change.
    * ``description`` — one-line human-readable description.
    * ``affects`` — list of free-form impact descriptions (each line of the
      ``Affects:`` block after the leading ``- `` marker). The contract is
      intentionally loose; the closure / drift audits separately verify
      that each affected symbol is wired into the rename properly.
    * ``tests`` — list of repo-relative POSIX paths to the codemod's tests.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    adr: ADRRef
    description: str = Field(min_length=1, max_length=500)
    affects: list[str] = Field(default_factory=list)
    tests: list[RepoRelativePath] = Field(default_factory=list)
