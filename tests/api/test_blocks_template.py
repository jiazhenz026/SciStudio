"""ADR-036 §3.12 (I36c) — block template endpoint integration tests."""

from __future__ import annotations

import ast

from fastapi.testclient import TestClient


def test_template_basic_returns_python_with_correct_imports(client: TestClient) -> None:
    """GET /api/blocks/template?kind=basic returns Python content with the right imports.

    Asserts the literal ``"from scistudio.blocks.base import"`` import line is
    present and the ``Block`` symbol is referenced. We do not pin the
    exact symbol list because the template tracks whatever
    ``base/__init__.py`` exports — see the long comment at the top of
    ``src/scistudio/blocks/_templates/block_base_template.py``.
    """
    r = client.get("/api/blocks/template?kind=basic")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "basic"
    assert body["suggested_filename"].endswith(".py")
    content = body["content"]
    assert "from scistudio.blocks.base import" in content
    assert "Block" in content
    # Must be syntactically valid Python — otherwise the editor renders it
    # with squiggles immediately on open and the template UX silently breaks.
    ast.parse(content)


def test_template_basic_has_run_marker(client: TestClient) -> None:
    """The template content contains the ``# >>> EDIT THIS <<<`` marker.

    This is the user-visible "start typing here" pointer. If it
    disappears, the new-block UX silently regresses.
    """
    r = client.get("/api/blocks/template?kind=basic")
    assert r.status_code == 200
    assert "# >>> EDIT THIS <<<" in r.json()["content"]


def test_template_default_kind_is_basic(client: TestClient) -> None:
    """Omitting ``kind`` defaults to ``basic`` per the FastAPI signature."""
    r = client.get("/api/blocks/template")
    assert r.status_code == 200
    assert r.json()["kind"] == "basic"


def test_template_unknown_kind_400(client: TestClient) -> None:
    """GET with an unknown kind returns HTTP 400 with a useful message."""
    r = client.get("/api/blocks/template?kind=frobnicator")
    assert r.status_code == 400
    body = r.json()
    assert "frobnicator" in body["detail"]


# #1723 — the template is copied verbatim into the user's project. It must read
# as user-facing guidance, never as internal agent/phase collaboration notes.
_INTERNAL_MARKERS = (
    "Skeleton",
    "skeleton agent",
    "S36",
    "I36c",
    "dispatch prompt",
    "lockstep",
)


def test_template_basic_has_no_internal_dev_text(client: TestClient) -> None:
    """The user-facing template must not leak internal agent/phase notes (#1723)."""
    content = client.get("/api/blocks/template?kind=basic").json()["content"]
    leaks = [marker for marker in _INTERNAL_MARKERS if marker in content]
    assert not leaks, f"template leaks internal dev text: {leaks}"


def test_template_documents_real_run_contract(client: TestClient) -> None:
    """The template documents the real run() contract + parameter accessor (#1723).

    The old template wrongly told users to "Return a BlockResult" and to read
    parameters via ``self.config["..."]``. The real contract returns
    ``dict[str, Collection]`` and reads parameters with ``config.get(...)``.
    """
    content = client.get("/api/blocks/template?kind=basic").json()["content"]
    assert "dict[str, Collection]" in content
    assert "BlockResult" not in content
    assert "config.get(" in content
    # #1725 — ADR-031 removed ViewProxy/DataObject.view(); the read path is
    # item.to_memory() directly. The template must not teach the removed view().
    assert ".view(" not in content, "template must use item.to_memory(), not the removed view()"
    assert "item.to_memory()" in content
    # A worked, paste-over example is part of the user-friendly rewrite.
    assert "Minimal example" in content


# #1816 — the template is the only thing our non-programmer authors actually
# read, so the teaching content lives in the template itself. These tests pin
# the sections the rewrite promised so they cannot silently disappear.


def _template(client: TestClient) -> str:
    return client.get("/api/blocks/template?kind=basic").json()["content"]


def test_template_teaches_block_family(client: TestClient) -> None:
    """Section 1 — authors must learn which base classes exist and when to use them."""
    content = _template(client)
    # The default base plus the realistic alternatives a human might subclass.
    for base in ("ProcessBlock", "IOBlock", "AppBlock", "CodeBlock"):
        assert base in content, f"template should mention the {base} base class"


