"""Insert implementation-tracker rows for ADR addendum frontmatter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from scieasy.qa.schemas.tracker import ImplementationTracker  # noqa: E402

TRACKER_PATH = Path("docs/audit/adr-042-implementation-tracker.yaml")


def parse_frontmatter(path: Path) -> dict[str, Any]:
    """Return YAML frontmatter from a markdown file."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    _, frontmatter, _body = text.split("---", 2)
    return yaml.safe_load(frontmatter) or {}


def propagate(addendum_path: Path, tracker_path: Path) -> bool:
    """Add a not_started tracker row for an addendum without overwriting rows."""
    frontmatter = parse_frontmatter(addendum_path)
    governs = frontmatter.get("governs") or {}
    files = sorted(set(governs.get("files") or []))
    symbols = sorted(set(governs.get("contracts") or []))
    tests = sorted(set(frontmatter.get("tests") or []))
    if not files and not symbols and not tests:
        return False

    payload = yaml.safe_load(tracker_path.read_text(encoding="utf-8"))
    payload.setdefault("sections", [])
    section = f"ADR-{int(frontmatter.get('adr', 0)):03d} addendum propagation"
    if any(entry.get("section") == section for entry in payload["sections"]):
        return False

    payload["sections"].append(
        {
            "section": section,
            "requires_artifacts": {"files": files, "symbols": symbols, "tests": tests},
            "verification_checks": [
                {
                    "id": "addendum-artifacts-exist",
                    "description": "All addendum-declared artifacts are represented in the tracker.",
                }
            ],
            "status": "not_started",
            "implemented_in_pr": None,
            "verified_at": None,
            "verifier_skill": None,
            "verifier_command": "python scripts/audit/adr_implementation_check.py",
        }
    )
    tracker = ImplementationTracker.model_validate(payload)
    tracker_path.write_text(yaml.safe_dump(tracker.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("addendum", type=Path)
    parser.add_argument("--tracker", type=Path, default=TRACKER_PATH)
    args = parser.parse_args(argv)

    changed = propagate(args.addendum, args.tracker)
    print("tracker updated" if changed else "tracker unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
