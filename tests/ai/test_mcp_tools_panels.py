"""The four panel MCP tools, and the harness that makes the authoring form honest.

ADR-054 spec 5 T-004, FR-014 to FR-018, plus the T-003 assertion that
``block-contract.md`` no longer teaches the retired ES-module form (FR-011).

The load-bearing test here is
:func:`test_harness_renders_and_captures_an_emission_in_a_browser`. ADR-054 §8.5
says the argument for a plain HTML panel is sound only if the agent can open its
work and look at it, so the harness is checked by *opening it* in the browser the
end-to-end toolchain provides and reading back what it captured — not by
asserting a file exists. When no browser is available that test skips loudly, and
:func:`test_harness_is_generated_from_the_contract_module` still holds the
generated documents to the contract module.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from collections.abc import Coroutine, Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import pytest

from scistudio.ai.agent.mcp import _context
from scistudio.ai.agent.mcp.tools_panels import (
    _contract,
    _scaffold,
    list_panel_examples,
    read_panel_source,
    reload_panels,
    scaffold_panel,
)
from scistudio.core import dropins
from scistudio.core.panels import PanelCapability, PanelManifest, read_panel_declaration
from scistudio.explore.queue import SnippetRefusedError, admit_snippet

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_REFERENCE = REPO_ROOT / "src" / "scistudio" / "_agent_reference"
HOST_CONTRACT = REPO_ROOT / _contract.HOST_CONTRACT_RELATIVE_PATH

_T = TypeVar("_T")


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run one tool coroutine. The repository does not install pytest-asyncio."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Stub context + tier fixtures
# ---------------------------------------------------------------------------


class _StubTypeRegistry:
    """Answers the one question ``scaffold_panel``'s soft validation asks.

    Shaped like the real :class:`scistudio.core.types.registry.TypeRegistry`:
    ``all_types()`` returns a mapping, which is what the shared
    ``_type_registry_has`` helper reads.
    """

    def __init__(self, names: set[str]) -> None:
        self._names = names

    def all_types(self) -> dict[str, object]:
        return dict.fromkeys(self._names, object())


@dataclass
class _StubContext:
    project_dir: Path | None
    type_registry: _StubTypeRegistry = field(default_factory=lambda: _StubTypeRegistry({"Series", "DataFrame"}))
    block_registry: object = field(default_factory=object)
    active_workflow_id: str | None = None


@pytest.fixture
def tiers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[dict[str, Path], None, None]:
    """A temporary project tier and user tier, with the context installed.

    The user library is redirected away from ``~/.scistudio`` the way the panel
    subsystem's own tests redirect it, so a test never writes into the person's
    library.
    """
    project = tmp_path / "project"
    (project / ".scistudio").mkdir(parents=True)
    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(dropins, "user_library_dir", lambda: library)

    _context.set_context(_StubContext(project_dir=project))  # type: ignore[arg-type]
    try:
        yield {"project": project, "library": library}
    finally:
        _context.set_context(None)


@pytest.fixture
def isolated_registry(tiers: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Make ``reload_panels`` scan only the temporary tiers.

    The core tier is replaced with an empty directory so a discovery assertion
    is about what the test wrote rather than about the eleven built-ins, and the
    package tier is silenced so an installed plugin cannot change the answer.
    The process-global preview service is reset so tests do not leak a registry
    into one another.
    """
    import scistudio.panels as panels_pkg
    from scistudio.panels import discovery as discovery_module

    empty_core = tiers["project"].parent / "empty-core"
    empty_core.mkdir(exist_ok=True)
    monkeypatch.setattr(discovery_module, "BUILTIN_PANELS_ROOT", empty_core)
    monkeypatch.setattr(discovery_module, "package_panel_roots", lambda **_kwargs: [])
    monkeypatch.setattr(panels_pkg, "_default_service", None, raising=False)
    return tiers


