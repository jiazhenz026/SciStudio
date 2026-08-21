"""The canonical root is sufficient to author a tutorial driver (ADR-052 §3).

``scistudio.tutorials`` became a canonical public root in #2080, because
``docs/specs/adr-053-learning-center.md`` FR-040 lets a package ship its own
driver and FR-042 names
:func:`~scistudio.tutorials.conditions.evaluate` and
:func:`~scistudio.tutorials.conditions.parse_condition` public for it to call.

Every other test in this directory imports by deep path
(``scistudio.tutorials.driver``, ``...conditions``), which is what core does and
what a *package* must not have to do. So nothing here proved the promise the
root now makes: that a third party can build a working driver against
``from scistudio.tutorials import ...`` alone. These tests hold that line from
both sides — the surface is sufficient to author against, and it does not
quietly grow back into the 82-name re-export it replaced.
"""

from __future__ import annotations

import importlib
from pathlib import Path

# The authoring path under test: root-level imports only, exactly as a package
# driver would write them. Deep-path imports would defeat the point.
from scistudio.tutorials import (
    Condition,
    ConditionValidationError,
    DeclaresConditions,
    DriverContext,
    ProductState,
    RunSummary,
    StepView,
    TutorialDriver,
    TutorialKey,
    WriteAction,
    evaluate,
    parse_condition,
)

from .conftest import StubProductState

#: Runtime machinery that must stay out of the contract. Each was re-exported
#: from the root before #2080; republishing any of them would hand packages a
#: promise about the session store, the discovery walk, or the progress file.
_INTERNAL_NAMES = (
    "SessionRecord",
    "SessionStore",
    "TutorialRuntime",
    "DiscoveryEnvironment",
    "ProgressStore",
    "TutorialManifest",
    "ManifestDriver",
    "load_driver",
    "perform_step_entry",
)


class _PackageDriver:
    """A driver written the way a package author would write one.

    Deliberately built from the root-level names imported above and nothing
    else: if the public surface were missing a type this needs, this class would
    not be expressible.
    """

    def __init__(self, step_ids: tuple[str, ...], condition: Condition) -> None:
        self._ids = step_ids
        self._condition = condition

    def step_view(self, context: DriverContext) -> StepView:
        step_id = context.step_id or self._ids[0]
        return StepView(
            id=step_id,
            index=self._ids.index(step_id),
            total=len(self._ids),
            title=f"Step {step_id}",
            say="Authored against the canonical root.",
        )

    def is_satisfied(self, context: DriverContext, product: ProductState) -> bool:
        # FR-042: defer to the core evaluator for what the vocabulary covers.
        return evaluate(self._condition, product)

    def entry_actions(self, context: DriverContext) -> tuple[WriteAction, ...]:
        return (WriteAction(source="assets/notes.md", destination="notes.md"),)

    def advance(self, context: DriverContext) -> str | None:
        if context.step_id is None:
            return self._ids[0]
        nxt = self._ids.index(context.step_id) + 1
        return self._ids[nxt] if nxt < len(self._ids) else None


def _condition() -> Condition:
    return parse_condition({"block_registered": {"block_type": "Load"}})


def _context(step_id: str | None) -> DriverContext:
    return DriverContext(
        key=TutorialKey(source_kind="package", source_id="demo-pkg", tutorial_id="demo"),
        tutorial_dir=Path("tutorial"),
        project_dir=Path("project"),
        step_id=step_id,
    )


def test_every_public_name_resolves_from_the_root() -> None:
    root = importlib.import_module("scistudio.tutorials")
    missing = [name for name in root.__all__ if not hasattr(root, name)]
    assert missing == [], f"declared in __all__ but not importable: {missing}"


def test_a_driver_authored_from_the_root_alone_satisfies_the_protocol() -> None:
    driver = _PackageDriver(("first", "second"), _condition())

    # runtime_checkable: this is the check load_driver performs on a package's class.
    assert isinstance(driver, TutorialDriver)


def test_the_four_questions_answer_through_root_level_types_only() -> None:
    driver = _PackageDriver(("first", "second"), _condition())

    assert driver.advance(_context(None)) == "first"
    assert driver.advance(_context("first")) == "second"
    assert driver.advance(_context("second")) is None

    view = StepView.of(driver.step_view(_context("second")))
    assert (view.id, view.index, view.total) == ("second", 1, 2)

    actions = driver.entry_actions(_context("first"))
    assert isinstance(actions[0], WriteAction)


def test_the_core_evaluator_is_reachable_from_the_root(tmp_path: Path) -> None:
    """FR-042: the two functions a driver may lean on are public by name."""
    condition = parse_condition({"type_registered": {"type_name": "Spectrum"}})
    driver = _PackageDriver(("only",), condition)

    absent = StubProductState(project_dir=tmp_path)
    present = StubProductState(project_dir=tmp_path, data_types=frozenset({"Spectrum"}))

    assert driver.is_satisfied(_context("only"), absent) is False
    assert driver.is_satisfied(_context("only"), present) is True


def test_a_rejected_condition_names_the_field_through_the_public_error() -> None:
    try:
        parse_condition({"no_such_term": {}}, field_name="done_when")
    except ConditionValidationError as exc:
        assert "done_when" in str(exc)
    else:  # pragma: no cover - the parse must not succeed
        raise AssertionError("parse_condition accepted a term outside the vocabulary")


def test_run_summary_is_public_because_product_state_hands_it_back(tmp_path: Path) -> None:
    """``ProductState.run_records`` returns these, so a driver reading runs needs the type."""
    run = RunSummary(run_id="r1", workflow_id="w1", succeeded=True)
    state = StubProductState(project_dir=tmp_path, runs=(run,))

    assert state.run_records() == (run,)
    assert isinstance(state, ProductState)


def test_declares_conditions_is_optional_and_separate_from_the_driver_protocol() -> None:
    """FR-038 fixes the driver at four members; the capability is opt-in."""
    plain = _PackageDriver(("only",), _condition())
    assert isinstance(plain, TutorialDriver)
    assert not isinstance(plain, DeclaresConditions)

    class _Declaring(_PackageDriver):
        def condition(self, context: DriverContext) -> Condition | None:
            return self._condition

    declaring = _Declaring(("only",), _condition())
    assert isinstance(declaring, DeclaresConditions)


def test_runtime_internals_stay_out_of_the_public_surface() -> None:
    root = importlib.import_module("scistudio.tutorials")
    leaked = [name for name in _INTERNAL_NAMES if name in root.__all__]
    assert leaked == [], f"runtime internals republished as public API: {leaked}"


def test_internals_remain_importable_by_deep_path() -> None:
    """Narrowing ``__all__`` withdrew the promise, not the import.

    ADR-052's rule is that everything outside a canonical root's ``__all__`` is
    "importable today, unsupported". Core and the API layer reach these by deep
    path, so removing them would be a different change than the one #2080 made.
    """
    driver_mod = importlib.import_module("scistudio.tutorials.driver")
    session_mod = importlib.import_module("scistudio.tutorials.session")
    discovery_mod = importlib.import_module("scistudio.tutorials.discovery")

    assert hasattr(driver_mod, "ManifestDriver")
    assert hasattr(driver_mod, "load_driver")
    assert hasattr(session_mod, "TutorialRuntime")
    assert hasattr(discovery_mod, "DiscoveryEnvironment")
