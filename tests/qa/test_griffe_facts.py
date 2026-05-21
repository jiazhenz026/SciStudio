from __future__ import annotations

from pathlib import Path

from scistudio.qa.audit.griffe_facts import extract_symbol_facts, generate_registry


def test_extract_symbol_facts_from_temporary_package(tmp_path: Path) -> None:
    package = tmp_path / "src" / "samplepkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("from .api import PublicClass, public_func\n", encoding="utf-8")
    (package / "api.py").write_text(
        """
class PublicClass:
    field: int = 1

    def method(self, value: str) -> bool:
        return bool(value)


def public_func(count: int, *, label: str = "x") -> str:
    return label * count


def _private_func() -> None:
    return None
""",
        encoding="utf-8",
    )

    facts = extract_symbol_facts(
        tmp_path,
        package="samplepkg",
        search_paths=[tmp_path / "src"],
        source_sha="abc123",
    )

    by_subject = {fact.subject: fact for fact in facts}
    assert "samplepkg.api.PublicClass" in by_subject
    assert "samplepkg.api.PublicClass.method" in by_subject
    assert "samplepkg.api.public_func" in by_subject
    assert "samplepkg.api._private_func" not in by_subject
    assert by_subject["samplepkg.api.public_func"].value["parameters"][0]["name"] == "count"
    assert by_subject["samplepkg.api.public_func"].value["return_annotation"] == "str"


def test_generate_registry_wraps_symbol_facts(tmp_path: Path) -> None:
    package = tmp_path / "src" / "samplepkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")

    registry = generate_registry(
        tmp_path,
        package="samplepkg",
        search_paths=[tmp_path / "src"],
        source_sha="abc123",
    )

    assert registry.source_sha == "abc123"
    assert registry.find(kind="symbol")
