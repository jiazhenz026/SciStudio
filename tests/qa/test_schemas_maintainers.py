from __future__ import annotations

import pytest
from pydantic import ValidationError

from scieasy.qa.schemas.maintainers import MaintainerRule, Maintainers


def test_maintainers_schema_accepts_owner_rule() -> None:
    registry = Maintainers(rules=[MaintainerRule(pattern="src/scieasy/**", owners=["@owner"])])

    assert registry.rules[0].required_reviewers == 1


def test_maintainers_schema_rejects_empty_owners() -> None:
    with pytest.raises(ValidationError):
        MaintainerRule(pattern="src/**", owners=[])
