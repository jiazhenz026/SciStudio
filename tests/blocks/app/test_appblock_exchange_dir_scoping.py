"""Regression tests for per-(workflow, block, run) AppBlock exchange folders (#2424).

Before #2424 an AppBlock inside a project exchanged files through
``data/exchange/<block_id>``: two workflows with a same-named node shared the
folder (each collected the other's outputs, and the later run overwrote the
file the earlier run's lineage records), and a second run of a single-input
node failed because SaveData refused to overwrite the staged input.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

from scistudio.blocks.app.app_block import AppBlock, _is_legacy_default_output_dir, _project_exchange_dir
from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.collection import Collection
from scistudio.workflow.flatten import flatten_subworkflows
from scistudio.workflow.serializer import load_yaml

# Copies the first staged ``src`` input into ``outputs/result.txt``.
_COPY_APP = """\
import json, pathlib
cwd = pathlib.Path.cwd()
entry = json.loads((cwd / "manifest.json").read_text())["src"]
source = entry.get("path") or entry["items"][0]["path"]
out = cwd / "outputs"
out.mkdir(exist_ok=True)
(out / "result.txt").write_text(pathlib.Path(source).read_text())
"""

# Writes a result file named after the workflow the node runs in.
_TAG_APP = """\
import pathlib, sys, time
out = pathlib.Path.cwd() / "outputs"
out.mkdir(exist_ok=True)
time.sleep(0.3)
(out / (sys.argv[1] + ".txt")).write_text(sys.argv[1])
"""


def _script(tmp_path: Path, name: str, body: str) -> Path:
    script = tmp_path / name
    script.write_text(body, encoding="utf-8")
    return script


def _inputs(tmp_path: Path, tag: str, count: int) -> dict[str, Collection]:
    artifacts = []
    for index in range(count):
        source = tmp_path / f"{tag}_{index}.txt"
        source.write_text(f"{tag} #{index}", encoding="utf-8")
        artifacts.append(Artifact(file_path=source))
    return {"src": Collection(artifacts)}


def _config(project: Path, script: Path, workflow_id: str, **extra: object) -> BlockConfig:
    params: dict[str, object] = {
        "app_command": [sys.executable, str(script)],
        "stability_period": 0.2,
        "project_dir": str(project),
        "block_id": "fiji",
        "workflow_id": workflow_id,
    }
    params.update(extra)
    return BlockConfig(params=params)


def _only_file(result: dict) -> Path:
    return Path(next(iter(result.values()))[0].file_path)


def test_exchange_dir_layout_is_workflow_block_run(tmp_path: Path) -> None:
    project = tmp_path / "proj"

    assert _project_exchange_dir(project, workflow_id="main", block_id="fiji", run_id="r1") == (
        project / "data" / "exchange" / "main" / "fiji" / "r1"
    )
    # A path-form run identity (#2394) is already one segment and stays unchanged.
    assert _project_exchange_dir(project, workflow_id="@subworkflows@qc.yaml", block_id="fiji", run_id="r1") == (
        project / "data" / "exchange" / "@subworkflows@qc.yaml" / "fiji" / "r1"
    )
    # No workflow → ad-hoc; separators can never escape the exchange root.
    unsafe = _project_exchange_dir(project, workflow_id="", block_id="../x", run_id="a/b")
    assert unsafe.parent.parent == project / "data" / "exchange" / "adhoc"
    assert unsafe.parent.name.startswith(".._x-")
    assert unsafe.name.startswith("a_b-")


def test_sanitized_node_ids_do_not_collide(tmp_path: Path) -> None:
    project = tmp_path / "proj"

    slash = _project_exchange_dir(project, workflow_id="main", block_id="a/b", run_id="r1")
    underscore = _project_exchange_dir(project, workflow_id="main", block_id="a_b", run_id="r1")

    assert slash != underscore
    # Ordinary ids stay readable and unchanged.
    assert underscore == project / "data" / "exchange" / "main" / "a_b" / "r1"
    assert slash.parent.parent == project / "data" / "exchange" / "main"


def test_same_node_in_two_workflows_keeps_separate_outputs(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    script = _script(tmp_path, "copy_app.py", _COPY_APP)

    out_a = _only_file(AppBlock().run(inputs=_inputs(tmp_path, "wfA", 2), config=_config(project, script, "wfA")))
    out_b = _only_file(AppBlock().run(inputs=_inputs(tmp_path, "wfB", 2), config=_config(project, script, "wfB")))

    assert out_a != out_b
    assert out_a.relative_to(project).parts[:4] == ("data", "exchange", "wfA", "fiji")
    assert out_b.relative_to(project).parts[:4] == ("data", "exchange", "wfB", "fiji")
    # Workflow A's recorded output still holds workflow A's data.
    assert out_a.read_text() == "wfA #0"
    assert out_b.read_text() == "wfB #0"


def test_rerunning_single_input_node_does_not_trip_overwrite_guard(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    script = _script(tmp_path, "copy_app.py", _COPY_APP)

    first = _only_file(AppBlock().run(inputs=_inputs(tmp_path, "first", 1), config=_config(project, script, "wfA")))
    second = _only_file(AppBlock().run(inputs=_inputs(tmp_path, "second", 1), config=_config(project, script, "wfA")))

    assert first.parent.parent != second.parent.parent
    assert first.read_text() == "first #0"
    assert second.read_text() == "second #0"


def test_concurrent_workflows_collect_only_their_own_outputs(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    script = _script(tmp_path, "tag_app.py", _TAG_APP)
    collected: dict[str, list[str]] = {}

    def run(workflow_id: str) -> None:
        block = AppBlock()
        block.prepare_launch = lambda exchange_dir, output_dir, config: [workflow_id]  # type: ignore[method-assign]
        result = block.run(inputs={}, config=_config(project, script, workflow_id, output_patterns=["*.txt"]))
        collected[workflow_id] = sorted(Path(item.file_path).name for coll in result.values() for item in coll)

    threads = [threading.Thread(target=run, args=(wf,)) for wf in ("wf_a", "wf_b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert collected == {"wf_a": ["wf_a.txt"], "wf_b": ["wf_b.txt"]}


def test_run_id_from_config_names_the_run_folder(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    script = _script(tmp_path, "copy_app.py", _COPY_APP)

    out = _only_file(
        AppBlock().run(inputs=_inputs(tmp_path, "x", 1), config=_config(project, script, "main", run_id="run-7"))
    )

    assert out == project / "data" / "exchange" / "main" / "fiji" / "run-7" / "outputs" / "result.txt"


def test_legacy_prefilled_output_dir_uses_the_per_run_folder(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    script = _script(tmp_path, "copy_app.py", _COPY_APP)
    legacy = project / "data" / "exchange" / "fiji" / "outputs"

    out = _only_file(
        AppBlock().run(
            inputs=_inputs(tmp_path, "x", 1),
            config=_config(project, script, "main", run_id="r1", output_dir=str(legacy)),
        )
    )

    assert out == project / "data" / "exchange" / "main" / "fiji" / "r1" / "outputs" / "result.txt"
    assert not legacy.exists()


def test_legacy_default_detection_keeps_user_chosen_folders(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    exchange = project / "data" / "exchange"

    assert _is_legacy_default_output_dir(str(exchange / "outputs"), project_dir=str(project), block_id="fiji")
    assert _is_legacy_default_output_dir(str(exchange / "fiji" / "outputs"), project_dir=str(project), block_id="fiji")
    assert not _is_legacy_default_output_dir(str(project / "results"), project_dir=str(project), block_id="fiji")
    assert not _is_legacy_default_output_dir(
        str(exchange / "other" / "outputs"), project_dir=str(project), block_id="fiji"
    )
    assert not _is_legacy_default_output_dir(str(exchange / "outputs"), project_dir=None, block_id="fiji")


def test_legacy_default_detection_matches_authored_id_of_flattened_node(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    exchange = project / "data" / "exchange"

    # ``sw1__fiji`` is the runtime id of node ``fiji`` inlined from subworkflow node ``sw1``.
    for runtime_id in ("sw1__fiji", "outer__sw1__fiji"):
        assert _is_legacy_default_output_dir(
            str(exchange / "fiji" / "outputs"), project_dir=str(project), block_id=runtime_id
        )
    assert _is_legacy_default_output_dir(
        str(exchange / "sw1__fiji" / "outputs"), project_dir=str(project), block_id="sw1__fiji"
    )
    assert not _is_legacy_default_output_dir(
        str(exchange / "sw1" / "outputs"), project_dir=str(project), block_id="sw1__fiji"
    )


def test_appblock_in_inlined_subworkflow_ignores_legacy_output_dir(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    script = _script(tmp_path, "copy_app.py", _COPY_APP)
    legacy = project / "data" / "exchange" / "fiji" / "outputs"
    (project / "subworkflows").mkdir()
    (project / "subworkflows" / "qc.yaml").write_text(
        "workflow:\n"
        "  id: qc\n"
        "  nodes:\n"
        "    - id: fiji\n"
        "      block_type: app_block\n"
        "      config:\n"
        f"        output_dir: {json.dumps(str(legacy))}\n"
        "  edges: []\n",
        encoding="utf-8",
    )
    (project / "main.yaml").write_text(
        "workflow:\n"
        "  id: main\n"
        "  nodes:\n"
        "    - id: sw1\n"
        "      block_type: subworkflow_block\n"
        "      config:\n"
        "        ref:\n"
        "          path: subworkflows/qc.yaml\n"
        "  edges: []\n",
        encoding="utf-8",
    )
    flat = flatten_subworkflows(load_yaml(project / "main.yaml"), base_dir=project, self_path=project / "main.yaml")
    (node,) = flat.nodes
    assert node.id == "sw1__fiji"

    config = _config(project, script, "main", run_id="r1", block_id=node.id, output_dir=node.config["output_dir"])
    out = _only_file(AppBlock().run(inputs=_inputs(tmp_path, "x", 1), config=config))

    assert out == project / "data" / "exchange" / "main" / "sw1__fiji" / "r1" / "outputs" / "result.txt"
    assert not legacy.exists()
