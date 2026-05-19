"""Public schema-loading helpers for ADR-042 audit tools."""

from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit._util import load_adr_frontmatter as _load_adr_frontmatter
from scieasy.qa.audit._util import load_maintainers as _load_maintainers
from scieasy.qa.audit._util import load_spec_frontmatter as _load_spec_frontmatter
from scieasy.qa.schemas.frontmatter import ADRFrontmatter, SpecFrontmatter
from scieasy.qa.schemas.maintainers import Maintainers


def load_adr_frontmatter(path: Path) -> ADRFrontmatter:
    """Load and validate ADR frontmatter, raising on invalid input."""

    frontmatter, _body, findings = _load_adr_frontmatter(path)
    if frontmatter is None:
        raise ValueError(f"invalid ADR frontmatter in {path}: {findings}")
    return frontmatter


def load_spec_frontmatter(path: Path) -> SpecFrontmatter:
    """Load and validate spec frontmatter, raising on invalid input."""

    frontmatter, _body, findings = _load_spec_frontmatter(path)
    if frontmatter is None:
        raise ValueError(f"invalid spec frontmatter in {path}: {findings}")
    return frontmatter


def load_maintainers(path: Path) -> Maintainers:
    """Load and validate the repository maintainer registry."""

    return _load_maintainers(path)