def test_template_teaches_type_to_memory_returns(client: TestClient) -> None:
    """Section 2 — the type table must surface the differing to_memory() returns.

    The #1 newbie trap is that Array.to_memory() is a numpy array while
    DataFrame.to_memory() is an Arrow table. Both must be named explicitly.
    """
    content = _template(client)
    for type_name in ("Array", "DataFrame", "Series", "Text", "Artifact"):
        assert type_name in content, f"template should list the {type_name} type"
    assert "numpy" in content
    assert "pyarrow" in content or "Arrow" in content
    assert "to_pandas()" in content, "template must show how to get a pandas frame"


def test_template_teaches_collection_helpers(client: TestClient) -> None:
    """Section 3 — Collection is exposed directly, so its helpers must be taught."""
    content = _template(client)
    for helper in ("map_items", "parallel_map", "pack", "unpack"):
        assert helper in content, f"template should mention the {helper} helper"


def test_template_has_array_and_dataframe_examples(client: TestClient) -> None:
    """Section 6 — owner directive: two batch examples, one Array and one DataFrame."""
    content = _template(client)
    # ADR-052 §2: the template imports core types from the canonical root
    # (``scistudio.core.types``), not the deep per-module paths.
    assert "from scistudio.core.types import Array" in content
    assert "from scistudio.core.types import DataFrame" in content
    # Both examples drive the point that batch processing is the default.
    assert content.count("self.map_items(") >= 2


def test_template_ports_use_concrete_type_not_empty(client: TestClient) -> None:
    """The default ports must declare a concrete type, never ``accepted_types=[]``.

    The old template used ``[]``, which contradicts the block contract that
    requires concrete types for connection checks and preview routing.
    """
    content = _template(client)
    assert "accepted_types=[]" not in content
    assert "accepted_types=[Array]" in content


def test_template_points_authors_at_package_docs(client: TestClient) -> None:
    """Section 7 — authors must be told where domain (package) types come from."""
    content = _template(client)
    assert "package" in content
    # Warn against the private internals AI code is seen reaching into (#1817).
    assert "_support" in content


def test_template_myblock_validates_via_harness(client: TestClient) -> None:
    """The served template must define a block that passes the contract harness.

    Executing the template content also guarantees the worked ``run()`` body is
    importable and syntactically sound, not just the file as a whole.
    """
    from scistudio.testing import BlockTestHarness

    content = _template(client)
    namespace: dict[str, object] = {}
    exec(compile(content, "block_base_template.py", "exec"), namespace)
    my_block = namespace["MyBlock"]
    errors = BlockTestHarness(my_block).validate_block()
    assert not errors, errors


def test_template_preimports_every_advertised_type(client: TestClient) -> None:
    """Switching a port to any advertised type must not NameError (#1818 review).

    Section 4 tells authors to change ``accepted_types`` to DataFrame / Series /
    Text / Artifact. The old template only imported ``Array`` in the executable
    body, so a non-programmer's copied module raised ``NameError`` at registry
    import the moment they followed that instruction. Every base type named in
    the guidance must be importable in the served module.
    """
    content = _template(client)
    namespace: dict[str, object] = {}
    exec(compile(content, "block_base_template.py", "exec"), namespace)
    for type_name in ("Array", "DataFrame", "Series", "Text", "Artifact"):
        assert type_name in namespace, (
            f"{type_name} is advertised in the template but not imported in the "
            "executable body — switching a port to it would NameError on import"
        )


def test_template_basic_documents_node_visual_hints(client: TestClient) -> None:
    """#1839: the basic template teaches the optional ui_color / ui_icon hints.

    These are a teaching surface (memory: author guidance lives IN the starter
    template, not in separate docs). The hints must be present as commented
    guidance so a non-programmer author discovers them, and the template must
    stay syntactically valid Python (they are comments, not active code).
    """
    content = _template(client)
    assert "ui_color" in content
    assert "ui_icon" in content
    # #1839 lands them commented-out (opt-in); the served module must still parse.
    ast.parse(content)
