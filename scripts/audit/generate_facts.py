"""Generate or check ADR-042 repository facts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from scieasy.qa.audit.facts import check_generated_facts  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate ADR-042 repository facts.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--facts-path", default="docs/facts/generated.yaml")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)

    report = check_generated_facts(
        REPO_ROOT,
        facts_path=Path(args.facts_path),
        update=args.write,
    )
    if args.format == "json":
        print(report.model_dump_json())
    elif report.findings:
        for finding in report.findings:
            print(f"[{finding.severity}] {finding.path}:{finding.line or 0} {finding.id} {finding.message}")
    return 1 if report.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
