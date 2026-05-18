"""Extract MAINTAINERS facts (ADR-042 §7.5.3).

Produces a :class:`scieasy.qa.schemas.facts.MaintainersFacts` instance with:

- ``entry_count``: number of ownership entries.
- ``human_count``: distinct human GitHub handles across all entries.
- ``paths_covered_count``: number of distinct path globs referenced.

The ``MAINTAINERS`` file format follows ADR-042 §6 (YAML stream with one
``MaintainersEntry`` per document). If the file is absent, returns a
zeroed :class:`MaintainersFacts` — bootstrap projects without a
``MAINTAINERS`` file should not block the facts pipeline.

# TODO(#1155): once ``MAINTAINERS`` lands as a tracked file (ADR-042 §6,
#   currently absent from the repo), tighten this extractor to require the
#   file's presence. Out of scope per ADR-042 §7.5.3 + §27.4 self-exemption.
#   Followup: open as part of ADR-042 Phase 1 (TC-1H.8 followup batch).

Reads
-----
``MAINTAINERS`` — repo root (optional; absence is non-fatal).

References
----------
ADR-042 §6 — MAINTAINERS schema.
ADR-042 §7.5.3 — generation table (maintainers namespace row).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from scieasy.qa.schemas.facts import MaintainersFacts


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise FileNotFoundError("could not locate repo root from extract_maintainers_facts.py")


def extract(maintainers_path: Path | None = None) -> MaintainersFacts:
    """Read ``MAINTAINERS`` and return a :class:`MaintainersFacts` aggregate.

    Args:
        maintainers_path: Optional explicit path. Defaults to ``<root>/MAINTAINERS``.

    If the file does not exist, returns ``MaintainersFacts(entry_count=0, ...)``
    rather than raising — see the module-level TODO for follow-up.
    """
    root = _find_repo_root()
    path = maintainers_path or (root / "MAINTAINERS")
    if not path.is_file():
        return MaintainersFacts(entry_count=0, human_count=0, paths_covered_count=0)

    raw = path.read_text(encoding="utf-8")
    docs = list(yaml.safe_load_all(raw))
    entries = [d for d in docs if isinstance(d, dict) and d]

    humans: set[str] = set()
    paths: set[str] = set()
    for entry in entries:
        owners = entry.get("owners") or []
        if isinstance(owners, list):
            for owner in owners:
                if isinstance(owner, str) and owner.startswith("@"):
                    humans.add(owner)
        entry_paths = entry.get("paths") or []
        if isinstance(entry_paths, list):
            for p in entry_paths:
                if isinstance(p, str):
                    paths.add(p)

    return MaintainersFacts(
        entry_count=len(entries),
        human_count=len(humans),
        paths_covered_count=len(paths),
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Prints a JSON dump of the maintainers facts to stdout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maintainers", type=Path, default=None)
    args = parser.parse_args(argv)
    facts = extract(args.maintainers)
    print(json.dumps(facts.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
