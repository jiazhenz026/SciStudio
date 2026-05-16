"""Wheel-install regression for ADR-040 §3.4 / #824 — relocated skill tree."""

import pytest


@pytest.mark.skip(
    reason=("S40b skeleton — Phase 2c (I40b) flips to passing once base SKILL.md body authored. TODO(#1011).")
)
def test_skills_loadable_via_importlib_resources() -> None:
    """After ``pip install dist/*.whl``, the relocated skills are findable.

    TODO(#1011): I40b in Phase 2c — flip to passing assertion::

        from importlib.resources import files

        content = (files("scieasy") / "_skills" / "scieasy" / "SKILL.md").read_text(
            "utf-8"
        )
        assert "scieasy" in content

    Out of scope per ADR-040 §3.4 / S40b dispatch (structure-only skeleton).
    Followup: Phase 2c (I40b) authors skill bodies and flips this assertion.
    """
