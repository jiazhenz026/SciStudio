"""``/api/user-docs`` — the shipped user documentation, as the reader gets it (#2157).

The owner's requirement for the in-app reader was that its menu match the
published site's, so these tests are written against the *published sidebar*
rather than against this module's own idea of a nice tree. The expected values
below were read out of a real ``mkdocs build`` of ``mkdocs.site.yml`` — including
the parts that are not pretty:

* ``api-reference/index.md`` is titled **"Index"**, not "SciStudio API reference".
  MkDocs takes a page title off the document's *first* element and only when
  that element is an ``h1``; the generated reference opens with a provenance
  comment, so it falls back to its filename. The reader reproduces that, because
  matching the site means matching it where it is unflattering too.
* Section titles are MkDocs' ``dirname_to_title``, which is why they read
  "Api reference" and "App fiji" rather than "API Reference" and "app-fiji".
* Files that are not Markdown — an example's ``block.py`` — are absent from the
  menu and reachable by path, exactly as they are on the site, which navigates
  pages and copies everything else beside them.

Package Development is not part of this tree and so cannot appear here: it is a
developer guide that lives in the repository, not in the wheel.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

#: The User Guide group of the published sidebar, in order, as
#: ``(depth, kind, title)``. Depth 0 is a top-level row.
PUBLISHED_SIDEBAR: tuple[tuple[int, str, str], ...] = (
    (0, "page", "SciStudio user guide"),
    (0, "page", "The AI assistant"),
    (0, "page", "Built-in blocks"),
    (0, "page", "Making your own data type"),
    (0, "page", "Data types"),
    (0, "page", "Getting started with SciStudio"),
    (0, "page", "Run history and branches"),
    (0, "page", "How SciStudio works"),
    (0, "page", "Using the canvas: build, run, preview"),
    (0, "page", "Writing a block"),
    (0, "page", "Writing a plot"),
    (0, "section", "Api reference"),
    (1, "page", "Index"),
    (1, "page", "Scistudio.blocks.app"),
    (1, "page", "Scistudio.blocks.base"),
    (1, "page", "Scistudio.blocks.code"),
    (1, "page", "Scistudio.blocks.io"),
    (1, "page", "Scistudio.blocks.process"),
    (1, "page", "Scistudio.core.meta"),
    (1, "page", "Scistudio.core.types"),
    (1, "page", "Scistudio.panels.data access"),
    (1, "page", "Scistudio.panels.models"),
    (1, "page", "Scistudio.tutorials"),
    (0, "section", "Examples"),
    (1, "page", "Examples"),
    (1, "section", "App fiji"),
    (2, "page", "AppBlock example — run a Fiji macro"),
    (1, "section", "Code accucor r"),
    (2, "page", "CodeBlock example — run an R script (AccuCor)"),
    (1, "section", "Io load npy"),
    (2, "page", "IOBlock example — a custom .npy loader"),
    (1, "section", "Process scale array"),
    (2, "page", "ProcessBlock example — normalize table columns"),
)


def _flatten(items: list[dict], depth: int = 0) -> list[tuple[int, str, str]]:
    rows: list[tuple[int, str, str]] = []
    for item in items:
        rows.append((depth, item["kind"], item["title"]))
        rows.extend(_flatten(item.get("children", []), depth + 1))
    return rows


def _paths(items: list[dict]) -> list[str]:
    found: list[str] = []
    for item in items:
        if item["kind"] == "page":
            found.append(item["path"])
        found.extend(_paths(item.get("children", [])))
    return found


@pytest.fixture()
def nav(client: TestClient) -> dict:
    response = client.get("/api/user-docs/nav")
    assert response.status_code == 200
    return response.json()


class TestNavigation:
    def test_matches_the_published_sidebar(self, nav: dict) -> None:
        """Row for row, in order: the site's User Guide group."""
        assert _flatten(nav["items"]) == list(PUBLISHED_SIDEBAR)

    def test_opens_on_the_user_guide_front_page(self, nav: dict) -> None:
        assert nav["root"] == "README.md"
        assert nav["title"] == "User guide"
        assert nav["items"][0] == {
            "kind": "page",
            "title": "SciStudio user guide",
            "path": "README.md",
            "children": [],
        }

    def test_a_section_opens_nothing(self, nav: dict) -> None:
        """A directory MkDocs turned into a heading has no page behind it."""
        sections = [row for row in nav["items"] if row["kind"] == "section"]
        assert sections, "the tree has directories, so it must have sections"
        assert all(section["path"] is None for section in sections)
        assert all(section["children"] for section in sections)

    def test_excludes_the_package_development_guide(self, nav: dict) -> None:
        """It is a developer document in the repository, never in the wheel."""
        titles = {title for _, _, title in _flatten(nav["items"])}
        assert not any("ackage development" in title for title in titles)

    def test_lists_only_markdown_pages(self, nav: dict) -> None:
        """An example's sources are linked from its page, not from the menu."""
        assert all(path.endswith(".md") for path in _paths(nav["items"]))
        assert "examples/app-fiji/block.py" not in _paths(nav["items"])

    def test_every_listed_page_can_be_opened(self, client: TestClient, nav: dict) -> None:
        for path in _paths(nav["items"]):
            assert client.get(f"/api/user-docs/pages/{path}").status_code == 200, path


