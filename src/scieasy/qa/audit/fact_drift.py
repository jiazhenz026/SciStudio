"""Check explicit fact substitutions in documentation."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa.audit._cli import exit_code, print_report
from scieasy.qa.schemas.facts import FactsRegistry, load_facts

_SUBSTITUTION_RE = re.compile(
    r"\{\{\s*fact:(?P<brace_id>[^}\s=]+)(?:\s*=\s*(?P<brace_value>[^}]+))?\s*\}\}|"
    r"<!--\s*fact:(?P<html_id>[^\s]+)(?:\s+value:(?P<html_value>[^-]+))?\s*-->",
    flags=re.IGNORECASE,
)


def _docs(repo_root: Path, docs: Sequence[Path] | None) -> list[Path]:
    if docs:
        result: list[Path] = []
        for item in docs:
            candidate = item if item.is_absolute() else repo_root / item
            if candidate.is_dir():
                result.extend(sorted(candidate.rglob("*.md")))
            elif candidate.suffix.lower() == ".md" and candidate.exists():
                result.append(candidate)
        return result
    return sorted((repo_root / "docs").rglob("*.md")) if (repo_root / "docs").exists() else []


def check_substitutions(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    docs: Sequence[Path] | None = None,
):
    repo_root = repo_root.resolve()
    fact_map = facts.by_id()
    findings = []
    for path in _docs(repo_root, docs):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in _SUBSTITUTION_RE.finditer(text):
            fact_id = (match.group("brace_id") or match.group("html_id") or "").strip()
            expected_value = (match.group("brace_value") or match.group("html_value") or "").strip()
            line = text[: match.start()].count("\n") + 1
            fact = fact_map.get(fact_id)
            if fact is None:
                findings.append(
                    build_finding(
                        finding_id="fact-drift-phantom",
                        tool="fact_drift",
                        finding_class="phantom-reference",
                        severity="error",
                        message=f"Fact substitution references missing fact {fact_id}",
                        path=path,
                        line=line,
                        subject=fact_id,
                    )
                )
                continue
            actual = str(fact.value)
            if expected_value and expected_value not in {actual, str(fact.subject), str(fact.id)}:
                findings.append(
                    build_finding(
                        finding_id="fact-drift-stale-substitution",
                        tool="fact_drift",
                        finding_class="behavior-drift",
                        severity="error",
                        message=f"Fact substitution for {fact_id} is stale",
                        path=path,
                        line=line,
                        subject=fact_id,
                        expected=actual,
                        actual=expected_value,
                    )
                )
    return build_report(tool="fact_drift", repo_root=repo_root, findings=findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate ADR-042 fact substitutions.")
    parser.add_argument("--facts", default="docs/facts/generated.yaml")
    parser.add_argument("docs", nargs="*")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    try:
        report = check_substitutions(
            Path.cwd(),
            load_facts(Path(args.facts)),
            docs=[Path(item) for item in args.docs] or None,
        )
    except Exception as exc:
        print(f"fact_drift: {exc}", file=sys.stderr)
        return 2
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
