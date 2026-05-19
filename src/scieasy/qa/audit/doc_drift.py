"""Classify explicit documentation references against repository facts."""

from __future__ import annotations

import argparse
import importlib
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa._shared import AuditReport
from scieasy.qa.audit._cli import exit_code, print_report
from scieasy.qa.schemas.facts import FactsRegistry, load_facts

_PATH_RE = re.compile(r"`(?P<path>(?:src|docs|scripts|tests|\.github|\.claude|\.codex)/[^`]+)`")
_SYMBOL_RE = re.compile(r"`(?P<symbol>scieasy(?:\.[A-Za-z_][\w]*){1,})`")


def _docs(repo_root: Path, docs: Sequence[Path] | None) -> list[Path]:
    if docs:
        result: list[Path] = []
        for item in docs:
            candidate = item if item.is_absolute() else repo_root / item
            if candidate.is_dir():
                result.extend(sorted(candidate.rglob("*.md")))
            elif candidate.exists() and candidate.suffix.lower() == ".md":
                result.append(candidate)
        return result
    return sorted((repo_root / "docs").rglob("*.md")) if (repo_root / "docs").exists() else []


def _symbol_exists(symbol: str) -> bool:
    parts = symbol.split(".")
    for index in range(len(parts), 0, -1):
        module_name = ".".join(parts[:index])
        attrs = parts[index:]
        try:
            current = importlib.import_module(module_name)
        except Exception:
            continue
        for attr in attrs:
            if not hasattr(current, attr):
                return False
            current = getattr(current, attr)
        return True
    return False


def classify_repo(
    repo_root: Path,
    facts: FactsRegistry,
    *,
    docs: Sequence[Path] | None = None,
) -> AuditReport:
    repo_root = repo_root.resolve()
    findings = []
    fact_subjects = {fact.subject for fact in facts.facts}
    for path in _docs(repo_root, docs):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in _PATH_RE.finditer(text):
            ref = match.group("path").strip()
            line = text[: match.start()].count("\n") + 1
            if "*" in ref:
                continue
            if not (repo_root / ref).exists() and ref not in fact_subjects:
                findings.append(
                    build_finding(
                        finding_id="doc-drift-phantom-reference",
                        tool="doc_drift",
                        finding_class="phantom-reference",
                        severity="error",
                        message=f"Document references missing path {ref}",
                        path=path,
                        line=line,
                        subject=ref,
                    )
                )
        for match in _SYMBOL_RE.finditer(text):
            symbol = match.group("symbol")
            line = text[: match.start()].count("\n") + 1
            if symbol not in fact_subjects and not _symbol_exists(symbol):
                findings.append(
                    build_finding(
                        finding_id="doc-drift-phantom-symbol",
                        tool="doc_drift",
                        finding_class="phantom-reference",
                        severity="error",
                        message=f"Document references missing symbol {symbol}",
                        path=path,
                        line=line,
                        subject=symbol,
                    )
                )
    return build_report(tool="doc_drift", repo_root=repo_root, findings=findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify ADR-042 documentation drift.")
    parser.add_argument("--facts", default="docs/facts/generated.yaml")
    parser.add_argument("docs", nargs="*")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    try:
        report = classify_repo(
            Path.cwd(),
            load_facts(Path(args.facts)),
            docs=[Path(item) for item in args.docs] or None,
        )
    except Exception as exc:
        print(f"doc_drift: {exc}", file=sys.stderr)
        return 2
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