@pytest.fixture(autouse=True)
def _reset_global_preview_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may inherit or leave behind a process-global panel registry."""
    import scistudio.panels as panels_pkg

    monkeypatch.setattr(panels_pkg, "_default_service", None, raising=False)


def _scaffold_demo(tier: str = "project", **overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "panel_id": "demo.pick_baseline",
        "target_types": ["Series"],
        "capability": "producing",
        "tier": tier,
        "display_name": "Pick baseline",
    }
    kwargs.update(overrides)
    return _run(scaffold_panel(**kwargs))


def _demo_manifest(**overrides: Any) -> PanelManifest:
    fields: dict[str, Any] = {
        "panel_id": "demo.pick_baseline",
        "display_name": "Pick baseline",
        "target_types": ("Series",),
        "capability": PanelCapability.PRODUCING,
    }
    fields.update(overrides)
    return PanelManifest(**fields)


# ---------------------------------------------------------------------------
# FR-014 — the scaffold writes three files, and the skeleton runs
# ---------------------------------------------------------------------------


def test_scaffold_panel_writes_exactly_three_files(tiers: dict[str, Path]) -> None:
    """FR-014: a declaration, a self-contained document, and a harness."""
    result = _scaffold_demo()

    directory = Path(result.directory)
    written = sorted(path.name for path in directory.iterdir())
    assert written == ["harness.html", "index.html", "panel.json"]
    assert result.files_written == [result.declaration_path, result.document_path, result.harness_path]
    assert directory == tiers["project"] / "panels" / "demo.pick_baseline"


def test_scaffolded_declaration_validates_against_the_landed_contract(tiers: dict[str, Path]) -> None:
    """The file the scaffold writes is the file the runtime reads back."""
    result = _scaffold_demo()

    manifest = read_panel_declaration(Path(result.directory))
    assert manifest.panel_id == "demo.pick_baseline"
    assert manifest.display_name == "Pick baseline"
    assert manifest.target_types == ("Series",)
    assert manifest.capability is PanelCapability.PRODUCING
    assert manifest.entry == "index.html"
    assert manifest.api_version == _contract.PANEL_API_VERSION
    # The declaration round-trips: what was written parses back to itself.
    assert json.loads(Path(result.declaration_path).read_text(encoding="utf-8")) == manifest.to_declaration_dict()


def test_scaffolded_document_is_not_a_stub_that_cannot_run(tiers: dict[str, Path]) -> None:
    """The skeleton completes the handshake, renders, and carries the emit path.

    A document that answered nothing would still be three files on disk; what
    makes the scaffold worth calling is that the panel works before it is
    edited.
    """
    result = _scaffold_demo()
    document = Path(result.document_path).read_text(encoding="utf-8")

    assert "NotImplementedError" not in document
    for fragment in ('post("ready"', "function render()", 'post("emit"', 'id = "panel-emit"'):
        assert fragment in document, fragment
    # Self-contained (spec 1 FR-034): no external script, stylesheet, or import.
    # The banner comment names those forms in order to forbid them, so it is
    # stripped before the document itself is checked for them.
    body = re.sub(r"<!--.*?-->", "", document, flags=re.DOTALL)
    assert "<script src=" not in body
    assert "<link rel=" not in body
    assert "import(" not in body


def test_scaffold_warns_about_unregistered_types_and_a_displaying_capability(tiers: dict[str, Path]) -> None:
    result = _scaffold_demo(
        panel_id="demo.unknown_type",
        target_types=["NotARecordedType"],
        capability="displaying",
    )
    joined = " ".join(result.warnings)
    assert "NotARecordedType" in joined
    assert "displaying" in joined
    assert result.capability == "displaying"


def test_scaffold_refuses_to_overwrite_and_refuses_a_traversing_id(tiers: dict[str, Path]) -> None:
    _scaffold_demo()
    with pytest.raises(FileExistsError):
        _scaffold_demo()
    # Overwriting is possible, but only when asked for.
    assert _scaffold_demo(overwrite=True).panel_id == "demo.pick_baseline"

    with pytest.raises(ValueError, match="single path segment"):
        _scaffold_demo(panel_id="../escape")


def test_scaffold_refuses_a_read_only_tier(tiers: dict[str, Path]) -> None:
    with pytest.raises(ValueError, match="not writable"):
        _scaffold_demo(tier="core")


def test_scaffold_refuses_an_unknown_capability(tiers: dict[str, Path]) -> None:
    with pytest.raises(ValueError, match="capability"):
        _scaffold_demo(capability="mutating")


# ---------------------------------------------------------------------------
# FR-015 — the harness is generated from the contract module
# ---------------------------------------------------------------------------


def test_harness_carries_every_message_name_the_contract_module_names() -> None:
    harness = _scaffold.harness_document(_demo_manifest())
    for name in _contract.HOST_TO_PANEL_TYPES + _contract.PANEL_TO_HOST_TYPES + _contract.PANEL_HOST_ACTIONS:
        assert f'"{name}"' in harness, name
    assert f"var PANEL_MESSAGE_MARKER = {_contract.PANEL_MESSAGE_MARKER};" in harness


def test_harness_is_generated_from_the_contract_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Change the module's message names and the harness must change with them.

    This is the assertion that separates "generated from the contract" from
    "hand-copied and currently agreeing". A harness built from a literal would
    pass :func:`test_harness_carries_every_message_name_the_contract_module_names`
    and fail here.
    """
    assert "sentinel_reply" not in _scaffold.harness_document(_demo_manifest())

    monkeypatch.setattr(_contract, "PANEL_TO_HOST_TYPES", (*_contract.PANEL_TO_HOST_TYPES, "sentinel_request"))
    monkeypatch.setattr(_contract, "HOST_TO_PANEL_TYPES", (*_contract.HOST_TO_PANEL_TYPES, "sentinel_reply"))
    monkeypatch.setattr(
        _contract,
        "PANEL_REQUEST_RESULT_TYPES",
        {**_contract.PANEL_REQUEST_RESULT_TYPES, "sentinel_request": "sentinel_reply"},
    )

    regenerated = _scaffold.harness_document(_demo_manifest())
    assert '"sentinel_request"' in regenerated
    assert '"sentinel_reply"' in regenerated
    # The panel document is generated from the same block, so it moves too.
    assert '"sentinel_reply"' in _scaffold.panel_document(_demo_manifest())


