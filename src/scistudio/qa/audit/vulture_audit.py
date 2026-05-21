"""Vulture dead-code child report for the ADR-042 full audit pipeline.

Vulture is named in ``docs/specs/adr-042-code-quality-tools.md`` as a standard
external code-quality tool the project assumes is run. Before issue #1340 it
was never wired anywhere. This module runs vulture against the configured paths
and emits the result as an :class:`AuditReport` so it surfaces through the same
``full_audit`` pipeline as the other ADR-042 consistency checks.

Severity policy
---------------

Vulture findings are reported at :attr:`Severity.WARNING` so the child report
never sets ``blocks_merge`` on its own. This matches the informational rollout
called out in issue #1340: noise has not been baselined yet, and an immediate
hard-fail would punish PRs for pre-existing dead code unrelated to their scope.
A follow-up issue can promote selected vulture rule classes to ``ERROR`` once
the allowlist is curated.

If the ``vulture`` package is not importable, the child report is emitted with
``AuditStatus.SKIPPED`` and a single ``info`` finding. This keeps the full
audit usable on developer machines that have not yet installed the optional
dev dependency.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scistudio.qa.audit._util import normalise_path
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

if TYPE_CHECKING:
    from vulture import Vulture as _VultureType

TOOL_NAME = "vulture"

DEFAULT_PATHS: tuple[str, ...] = ("src/scistudio",)
DEFAULT_MIN_CONFIDENCE = 80
DEFAULT_ALLOWLIST = "vulture_allowlist.py"

# File path uses non-greedy ``.+?`` because Windows paths begin with a drive
# letter colon (``C:\``) that would otherwise be confused with the
# line-number colon.
_VULTURE_LINE_RE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):\s+(?P<message>.+?)\s+\((?P<confidence>\d+)%\s+confidence\)\s*$"
)


def _vulture_available() -> bool:
    try:
        import vulture  # noqa: F401
    except ImportError:
        return False
    return True


def _resolve_targets(repo_root: Path, paths: Sequence[str]) -> list[Path]:
    resolved: list[Path] = []
    for raw in paths:
        candidate = Path(raw)
        absolute = candidate if candidate.is_absolute() else repo_root / candidate
        if absolute.exists():
            resolved.append(absolute)
    return resolved


def _load_pyproject_vulture_config(repo_root: Path) -> Mapping[str, Any]:
    """Return ``[tool.vulture]`` from ``pyproject.toml`` or an empty mapping.

    Vulture's CLI reads ``[tool.vulture]`` automatically, but the in-process
    API does not. Loading the same table here keeps the audit child report
    consistent with ``vulture`` run from the command line, so config such as
    ``ignore_decorators = ["@app.*", "@router.*", "@pytest.fixture"]`` and
    ``exclude = ["src/scistudio/api/static/**"]`` actually applies and isn't
    silent dead config (#1340).
    """

    pyproject = repo_root / "pyproject.toml"
    if not pyproject.exists():
        return {}
    try:
        with pyproject.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    tool_section = data.get("tool", {})
    if not isinstance(tool_section, Mapping):
        return {}
    vulture_section = tool_section.get("vulture", {})
    return vulture_section if isinstance(vulture_section, Mapping) else {}


def _config_list(config: Mapping[str, Any], key: str) -> list[str]:
    value = config.get(key)
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _run_vulture(
    repo_root: Path,
    targets: Sequence[Path],
    *,
    allowlist: Path | None,
    min_confidence: int,
    pyproject_config: Mapping[str, Any] | None = None,
) -> str:
    """Run vulture in-process and return its captured stdout.

    Running in-process keeps the subprocess boundary out of the audit path
    (important on Windows where ``subprocess`` startup latency dominates).
    The ``[tool.vulture]`` table from ``pyproject.toml`` is honored here so
    ``exclude``, ``ignore_decorators``, and ``ignore_names`` from the repo
    config match what the ``vulture`` CLI would do.
    """

    from vulture import Vulture

    config = pyproject_config if pyproject_config is not None else _load_pyproject_vulture_config(repo_root)
    ignore_decorators = _config_list(config, "ignore_decorators")
    ignore_names = _config_list(config, "ignore_names")
    excludes = _config_list(config, "exclude")

    vulture: _VultureType = Vulture(
        verbose=False,
        ignore_decorators=ignore_decorators or None,
        ignore_names=ignore_names or None,
    )
    scan_paths: list[str] = [str(path) for path in targets]
    if allowlist is not None and allowlist.exists():
        scan_paths.append(str(allowlist))
    vulture.scavenge(scan_paths, exclude=excludes or None)

    buf = io.StringIO()
    stdout, sys.stdout = sys.stdout, buf
    try:
        vulture.report(min_confidence=min_confidence, sort_by_size=False, make_whitelist=False)
    finally:
        sys.stdout = stdout
    return buf.getvalue()


def _parse_findings(report_text: str, repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for line in report_text.splitlines():
        match = _VULTURE_LINE_RE.match(line.strip())
        if match is None:
            continue
        raw_path = match.group("file")
        try:
            relative = Path(raw_path).resolve().relative_to(repo_root)
            display = normalise_path(relative)
        except (OSError, ValueError):
            display = normalise_path(Path(raw_path))
        line_no = int(match.group("line"))
        message = match.group("message")
        confidence = int(match.group("confidence"))
        findings.append(
            Finding(
                rule_id="vulture.dead-code",
                severity=Severity.WARNING,
                file=display,
                line=line_no,
                message=f"{message} ({confidence}% confidence)",
                evidence={"confidence": confidence},
            )
        )
    return findings


def check(
    repo_root: Path,
    *,
    paths: Sequence[str] = DEFAULT_PATHS,
    allowlist: str | Path | None = DEFAULT_ALLOWLIST,
    min_confidence: int = DEFAULT_MIN_CONFIDENCE,
) -> AuditReport:
    """Run vulture against ``paths`` and return the audit child report.

    Returns ``AuditStatus.SKIPPED`` when vulture is not importable. Otherwise
    returns ``AuditStatus.PASS`` with WARNING-severity findings; the report
    never sets ``blocks_merge`` in this rollout phase.
    """

    root = repo_root.resolve()
    if not _vulture_available():
        return AuditReport(
            tool=TOOL_NAME,
            status=AuditStatus.SKIPPED,
            source_sha="",
            findings=[
                Finding(
                    rule_id="vulture.unavailable",
                    severity=Severity.INFO,
                    file="",
                    message="vulture is not installed; install the dev extras to enable this check",
                )
            ],
            summary={
                "paths": list(paths),
                "min_confidence": min_confidence,
                "vulture_available": False,
            },
        )

    targets = _resolve_targets(root, paths)
    if not targets:
        return AuditReport(
            tool=TOOL_NAME,
            status=AuditStatus.PASS,
            source_sha="",
            findings=[],
            summary={
                "paths": list(paths),
                "min_confidence": min_confidence,
                "targets_resolved": 0,
                "vulture_available": True,
            },
        )

    allowlist_path: Path | None = None
    if allowlist is not None:
        candidate = Path(allowlist)
        allowlist_path = candidate if candidate.is_absolute() else root / candidate

    pyproject_config = _load_pyproject_vulture_config(root)
    report_text = _run_vulture(
        root,
        targets,
        allowlist=allowlist_path,
        min_confidence=min_confidence,
        pyproject_config=pyproject_config,
    )
    findings = _parse_findings(report_text, root)

    return AuditReport(
        tool=TOOL_NAME,
        status=AuditStatus.PASS,
        source_sha="",
        findings=findings,
        summary={
            "pyproject_config_honored": {
                "ignore_decorators": _config_list(pyproject_config, "ignore_decorators"),
                "ignore_names": _config_list(pyproject_config, "ignore_names"),
                "exclude": _config_list(pyproject_config, "exclude"),
            },
            "paths": list(paths),
            "min_confidence": min_confidence,
            "targets_resolved": len(targets),
            "allowlist": normalise_path(allowlist_path.relative_to(root))
            if allowlist_path is not None and allowlist_path.exists()
            else None,
            "total_findings": len(findings),
            "vulture_available": True,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run vulture as an ADR-042 audit child report.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--path", action="append", dest="paths", default=None)
    parser.add_argument("--allowlist", type=Path, default=Path(DEFAULT_ALLOWLIST))
    parser.add_argument("--min-confidence", type=int, default=DEFAULT_MIN_CONFIDENCE)
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args(argv)

    paths: Sequence[str] = tuple(args.paths) if args.paths else DEFAULT_PATHS
    report = check(args.repo_root, paths=paths, allowlist=args.allowlist, min_confidence=args.min_confidence)
    if args.format == "json":
        print(report.model_dump_json(indent=2))
    else:
        print(f"vulture: {report.status} ({len(report.findings)} findings)")
        for finding in report.findings:
            print(f"  {finding.file}:{finding.line or '?'} {finding.message}")
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    raise SystemExit(main())
