"""Shared helpers for ADR-042 audit tools."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from scieasy.qa.schemas.frontmatter import ADRFrontmatter, SpecFrontmatter
from scieasy.qa.schemas.maintainers import Maintainers
from scieasy.qa.schemas.report import Finding, Severity


def normalise_path(path: Path | str) -> str:
    """Return a repository-style slash-separated path string."""

    return str(path).replace("\\", "/")


def git_tracked_relative_paths(repo_root: Path) -> set[str] | None:
    """Return git-indexed repo paths, or ``None`` outside a git worktree."""

    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=False,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return {item.decode("utf-8").replace("\\", "/") for item in result.stdout.split(b"\0") if item}


def is_tracked_path(path: Path, repo_root: Path, tracked_paths: set[str] | None) -> bool:
    """Return true when ``path`` should participate in committed-state audits."""

    if tracked_paths is None:
        return True
    try:
        relative = normalise_path(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return False
    return relative in tracked_paths


def parse_frontmatter_block(path: Path) -> tuple[str | None, str]:
    """Return ``(frontmatter_text, body_text)`` for a Markdown file."""

    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n") and not raw.startswith("---\r\n"):
        return None, raw

    marker = "\r\n---\r\n" if raw.startswith("---\r\n") else "\n---\n"
    start = 5 if marker.startswith("\r\n") else 4
    end = raw.find(marker, start)
    if end < 0:
        return None, raw
    return raw[start:end].strip(), raw[end + len(marker) :]


def parse_yaml_frontmatter(path: Path) -> tuple[dict[str, Any] | None, str, list[Finding]]:
    """Parse YAML frontmatter and return ``(data, body, findings)``."""

    payload, body = parse_frontmatter_block(path)
    if payload is None:
        return (
            None,
            body,
            [
                Finding(
                    rule_id="frontmatter.missing",
                    severity=Severity.ERROR,
                    file=normalise_path(path),
                    line=1,
                    message="missing YAML frontmatter",
                )
            ],
        )

    try:
        loaded = yaml.safe_load(payload) or {}
    except yaml.YAMLError as exc:
        return (
            None,
            body,
            [
                Finding(
                    rule_id="frontmatter.yaml",
                    severity=Severity.ERROR,
                    file=normalise_path(path),
                    line=1,
                    message=f"invalid frontmatter YAML: {exc}",
                )
            ],
        )

    if not isinstance(loaded, dict):
        return (
            None,
            body,
            [
                Finding(
                    rule_id="frontmatter.yaml",
                    severity=Severity.ERROR,
                    file=normalise_path(path),
                    line=1,
                    message="frontmatter root must be a mapping",
                )
            ],
        )
    return loaded, body, []


def _iter_governance_amendment_blocks(body: str) -> list[str]:
    blocks: list[str] = []
    active = False
    current: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            fence_info = stripped[3:].strip()
            if active:
                blocks.append("\n".join(current))
                current = []
                active = False
                continue
            if fence_info == "yaml adr042-governance-amendment":
                active = True
                current = []
                continue
        if active:
            current.append(line)
    return blocks


def _merge_unique(existing: list[str], *, add: list[str], remove: list[str]) -> list[str]:
    remove_set = set(remove)
    merged = [item for item in existing if item not in remove_set]
    seen = set(merged)
    for item in add:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


def _apply_governance_amendments(
    data: dict[str, Any],
    body: str,
    *,
    path: Path,
) -> tuple[dict[str, Any], list[Finding]]:
    amendments = _iter_governance_amendment_blocks(body)
    if not amendments:
        return data, []

    amended = dict(data)
    governs = dict(amended.get("governs") or {})
    findings: list[Finding] = []
    for index, raw in enumerate(amendments, start=1):
        try:
            loaded = yaml.safe_load(raw) or {}
        except yaml.YAMLError as exc:
            findings.append(
                Finding(
                    rule_id="frontmatter.amendment-yaml",
                    severity=Severity.ERROR,
                    file=normalise_path(path),
                    line=1,
                    message=f"invalid ADR-042 governance amendment #{index}: {exc}",
                )
            )
            continue
        if not isinstance(loaded, dict):
            findings.append(
                Finding(
                    rule_id="frontmatter.amendment-shape",
                    severity=Severity.ERROR,
                    file=normalise_path(path),
                    line=1,
                    message=f"ADR-042 governance amendment #{index} must be a mapping",
                )
            )
            continue
        amended_governs = loaded.get("governs", {})
        if not isinstance(amended_governs, dict):
            findings.append(
                Finding(
                    rule_id="frontmatter.amendment-shape",
                    severity=Severity.ERROR,
                    file=normalise_path(path),
                    line=1,
                    message=f"ADR-042 governance amendment #{index} governs must be a mapping",
                )
            )
            continue
        for surface in ("modules", "contracts", "entry_points", "files", "excludes"):
            operations = amended_governs.get(surface)
            if operations is None:
                continue
            if not isinstance(operations, dict):
                findings.append(
                    Finding(
                        rule_id="frontmatter.amendment-shape",
                        severity=Severity.ERROR,
                        file=normalise_path(path),
                        line=1,
                        message=f"ADR-042 governance amendment #{index} {surface} must use add/remove lists",
                    )
                )
                continue
            add = operations.get("add", [])
            remove = operations.get("remove", [])
            if not isinstance(add, list) or not isinstance(remove, list):
                findings.append(
                    Finding(
                        rule_id="frontmatter.amendment-shape",
                        severity=Severity.ERROR,
                        file=normalise_path(path),
                        line=1,
                        message=f"ADR-042 governance amendment #{index} {surface} add/remove must be lists",
                    )
                )
                continue
            governs[surface] = _merge_unique(list(governs.get(surface) or []), add=add, remove=remove)
    amended["governs"] = governs
    return amended, findings


def load_adr_frontmatter(path: Path) -> tuple[ADRFrontmatter | None, str, list[Finding]]:
    """Load and validate ADR frontmatter."""

    data, body, findings = parse_yaml_frontmatter(path)
    if data is None:
        return None, body, findings
    data, amendment_findings = _apply_governance_amendments(data, body, path=path)
    if amendment_findings:
        return None, body, amendment_findings
    try:
        return ADRFrontmatter.model_validate(data), body, []
    except ValidationError as exc:
        return (
            None,
            body,
            [
                Finding(
                    rule_id="frontmatter.validation",
                    severity=Severity.ERROR,
                    file=normalise_path(path),
                    line=1,
                    message=f"ADR frontmatter validation failed: {exc}",
                )
            ],
        )


def load_spec_frontmatter(path: Path) -> tuple[SpecFrontmatter | None, str, list[Finding]]:
    """Load and validate spec frontmatter."""

    data, body, findings = parse_yaml_frontmatter(path)
    if data is None:
        return None, body, findings
    data, amendment_findings = _apply_governance_amendments(data, body, path=path)
    if amendment_findings:
        return None, body, amendment_findings
    try:
        return SpecFrontmatter.model_validate(data), body, []
    except ValidationError as exc:
        return (
            None,
            body,
            [
                Finding(
                    rule_id="frontmatter.validation",
                    severity=Severity.ERROR,
                    file=normalise_path(path),
                    line=1,
                    message=f"Spec frontmatter validation failed: {exc}",
                )
            ],
        )


def load_maintainers(path: Path) -> Maintainers:
    """Load and validate a MAINTAINERS ownership registry."""

    return Maintainers.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
