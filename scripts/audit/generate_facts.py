"""Generate ADR-042 repository facts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scieasy.qa.audit.griffe_facts import generate_registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ADR-042 facts registry")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--package", default="scieasy")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    registry = generate_registry(args.repo_root, package=args.package)
    payload = registry.model_dump(mode="json")
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
