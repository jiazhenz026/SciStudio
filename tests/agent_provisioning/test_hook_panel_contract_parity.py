"""Surface 3 (#2196): the panel-contract hook, and the guard against it drifting.

The hook script cannot import ``scistudio``. Every provisioned hook runs under
the *base* interpreter — that is what makes the frozen command outlive the venv
it was written in (``hooks.hook_interpreter``) — so the panel source checks are
transcribed into the template rather than imported from
:mod:`scistudio.blocks.base.panel_contract`.

A transcription that nobody compares is a copy that silently rots, so the parity
test below runs both implementations over the same fixture corpus and requires
identical output, code, severity, message, and repair alike. If you change a
rule or a word in one, this test tells you to change it in the other.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from scistudio.blocks.base.interactive import PANEL_API_VERSION
from scistudio.blocks.base.panel_contract import check_panel_module_source

_TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "scistudio"
    / "agent_provisioning"
    / "templates"
    / "hook_check_panel_contract.py"
)

GOOD_PANEL = """
// A panel that satisfies the contract.
export default {
  apiVersion: "1",
  mount(container, host) {
    const ok = document.createElement("button");
    ok.addEventListener("click", () => host.confirm({ picked: 1 }));
    ok.addEventListener("auxclick", () => host.cancel());
    container.append(ok);
    return { unmount() { container.replaceChildren(); } };
  },
};
"""

#: One entry per rule the two implementations share, plus the shapes that must
#: *not* be flagged. Every case is a whole module so both sides see the same
#: text a real write would produce.
FIXTURES = {
    "good": GOOD_PANEL,
    "named_export_only": 'export const panel = { apiVersion: "1", mount(c, host) { host.confirm(); '
    "host.cancel(); return { unmount() {} }; } };",
    "no_api_version": "export default { mount(c, host) { host.confirm(); host.cancel(); return { unmount() {} }; } };",
    "no_mount": 'export default { apiVersion: "1", render() {} };',
    "wrong_major": 'export default { apiVersion: "3", mount(c, host) { host.confirm(); host.cancel(); '
    "return { unmount() {} }; } };",
    "no_unmount": GOOD_PANEL.replace("return { unmount() { container.replaceChildren(); } };", "return {};"),
    "no_controls": 'export default { apiVersion: "1", mount(container, host) { return { unmount() {} }; } };',
    "destructured_controls": 'export default { apiVersion: "1", mount(c, host) { const { confirm, cancel } = host; '
    "return { unmount() {} }; } };",
    "renamed_host_binding": 'export default { apiVersion: "1", mount(el, h) { h.confirm(); h.cancel(); '
    "return { unmount() {} }; } };",
    "remote_import": 'import lib from "https://cdn.example.com/lib.js";\n' + GOOD_PANEL,
    "relative_import": 'import lib from "./helpers.mjs";\n' + GOOD_PANEL,
    "star_reexport": 'export * from "./impl.mjs";\n',
    "export_as_default": 'const panel = { apiVersion: "1", mount(c, host) { host.confirm(); host.cancel(); '
    "return { unmount() {} }; } };\nexport { panel as default };",
    "comment_only_controls": "// calls host.confirm and host.cancel\n"
    'export default { apiVersion: "1", mount(c, h) { return {}; } };',
    "template_literal_that_looks_like_a_comment": "const tip = `/*`;\n" + GOOD_PANEL,
    "empty": "",
}


@pytest.fixture(scope="module")
def hook_module() -> ModuleType:
    """Import the template as a module, the way the parity check needs it."""
    spec = importlib.util.spec_from_file_location("_panel_contract_hook_under_test", _TEMPLATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hook_pins_the_same_panel_api_version(hook_module: ModuleType) -> None:
    """The hook hardcodes the version because it cannot import it — so pin it here."""
    assert hook_module.PANEL_API_VERSION == PANEL_API_VERSION


@pytest.mark.parametrize("case", sorted(FIXTURES))
def test_hook_and_shared_module_agree(hook_module: ModuleType, case: str) -> None:
    source = FIXTURES[case]

    expected = [(d.code, d.severity, d.message, d.fix) for d in check_panel_module_source(source)]
    actual = hook_module.check_panel_module_source(source)

    assert actual == expected


@pytest.mark.parametrize("case", ["named_export_only"])
def test_hook_and_shared_module_agree_on_a_custom_export_name(hook_module: ModuleType, case: str) -> None:
    source = FIXTURES[case]

    expected = [(d.code, d.severity, d.message, d.fix) for d in check_panel_module_source(source, export_name="panel")]
    actual = hook_module.check_panel_module_source(source, export_name="panel")

    assert actual == expected


def test_the_shipped_tutorial_panel_is_clean_under_the_hook(hook_module: ModuleType) -> None:
    panel = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "scistudio"
        / "tutorials"
        / "core"
        / "what-is-a-type"
        / "assets"
        / "panels"
        / "review_labels"
        / "panel.mjs"
    )
    if not panel.is_file():  # pragma: no cover - only when tutorial assets are stripped
        pytest.skip("tutorial panel assets are not present in this checkout")

    assert hook_module.check_panel_module_source(panel.read_text(encoding="utf-8")) == []


# ---------------------------------------------------------------------------
# End-to-end: the provisioned script, driven the way the CLI drives it.
# ---------------------------------------------------------------------------


def _run_hook(script: Path, payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def hook_script(tmp_project_dir: Path) -> Path:
    from scistudio.agent_provisioning.hooks import write_hooks

    write_hooks(tmp_project_dir, force=False)
    return tmp_project_dir / ".claude" / "hooks" / "check_panel_contract.py"


def test_hook_is_provisioned(hook_script: Path) -> None:
    assert hook_script.is_file()


@pytest.mark.parametrize("suffix", [".js", ".mjs"])
def test_hook_warns_after_a_panel_write(hook_script: Path, tmp_project_dir: Path, suffix: str) -> None:
    """The gap this hook closes: no hook matched a panel module at all."""
    panels = tmp_project_dir / "panels"
    panels.mkdir(parents=True, exist_ok=True)
    target = panels / f"panel{suffix}"
    target.write_text('export const p = { apiVersion: "5", mount(c, h) {} };', encoding="utf-8")

    result = _run_hook(hook_script, {"tool_name": "Write", "tool_input": {"file_path": str(target)}})

    assert result.returncode == 0  # PostToolUse can never block
    assert "export_missing" in result.stderr
    assert "api_version_mismatch" in result.stderr


def test_hook_is_silent_on_a_sound_panel(hook_script: Path, tmp_project_dir: Path) -> None:
    panels = tmp_project_dir / "panels"
    panels.mkdir(parents=True, exist_ok=True)
    target = panels / "panel.mjs"
    target.write_text(GOOD_PANEL, encoding="utf-8")

    result = _run_hook(hook_script, {"tool_name": "Write", "tool_input": {"file_path": str(target)}})

    assert result.returncode == 0
    assert result.stderr.strip() == ""


def test_hook_ignores_ordinary_project_javascript(hook_script: Path, tmp_project_dir: Path) -> None:
    """A ``mount`` function in unrelated JS must not train the author to ignore this hook."""
    target = tmp_project_dir / "scripts" / "widget.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("export function mount(el) { el.textContent = 'hi'; }\n", encoding="utf-8")

    result = _run_hook(hook_script, {"tool_name": "Write", "tool_input": {"file_path": str(target)}})

    assert result.stderr.strip() == ""


def test_hook_ignores_a_python_write(hook_script: Path, tmp_project_dir: Path) -> None:
    target = tmp_project_dir / "blocks" / "thing.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x = 1\n", encoding="utf-8")

    result = _run_hook(hook_script, {"tool_name": "Write", "tool_input": {"file_path": str(target)}})

    assert result.returncode == 0
    assert result.stderr.strip() == ""


def test_hook_survives_an_empty_payload(hook_script: Path) -> None:
    """#1994: an unreadable payload must exit 0, not die and be reported as failed."""
    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input="",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
