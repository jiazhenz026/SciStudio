"""Shared pydantic primitive types for the QA schemas subpackage.

ADR-042 audit fix C1 (§5.2 lines 618-639) extracts a handful of
``Annotated`` type aliases out of ``frontmatter.py`` and
``maintainers.py`` into this neutral module to break the circular import
that otherwise existed between those two files: ``frontmatter`` needs
``AgentRuntime`` from ``maintainers``, and ``maintainers`` needs path /
handle / ADR-ref primitives that were originally declared inside
``frontmatter``. By relocating those primitives here, both modules
import from ``_common`` and neither imports the other at module-load
time.

These nine aliases are intentionally a closed set; expansion happens via
errata to ADR-042 (per §27.4). The reference column maps each alias back
to the ADR text that defines it.

References
----------
ADR-042 §5.2 (lines 618-639) — declaration site.
ADR-042 §5.4 — ``governs.contracts`` granularity rationale for
``DottedModulePath`` and ``FunctionOrClassPath``.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

# --------------------------------------------------------------------------- #
# Path-like primitives                                                        #
# --------------------------------------------------------------------------- #

#: Repo-relative POSIX path. Must not start or end with ``/``. The lone
#: single-character form is permitted (pattern fix I2 — the original
#: regex required two characters which excluded valid 1-char paths such
#: as ``a``).
RepoRelativePath = Annotated[str, Field(min_length=1, pattern=r"^[^/](?:.*[^/])?$")]

#: Broader glob form for the ``governs.files``/``excludes`` family —
#: allows ``**`` wildcards anywhere in the pattern. Validation is
#: deliberately permissive; the closure check (ADR-042 §11) is what
#: tightens semantics on glob-coverage.
PathGlob = Annotated[str, Field(min_length=1)]


# --------------------------------------------------------------------------- #
# Dotted-name primitives                                                      #
# --------------------------------------------------------------------------- #

#: Dotted Python module path such as ``scieasy.qa.schemas.frontmatter``.
#: Components must match the Python identifier grammar (lowercase + ``_``
#: only — class casing belongs to ``FunctionOrClassPath``).
DottedModulePath = Annotated[str, Field(pattern=r"^[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*$")]

#: Dotted Python qualified name pointing at a function or class symbol
#: (e.g. ``scieasy.qa.schemas.frontmatter.ADRFrontmatter``). Requires at
#: least one upper-case-starting tail component so module-only paths fall
#: into ``DottedModulePath`` instead.
FunctionOrClassPath = Annotated[str, Field(pattern=r"^[a-z_][a-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")]


# --------------------------------------------------------------------------- #
# Identity primitives                                                         #
# --------------------------------------------------------------------------- #

#: GitHub-style handle, e.g. ``@claude``. The leading ``@`` is mandatory;
#: the tail must satisfy GitHub's username grammar.
GitHandle = Annotated[str, Field(pattern=r"^@[A-Za-z0-9][A-Za-z0-9_-]*$")]

#: ``Assisted-by`` trailer line body (without the ``Assisted-by: ``
#: prefix), per ADR-042 §13.2. Form: ``<Runtime>:<ModelID> [tools]`` —
#: the bracket tail is optional.
AssistedByLine = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*:[A-Za-z0-9._-]+(?: \[.+\])?$")]


# --------------------------------------------------------------------------- #
# Misc primitives                                                             #
# --------------------------------------------------------------------------- #

#: Locale code per BCP-47 short form: two-letter language plus optional
#: two-letter country, e.g. ``en`` or ``zh-CN``.
LocaleCode = Annotated[str, Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")]

#: Numeric ADR reference. Bounded ``[1, 9999]`` — the upper bound is a
#: paranoid sanity ceiling; current numbering is in the low hundreds.
ADRRef = Annotated[int, Field(ge=1, le=9999)]

#: Numeric GitHub issue reference.
IssueRef = Annotated[int, Field(ge=1)]
