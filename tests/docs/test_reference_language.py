"""Keep the generated API reference free of internal development references."""

from pathlib import Path

from scistudio.qa.audit.docstrings import INTERNAL_MARKERS


def test_packaged_reference_has_no_development_markers() -> None:
    root = Path(__file__).resolve().parents[2]
    pages = sorted((root / "src/scistudio/_user_guide/api-reference").glob("*.md"))
    assert pages, "Generate the packaged API reference before running this check."
    for page in pages:
        text = page.read_text(encoding="utf-8")
        match = INTERNAL_MARKERS.search(text)
        assert match is None, f"{page.name}: {match.group() if match else ''}"
