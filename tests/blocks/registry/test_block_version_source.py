"""Where a block spec's version comes from (ADR-038 §3.3, ADR-054 FR-054).

ADR-038 §3.3 force-injects the version of the distribution that shipped a block
onto its spec, because a hand-written ``version = "1.2.0"`` on a class drifts
and is not reproducible. ADR-054 FR-054 needs the opposite for one shape of
block: a packaged notebook block's version is the notebook commit it was
packaged from, and that sha is the entire mechanism by which a run points back
at the Explore session behind it.

The rule this file pins is therefore **not** "a declared version wins". Every
block inherits ``Block.version`` and some declare their own, and neither is a
claim about reproducibility — ``AIBlock`` declares ``version = "0.3.0"`` today
and must go on recording the SciStudio version, which is the first test here and
the one that matters most. What wins is an explicit opt-in a block makes,
``block_version_source = "self"``, which says *this class's version is a content
identity of the block itself*. Any block with such a version may declare it; no
block gets the behaviour by accident.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

import scistudio
from scistudio.blocks.ai.ai_block import AIBlock
from scistudio.blocks.base.block import Block
from scistudio.blocks.code.code_block import CodeBlock
from scistudio.blocks.registry import BlockRegistry
from scistudio.blocks.registry._spec import (
    BLOCK_VERSION_SOURCE_ATTR,
    SELF_DECLARED_VERSION,
    _resolve_spec_version,
    _spec_from_class,
)

# ---------------------------------------------------------------------------
# Strictly additive: every block that does not opt in is unchanged
# ---------------------------------------------------------------------------


def test_a_real_block_that_hand_declares_a_version_still_records_the_distribution_one() -> None:
    """ADR-038 §3.3 is untouched for a real, existing, version-declaring block.

    ``AIBlock`` sets ``version = "0.3.0"`` in its own class body. It does not
    opt in, so the spec must carry the SciStudio version exactly as it did
    before FR-054 existed. This is the assertion that fails the moment someone
    "simplifies" the rule to "a declared version wins".
    """
    assert AIBlock.version == "0.3.0", "fixture assumption: AIBlock hand-declares a version"
    assert not hasattr(AIBlock, BLOCK_VERSION_SOURCE_ATTR)

    assert _spec_from_class(AIBlock).version == scistudio.__version__


def test_every_scanned_in_tree_block_records_the_distribution_version() -> None:
    """A real registry scan: nothing in the shipped palette changed.

    Run over whatever the built-in scan finds rather than a curated list, so a
    block added later is covered without anyone remembering to add it here.
    """
    registry = BlockRegistry()
    registry.scan()
    specs = [registry.get_spec(name) for name in registry.all_specs()]
    scanned = [spec for spec in specs if spec is not None]
    assert scanned, "the built-in scan registered nothing; this test would prove nothing"

    wrong = {
        spec.name: spec.version
        for spec in scanned
        if spec.module_path.startswith("scistudio.") and spec.version != scistudio.__version__
    }
    assert wrong == {}, f"in-tree blocks stopped recording the distribution version: {wrong}"


def test_the_plain_code_block_is_unchanged() -> None:
    """The Code Block is the class a packaged block extends; it must not move."""
    assert _spec_from_class(CodeBlock).version == scistudio.__version__


# ---------------------------------------------------------------------------
# The opt-in
# ---------------------------------------------------------------------------


class _ContentIdentityBlock(Block):
    """A block whose version is a content identity, opting out of §3.3."""

    name: ClassVar[str] = "_ContentIdentityBlock"
    version: ClassVar[str] = "b" * 40
    block_version_source: ClassVar[str] = SELF_DECLARED_VERSION
    input_ports: ClassVar[list] = []
    output_ports: ClassVar[list] = []

    def run(self, inputs: dict, config: object) -> dict:
        return {}


class _BlankIdentityBlock(_ContentIdentityBlock):
    """Opted in, but carries no identity of its own — a base class, in effect."""

    name: ClassVar[str] = "_BlankIdentityBlock"
    version: ClassVar[str] = ""


class _MistypedMarkerBlock(_ContentIdentityBlock):
    """Opted in with a value the rule does not recognise."""

    name: ClassVar[str] = "_MistypedMarkerBlock"
    block_version_source: ClassVar[str] = "notebook"


def test_an_opted_in_block_records_its_own_version() -> None:
    """FR-054: a content identity wins over the injected default."""
    assert _resolve_spec_version(_ContentIdentityBlock) == "b" * 40
    assert _spec_from_class(_ContentIdentityBlock).version == "b" * 40


def test_the_marker_is_case_and_whitespace_insensitive() -> None:
    class _Loud(_ContentIdentityBlock):
        name: ClassVar[str] = "_Loud"
        block_version_source: ClassVar[str] = "  SELF  "

    assert _resolve_spec_version(_Loud) == "b" * 40


def test_an_opted_in_block_with_a_blank_version_falls_back() -> None:
    """A base that opts in but was built from nothing must not stamp nothing."""
    assert _resolve_spec_version(_BlankIdentityBlock) == scistudio.__version__


def test_an_unrecognised_marker_value_falls_back() -> None:
    """A typo in the marker degrades to the ADR-038 default rather than to a lie."""
    assert _resolve_spec_version(_MistypedMarkerBlock) == scistudio.__version__


@pytest.mark.parametrize("marker", [None, 7, True, ["self"], {"source": "self"}])
def test_a_non_string_marker_falls_back(marker: object) -> None:
    class _Odd(_ContentIdentityBlock):
        name: ClassVar[str] = "_Odd"

    _Odd.block_version_source = marker  # type: ignore[assignment]

    assert _resolve_spec_version(_Odd) == scistudio.__version__


def test_the_opt_in_is_inherited_so_a_generated_subclass_needs_only_its_version() -> None:
    """The marker lives on the base a generator writes against, not on each file."""

    class _Generated(_ContentIdentityBlock):
        name: ClassVar[str] = "_Generated"
        version: ClassVar[str] = "c" * 40

    assert _resolve_spec_version(_Generated) == "c" * 40


def test_the_rule_is_not_about_packaged_notebook_blocks() -> None:
    """The registry recognises the declaration, never the class.

    A block with no relationship to ADR-054 gets the same behaviour, which is
    what stops the fix from evaporating the next time someone needs a
    content-identity version for another reason.
    """
    from scistudio.explore.packaging import PackagedNotebookBlock

    assert not issubclass(_ContentIdentityBlock, PackagedNotebookBlock)
    assert _resolve_spec_version(_ContentIdentityBlock) == "b" * 40
