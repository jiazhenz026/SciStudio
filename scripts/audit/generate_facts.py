"""Generate ADR-042 repository facts."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from scieasy.qa.audit.facts import (
    DEFAULT_FACTS_PATH,
    DEFAULT_GENERATED_AT,
    check_generated_facts,
    facts_to_yaml,
    generate_facts,
    write_facts,
)
from scieasy.qa.schemas.report import Severity


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO datetime: {value}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ADR-042 facts registry")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--package", default="scieasy")
    parser.add_argument("--facts-path", type=Path, default=DEFAULT_FACTS_PATH)
    parser.add_argument("--output", type=Path, default=None, help="Alias for --facts-path when writing/checking")
    parser.add_argument("--source-sha", default=None)
    parser.add_argument("--generated-at", type=_parse_datetime, default=None)
    parser.add_argument("--write", action="store_true", help="Write docs/facts/generated.yaml")
    parser.add_argument("--check", action="store_true", help="Fail if docs/facts/generated.yaml is stale")
    args = parser.parse_args()

    if args.write and args.check:
        parser.error("--write and --check are mutually exclusive")

    facts_path = args.output or args.facts_path
    resolved_facts_path = facts_path if facts_path.is_absolute() else args.repo_root / facts_path
    generated_at = args.generated_at or DEFAULT_GENERATED_AT

    try:
        if args.write:
            registry = generate_facts(
                args.repo_root,
                package=args.package,
                source_sha=args.source_sha,
                generated_at=generated_at,
            )
            write_facts(registry, resolved_facts_path)
            return 0

        if args.check:
            findings = check_generated_facts(
                args.repo_root,
                facts_path=facts_path,
                package=args.package,
                source_sha=args.source_sha,
                generated_at=generated_at,
            )
            for finding in findings:
                print(f"{finding.severity}: {finding.file}: {finding.message}", file=sys.stderr)
            return 1 if any(finding.severity == Severity.ERROR for finding in findings) else 0

        registry = generate_facts(
            args.repo_root,
            package=args.package,
            source_sha=args.source_sha,
            generated_at=generated_at,
        )
    except Exception as exc:
        print(f"generate_facts failed: {exc}", file=sys.stderr)
        return 2

    text = facts_to_yaml(registry)
    if args.output is None:
        print(text, end="")
    else:
        write_facts(registry, resolved_facts_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
