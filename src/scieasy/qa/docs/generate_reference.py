"""Aggregate all documentation generators used by ADR-042."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path

from scieasy.qa.docs._models import GeneratorResult
from scieasy.qa.docs.block_catalog import generate as generate_blocks
from scieasy.qa.docs.cli_reference import generate as generate_cli
from scieasy.qa.docs.entry_point_catalog import generate as generate_entry_points
from scieasy.qa.docs.llms_txt import generate as generate_llms
from scieasy.qa.docs.openapi_reference import generate as generate_openapi
from scieasy.qa.docs.runner_catalog import generate as generate_runners
from scieasy.qa.docs.schema_reference import generate as generate_schemas

TARGETS = {
    "llms_txt": generate_llms,
    "entry_point_catalog": generate_entry_points,
    "cli_reference": generate_cli,
    "openapi_reference": generate_openapi,
    "schema_reference": generate_schemas,
    "block_catalog": generate_blocks,
    "runner_catalog": generate_runners,
}


def _coerce_list(results: object) -> list[GeneratorResult]:
    if isinstance(results, list):
        return list(results)
    return [results] if results is not None else []


def collect_results(
    *,
    repo_root: Path,
    generators: Iterable[str] | None = None,
    write: bool = False,
) -> list[GeneratorResult]:
    selected = set(generators or TARGETS.keys())
    results: list[GeneratorResult] = []

    for key, generator in TARGETS.items():
        if key not in selected:
            continue
        for result in _coerce_list(generator(repo_root=repo_root)):
            if result is None:
                continue
            target = Path(result.target_path)
            if write:
                target = Path(repo_root, result.target_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(result.content, encoding="utf-8")
            results.append(result)

    return results


def run(
    repo_root: Path,
    *,
    target: str = "all",
    write: bool = False,
) -> tuple[bool, list[GeneratorResult]]:
    selected = TARGETS.keys() if target == "all" else (target,)
    results = collect_results(repo_root=repo_root, generators=selected, write=write)
    return True, results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate ADR-042 docs reference artifacts.")
    parser.add_argument("--target", default="all", choices=[*sorted(TARGETS.keys()), "all"])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check and args.write:
        print("--check and --write are mutually exclusive.")
        return 2

    _, results = run(repo_root=Path.cwd(), target=args.target, write=args.write)

    if args.check:
        for result in results:
            on_disk = (Path.cwd() / result.target_path).read_text(encoding="utf-8")
            if on_disk != result.content:
                print(f"Generated docs are out of date: {result.target_path}")
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
