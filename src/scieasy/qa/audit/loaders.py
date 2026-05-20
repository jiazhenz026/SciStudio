"""Public schema-loading helpers for ADR-042 audit tools."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import ValidationError

from scieasy.qa.audit._util import _apply_governance_amendments, parse_yaml_frontmatter
from scieasy.qa.audit._util import load_adr_frontmatter as _load_adr_frontmatter
from scieasy.qa.audit._util import load_maintainers as _load_maintainers
from scieasy.qa.audit._util import load_spec_frontmatter as _load_spec_frontmatter
from scieasy.qa.schemas.frontmatter import ADRAddendumFrontmatter, ADRFrontmatter, SpecFrontmatter
from scieasy.qa.schemas.maintainers import Maintainers

_ADR_ADDENDUM_RE = re.compile(r"^ADR-\d{3}-addendum")


def _is_adr_addendum(path: Path) -> bool:
    return _ADR_ADDENDUM_RE.match(path.name) is not None


def load_adr_frontmatter(path: Path) -> ADRFrontmatter | ADRAddendumFrontmatter:
    """Load and validate ADR or standalone ADR addendum frontmatter."""

    if _is_adr_addendum(path):
        return load_adr_addendum_frontmatter(path)

    frontmatter, _body, findings = _load_adr_frontmatter(path)
    if frontmatter is None:
        raise ValueError(f"invalid ADR frontmatter in {path}: {findings}")
    return frontmatter


def load_adr_addendum_frontmatter(path: Path) -> ADRAddendumFrontmatter:
    """Load and validate standalone ADR addendum frontmatter."""

    data, body, findings = parse_yaml_frontmatter(path)
    if data is None:
        raise ValueError(f"invalid ADR addendum frontmatter in {path}: {findings}")
    data, amendment_findings = _apply_governance_amendments(data, body, path=path)
    if amendment_findings:
        raise ValueError(f"invalid ADR addendum frontmatter in {path}: {amendment_findings}")
    try:
        return ADRAddendumFrontmatter.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"invalid ADR addendum frontmatter in {path}: {exc}") from exc


def load_spec_frontmatter(path: Path) -> SpecFrontmatter:
    """Load and validate spec frontmatter, raising on invalid input."""

    frontmatter, _body, findings = _load_spec_frontmatter(path)
    if frontmatter is None:
        raise ValueError(f"invalid spec frontmatter in {path}: {findings}")
    return frontmatter


def load_maintainers(path: Path) -> Maintainers:
    """Load and validate the repository maintainer registry."""

    return _load_maintainers(path)