def _ts_string_list(source: str, name: str) -> list[str]:
    """Extract a ``const NAME ... = [ "a", "b" ]`` list from TypeScript source."""
    match = re.search(rf"const {name}[^=]*=\s*\[(.*?)\]", source, re.DOTALL)
    assert match is not None, f"{name} not found in {HOST_CONTRACT}"
    return re.findall(r'"([^"]+)"', match.group(1))


@pytest.mark.skipif(not HOST_CONTRACT.is_file(), reason="the frontend host contract is not in this checkout")
def test_contract_module_mirrors_the_host_contract() -> None:
    """The Python mirror and the host's TypeScript must name the same messages.

    A Python scaffold cannot import ``panelMessages.ts``, so this test is what
    keeps the mirror from becoming a fork: the host learns a message type, and
    the scaffold's harness is told about it here rather than by a bug report.
    """
    source = HOST_CONTRACT.read_text(encoding="utf-8")
    assert _ts_string_list(source, "HOST_TO_PANEL_TYPES") == list(_contract.HOST_TO_PANEL_TYPES)
    assert _ts_string_list(source, "PANEL_TO_HOST_TYPES") == list(_contract.PANEL_TO_HOST_TYPES)
    assert _ts_string_list(source, "PANEL_HOST_ACTIONS") == list(_contract.PANEL_HOST_ACTIONS)
    assert _ts_string_list(source, "PANEL_REQUEST_TYPES") == list(_contract.PANEL_REQUEST_TYPES)
    assert f"PANEL_MESSAGE_MARKER = {_contract.PANEL_MESSAGE_MARKER} as const" in source


