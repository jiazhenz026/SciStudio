"""Generate ``docs/facts/generated.yaml`` (ADR-042 §7.5.3 orchestrator).

Runs every per-namespace extractor (workflow / tool / adr / maintainers /
skill) and aggregates the results into a :class:`scieasy.qa.schemas.facts.FactsRegistry`
which is serialised to ``docs/facts/generated.yaml``.

Source-SHA tracking
-------------------
For each contributing source file, we record the file's blob SHA via
``git hash-object`` semantics (computed in-process from the bytes so this
script does not require a Git executable). The map is keyed by repo-relative
posix path and embedded in :attr:`FactsRegistry.source_shas`.

Generation cadence (per ADR-042 §7.5.3):

- Pre-commit hook on relevant source change.
- CI per PR (regenerate + diff vs committed copy).
- Manual: ``python -m scripts.audit.generate_facts`` or
  ``python scripts/audit/generate_facts.py``.

References
----------
ADR-042 §7.5.1 — design rationale.
ADR-042 §7.5.2 — pydantic models.
ADR-042 §7.5.3 — generation pipeline (this script).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from scieasy.qa.schemas.facts import FactsRegistry

if __package__:
    # Imported as ``scripts.audit.generate_facts`` — preferred. Use relative imports.
    from . import (
        extract_adr_facts,
        extract_maintainers_facts,
        extract_skill_facts,
        extract_tool_facts,
        extract_workflow_facts,
    )
else:  # pragma: no cover - direct script execution path
    # Script invoked as ``python scripts/audit/generate_facts.py``.
    # ``scripts/`` is not yet in sys.path; add the repo root and re-import.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.audit import (  # type: ignore[no-redef]
        extract_adr_facts,
        extract_maintainers_facts,
        extract_skill_facts,
        extract_tool_facts,
        extract_workflow_facts,
    )


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise FileNotFoundError("could not locate repo root from generate_facts.py")


def _git_blob_sha(path: Path) -> str:
    """Compute the git blob SHA-1 of a file's contents.

    Matches ``git hash-object <path>`` byte-for-byte without requiring the
    Git binary. Returns the empty string if the file is absent.
    """
    if not path.is_file():
        return ""
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def generate(repo_root: Path | None = None) -> FactsRegistry:
    """Run all extractors and return the populated :class:`FactsRegistry`."""
    root = repo_root or _find_repo_root()

    workflow = extract_workflow_facts.extract(root / ".workflow" / "schema-v2.yaml")
    tool = extract_tool_facts.extract(
        root / "pyproject.toml",
        root / ".pre-commit-config.yaml",
    )
    adr = extract_adr_facts.extract(root / "docs" / "adr")
    maintainers = extract_maintainers_facts.extract(root / "MAINTAINERS")
    skill = extract_skill_facts.extract(
        root / "docs" / "skills" / "required.yaml",
        repo_root=root,
    )

    source_shas = {
        ".workflow/schema-v2.yaml": _git_blob_sha(root / ".workflow" / "schema-v2.yaml"),
        "pyproject.toml": _git_blob_sha(root / "pyproject.toml"),
        ".pre-commit-config.yaml": _git_blob_sha(root / ".pre-commit-config.yaml"),
        "MAINTAINERS": _git_blob_sha(root / "MAINTAINERS"),
        "docs/skills/required.yaml": _git_blob_sha(root / "docs" / "skills" / "required.yaml"),
    }

    return FactsRegistry(
        schema_version=1,
        generated_at=datetime.now(UTC),
        source_shas=source_shas,
        workflow=workflow,
        tool=tool,
        adr=adr,
        maintainers=maintainers,
        skill=skill,
    )


def write_yaml(registry: FactsRegistry, output_path: Path) -> None:
    """Serialise a :class:`FactsRegistry` to a YAML file (UTF-8, sorted keys disabled)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Use mode='json' so datetime → ISO string + StrEnum → bare value.
    payload = registry.model_dump(mode="json")
    output_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Writes ``docs/facts/generated.yaml`` and exits 0."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output YAML path (defaults to docs/facts/generated.yaml).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Generate but do not write; compare against existing file and exit 1 on diff.",
    )
    args = parser.parse_args(argv)

    root = _find_repo_root()
    output = args.output or (root / "docs" / "facts" / "generated.yaml")

    registry = generate(root)

    if args.check:
        if not output.is_file():
            print(f"check failed: {output} does not exist", file=sys.stderr)
            return 1
        existing = output.read_text(encoding="utf-8")
        candidate = yaml.safe_dump(
            registry.model_dump(mode="json"),
            sort_keys=False,
            default_flow_style=False,
        )
        # Strip the generated_at timestamp before comparing (it always differs).
        if _strip_volatile(existing) != _strip_volatile(candidate):
            print(f"check failed: {output} is out of date", file=sys.stderr)
            return 1
        return 0

    write_yaml(registry, output)
    print(f"wrote {output}")
    return 0


def _strip_volatile(text: str) -> str:
    """Strip the ``generated_at:`` line so two runs compare equal."""
    return "\n".join(line for line in text.splitlines() if not line.startswith("generated_at:"))


if __name__ == "__main__":
    sys.exit(main())
