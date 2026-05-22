"""Full-audit child report for semantic duplication scan.

Wraps ``scripts/semantic_dup_scan.py`` as an opt-in child of
``scistudio.qa.audit.full_audit``. CI does not include this child by
default — the scan adds ~30-90s and the per-PR CI gate already runs
``--check`` against the committed baseline using BGE-small (see ADR-042
Addendum 2 §3 two-tier model policy). The full-audit child is intended
for **local** runs (``python -m scistudio.qa.audit.full_audit
--include-semantic-dup``) where it invokes the script with BGE-base for
higher-fidelity cluster detection and surfaces the result as an
advisory child report (status always PASS, regardless of cluster count).

The wrapper invokes the script via subprocess so that ``full_audit``'s
import surface does not transitively depend on ``fastembed`` /
``numpy`` / ONNX runtime. Local runs that don't pass
``--include-semantic-dup`` therefore pay no embedding cost.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

DEFAULT_AUDIT_MODEL = "BAAI/bge-base-en-v1.5"


def check_semantic_dup(
    repo_root: Path,
    *,
    model: str = DEFAULT_AUDIT_MODEL,
    scan_root: str = "src/scistudio",
) -> AuditReport:
    """Run the semantic-duplication scan via subprocess and wrap the result.

    Always returns ``AuditStatus.PASS`` (advisory). The cluster count
    and other aggregate metrics are reported under the ``summary``
    field so the full-audit JSON contains the deeper-fidelity signal.
    Subprocess failures degrade gracefully to a single ``Finding``
    explaining the error rather than failing the parent audit.
    """

    script = repo_root / "scripts" / "semantic_dup_scan.py"
    if not script.exists():
        return AuditReport(
            tool="semantic_dup",
            status=AuditStatus.PASS,
            source_sha="fixture",
            findings=[
                Finding(
                    rule_id="semantic-dup.script-missing",
                    severity=Severity.WARNING,
                    file=str(script),
                    message="semantic_dup_scan.py not found; skipping advisory full-audit scan.",
                )
            ],
            summary={"included": False, "reason": "script-missing"},
        )

    out_dir = repo_root / "docs" / "audit" / "latest"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_out = out_dir / "semantic-dup-full.json"
    md_out = out_dir / "semantic-dup-full.md"

    python = shutil.which("python") or sys.executable
    cmd = [
        python,
        str(script),
        "--root",
        scan_root,
        "--model",
        model,
        "--json-out",
        str(json_out),
        "--out",
        str(md_out),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "src", **_safe_env()},
    )

    if result.returncode != 0:
        return AuditReport(
            tool="semantic_dup",
            status=AuditStatus.PASS,
            source_sha="fixture",
            findings=[
                Finding(
                    rule_id="semantic-dup.subprocess-failed",
                    severity=Severity.WARNING,
                    file=str(script),
                    message=f"semantic_dup_scan.py exited {result.returncode}: {result.stderr[-500:].strip()}",
                )
            ],
            summary={"included": True, "subprocess_exit": result.returncode},
        )

    try:
        payload = json.loads(json_out.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return AuditReport(
            tool="semantic_dup",
            status=AuditStatus.PASS,
            source_sha="fixture",
            findings=[
                Finding(
                    rule_id="semantic-dup.payload-unreadable",
                    severity=Severity.WARNING,
                    file=str(json_out),
                    message=f"semantic_dup JSON payload unreadable: {exc}",
                )
            ],
            summary={"included": True, "payload_error": str(exc)},
        )

    metrics = payload.get("metrics", {})
    return AuditReport(
        tool="semantic_dup",
        status=AuditStatus.PASS,
        source_sha="fixture",
        findings=[],
        summary={
            "included": True,
            "model": model,
            "report_md": str(md_out.relative_to(repo_root)) if md_out.exists() else None,
            "report_json": str(json_out.relative_to(repo_root)),
            **metrics,
        },
    )


def _safe_env() -> dict[str, str]:
    """Filter os.environ to a minimal set so subprocess inheritance is predictable."""
    import os

    keep = {
        "PATH",
        "HOME",
        "USERPROFILE",
        "TMP",
        "TEMP",
        "LANG",
        "LC_ALL",
        "PYTHONIOENCODING",
        "HF_HOME",
        "HF_HUB_CACHE",
        "HUGGINGFACE_HUB_CACHE",
        "FASTEMBED_CACHE",
    }
    return {k: v for k, v in os.environ.items() if k in keep}