def test_harness_supplies_representative_data_for_each_declared_type() -> None:
    """FR-015: stub data per declared target type, in the host's own wire shape."""
    harness = _scaffold.harness_document(
        _demo_manifest(panel_id="demo.two_types", display_name="Two types", target_types=("Series", "DataFrame"))
    )
    match = re.search(r"var STUBS = (\{.*?\});\n", harness, re.DOTALL)
    assert match is not None
    stubs = json.loads(match.group(1))

    assert sorted(stubs) == ["DataFrame", "Series"]
    assert stubs["Series"]["kind"] == "series"
    assert stubs["DataFrame"]["kind"] == "dataframe"
    for envelope in stubs.values():
        assert set(envelope) >= {"kind", "payload", "metadata", "diagnostics", "target", "previewer_id"}
    assert stubs["DataFrame"]["payload"]["rows"], "a stub table with no rows renders as an empty box"


@pytest.mark.parametrize("build", ["panel", "harness"])
def test_generated_documents_parse_as_javascript(tmp_path: Path, build: str) -> None:
    """Both templates are interpolated Python strings; a bad escape is silent.

    The scaffold builds the two documents by substituting into a non-raw Python
    template, so one missing backslash turns a JavaScript escape into a real
    newline and the panel stops loading with nothing said. ``node --check``
    catches that in a second.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH, so the generated documents cannot be syntax-checked")

    document = (_scaffold.panel_document if build == "panel" else _scaffold.harness_document)(_demo_manifest())
    body = document[document.index("<script>") + len("<script>") : document.index("</script>")]
    script = tmp_path / f"{build}.js"
    script.write_text(body, encoding="utf-8", newline="\n")

    completed = subprocess.run([node, "--check", str(script)], capture_output=True, text=True, timeout=60, check=False)
    assert completed.returncode == 0, completed.stderr


def test_harness_read_limits_come_from_the_descriptor_builder() -> None:
    """The bounds the harness states are the bounds the host states."""
    from scistudio.panels.descriptor import read_limits_payload

    harness = _scaffold.harness_document(_demo_manifest())
    match = re.search(r"var READ_LIMITS = (\{.*?\});\n", harness, re.DOTALL)
    assert match is not None
    assert json.loads(match.group(1)) == read_limits_payload()


# ---------------------------------------------------------------------------
# FR-015 — the harness is opened in a browser and an emission is captured
# ---------------------------------------------------------------------------

_DRIVER = r"""
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.SCISTUDIO_PLAYWRIGHT_MODULE);

