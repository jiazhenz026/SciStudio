"""The shipped architecture document cannot drift from its source (#2469).

``docs/architecture/ARCHITECTURE.md`` is the single source; the user
documentation tree carries a generated copy (``_user_guide/architecture.md``)
so the published site and the in-app reader can show it. These tests fail when
the source changes and the copy is not regenerated with
``python scripts/docs/sync_architecture_doc.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "docs" / "sync_architecture_doc.py"


@pytest.fixture(scope="module")
def sync() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_sync_architecture_doc_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_shipped_copy_matches_the_source(sync: ModuleType) -> None:
    assert sync.COPY.is_file(), "run `python scripts/docs/sync_architecture_doc.py`"
    assert sync.COPY.read_text(encoding="utf-8") == sync.expected_copy(), (
        "src/scistudio/_user_guide/architecture.md drifted from docs/architecture/ARCHITECTURE.md; "
        "run `python scripts/docs/sync_architecture_doc.py`"
    )


def test_check_mode_reports_current(sync: ModuleType) -> None:
    assert sync.main(["--check"]) == 0


def test_copy_opens_on_the_document_title(sync: ModuleType) -> None:
    first = sync.COPY.read_text(encoding="utf-8").splitlines()[0]
    assert first == "# SciStudio Architecture Document"


def test_render_strips_only_the_front_matter(sync: ModuleType) -> None:
    source = "---\ntitle: x\nowner: y\n---\n\n# Title\n\nbody\n---\nmore\n"
    assert sync.render(source) == "# Title\n\nbody\n---\nmore\n"


def test_render_leaves_text_without_front_matter_unchanged(sync: ModuleType) -> None:
    for source in ("# Title\n\n---\n", "", "---\nunterminated\n"):
        assert sync.render(source) == source