class TestPages:
    def test_serves_a_guide_page_as_markdown(self, client: TestClient) -> None:
        body = client.get("/api/user-docs/pages/README.md").json()

        assert body["kind"] == "markdown"
        assert body["path"] == "README.md"
        assert body["title"] == "SciStudio user guide"
        assert body["text"].startswith("# SciStudio user guide")

    def test_serves_a_linked_source_file_verbatim(self, client: TestClient) -> None:
        """The site copies these beside the page that links them; so does this."""
        response = client.get("/api/user-docs/pages/examples/app-fiji/block.py")

        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "source"
        assert body["title"] == "block.py"
        assert "AppBlock" in body["text"]

    @pytest.mark.parametrize(
        "path",
        ["examples/", "examples/app-fiji/", "api-reference/"],
        ids=["examples", "one example", "reference"],
    )
    def test_a_directory_serves_its_index_page(self, client: TestClient, path: str) -> None:
        """The guide links to directories (`examples/`), and the site indexes them."""
        response = client.get(f"/api/user-docs/pages/{path}")

        assert response.status_code == 200
        assert response.json()["kind"] == "markdown"

    def test_reports_a_missing_page_rather_than_failing(self, client: TestClient) -> None:
        response = client.get("/api/user-docs/pages/no-such-page.md")

        assert response.status_code == 404
        assert "no-such-page.md" in response.json()["detail"]


class TestContainment:
    """The path is a request parameter, so it is never allowed to leave the tree.

    The backslash cases below are a defect this route shipped in review, not a
    hypothetical. Splitting the request path on ``/`` alone left
    ``..\\version.py`` as a single segment: it passed the ``..`` test, and then
    ``Path`` joined it and Windows read the backslash as a separator.
    ``GET /api/user-docs/pages/%2e%2e%5cversion.py`` returned
    ``scistudio/version.py``, and repeated climbs reached ``pyproject.toml`` at
    the repository root. The rule is now
    ``tutorials.actions.validate_relative_path``'s — a backslash is refused
    outright, because it is a separator on Windows and a filename character
    elsewhere — with a realpath containment check behind it.
    """

    @pytest.mark.parametrize(
        "path",
        [
            "../../pyproject.toml",
            "../version.py",
            "..%2f..%2fpyproject.toml",
            "examples/../../version.py",
            "....//pyproject.toml",
            "..%5cversion.py",
            "%2e%2e%5cversion.py",
            "..%5capi%5capp.py",
            "..%5c..%5c..%5cpyproject.toml",
            "examples%5c..%5c..%5cversion.py",
            "..%5c_agent_reference%5cREADME.md",
            "%2e%2e%5c%2e%2e%5cscistudio%5cversion.py",
            "C:%5cWindows%5cwin.ini",
            "%2fetc%2fpasswd",
        ],
        ids=[
            "climb",
            "sibling",
            "encoded climb",
            "climb from within",
            "doubled dots",
            "backslash climb",
            "encoded backslash climb",
            "backslash into a sibling package",
            "backslash to the repository root",
            "backslash climb from within",
            "backslash to a sibling doc tree",
            "backslash climb back down",
            "drive letter",
            "absolute posix path",
        ],
    )
    def test_refuses_a_path_that_leaves_the_documentation(self, client: TestClient, path: str) -> None:
        response = client.get(f"/api/user-docs/pages/{path}")

        assert response.status_code == 404
        # The refusal quotes the path back, which is the point of a 404; what
        # must never appear is any of the file it asked for.
        for outside in ("[build-system]", "[project]", "def get_version"):
            assert outside not in response.text

    def test_refuses_an_empty_path(self, client: TestClient) -> None:
        assert client.get("/api/user-docs/pages/").status_code == 404

    def test_a_refusal_never_carries_the_file_it_refused(self, client: TestClient) -> None:
        """A 404 quotes the path; it must never quote what was behind it."""
        response = client.get("/api/user-docs/pages/%2e%2e%5cversion.py")

        assert response.status_code == 404
        assert "Version deriver" not in response.text

    def test_the_pages_the_guide_really_links_to_still_open(self, client: TestClient) -> None:
        """The refusal is of separators, not of the tree's own shape."""
        for path in ("README.md", "examples/app-fiji/block.py", "api-reference/index.md"):
            assert client.get(f"/api/user-docs/pages/{path}").status_code == 200, path