const harness = process.argv[2];
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  const consoleLines = [];
  page.on("console", (m) => consoleLines.push(m.type() + ": " + m.text()));
  page.on("pageerror", (e) => consoleLines.push("pageerror: " + e.message));

  await page.goto("file:///" + harness.replace(/\\/g, "/"));
  await page.waitForFunction(
    () => window.__scistudio_panel_harness__ && window.__scistudio_panel_harness__.ready === true,
    null,
    { timeout: 20000 },
  );

  const frame = page.frameLocator("#harness-frame");
  const heading = await frame.locator("h1").first().textContent();
  const rendered = await frame.locator("#root").first().textContent();
  await frame.locator("#panel-emit").click({ timeout: 20000 });
  await page.waitForFunction(
    () => window.__scistudio_panel_harness__.emissions.length > 0,
    null,
    { timeout: 20000 },
  );

  const record = await page.evaluate(() => window.__scistudio_panel_harness__);
  const emissionsShown = await page.locator("#emissions .emission").allTextContents();
  console.log("SCISTUDIO_RESULT " + JSON.stringify({
    ready: record.ready,
    ready_api_version: record.ready_api_version,
    emissions: record.emissions,
    emissions_shown: emissionsShown,
    errors: record.errors,
    conversation: record.messages.map((m) => m.direction + ":" + m.type),
    heading,
    rendered,
    consoleLines,
  }));
} finally {
  await browser.close();
}
"""


def _playwright_module() -> str | None:
    """Path of the Playwright module the end-to-end toolchain installs, if present.

    ``frontend/package.json`` declares ``@playwright/test``; ``npm ci`` in
    ``frontend/`` installs it and its ``playwright-core``. Nothing new is added
    to the Python dependency set for this test — it borrows the browser the
    repository's own e2e suite uses.
    """
    node_modules = REPO_ROOT / "frontend" / "node_modules"
    for candidate in ("playwright", "playwright-core"):
        if (node_modules / candidate / "package.json").is_file():
            return str(node_modules / candidate)
    return None


def _drive_harness(harness_path: Path, tmp_path: Path) -> dict[str, Any]:
    """Open *harness_path* in the e2e toolchain's chromium and report what it saw."""
    node = shutil.which("node")
    module = _playwright_module()
    if node is None or module is None:
        pytest.skip(
            "no browser available: this test opens the scaffolded harness in the chromium the frontend "
            "e2e toolchain installs. Run `npm ci` in frontend/ (and `npx playwright install chromium`) "
            "to enable it."
        )

    driver = tmp_path / "drive_harness.mjs"
    driver.write_text(_DRIVER, encoding="utf-8", newline="\n")
    env = {**os.environ, "SCISTUDIO_PLAYWRIGHT_MODULE": module.replace("\\", "/")}
    completed = subprocess.run(
        [node, str(driver), str(harness_path)],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        if "Executable doesn't exist" in completed.stderr or "browserType.launch" in completed.stderr:
            pytest.skip(f"the chromium build the e2e toolchain uses is not installed: {completed.stderr[-400:]}")
        pytest.fail(f"driving the harness failed ({completed.returncode}):\n{completed.stdout}\n{completed.stderr}")
    for line in completed.stdout.splitlines():
        if line.startswith("SCISTUDIO_RESULT "):
            return json.loads(line[len("SCISTUDIO_RESULT ") :])
    pytest.fail(f"the harness driver printed no result:\n{completed.stdout}\n{completed.stderr}")
    raise AssertionError("unreachable")  # pragma: no cover - pytest.fail does not return


def test_harness_renders_and_captures_an_emission_in_a_browser(tiers: dict[str, Path], tmp_path: Path) -> None:
    """FR-015, the whole point: open the harness, see it work, read the emission.

    Asserts in one pass that the harness completes the handshake, that the panel
    renders the stub data rather than an empty frame, that a person's
    interaction produces an emission, that the harness shows it, and that what
    was emitted is code the explore session would actually admit.
    """
    result = _scaffold_demo(target_types=["DataFrame"])
    observed = _drive_harness(Path(result.harness_path), tmp_path)

    assert observed["ready"] is True, observed
    assert observed["ready_api_version"] == _contract.PANEL_API_VERSION
    assert observed["errors"] == [], observed["errors"]
    assert observed["consoleLines"] == [], observed["consoleLines"]

    # It rendered over the stub data, not an empty frame.
    assert observed["heading"] == "Pick baseline"
    assert "wavelength" in observed["rendered"], observed["rendered"]

    # The conversation is the contract's: init out, ready back, then the emission.
    assert observed["conversation"][:2] == ["out:init", "in:ready"]
    assert "in:emit" in observed["conversation"]

    # The emission was captured and shown.
    assert len(observed["emissions"]) == 1, observed["emissions"]
    emitted = observed["emissions"][0]
    assert observed["emissions_shown"] == [emitted]
    assert emitted.startswith("selection = ")
    # Both statements, so the same document works in a session and at an
    # interactive block's pause.
    assert "scistudio.output(selection=selection)" in emitted

    # It is code the session's admission whitelist accepts (ADR-054 §3.6): an
    # assignment whose every target is a plain name, plus a scistudio.output
    # call.
    admit_snippet(emitted, panel="demo.pick_baseline")
    with pytest.raises(SnippetRefusedError):
        admit_snippet("selection['start'] = 400", panel="demo.pick_baseline")

    # And it is the decision an interactive block's pause settles it into.
    from scistudio.blocks.base.interactive import settle_panel_emission

    decision = settle_panel_emission(emitted, block_name="DemoBlock", panel_id="demo.pick_baseline")
    assert decision == {"selection": {"start": 400, "end": 430}}


# ---------------------------------------------------------------------------
# FR-018 — reload_panels
# ---------------------------------------------------------------------------


def test_reload_panels_discovers_the_scaffolded_panel(isolated_registry: dict[str, Path]) -> None:
    _scaffold_demo()

    result = _run(reload_panels())
    found = {entry.panel_id: entry for entry in result.panels}
    assert "demo.pick_baseline" in found, result.diagnostics
    entry = found["demo.pick_baseline"]
    assert entry.tier == "project"
    assert entry.capability == "producing"
    assert entry.target_types == ["Series"]
    assert entry.api_version == _contract.PANEL_API_VERSION
    assert result.count == len(result.panels)
    # The stub context carries no preview service, so the rebuild is process-local
    # and the tool says so rather than implying the GUI saw it.
    assert result.reached_running_gui is False


def test_reload_panels_reports_a_broken_declaration_as_a_diagnostic(isolated_registry: dict[str, Path]) -> None:
    """One broken panel is a diagnostic, never a failed reload."""
    _scaffold_demo()
    broken = isolated_registry["project"] / "panels" / "demo.broken"
    broken.mkdir(parents=True)
    (broken / "panel.json").write_text('{"panel_id": "demo.broken"}', encoding="utf-8")
    (broken / "index.html").write_text("<!doctype html>", encoding="utf-8")

    result = _run(reload_panels())
    assert "demo.pick_baseline" in {entry.panel_id for entry in result.panels}
    assert any("demo.broken" in line for line in result.diagnostics), result.diagnostics


# ---------------------------------------------------------------------------
# FR-016 — read_panel_source, from each tier it can resolve from
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tier", ["project", "user"])
def test_read_panel_source_round_trips_from_each_tier(isolated_registry: dict[str, Path], tier: str) -> None:
    scaffolded = _scaffold_demo(tier=tier)
    _run(reload_panels())

    result = _run(read_panel_source("demo.pick_baseline"))
    assert result.tier == tier
    assert result.directory == scaffolded.directory
    assert result.entry == "index.html"
    assert result.document == Path(scaffolded.document_path).read_text(encoding="utf-8")
    assert result.harness_path == scaffolded.harness_path
    assert result.declaration["panel_id"] == "demo.pick_baseline"
    assert result.read_only is False


def test_read_panel_source_reports_the_shadowed_tier(isolated_registry: dict[str, Path]) -> None:
    """A project copy shadows the user panel of the same id; the tool says so."""
    _scaffold_demo(tier="user")
    _scaffold_demo(tier="project")
    _run(reload_panels())

    result = _run(read_panel_source("demo.pick_baseline"))
    assert result.tier == "project"
    assert result.shadowed_tiers == ["user"]


def test_read_panel_source_names_the_registered_ids_when_it_refuses(isolated_registry: dict[str, Path]) -> None:
    _scaffold_demo()
    _run(reload_panels())
    with pytest.raises(KeyError, match=re.escape("demo.pick_baseline")):
        _run(read_panel_source("demo.not_there"))


def test_read_panel_source_marks_a_core_panel_read_only(tiers: dict[str, Path]) -> None:
    """The core tier resolves, and it is reported as read-only (spec 1 FR-026)."""
    _run(reload_panels())
    result = _run(read_panel_source("core.text.basic"))
    assert result.tier == "core"
    assert result.read_only is True
    assert "<!doctype html>" in result.document.lower()


# ---------------------------------------------------------------------------
# FR-017 — list_panel_examples, with and without a corpus
# ---------------------------------------------------------------------------


def test_list_panel_examples_is_empty_and_explains_itself_without_a_corpus(
    tiers: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The corpus entries are T-008's; this tool must not fail before they land."""
    from scistudio.ai.agent.mcp.tools_panels import tools as panel_tools

    empty = tmp_path / "no-examples"
    empty.mkdir()
    monkeypatch.setattr(panel_tools, "_examples_root", lambda: empty)

    result = _run(list_panel_examples())
    assert result.examples == []
    assert result.count == 0
    assert result.searched == [str(empty)]
    assert any("read_panel_source" in line for line in result.diagnostics), result.diagnostics


def test_list_panel_examples_returns_corpus_entries_when_they_exist(
    tiers: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scistudio.ai.agent.mcp.tools_panels import tools as panel_tools

    corpus = tmp_path / "examples"
    corpus.mkdir()
    for panel_id, capability in (("panel-show-series", "displaying"), ("panel-pick-region", "producing")):
        _scaffold.scaffold_panel_files(
            corpus,
            panel_id=panel_id,
            display_name=panel_id,
            target_types=("Series",),
            capability=PanelCapability(capability),
            tier="corpus",
        )
        (corpus / panel_id / "README.md").write_text(
            f"# {panel_id}\n\nWhat {capability} looks like.\n", encoding="utf-8"
        )
    # A stray non-panel directory must be ignored rather than refused.
    (corpus / "io-load-npy").mkdir()

    monkeypatch.setattr(panel_tools, "_examples_root", lambda: corpus)

    every = _run(list_panel_examples())
    assert [entry.example_id for entry in every.examples] == ["panel-pick-region", "panel-show-series"]
    assert every.count == 2
    assert all(entry.source == "corpus" for entry in every.examples)
    assert every.examples[0].description == "What producing looks like."

    producing = _run(list_panel_examples(capability="producing"))
    assert [entry.example_id for entry in producing.examples] == ["panel-pick-region"]

    with pytest.raises(ValueError, match="capability"):
        _run(list_panel_examples(capability="nonsense"))


def test_list_panel_examples_reads_the_shipped_corpus_location(tiers: dict[str, Path]) -> None:
    """Unmonkeypatched, the tool looks where the shipped corpus lives."""
    result = _run(list_panel_examples())
    assert result.searched == [str(REPO_ROOT / "src" / "scistudio" / "_user_guide" / "examples")]


# ---------------------------------------------------------------------------
# FR-010 / FR-011 / FR-013 — the reference documents
# ---------------------------------------------------------------------------

#: Vocabulary that belongs only to the retired ADR-048/ADR-051 module form and
#: to the asset route the panel contract retired. If one of these comes back
#: into the block contract, the document is teaching two forms again.
_RETIRED_PANEL_VOCABULARY = (
    "module_url",
    "export_name",
    "/api/blocks/panels/",
    "ES module",
    "es module",
    "host.confirm",
    "host.panelPayload",
    "mount(container, host)",
)


def test_block_contract_no_longer_teaches_the_retired_panel_form() -> None:
    """FR-011: the panel section is rewritten, not appended to."""
    text = (AGENT_REFERENCE / "block-contract.md").read_text(encoding="utf-8")
    offenders = [needle for needle in _RETIRED_PANEL_VOCABULARY if needle in text]
    assert not offenders, f"block-contract.md still teaches the retired panel form: {offenders}"


def test_block_contract_teaches_the_framed_document_form() -> None:
    text = (AGENT_REFERENCE / "block-contract.md").read_text(encoding="utf-8")
    for fragment in ("panel-contract.md", "panel.json", "index.html", "scaffold_panel"):
        assert fragment in text, fragment


def test_panel_contract_reference_covers_the_six_subjects_it_owns() -> None:
    """FR-010: one document, and it is the single description of all six."""
    text = (AGENT_REFERENCE / "panel-contract.md").read_text(encoding="utf-8")
    for fragment in (
        "panel.json",  # the capability declaration and the on-disk layout
        "displaying",
        "producing",
        "scistudio_panel",  # the message contract's envelope
        "project",  # the tiers and the registration per tier
        "reload_panels",
        "scistudio.output",  # the statement whitelist
    ):
        assert fragment in text, fragment
    for name in _contract.HOST_TO_PANEL_TYPES + _contract.PANEL_TO_HOST_TYPES:
        assert f"`{name}`" in text, name


def test_reference_readme_indexes_the_panel_contract() -> None:
    """FR-013."""
    text = (AGENT_REFERENCE / "README.md").read_text(encoding="utf-8")
    assert "panel-contract.md" in text


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_the_four_panel_tools_are_registered_on_the_shared_instance() -> None:
    from scistudio.ai.agent.mcp.server import mcp

    registered = {tool.name: tool for tool in _run(mcp.list_tools())}
    for name in ("scaffold_panel", "read_panel_source", "list_panel_examples", "reload_panels"):
        assert name in registered, name
        assert "category:panel" in set(registered[name].tags or set())
