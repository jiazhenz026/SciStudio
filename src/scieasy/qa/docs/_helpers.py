"""Shared helpers for deterministic documentation generator output."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

from scieasy.qa.docs._models import GeneratorResult


def source_sha_from_sources(repo_root: Path, source_paths: list[str] | list[Path]) -> str:
    if not source_paths:
        return "no-sources"
    hasher = hashlib.sha256()
    for source in sorted(source_paths):
        source_path = Path(source)
        source_abs = source_path if source_path.is_absolute() else repo_root / source_path
        if source_abs.is_dir():
            for item in sorted(source_abs.rglob("*.py")):
                hasher.update(item.read_bytes())
        elif source_abs.exists():
            hasher.update(source_abs.read_bytes())
    return hasher.hexdigest()


def content_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def join_markdown_lines(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


def parse_pyproject_groups(repo_root: Path) -> dict[str, object]:
    path = repo_root / "pyproject.toml"
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return data.get("project", {}).get("entry-points", {})


def build_result(
    *,
    generator_id: str,
    repo_root: Path,
    target_path: Path,
    source_paths: list[str] | list[Path],
    content: str,
    marker: str,
) -> GeneratorResult:
    source_strings = [Path(path).as_posix() for path in source_paths]
    target_string = target_path.as_posix()
    manifest_entry = {
        "target_path": target_string,
        "generator_id": generator_id,
        "source_paths": source_strings,
        "source_sha": source_sha_from_sources(repo_root, source_strings),
        "content_sha256": content_sha(content),
        "marker": marker,
    }
    return GeneratorResult(
        generator_id=generator_id,
        target_path=target_string,
        content=content,
        source_paths=source_strings,
        manifest_entry=manifest_entry,
    )
