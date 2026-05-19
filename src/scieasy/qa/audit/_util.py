"""Shared helpers for ADR-042 audit tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from scieasy.qa.schemas.frontmatter import ADRFrontmatter, SpecFrontmatter
from scieasy.qa.schemas.report import Finding, Severity


def normalise_path(path: Path | str) -> str:
    """Return a repository-style slash-separated path string."""

    return str(path).replace("\\", "/")


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


def load_adr_frontmatter(path: Path) -> tuple[ADRFrontmatter | None, str, list[Finding]]:
    """Load and validate ADR frontmatter."""

    data, body, findings = parse_yaml_frontmatter(path)
    if data is None:
        return None, body, findings
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
