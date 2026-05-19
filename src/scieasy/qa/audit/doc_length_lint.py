"""Check hand-authored documentation size limits."""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from scieasy.qa._report_helpers import build_finding, build_report


@dataclass(frozen=True)
class DocLengthProfile:
    path_glob: str
    max_non_empty_lines: int = 120
    max_prose_words: int = 600
    generated_exempt: bool = True


DEFAULT_PROFILES = (
    DocLengthProfile("docs/contributing/*.md"),
    DocLengthProfile("docs/contributing/**/*.md"),
    DocLengthProfile("docs/user/*.md"),
    DocLengthProfile("docs/user/**/*.md"),
    DocLengthProfile("docs/prod-agent/*.md"),
    DocLengthProfile("docs/prod-agent/**/*.md"),
    DocLengthProfile("docs/doc-guide/*.md"),
    DocLengthProfile("docs/doc-guide/**/*.md"),
)


def _read_manifest(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return set()
    if not isinstance(loaded, dict):
        return set()

    targets: set[str] = set()
    entries = loaded.get("entries", [])
    if not isinstance(entries, list):
        return set()

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        target = entry.get("target_path")
        if isinstance(target, str):
            normalized = str(Path(target).as_posix()).lstrip("./")
            targets.add(normalized)
    return targets


def _normalize_path_for_match(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_generated(path: Path, manifest_paths: set[str], repo_root: Path) -> bool:
    try:
        relative = _normalize_path_for_match(path, repo_root)
    except ValueError:
        return False
    if relative in manifest_paths:
        return True

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "<!-- generated-by:" in text


def _count_prose_and_lines(path: Path) -> tuple[int, int]:
    non_empty_lines = 0
    prose_words = 0
    in_fence = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped or (stripped.startswith("|") and stripped.endswith("|")):
            continue
        non_empty_lines += 1
        prose_words += len(re.findall(r"\b[\w-]+\b", stripped))
    return non_empty_lines, prose_words


def _matches_profile(path: Path, profile: DocLengthProfile, repo_root: Path) -> bool:
    normalized = _normalize_path_for_match(path, repo_root)
    return fnmatch.fnmatch(normalized, profile.path_glob)


def check(
    paths: Sequence[Path] | None = None,
    *,
    repo_root: Path,
    profiles: Sequence[DocLengthProfile] | None = None,
    manifest_path: Path = Path("docs/user/reference/generated-docs.yaml"),
) -> Any:
    repo_paths = [Path(".")] if not paths else [Path(p) for p in paths]
    profiles = profiles or DEFAULT_PROFILES
    manifest_paths = _read_manifest(repo_root / manifest_path)
    targets: list[Path] = []
    for raw in repo_paths:
        candidate = raw if raw.is_absolute() else repo_root / raw
        if candidate.is_dir():
            for file in sorted(candidate.rglob("*.md")):
                if file.is_file():
                    targets.append(file)
            continue
        if candidate.is_file() and candidate.suffix.lower() == ".md":
            targets.append(candidate)

    findings: list[Any] = []
    for path in targets:
        profile = next((item for item in profiles if _matches_profile(path, item, repo_root)), None)
        if profile is None:
            continue

        if profile.generated_exempt and _is_generated(path, manifest_paths, repo_root):
            continue

        lines, words = _count_prose_and_lines(path)
        if lines > profile.max_non_empty_lines:
            findings.append(
                build_finding(
                    finding_id="doc-length-lines",
                    tool="doc_length_lint",
                    finding_class="length-limit",
                    severity="error",
                    message=(
                        f"{path.relative_to(repo_root)} has {lines} non-empty lines "
                        f"(limit {profile.max_non_empty_lines})"
                    ),
                    path=path,
                    subject="length",
                    evidence={"non_empty_lines": lines, "max_non_empty_lines": profile.max_non_empty_lines},
                )
            )
        if words > profile.max_prose_words:
            findings.append(
                build_finding(
                    finding_id="doc-length-words",
                    tool="doc_length_lint",
                    finding_class="length-limit",
                    severity="error",
                    message=f"{path.relative_to(repo_root)} has {words} words (limit {profile.max_prose_words})",
                    path=path,
                    subject="length",
                    evidence={"prose_words": words, "max_prose_words": profile.max_prose_words},
                )
            )
    return build_report(tool="doc_length_lint", repo_root=repo_root, findings=findings)


def _serialize(report: Any, format_json: bool) -> None:
    if format_json:
        print(report.model_dump_json())
        return
    for finding in report.findings:
        print(f"[{finding.severity}] {finding.path}:{finding.line or 0} {finding.id} {finding.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check documentation line and prose length.")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    try:
        report = check([Path(path) for path in args.paths], repo_root=Path.cwd())
    except RuntimeError as exc:
        print(f"doc_length_lint: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"doc_length_lint: file error: {exc}", file=sys.stderr)
        return 2
    _serialize(report, args.format == "json")
    return 1 if report.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
