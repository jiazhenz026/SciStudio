"""Local ADR-042 gate receipts for CI-parity pre-PR checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scistudio.qa.governance.gate_record.io import _load_record
from scistudio.qa.governance.gate_record.paths import _normalize_path

DEFAULT_RECEIPT_DIR = Path(".workflow/local/gate-receipts")
DEFAULT_BASE = "origin/main"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

CHECK_COMMANDS: Mapping[str, tuple[str, ...]] = {
    "ruff": ("ruff", "check", "."),
    "format": ("ruff", "format", "--check", "."),
    "mypy": ("mypy", "src/scistudio/", "--ignore-missing-imports", "--python-version", "3.13"),
    "pytest-governance": ("pytest", "tests/qa", "--timeout=60", "--no-cov"),
    "pytest-scripts": ("pytest", "tests/scripts", "--timeout=60", "--no-cov"),
    "pytest-agent-provisioning": ("pytest", "tests/agent_provisioning", "--timeout=60", "--no-cov"),
    "full_audit": (
        sys.executable,
        "-m",
        "scistudio.qa.audit.full_audit",
        "--repo-root",
        ".",
        "--format",
        "json",
        "--output",
        "docs/audit/full-audit-latest.json",
    ),
    "frontend_lint": ("npm", "--prefix", "frontend", "run", "lint"),
    "frontend_format": ("npm", "--prefix", "frontend", "run", "format:check"),
    "frontend_typecheck": ("npm", "--prefix", "frontend", "run", "typecheck"),
    "frontend_test": ("npm", "--prefix", "frontend", "test"),
    "frontend_build": ("npm", "--prefix", "frontend", "run", "build"),
}


@dataclass(frozen=True)
class CandidateFingerprint:
    """Immutable state that a local receipt is valid for."""

    base: str
    head: str
    head_sha: str
    branch: str
    changed_files: tuple[str, ...]
    diff_sha256: str
    gate_record_sha256: str
    pr_body_sha256: str

    def to_json(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "head": self.head,
            "head_sha": self.head_sha,
            "branch": self.branch,
            "changed_files": list(self.changed_files),
            "diff_sha256": self.diff_sha256,
            "gate_record_sha256": self.gate_record_sha256,
            "pr_body_sha256": self.pr_body_sha256,
        }


def _run_git_text(repo_root: Path, args: Sequence[str]) -> str:
    return str(subprocess.check_output(["git", *args], cwd=repo_root, text=True, stderr=subprocess.DEVNULL))


def _run_git_bytes(repo_root: Path, args: Sequence[str]) -> bytes:
    return bytes(subprocess.check_output(["git", *args], cwd=repo_root, text=False, stderr=subprocess.DEVNULL))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read_pr_body(pr_body: str = "", pr_body_file: Path | None = None) -> str:
    if pr_body_file is None:
        return pr_body
    return pr_body_file.read_text(encoding="utf-8")


def build_candidate(
    repo_root: Path,
    *,
    gate_record: Path,
    base: str = DEFAULT_BASE,
    head: str = "HEAD",
    pr_body: str = "",
) -> CandidateFingerprint:
    """Return the exact branch/diff/body fingerprint a receipt must match."""

    repo_root = repo_root.resolve()
    record_path = gate_record if gate_record.is_absolute() else repo_root / gate_record
    head_sha = _run_git_text(repo_root, ["rev-parse", head]).strip()
    branch = _run_git_text(repo_root, ["branch", "--show-current"]).strip()
    changed = _run_git_text(repo_root, ["diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base}...{head}"])
    diff = _run_git_bytes(repo_root, ["diff", "--binary", "--diff-filter=ACMRTUXB", f"{base}...{head}"])
    changed_files = tuple(_normalize_path(line) for line in changed.splitlines() if line.strip())
    return CandidateFingerprint(
        base=base,
        head=head,
        head_sha=head_sha,
        branch=branch,
        changed_files=changed_files,
        diff_sha256=_sha256_bytes(diff),
        gate_record_sha256=_file_sha256(record_path),
        pr_body_sha256=_sha256_text(pr_body),
    )


def receipt_paths(
    repo_root: Path,
    *,
    head_sha: str,
    pr_body_sha256: str = EMPTY_SHA256,
    receipt_dir: Path = DEFAULT_RECEIPT_DIR,
) -> tuple[Path, Path]:
    root = repo_root.resolve()
    directory = receipt_dir if receipt_dir.is_absolute() else root / receipt_dir
    safe_sha = "".join(ch for ch in head_sha if ch.isalnum())[:40] or "unknown"
    suffix = "" if pr_body_sha256 == EMPTY_SHA256 else f"-pr-{pr_body_sha256[:12]}"
    return directory / f"{safe_sha}{suffix}.json", directory / f"{safe_sha}{suffix}.log"


def infer_required_checks(
    changed_files: Sequence[str],
    *,
    gate_required: Sequence[str] = (),
) -> set[str]:
    """Infer local CI-parity checks from the diff plus gate-record plan."""

    required = set(gate_required)
    normalized = [_normalize_path(path) for path in changed_files]
    if any(path.startswith(("src/", "scripts/")) for path in normalized):
        required.update({"ruff", "format", "mypy"})
    if any(path.startswith("tests/") for path in normalized):
        required.update({"ruff", "format"})
    if any(path.startswith("tests/qa/") for path in normalized):
        required.add("pytest-governance")
    if any(path.startswith("tests/scripts/") for path in normalized):
        required.add("pytest-scripts")
    if any(path.startswith("tests/agent_provisioning/") for path in normalized):
        required.add("pytest-agent-provisioning")
    if any(
        path.startswith(("src/scistudio/qa/governance/", ".github/workflows/", ".pre-commit-config.yaml"))
        for path in normalized
    ):
        required.update({"full_audit", "gate_record_pre_push"})
    if any(path.startswith(("docs/adr/", "docs/specs/", "docs/ai-developer/")) for path in normalized):
        required.update({"frontmatter_lint", "full_audit"})
    if any(path.startswith("frontend/") for path in normalized):
        required.update({"frontend_lint", "frontend_format", "frontend_typecheck", "frontend_test", "frontend_build"})
    return required


def _load_receipt(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _initial_receipt(candidate: CandidateFingerprint) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "generated_at": datetime.now(UTC).isoformat(),
        "candidate": candidate.to_json(),
        "checks": [],
    }


def _write_receipt(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_check(
    repo_root: Path,
    *,
    gate_record: Path,
    name: str,
    command: Sequence[str],
    base: str = DEFAULT_BASE,
    head: str = "HEAD",
    pr_body: str = "",
    receipt_dir: Path = DEFAULT_RECEIPT_DIR,
) -> int:
    """Run one command and append stdout/stderr/exit code to the receipt."""

    candidate = build_candidate(repo_root, gate_record=gate_record, base=base, head=head, pr_body=pr_body)
    json_path, log_path = receipt_paths(
        repo_root,
        head_sha=candidate.head_sha,
        pr_body_sha256=candidate.pr_body_sha256,
        receipt_dir=receipt_dir,
    )
    existing = _load_receipt(json_path) if json_path.exists() else _initial_receipt(candidate)
    if existing.get("candidate") != candidate.to_json():
        existing = _initial_receipt(candidate)

    env = os.environ.copy()
    src_dir = repo_root / "src"
    if src_dir.is_dir():
        env["PYTHONPATH"] = str(src_dir) + os.pathsep + env.get("PYTHONPATH", "")
    started_at = datetime.now(UTC).isoformat()
    proc = subprocess.run(command, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
    ended_at = datetime.now(UTC).isoformat()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as log:
        log.write(f"\n===== {name} | exit={proc.returncode} | started={started_at} | ended={ended_at} =====\n")
        log.write("$ " + " ".join(command) + "\n")
        log.write("--- stdout ---\n")
        log.write(proc.stdout)
        if proc.stdout and not proc.stdout.endswith("\n"):
            log.write("\n")
        log.write("--- stderr ---\n")
        log.write(proc.stderr)
        if proc.stderr and not proc.stderr.endswith("\n"):
            log.write("\n")

    checks = [check for check in existing.get("checks", []) if isinstance(check, Mapping) and check.get("name") != name]
    checks.append(
        {
            "name": name,
            "command": list(command),
            "exit_code": proc.returncode,
            "started_at": started_at,
            "ended_at": ended_at,
            "stdout_sha256": _sha256_text(proc.stdout),
            "stderr_sha256": _sha256_text(proc.stderr),
            "log_path": _normalize_path(str(log_path.relative_to(repo_root)))
            if log_path.is_relative_to(repo_root)
            else str(log_path),
        }
    )
    existing["generated_at"] = ended_at
    existing["candidate"] = candidate.to_json()
    existing["checks"] = checks
    _write_receipt(json_path, existing)
    return proc.returncode


def validate_receipt(
    repo_root: Path,
    *,
    gate_record: Path,
    base: str = DEFAULT_BASE,
    head: str = "HEAD",
    pr_body: str = "",
    receipt_dir: Path = DEFAULT_RECEIPT_DIR,
) -> tuple[bool, list[str]]:
    """Validate receipt existence, fingerprint freshness, and zero-exit checks."""

    candidate = build_candidate(repo_root, gate_record=gate_record, base=base, head=head, pr_body=pr_body)
    json_path, _ = receipt_paths(
        repo_root,
        head_sha=candidate.head_sha,
        pr_body_sha256=candidate.pr_body_sha256,
        receipt_dir=receipt_dir,
    )
    if not json_path.exists():
        return False, [f"missing gate receipt: {_normalize_path(str(json_path))}"]
    try:
        data = _load_receipt(json_path)
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"invalid gate receipt JSON: {exc}"]

    errors: list[str] = []
    if data.get("candidate") != candidate.to_json():
        errors.append("gate receipt fingerprint does not match current HEAD/diff/gate record/PR body")

    record = _load_record(gate_record)
    required = infer_required_checks(candidate.changed_files, gate_required=record.required_checks)
    checks = {str(check.get("name")): check for check in data.get("checks", []) if isinstance(check, Mapping)}
    missing = sorted(required - set(checks))
    for name in missing:
        errors.append(f"missing gate receipt check: {name}")
    for name in sorted(required & set(checks)):
        exit_code = checks[name].get("exit_code")
        if exit_code != 0:
            errors.append(f"gate receipt check failed: {name} exit_code={exit_code}")
    return not errors, errors


def _command_for(
    name: str,
    *,
    base: str,
    head: str,
    gate_record: Path,
    candidate: CandidateFingerprint,
) -> tuple[str, ...]:
    if name == "frontmatter_lint":
        targets = [
            changed_file
            for changed_file in candidate.changed_files
            if changed_file.startswith(("docs/adr/", "docs/specs/"))
        ]
        if not targets:
            raise ValueError("frontmatter_lint requires at least one changed ADR or spec file")
        return (
            sys.executable,
            "-m",
            "scistudio.qa.audit.frontmatter_lint",
            *targets,
            "--format",
            "text",
        )
    if name == "docs_landing":
        record = _load_record(gate_record)
        docs_command = [
            sys.executable,
            "-m",
            "scistudio.qa.governance.docs_landing",
            "--repo-root",
            ".",
            "--docs-landing-json",
            json.dumps(record.docs_landing),
        ]
        for changed_file in candidate.changed_files:
            docs_command.extend(["--changed-file", changed_file])
        return tuple(docs_command)
    if name == "gate_record_pre_commit":
        return (
            sys.executable,
            "-m",
            "scistudio.qa.governance.gate_record",
            "pre-commit",
            "--repo-root",
            ".",
            "--gate-record",
            _normalize_path(str(gate_record)),
            "--staged",
        )
    if name == "gate_record_pre_push":
        return (
            sys.executable,
            "-m",
            "scistudio.qa.governance.gate_record",
            "pre-push",
            "--repo-root",
            ".",
            "--gate-record",
            _normalize_path(str(gate_record)),
            "--base",
            base,
            "--head",
            head,
        )
    command = CHECK_COMMANDS.get(name)
    if command is None:
        raise ValueError(f"no built-in command for receipt check {name!r}; use gate_receipt exec --name {name} -- ...")
    return tuple(command)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "run", "exec"):
        command_parser = sub.add_parser(name)
        command_parser.add_argument("--repo-root", type=Path, default=Path.cwd())
        command_parser.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
        command_parser.add_argument("--base", default=DEFAULT_BASE)
        command_parser.add_argument("--head", default="HEAD")
        command_parser.add_argument("--pr-body", default="")
        command_parser.add_argument("--pr-body-file", type=Path)
        command_parser.add_argument("--receipt-dir", type=Path, default=DEFAULT_RECEIPT_DIR)
    sub.choices["exec"].add_argument("--name", required=True)
    sub.choices["exec"].add_argument("command_args", nargs=argparse.REMAINDER)
    sub.choices["run"].add_argument("--check", action="append", default=[])

    args = parser.parse_args(argv)
    pr_body = _read_pr_body(args.pr_body, args.pr_body_file)
    repo_root = args.repo_root.resolve()
    gate_record = args.gate_record if args.gate_record.is_absolute() else repo_root / args.gate_record

    if args.command == "validate":
        ok, errors = validate_receipt(
            repo_root,
            gate_record=gate_record,
            base=args.base,
            head=args.head,
            pr_body=pr_body,
            receipt_dir=args.receipt_dir,
        )
        if ok:
            print("gate_receipt: pass")
            return 0
        print("gate_receipt: fail", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    if args.command == "exec":
        command_args = list(args.command_args)
        if command_args and command_args[0] == "--":
            command_args = command_args[1:]
        if not command_args:
            print("gate_receipt exec requires a command after --", file=sys.stderr)
            return 2
        return append_check(
            repo_root,
            gate_record=gate_record,
            name=args.name,
            command=command_args,
            base=args.base,
            head=args.head,
            pr_body=pr_body,
            receipt_dir=args.receipt_dir,
        )

    record = _load_record(gate_record)
    candidate = build_candidate(repo_root, gate_record=gate_record, base=args.base, head=args.head, pr_body=pr_body)
    checks = set(args.check) or infer_required_checks(candidate.changed_files, gate_required=record.required_checks)
    exit_code = 0
    for check in sorted(checks):
        code = append_check(
            repo_root,
            gate_record=gate_record,
            name=check,
            command=_command_for(check, base=args.base, head=args.head, gate_record=gate_record, candidate=candidate),
            base=args.base,
            head=args.head,
            pr_body=pr_body,
            receipt_dir=args.receipt_dir,
        )
        exit_code = exit_code or code
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
