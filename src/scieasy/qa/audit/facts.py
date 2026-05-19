"""Persistent facts registry helpers for ADR-042."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from scieasy.qa.audit._util import normalise_path
from scieasy.qa.audit.griffe_facts import generate_registry
from scieasy.qa.audit.signature_contracts import extract_signature_contracts
from scieasy.qa.schemas.facts import FactsRegistry
from scieasy.qa.schemas.report import Finding, Severity

DEFAULT_FACTS_PATH = Path("docs/facts/generated.yaml")
DEFAULT_GENERATED_AT = datetime(1970, 1, 1, tzinfo=UTC)


def _hash_tree(digest: Any, root: Path, repo_root: Path, pattern: str = "**/*") -> None:
    for path in sorted(candidate for candidate in root.glob(pattern) if candidate.is_file()):
        relative = path.relative_to(repo_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")


def _source_tree_sha(repo_root: Path, package: str) -> str:
    """Return a stable content hash for fact-producing source inputs."""

    digest = hashlib.sha256()
    for root, pattern in [
        (repo_root / "src" / package.replace(".", "/"), "**/*.py"),
        (repo_root / "docs" / "adr", "ADR-*.md"),
        (repo_root / "docs" / "specs", "*.md"),
        (repo_root / "scripts" / "audit", "*.py"),
    ]:
        if root.exists():
            _hash_tree(digest, root, repo_root, pattern)
    return digest.hexdigest()


def _with_generated_metadata(registry: FactsRegistry, generated_at: datetime) -> FactsRegistry:
    """Normalize generated timestamps across the registry and child facts."""

    registry.generated_at = generated_at
    for fact in registry.facts:
        fact.generated_at = generated_at
    return registry


def facts_to_yaml(registry: FactsRegistry) -> str:
    """Serialize a facts registry as deterministic YAML."""

    payload = registry.model_dump(mode="json")
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)  # type: ignore[no-any-return]


def load_facts(path: Path) -> FactsRegistry:
    """Load and validate a generated facts registry."""

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return FactsRegistry.model_validate(data)


def generate_facts(
    repo_root: Path,
    *,
    source_sha: str | None = None,
    include_observed: bool = False,
    include_signature_contracts: bool = True,
    package: str = "scieasy",
    generated_at: datetime = DEFAULT_GENERATED_AT,
) -> FactsRegistry:
    """Generate ADR-042 facts from the repository.

    ``include_observed`` and ``include_signature_contracts`` are accepted for
    ADR-042 API compatibility; the initial implementation emits griffe-backed
    Python symbol facts only.
    """

    del include_observed
    root = repo_root.resolve()
    sha = source_sha if source_sha is not None else _source_tree_sha(root, package)
    registry = generate_registry(root, package=package, source_sha=sha)
    if include_signature_contracts:
        registry.facts.extend(
            extract_signature_contracts(
                sorted((root / "docs" / "specs").glob("*.md")),
                repo_root=root,
                source_sha=sha,
            )
        )
    return _with_generated_metadata(registry, generated_at)


def write_facts(registry: FactsRegistry, path: Path) -> None:
    """Write a generated facts registry to ``path``."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(facts_to_yaml(registry), encoding="utf-8")


def check_generated_facts(
    repo_root: Path,
    *,
    facts_path: Path = DEFAULT_FACTS_PATH,
    update: bool = False,
    package: str = "scieasy",
    source_sha: str | None = None,
    generated_at: datetime = DEFAULT_GENERATED_AT,
) -> list[Finding]:
    """Check whether the committed facts registry matches generated output."""

    expected = generate_facts(repo_root, package=package, source_sha=source_sha, generated_at=generated_at)
    expected_text = facts_to_yaml(expected)
    path = facts_path if facts_path.is_absolute() else repo_root / facts_path

    if update:
        write_facts(expected, path)
        return []

    try:
        current_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [
            Finding(
                rule_id="facts.generated-missing",
                severity=Severity.ERROR,
                file=normalise_path(path),
                line=1,
                message=f"generated facts registry is missing or unreadable: {exc}",
            )
        ]

    try:
        FactsRegistry.model_validate(yaml.safe_load(current_text))
    except (ValidationError, yaml.YAMLError) as exc:
        return [
            Finding(
                rule_id="facts.generated-invalid",
                severity=Severity.ERROR,
                file=normalise_path(path),
                line=1,
                message=f"generated facts registry is invalid: {exc}",
            )
        ]

    if current_text != expected_text:
        return [
            Finding(
                rule_id="facts.generated-stale",
                severity=Severity.ERROR,
                file=normalise_path(path),
                line=1,
                message="generated facts registry is stale; run scripts/audit/generate_facts.py --write",
            )
        ]
    return []
