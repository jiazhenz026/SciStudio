#!/usr/bin/env python3
"""
SciEasy Workflow Gate — Enforces gated development workflow.

This is the single entry point for all workflow state transitions.
AI agents and developers MUST use this CLI to advance through stages.
No stage can be entered without completing all prerequisites.

Usage:
    python gate.py start <issue_title>              # Initialize a new workflow
    python gate.py advance <task_id> <stage_id>      # Advance to next stage
    python gate.py status <task_id>                  # Show current status
    python gate.py list                              # List all active workflows
    python gate.py validate <task_id> <stage_id>     # Check if stage is reachable
    python gate.py abort <task_id> [--reason TEXT]    # Abort a workflow

Schema versioning (ADR-042 §19):
    Add ``--schema-version v1|v2`` to any subcommand. v1 (default) is
    the current 6-gate workflow. v2 is the 7-stage Workflow v2 defined
    in `.workflow/schema-v2.yaml`. In Phase 1 of the ADR-042/043/044
    cascade, v2 runs in **shadow mode**: events go to a parallel
    `<task_id>.v2.jsonl` log, but v1 remains authoritative. Phase 2
    (post-cascade) flips v2 to authoritative.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ─── Paths ──────────────────────────────────────────────────────────────────

WORKFLOW_DIR = Path(__file__).parent
SCHEMA_PATH = WORKFLOW_DIR / "schema.json"
SCHEMA_V2_PATH = WORKFLOW_DIR / "schema-v2.yaml"
ACTIVE_DIR = WORKFLOW_DIR / "active"

# ─── Schema-version constants (ADR-042 §19) ─────────────────────────────────

SCHEMA_VERSION_V1 = "v1"
SCHEMA_VERSION_V2 = "v2"
DEFAULT_SCHEMA_VERSION = SCHEMA_VERSION_V1


# ─── Schema Loading ─────────────────────────────────────────────────────────


def load_schema() -> dict:
    """Load and validate the workflow schema."""
    if not SCHEMA_PATH.exists():
        print("ERROR: schema.json not found.", file=sys.stderr)
        sys.exit(1)
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def load_schema_v2() -> dict:
    """Load and validate the Workflow v2 schema (ADR-042 §19).

    Imports PyYAML lazily so v1-only consumers don't pay the dep cost.
    """
    if not SCHEMA_V2_PATH.exists():
        print(
            f"ERROR: {SCHEMA_V2_PATH.name} not found (Workflow v2 schema).",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover — pyyaml is in pyproject deps
        print(f"ERROR: PyYAML required to load schema-v2.yaml: {exc}", file=sys.stderr)
        sys.exit(1)

    with open(SCHEMA_V2_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "stages" not in data:
        print(
            f"ERROR: {SCHEMA_V2_PATH.name} malformed — top-level 'stages' missing.",
            file=sys.stderr,
        )
        sys.exit(1)

    if data.get("version", "").split(".")[0] != "2":
        print(
            f"ERROR: {SCHEMA_V2_PATH.name} version mismatch — expected '2.x.x', got {data.get('version')!r}.",
            file=sys.stderr,
        )
        sys.exit(1)

    return data


def get_stage_map(schema: dict) -> dict[str, dict]:
    """Build a lookup map of stage_id -> stage_definition."""
    return {s["id"]: s for s in schema["stages"]}


def get_stage_order(schema: dict) -> list[str]:
    """Return ordered list of stage IDs."""
    return [s["id"] for s in schema["stages"]]


# ─── Shadow-mode v2 event logging (ADR-042 §19) ─────────────────────────────


def shadow_log_path(task_id: str) -> Path:
    """Path to the per-task shadow-mode event log (one JSON object per line)."""
    return ACTIVE_DIR / f"{task_id}.v2.jsonl"


def append_shadow_event(task_id: str, event: dict) -> None:
    """Append one event record to the shadow log.

    The shadow log is intentionally append-only JSONL so v2 telemetry can
    be inspected without parsing the full v1 state file. v1 remains the
    authoritative source-of-truth during Phase 1 of the cascade.
    """
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = shadow_log_path(task_id)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def run_v2_validators_shadow(
    *,
    task_id: str,
    v1_stage_id: str,
    artifacts: dict[str, Any],
    branch: str | None = None,
) -> list[dict]:
    """Run v2 validators for the v1 stage ``v1_stage_id`` (shadow mode).

    Map v1 → v2 stage IDs per ADR-042 §19.6. Validators that fail or
    error do NOT block the v1 advance; results are written to the
    shadow log for later analysis.

    Returns the list of per-validator result records (also appended to
    the shadow log).
    """
    # ADR-042 §19.6 migration mapping. Stages 1 (start_and_route) and
    # 5 (implement_validate) have no v1 equivalent; they are skipped
    # in shadow mode triggered from v1 advances.
    v1_to_v2 = {
        "create_issue": ["create_issue"],
        "write_change_plan": ["change_plan"],
        "create_branch": ["branch"],
        # update_docs + update_changelog both map to v2 complete_artifacts
        "update_docs": ["complete_artifacts"],
        "update_changelog": ["complete_artifacts"],
        "submit_pr": ["submit_reconcile"],
    }
    v2_stages = v1_to_v2.get(v1_stage_id, [])
    if not v2_stages:
        return []

    # Lazy import the validators package; if it errors (e.g. import
    # cycle, missing module), shadow mode swallows the exception and
    # records it as a v2 error so the v1 path stays unaffected.
    try:
        from scieasy.qa.workflow.gate import StageContext
        from scieasy.qa.workflow.validators import VALIDATORS
    except Exception as exc:  # pragma: no cover — defensive
        append_shadow_event(
            task_id,
            {
                "event": "v2_import_error",
                "v1_stage": v1_stage_id,
                "error": repr(exc),
                "timestamp": now_iso(),
            },
        )
        return []

    schema_v2 = load_schema_v2()
    v2_stage_map = get_stage_map(schema_v2)

    results: list[dict] = []
    for v2_stage_id in v2_stages:
        stage_def = v2_stage_map.get(v2_stage_id)
        if not stage_def:
            results.append(
                {
                    "v2_stage": v2_stage_id,
                    "status": "error",
                    "message": f"v2 stage {v2_stage_id} not in schema-v2.yaml",
                }
            )
            continue

        ctx = StageContext(
            task_id=task_id,
            stage_name=v2_stage_id,
            repo_root=str(Path.cwd()),
            pr_number=artifacts.get("pr_number") if isinstance(artifacts, dict) else None,
            branch=branch or artifacts.get("branch_name", "") if isinstance(artifacts, dict) else "",
            declared_data=artifacts if isinstance(artifacts, dict) else {},
        )

        for validator_id in stage_def.get("validations", []):
            validator = VALIDATORS.get(validator_id)
            if validator is None:
                results.append(
                    {
                        "v2_stage": v2_stage_id,
                        "validator_id": validator_id,
                        "status": "error",
                        "message": f"unknown validator_id {validator_id!r}",
                    }
                )
                continue
            try:
                vr = validator(ctx)
                results.append(
                    {
                        "v2_stage": v2_stage_id,
                        "validator_id": vr.validator_id,
                        "status": vr.status,
                        "message": vr.message,
                        "blocking": vr.blocking,
                    }
                )
            except Exception as exc:  # pragma: no cover — defensive
                results.append(
                    {
                        "v2_stage": v2_stage_id,
                        "validator_id": validator_id,
                        "status": "error",
                        "message": f"validator raised: {exc!r}",
                    }
                )

    append_shadow_event(
        task_id,
        {
            "event": "v2_shadow_run",
            "v1_stage": v1_stage_id,
            "v2_stages": v2_stages,
            "results": results,
            "timestamp": now_iso(),
        },
    )
    return results


# ─── State File Operations ──────────────────────────────────────────────────


def state_path(task_id: str) -> Path:
    return ACTIVE_DIR / f"{task_id}.json"


def load_state(task_id: str) -> dict:
    """Load a task's state file."""
    path = state_path(task_id)
    if not path.exists():
        print(f"ERROR: No active workflow found for '{task_id}'.", file=sys.stderr)
        print("  Run `python gate.py list` to see active workflows.", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def save_state(task_id: str, state: dict) -> None:
    """Save a task's state file."""
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = state_path(task_id)
    with open(path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ─── Core Logic ─────────────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def generate_task_id(title: str) -> str:
    """Generate a task ID from the title."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    slug = slug[:40].rstrip("-")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{slug}"


def check_prerequisites(schema: dict, state: dict, target_stage: str) -> tuple[bool, list[str]]:
    """
    Check if all prerequisites for target_stage are satisfied.
    Returns (can_proceed, list_of_blocking_reasons).
    """
    stage_map = get_stage_map(schema)

    if target_stage not in stage_map:
        return False, [f"Unknown stage: {target_stage}"]

    stage_def = stage_map[target_stage]
    completed = {s["stage_id"] for s in state.get("completed_stages", [])}
    blockers: list[str] = []

    for req in stage_def["requires"]:
        if req not in completed:
            req_name = stage_map.get(req, {}).get("name", req)
            blockers.append(f"BLOCKED: Stage '{req_name}' ({req}) must be completed first.")

    if target_stage in completed:
        blockers.append(f"Stage '{stage_def['name']}' is already completed.")

    if state.get("status") == "aborted":
        blockers.append("This workflow has been aborted.")

    return len(blockers) == 0, blockers


def format_status(schema: dict, state: dict) -> str:
    """Format a human-readable status of the workflow."""
    stage_order = get_stage_order(schema)
    stage_map = get_stage_map(schema)
    completed = {s["stage_id"] for s in state.get("completed_stages", [])}

    lines = [
        "=" * 62,
        f"  Workflow: {state['title']}",
        f"  Task ID:  {state['task_id']}",
        f"  Status:   {state['status']}",
        f"  Created:  {state['created_at'][:19]}",
        "-" * 62,
    ]

    current_found = False
    for stage_id in stage_order:
        stage = stage_map[stage_id]
        if stage_id in completed:
            comp = next(s for s in state["completed_stages"] if s["stage_id"] == stage_id)
            marker = "[DONE]"
            extra = f"  (at {comp['completed_at'][:19]})"
        elif not current_found:
            marker = "[NEXT]"
            extra = "  <-- CURRENT"
            current_found = True
        else:
            marker = "[LOCK]"
            extra = ""

        lines.append(f"  {marker} {stage['name']:<35}{extra}")

    lines.append("=" * 62)
    return "\n".join(lines)


# ─── Commands ───────────────────────────────────────────────────────────────


def cmd_start(args: argparse.Namespace) -> None:
    """Start a new workflow."""
    load_schema()
    title = " ".join(args.title)
    task_id = generate_task_id(title)

    state = {
        "task_id": task_id,
        "title": title,
        "status": "active",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "completed_stages": [],
        "history": [
            {
                "event": "workflow_started",
                "timestamp": now_iso(),
                "title": title,
            }
        ],
    }

    save_state(task_id, state)
    print("Workflow started.")
    print(f"  Task ID: {task_id}")
    print(f"  Title:   {title}")
    print()
    print("Next step: complete 'create_issue' stage by running:")
    print(f"  python .workflow/gate.py advance {task_id} create_issue \\")
    print('    --data \'{"issue_number": 42, "issue_url": "https://..."}\'')


def cmd_advance(args: argparse.Namespace) -> None:
    """Advance a workflow to the next stage."""
    schema = load_schema()
    state = load_state(args.task_id)
    target = args.stage_id

    # ── GATE CHECK ──────────────────────────────────────────────────────
    can_proceed, blockers = check_prerequisites(schema, state, target)

    if not can_proceed:
        print("=" * 60, file=sys.stderr)
        print("  WORKFLOW GATE: ADVANCEMENT BLOCKED", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        for b in blockers:
            print(f"  X {b}", file=sys.stderr)
        print("", file=sys.stderr)
        print("  You must complete prerequisite stages first.", file=sys.stderr)
        print(f"  Run: python .workflow/gate.py status {args.task_id}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)
    # ── END GATE CHECK ──────────────────────────────────────────────────

    # Parse the artifacts data
    artifacts: dict[str, Any] = {}
    if args.data:
        try:
            artifacts = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in --data: {e}", file=sys.stderr)
            sys.exit(1)

    # Validate required artifacts
    stage_map = get_stage_map(schema)
    stage_def = stage_map[target]
    missing = [a for a in stage_def["artifacts"] if a not in artifacts]
    if missing:
        print(f"ERROR: Missing required artifacts: {missing}", file=sys.stderr)
        print(f"  Required: {stage_def['artifacts']}", file=sys.stderr)
        print(f"  Provided: {list(artifacts.keys())}", file=sys.stderr)
        sys.exit(1)

    # Record completion
    completion_record = {
        "stage_id": target,
        "stage_name": stage_def["name"],
        "completed_at": now_iso(),
        "artifacts": artifacts,
    }

    state["completed_stages"].append(completion_record)
    state["updated_at"] = now_iso()
    state["history"].append(
        {
            "event": "stage_completed",
            "stage_id": target,
            "timestamp": now_iso(),
            "artifacts": artifacts,
        }
    )

    # Check if all stages are done
    all_stages = set(get_stage_order(schema))
    completed = {s["stage_id"] for s in state["completed_stages"]}
    if all_stages == completed:
        state["status"] = "completed"
        state["completed_at"] = now_iso()
        state["history"].append({"event": "workflow_completed", "timestamp": now_iso()})

    save_state(args.task_id, state)

    print(f"[DONE] Stage '{stage_def['name']}' completed.")

    # ── Workflow v2 shadow-mode run (ADR-042 §19, Phase 1 cascade) ─────────
    # Opt-in via --schema-version v2. v1 behaviour above is untouched; this
    # block only emits to the shadow log. Errors here MUST NOT affect v1.
    if getattr(args, "schema_version", DEFAULT_SCHEMA_VERSION) == SCHEMA_VERSION_V2:
        try:
            shadow_results = run_v2_validators_shadow(
                task_id=args.task_id,
                v1_stage_id=target,
                artifacts=artifacts,
                branch=artifacts.get("branch_name") if isinstance(artifacts, dict) else None,
            )
            if shadow_results:
                fails = [r for r in shadow_results if r["status"] == "fail"]
                if fails:
                    print(f"  [v2-shadow] {len(fails)} validator(s) FAILED (non-blocking; v1 advance succeeded):")
                    for r in fails:
                        print(f"    - {r['validator_id']}: {r['message']}")
                else:
                    print(
                        f"  [v2-shadow] {len(shadow_results)} validator(s) ran "
                        f"({sum(1 for r in shadow_results if r['status'] == 'pass')} pass, "
                        f"{sum(1 for r in shadow_results if r['status'] == 'skip')} skip)."
                    )
        except Exception as exc:  # pragma: no cover — defensive
            print(
                f"  [v2-shadow] error during shadow run (ignored): {exc!r}",
                file=sys.stderr,
            )

    print()

    # Show what's next
    stage_order = get_stage_order(schema)
    remaining = [s for s in stage_order if s not in completed]
    if remaining:
        next_stage = remaining[0]
        next_name = stage_map[next_stage]["name"]
        print(f"Next step: {next_name} ({next_stage})")
        print(f"  python .workflow/gate.py advance {args.task_id} {next_stage} \\")
        print("    --data '{...}'")
    else:
        print("All stages completed! Workflow finished.")


def cmd_status(args: argparse.Namespace) -> None:
    """Show workflow status."""
    schema = load_schema()
    state = load_state(args.task_id)
    print(format_status(schema, state))


def cmd_list(args: argparse.Namespace) -> None:
    """List all active workflows."""
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(ACTIVE_DIR.glob("*.json"))

    if not files:
        print("No active workflows.")
        return

    schema = load_schema()
    stage_count = len(schema["stages"])

    print(f"{'Task ID':<35} {'Status':<12} {'Progress':<12} {'Title'}")
    print("-" * 90)
    for f in files:
        with open(f) as fh:
            state = json.load(fh)
        done = len(state.get("completed_stages", []))
        progress = f"{done}/{stage_count}"
        print(f"{state['task_id']:<35} {state['status']:<12} {progress:<12} {state['title']}")


def cmd_validate(args: argparse.Namespace) -> None:
    """Check if a stage is reachable."""
    schema = load_schema()
    state = load_state(args.task_id)
    can_proceed, blockers = check_prerequisites(schema, state, args.stage_id)

    if can_proceed:
        print(f"[OK] Stage '{args.stage_id}' is reachable. You may proceed.")
    else:
        print(f"[BLOCKED] Stage '{args.stage_id}' is BLOCKED:")
        for b in blockers:
            print(f"  X {b}")
        sys.exit(1)


def cmd_abort(args: argparse.Namespace) -> None:
    """Abort a workflow."""
    state = load_state(args.task_id)
    state["status"] = "aborted"
    state["updated_at"] = now_iso()
    state["history"].append(
        {
            "event": "workflow_aborted",
            "timestamp": now_iso(),
            "reason": args.reason or "No reason provided",
        }
    )
    save_state(args.task_id, state)
    print(f"Workflow '{args.task_id}' aborted.")


# ─── CLI ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="SciEasy Workflow Gate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--schema-version",
        choices=[SCHEMA_VERSION_V1, SCHEMA_VERSION_V2],
        default=DEFAULT_SCHEMA_VERSION,
        help=(
            "Workflow schema version. v1 (default) = current 6-gate workflow. "
            "v2 = ADR-042 §19 7-stage Workflow v2, runs in shadow mode "
            "during Phase 1 cascade."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # start
    p_start = sub.add_parser("start", help="Start a new workflow")
    p_start.add_argument("title", nargs="+", help="Task title / description")

    # advance
    p_advance = sub.add_parser("advance", help="Advance to next stage")
    p_advance.add_argument("task_id", help="Task ID")
    p_advance.add_argument("stage_id", help="Target stage ID")
    p_advance.add_argument("--data", help="JSON string of artifacts")

    # status
    p_status = sub.add_parser("status", help="Show workflow status")
    p_status.add_argument("task_id", help="Task ID")

    # list
    sub.add_parser("list", help="List all active workflows")

    # validate
    p_validate = sub.add_parser("validate", help="Check if stage is reachable")
    p_validate.add_argument("task_id", help="Task ID")
    p_validate.add_argument("stage_id", help="Target stage ID")

    # abort
    p_abort = sub.add_parser("abort", help="Abort a workflow")
    p_abort.add_argument("task_id", help="Task ID")
    p_abort.add_argument("--reason", help="Reason for aborting")

    args = parser.parse_args()
    commands = {
        "start": cmd_start,
        "advance": cmd_advance,
        "status": cmd_status,
        "list": cmd_list,
        "validate": cmd_validate,
        "abort": cmd_abort,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
