"""Validate generated documentation against generator outputs and manifests."""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa._shared import AuditFinding, AuditReport
from scieasy.qa.docs._models import GeneratorResult
from scieasy.qa.docs.generate_reference import TARGETS, collect_results


@dataclass
class GeneratedDocManifestEntry:
    target_path: str
    generator_id: str
    source_paths: list[str]
    source_sha: str
    content_sha256: str
    marker: str


@dataclass
class GeneratedDocManifest:
    schema_version: str
    entries: list[GeneratedDocManifestEntry]


def _text_sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _read_manifest(path: Path) -> GeneratedDocManifest:
    if not path.exists():
        return GeneratedDocManifest(schema_version="1", entries=[])
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return GeneratedDocManifest(schema_version="1", entries=[])
    if not isinstance(loaded, dict):
        return GeneratedDocManifest(schema_version="1", entries=[])

    raw_entries = loaded.get("entries", [])
    if not isinstance(raw_entries, list):
        raw_entries = []

    entries: list[GeneratedDocManifestEntry] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        entries.append(
            GeneratedDocManifestEntry(
                target_path=str(Path(str(item.get("target_path", ""))).as_posix()),
                generator_id=str(item.get("generator_id", "")),
                source_paths=[str(x) for x in item.get("source_paths", [])],
                source_sha=str(item.get("source_sha", "")),
                content_sha256=str(item.get("content_sha256", "")),
                marker=str(item.get("marker", "")),
            )
        )
    return GeneratedDocManifest(
        schema_version=str(loaded.get("schema_version", "1")),
        entries=entries,
    )


def _write_manifest(manifest: GeneratedDocManifest, path: Path) -> None:
    payload = {
        "schema_version": manifest.schema_version,
        "entries": [
            {
                "target_path": entry.target_path,
                "generator_id": entry.generator_id,
                "source_paths": entry.source_paths,
                "source_sha": entry.source_sha,
                "content_sha256": entry.content_sha256,
                "marker": entry.marker,
            }
            for entry in manifest.entries
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def load_manifest(path: Path) -> GeneratedDocManifest:
    return _read_manifest(path)


def write_manifest(manifest: GeneratedDocManifest, path: Path) -> None:
    _write_manifest(manifest, path)


def _result_map(results: Iterable[GeneratorResult]) -> dict[str, GeneratorResult]:
    return {_normalize_path(str(result.target_path), repo_root=None): result for result in results}


def _normalize_path(raw: str, repo_root: Path | None) -> str:
    path = Path(raw)
    if repo_root is not None:
        try:
            return path.relative_to(repo_root).as_posix()
        except ValueError:
            pass
    return str(path.as_posix()).lstrip("./")


def _iter_generators(requested: Iterable[str] | None) -> list[str]:
    if not requested:
        return list(TARGETS.keys())
    return [item for item in requested if item in TARGETS]


def check_generated(
    *,
    repo_root: Path,
    manifest_path: Path,
    update: bool = False,
    generators: Iterable[str] | None = None,
) -> tuple[AuditReport, GeneratedDocManifest]:
    manifest = load_manifest(manifest_path)
    selected = _iter_generators(generators)
    generated = collect_results(repo_root=repo_root, generators=selected)
    generated_map = _result_map(generated)
    findings: list[AuditFinding] = []

    # filter to only manifest rows for selected generators.
    manifest_entries = [entry for entry in manifest.entries if (not selected or entry.generator_id in selected)]
    manifest_map = {entry.target_path: entry for entry in manifest_entries}

    for target, manifest_entry in manifest_map.items():
        target_path = repo_root / target
        relative_target = _normalize_path(target, repo_root=repo_root)
        result = generated_map.get(relative_target)
        if result is None:
            absolute_target = _normalize_path(str(target_path), repo_root=repo_root)
            result = generated_map.get(absolute_target)

        if target_path.exists() is False:
            findings.append(
                build_finding(
                    finding_id="generated-doc-missing",
                    tool="auto_generated_lint",
                    finding_class="generated-doc",
                    severity="error",
                    message=f"Generated doc missing from filesystem: {target}",
                    path=target_path,
                    subject="generated-doc",
                )
            )
            continue

        current = target_path.read_text(encoding="utf-8")
        if result is not None:
            result_manifest = result.manifest_entry or {}
            fresh_source_sha = str(result_manifest["source_sha"])
            if manifest_entry.source_sha and manifest_entry.source_sha != fresh_source_sha:
                findings.append(
                    build_finding(
                        finding_id="generated-doc-stale",
                        tool="auto_generated_lint",
                        finding_class="generated-doc",
                        severity="error",
                        message=f"Generated doc {target} stale source hash mismatch",
                        path=target_path,
                        subject="generated-doc-source",
                    )
                )

            if manifest_entry.content_sha256 and manifest_entry.content_sha256 != _text_sha(current):
                findings.append(
                    build_finding(
                        finding_id="generated-doc-stale",
                        tool="auto_generated_lint",
                        finding_class="generated-doc",
                        severity="error",
                        message=f"Generated doc {target} appears to be hand-edited",
                        path=target_path,
                        subject="generated-doc-content",
                    )
                )
        else:
            findings.append(
                build_finding(
                    finding_id="generated-doc-untracked-target",
                    tool="auto_generated_lint",
                    finding_class="generated-doc",
                    severity="error",
                    message=f"Generated doc {target} is not in current generator output",
                    path=target_path,
                    subject="generated-doc-missing-generator",
                )
            )

    for target in generated_map:
        if target not in manifest_map:
            findings.append(
                build_finding(
                    finding_id="generated-doc-untracked",
                    tool="auto_generated_lint",
                    finding_class="generated-doc",
                    severity="error",
                    message=f"Generated output {target} not present in manifest",
                    path=repo_root / target,
                    subject="generated-doc-manifest",
                )
            )

    if update:
        updated = [
            GeneratedDocManifestEntry(
                target_path=str(result.target_path),
                generator_id=str((result.manifest_entry or {})["generator_id"]),
                source_paths=[str(x) for x in (result.manifest_entry or {})["source_paths"]],
                source_sha=str((result.manifest_entry or {})["source_sha"]),
                content_sha256=str((result.manifest_entry or {})["content_sha256"]),
                marker=str((result.manifest_entry or {})["marker"]),
            )
            for result in generated
            if result.manifest_entry is not None
        ]
        manifest = GeneratedDocManifest(schema_version=manifest.schema_version, entries=updated)
        _write_manifest(manifest, manifest_path)

    return build_report(tool="auto_generated_lint", repo_root=repo_root, findings=findings), manifest


def check(
    *,
    repo_root: Path,
    manifest_path: Path = Path("docs/user/reference/generated-docs.yaml"),
    update: bool = False,
    generators: Iterable[str] | None = None,
) -> AuditReport:
    report, _manifest = check_generated(
        repo_root=repo_root,
        manifest_path=repo_root / manifest_path,
        update=update,
        generators=generators,
    )
    return report


def _serialize(report: AuditReport, as_json: bool) -> None:
    if as_json:
        print(report.model_dump_json())
        return
    for finding in report.findings:
        print(f"[{finding.severity}] {finding.path}:{finding.line or 0} {finding.id} {finding.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check generated-doc freshness and manual edits.")
    parser.add_argument("--manifest", default="docs/user/reference/generated-docs.yaml")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--generator", action="append")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)

    report = check(
        repo_root=Path.cwd(),
        manifest_path=Path(args.manifest),
        update=args.update,
        generators=args.generator,
    )
    if args.update:
        return 0
    _serialize(report, args.format == "json")
    return 1 if report.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
