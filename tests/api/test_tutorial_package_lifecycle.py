"""FR-078 through the uninstall route, not through the store.

``docs/specs/adr-053-learning-center.md`` FR-078: uninstalling a package deletes
that package's progress group, and reinstalling starts it from zero.

These tests drive ``DELETE /api/packages/{name}`` rather than
:meth:`~scistudio.tutorials.progress.ProgressStore.remove_package_group`,
deliberately. ``tests/tutorials/test_progress.py`` already proves the method
does what it says; it called the method directly, so it passed for months while
the method had no production caller at all and FR-078 did not happen. What has
to be pinned is the **wiring**, and only a request can pin that.

The second half is the constraint the wiring has to respect: update and rollback
move the same package's code without the user losing anything they completed, so
neither may drop the group. All three routes share ``_after_package_change``,
which is why the hook is on the delete route alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.tutorials.progress import CatalogueTotals, ProgressStore
from scistudio.tutorials.projects import TutorialKey

PACKAGE = "scistudio-blocks-imaging"


@pytest.fixture
def bundled(monkeypatch: pytest.MonkeyPatch) -> None:
    """The package routes are bundled-desktop only."""
    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")


def _stub_manager(monkeypatch: pytest.MonkeyPatch, attr: str, package_name: str = PACKAGE) -> None:
    from scistudio.desktop import package_manager

    monkeypatch.setattr(
        package_manager,
        attr,
        lambda _name, **_kwargs: package_manager.PackageActionResult(
            package_name=package_name, version="1.0.0", action="probe", previous_version="0.9.0"
        ),
    )


def _seed_progress(store: ProgressStore) -> None:
    store.mark_completed(TutorialKey("package", PACKAGE, "intro"))
    store.mark_completed(TutorialKey("package", PACKAGE, "advanced"))
    store.mark_completed(TutorialKey("package", "scistudio-blocks-lcms", "intro"))
    store.mark_completed(TutorialKey.core("welcome-to-scistudio"))


def test_uninstalling_a_package_drops_its_progress_group(
    client: TestClient, bundled: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-078 end to end: the route is what removes the group."""
    store = ProgressStore()
    _seed_progress(store)
    _stub_manager(monkeypatch, "delete_package")

    response = client.delete(f"/api/packages/{PACKAGE}")

    assert response.status_code == 200, response.text
    remaining = ProgressStore().completed_keys()
    assert TutorialKey("package", PACKAGE, "intro") not in remaining
    assert TutorialKey("package", PACKAGE, "advanced") not in remaining
    # Only that package's group. Another package's progress and the core group
    # are untouched.
    assert TutorialKey("package", "scistudio-blocks-lcms", "intro") in remaining
    assert TutorialKey.core("welcome-to-scistudio") in remaining


def test_reinstalling_after_an_uninstall_starts_from_zero(
    client: TestClient, bundled: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-078's second sentence, which is what deleting rather than hiding buys."""
    store = ProgressStore()
    store.mark_completed(TutorialKey("package", PACKAGE, "intro"))
    _stub_manager(monkeypatch, "delete_package")

    assert client.delete(f"/api/packages/{PACKAGE}").status_code == 200

    (group,) = ProgressStore().groups(
        [CatalogueTotals(source_kind="package", source_id=PACKAGE, tutorial_ids=frozenset({"intro"}))]
    )
    assert (group.completed, group.total) == (0, 1)


@pytest.mark.parametrize(
    ("url", "manager_attr"),
    [
        (f"/api/packages/{PACKAGE}/update", "update_package"),
        (f"/api/packages/{PACKAGE}/rollback", "rollback_package"),
    ],
)
def test_update_and_rollback_keep_the_progress_group(
    client: TestClient,
    bundled: None,
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    manager_attr: str,
) -> None:
    """Only uninstall may forget progress.

    Update and rollback travel the same ``_after_package_change`` hook as the
    delete route. Hooking FR-078 there would have thrown away completions the
    user still has the package for, which no requirement asks for and no surface
    would explain.
    """
    ProgressStore().mark_completed(TutorialKey("package", PACKAGE, "intro"))
    _stub_manager(monkeypatch, manager_attr)

    assert client.post(url).status_code == 200

    assert TutorialKey("package", PACKAGE, "intro") in ProgressStore().completed_keys()


def test_the_uninstalled_name_is_folded_to_the_spelling_progress_records(
    client: TestClient, bundled: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The manifest name and the discovery source id need not be spelled alike.

    A package tutorial's ``source_id`` is the PEP 503 normalized distribution
    name; the name arriving from the install manifest may still carry
    underscores or capitals. Without the fold the removal is a silent no-op —
    the failure mode this whole finding was, one layer down.
    """
    ProgressStore().mark_completed(TutorialKey("package", PACKAGE, "intro"))
    _stub_manager(monkeypatch, "delete_package", package_name="SciStudio_Blocks_Imaging")

    assert client.delete("/api/packages/SciStudio_Blocks_Imaging").status_code == 200

    assert TutorialKey("package", PACKAGE, "intro") not in ProgressStore().completed_keys()


def test_a_failing_progress_removal_does_not_fail_the_uninstall(
    client: TestClient, bundled: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The package is already off disk, so the request must still succeed.

    Reporting a failure here would tell the caller the uninstall did not happen
    when it did. The cost of the swallow is a stale progress group, which the
    user can still clear.
    """
    _stub_manager(monkeypatch, "delete_package")

    def _explode(self: ProgressStore, distribution: str) -> int:
        raise OSError("progress file is unreadable")

    monkeypatch.setattr(ProgressStore, "remove_package_group", _explode)

    assert client.delete(f"/api/packages/{PACKAGE}").status_code == 200
