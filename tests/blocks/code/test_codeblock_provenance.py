from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from scistudio.blocks.code.interpreters import resolve_script_interpreter
from scistudio.blocks.code.provenance import (
    build_codeblock_provenance_payload,
    capture_environment_snapshot,
    capture_script_provenance,
)


def _write_script(project_dir: Path) -> Path:
    script = project_dir / "scripts" / "run.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("print('tracked')\n", encoding="utf-8")
    return script


def _git(project_dir: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=project_dir, check=True, capture_output=True, text=True)


def test_capture_script_provenance_records_hash_and_tracked_state(tmp_path: Path) -> None:
    script = _write_script(tmp_path)
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "agent@example.com")
    _git(tmp_path, "config", "user.name", "SciStudio Agent")
    _git(tmp_path, "add", "scripts/run.py")
    _git(tmp_path, "commit", "-m", "add script")

    provenance = capture_script_provenance(script, project_dir=tmp_path)

    expected_hash = hashlib.sha256(script.read_bytes()).hexdigest()
    assert provenance.relative_path == "scripts/run.py"
    assert provenance.content_sha256 == expected_hash
    assert provenance.git_status == "tracked-clean"
    assert provenance.git_commit is not None
    assert provenance.size_bytes == len(script.read_bytes())


def test_capture_script_provenance_marks_untracked_scripts(tmp_path: Path) -> None:
    script = _write_script(tmp_path)

    provenance = capture_script_provenance(script, project_dir=tmp_path)

    assert provenance.git_status == "untracked"
    assert provenance.git_commit is None


def test_environment_snapshot_uses_sorted_delta(tmp_path: Path) -> None:
    script = _write_script(tmp_path)
    resolved = resolve_script_interpreter(
        script,
        project_dir=tmp_path,
        mode="existing",
        interpreter_path=sys.executable,
        environment_config={"environment_variables": {"Z_VAR": "2", "A_VAR": "1"}},
    )

    snapshot = capture_environment_snapshot(resolved, mode="existing")

    assert snapshot.mode == "existing"
    assert Path(snapshot.interpreter_path).resolve() == Path(sys.executable).resolve()
    assert list(snapshot.environment_delta) == ["A_VAR", "Z_VAR"]


def test_codeblock_provenance_payload_shape_is_stable(tmp_path: Path) -> None:
    script = _write_script(tmp_path)
    script_provenance = capture_script_provenance(script, project_dir=tmp_path)
    interpreter = resolve_script_interpreter(script, project_dir=tmp_path)
    environment = capture_environment_snapshot(interpreter, mode="auto")

    payload = build_codeblock_provenance_payload(
        script=script_provenance,
        interpreter=interpreter,
        environment=environment,
        started_at="2026-05-19T00:00:00Z",
        completed_at="2026-05-19T00:00:01Z",
        selected_capabilities={"output:table": "core.dataframe.csv.load", "input:image": "imaging.image.tiff.save"},
        exchange_manifest={"outputs": ["outputs/table/result.csv"]},
    )

    assert list(payload) == [
        "script",
        "interpreter",
        "environment",
        "started_at",
        "completed_at",
        "selected_capabilities",
        "exchange_manifest",
    ]
    assert payload["script"]["relative_path"] == "scripts/run.py"
    assert list(payload["selected_capabilities"]) == ["input:image", "output:table"]
    assert payload["interpreter"]["argv"][1] == "scripts/run.py"
