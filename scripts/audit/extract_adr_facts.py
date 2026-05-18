"""Extract ADR facts from ``docs/adr/*.md`` frontmatter (ADR-042 §7.5.3).

Produces a :class:`scieasy.qa.schemas.facts.ADRFacts` instance with:

- ``total_count``: number of ``docs/adr/ADR-NNN.md`` files matched.
- ``by_status``: histogram of frontmatter ``status:`` values.
- ``latest_adr_number``: max ``adr:`` number across the corpus.

We deliberately parse frontmatter as raw YAML without pydantic-validating it,
because the corpus contains historical ADRs whose frontmatter shapes pre-date
the 1A-a ``ADRFrontmatter`` schema. Validation lives in a different
auditor (``frontmatter_lint``, Phase 1B); the facts extractor only counts.

Reads
-----
``docs/adr/ADR-*.md`` — the entire ADR corpus.

References
----------
ADR-042 §7.5.3 — generation table (adr namespace row).
ADR-042 §5 — ADRFrontmatter schema (for the canonical ``adr`` / ``status``
field names, but NOT enforced here).
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from scieasy.qa.schemas.facts import ADRFacts

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_FILENAME_RE = re.compile(r"^ADR-(\d+)(?:[.\-].*)?\.md$", re.IGNORECASE)


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise FileNotFoundError("could not locate repo root from extract_adr_facts.py")


def _parse_frontmatter(text: str) -> dict[str, Any]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    parsed = yaml.safe_load(match.group(1)) or {}
    return parsed if isinstance(parsed, dict) else {}


def extract(adr_dir: Path | None = None) -> ADRFacts:
    """Walk ``docs/adr/`` and return an :class:`ADRFacts` aggregate.

    Args:
        adr_dir: Optional explicit ADR directory. Defaults to
            ``<repo-root>/docs/adr``.

    Empty / malformed frontmatter is tolerated (the file is counted but
    contributes ``status='unknown'`` to the histogram).
    """
    root = _find_repo_root()
    adr_dir = adr_dir or (root / "docs" / "adr")
    if not adr_dir.is_dir():
        # Empty corpus is a valid (if degenerate) state — bootstrap projects.
        return ADRFacts(total_count=0, by_status={}, latest_adr_number=0)

    status_counter: collections.Counter[str] = collections.Counter()
    latest = 0
    total = 0
    for entry in sorted(adr_dir.iterdir()):
        if not entry.is_file():
            continue
        m = _FILENAME_RE.match(entry.name)
        if not m:
            # Skip non-ADR markdown (e.g. ADR.md catalogue, READMEs).
            continue
        total += 1
        try:
            number = int(m.group(1))
        except ValueError:
            number = 0
        latest = max(latest, number)

        try:
            fm = _parse_frontmatter(entry.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            fm = {}
        status = str(fm.get("status") or "unknown")
        status_counter[status] += 1

    return ADRFacts(
        total_count=total,
        by_status=dict(status_counter),
        latest_adr_number=latest,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Prints a JSON dump of the ADR facts to stdout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adr-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    facts = extract(args.adr_dir)
    print(json.dumps(facts.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
