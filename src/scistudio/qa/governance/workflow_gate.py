"""CLI wrapper for shared local/CI ADR-042 workflow gate orchestration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scistudio.qa.governance.gate_record.workflow import run_ci


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("ci",))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--pr-body", default="")
    parser.add_argument("--pr-label", action="append", default=[])
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = run_ci(
        repo_root=args.repo_root,
        gate_record=args.gate_record,
        base=args.base,
        head=args.head,
        pr_body=args.pr_body,
        pr_labels=args.pr_label,
    )
    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        if report.blocks_merge:
            print("workflow_gate: fail")
            for finding in report.findings:
                print(f"- {finding.rule_id}: {finding.message}")
        else:
            print("workflow_gate: pass")
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    raise SystemExit(main())
