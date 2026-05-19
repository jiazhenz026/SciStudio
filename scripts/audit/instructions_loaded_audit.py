"""Report loaded AI instruction metadata for ADR-042 diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from scieasy.qa._report_helpers import build_report  # noqa: E402


def audit_loaded_instructions(*, repo_root: Path, runtime: str, metadata_path: Path | None = None):
    metadata = {}
    if metadata_path and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    instruction_files = [
        path.as_posix()
        for path in [
            repo_root / "AGENTS.md",
            repo_root / f".{runtime}" / "memory" / "constitution.md",
        ]
        if path.exists()
    ]
    report = build_report(
        tool="instructions_loaded_audit",
        repo_root=repo_root,
        findings=[],
        summary={
            "runtime": runtime,
            "metadata": metadata,
            "instruction_files": instruction_files,
            "report_only": True,
        },
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report loaded AI instructions.")
    parser.add_argument("--runtime", default="codex")
    parser.add_argument("--metadata")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    report = audit_loaded_instructions(
        repo_root=REPO_ROOT,
        runtime=args.runtime,
        metadata_path=Path(args.metadata) if args.metadata else None,
    )
    if args.format == "json":
        print(report.model_dump_json())
    else:
        print(f"runtime={args.runtime} instruction_files={len(report.summary.get('instruction_files', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
