"""Tests for the seeded ``MAINTAINERS`` file and bootstrap script (TC-1C.2).

Covers the file itself (validates against ``Maintainers`` schema, has
real entries) and the bootstrap script (idempotency, schema validation,
expected output shape).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

from scieasy.qa.schemas.maintainers import AgentRuntime, Maintainers

REPO_ROOT = Path(__file__).resolve().parents[2]
MAINTAINERS_PATH = REPO_ROOT / "MAINTAINERS"


def _load_bootstrap_module():
    """Import the bootstrap script as a module (it lives outside ``src/``)."""
    spec = importlib.util.spec_from_file_location(
        "_bootstrap_maintainers",
        REPO_ROOT / "scripts" / "migrate" / "bootstrap_maintainers.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("_bootstrap_maintainers", module)
    spec.loader.exec_module(module)
    return module


def _load_maintainers() -> Maintainers:
    """Helper: load the seed MAINTAINERS from the repo root."""
    with MAINTAINERS_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return Maintainers(**data)


def test_maintainers_exists() -> None:
    """The seed MAINTAINERS file must exist at the repo root."""
    assert MAINTAINERS_PATH.exists(), f"missing {MAINTAINERS_PATH}"


def test_maintainers_parses_against_schema() -> None:
    """The seed file validates against ``Maintainers``."""
    m = _load_maintainers()
    assert m.version == 1
    assert len(m.entries) >= 1


def test_every_entry_has_owner() -> None:
    """Every bootstrapped entry has at least one human."""
    m = _load_maintainers()
    for entry in m.entries:
        assert entry.humans, f"entry without humans: {entry.path_glob}"


def test_every_entry_has_full_agent_runtime_set() -> None:
    """Default policy: bootstrap entries permit all 5 AgentRuntime values."""
    m = _load_maintainers()
    full_set = set(AgentRuntime)
    for entry in m.entries:
        assert set(entry.agents_allowed) == full_set, (
            f"entry {entry.path_glob} agents_allowed != full set: {[a.value for a in entry.agents_allowed]}"
        )


def test_adr_042_modules_covered() -> None:
    """ADR-042's ``governs.modules`` are represented in MAINTAINERS."""
    m = _load_maintainers()
    globs = {e.path_glob for e in m.entries}
    # Spot-check from ADR-042 frontmatter governs.modules.
    for module in ("scieasy.qa", "scieasy.qa.schemas", "scieasy.qa.audit"):
        expected_glob = "src/" + module.replace(".", "/") + "/**"
        assert expected_glob in globs, f"{expected_glob} missing from MAINTAINERS"


def test_adr_043_modules_covered() -> None:
    """ADR-043's ``governs.modules`` are represented in MAINTAINERS."""
    m = _load_maintainers()
    globs = {e.path_glob for e in m.entries}
    for module in ("scieasy.qa.tracker", "scieasy.qa.governance", "scieasy.qa.test_quality"):
        expected_glob = "src/" + module.replace(".", "/") + "/**"
        assert expected_glob in globs, f"{expected_glob} missing from MAINTAINERS"


def test_adr_044_modules_covered() -> None:
    """ADR-044's ``governs.modules`` are represented in MAINTAINERS."""
    m = _load_maintainers()
    globs = {e.path_glob for e in m.entries}
    for module in ("scieasy.qa.docs", "scieasy.qa.docs.schemas"):
        expected_glob = "src/" + module.replace(".", "/") + "/**"
        assert expected_glob in globs, f"{expected_glob} missing from MAINTAINERS"


def test_bootstrap_render_is_idempotent(tmp_path: Path) -> None:
    """Two consecutive renders produce byte-identical output.

    This is the contract that lets the bootstrap script be re-run safely
    on the same ADR/spec tree.
    """
    boot = _load_bootstrap_module()
    a = boot.render_maintainers(REPO_ROOT)
    b = boot.render_maintainers(REPO_ROOT)
    assert a == b


def test_bootstrap_render_validates(tmp_path: Path) -> None:
    """Rendered text always parses against ``Maintainers``."""
    boot = _load_bootstrap_module()
    rendered = boot.render_maintainers(REPO_ROOT)
    data = yaml.safe_load(rendered)
    m = Maintainers(**data)
    assert m.version == 1
    assert m.entries  # non-empty


def test_bootstrap_module_to_glob() -> None:
    """``scieasy.foo.bar`` → ``src/scieasy/foo/bar/**`` per ADR-042 §6.4."""
    boot = _load_bootstrap_module()
    assert boot._module_to_glob("scieasy.qa.audit") == "src/scieasy/qa/audit/**"
    assert boot._module_to_glob("scieasy") == "src/scieasy/**"


def test_bootstrap_fallback_on_empty_governance(tmp_path: Path) -> None:
    """When no ADRs/specs are present, a fallback entry keeps the schema valid."""
    # ``Maintainers`` requires ``entries`` non-empty (min_length=1), so the
    # bootstrap must emit *something* even on a bare directory.
    boot = _load_bootstrap_module()
    rendered = boot.render_maintainers(tmp_path)  # empty dir
    data = yaml.safe_load(rendered)
    m = Maintainers(**data)
    assert len(m.entries) == 1
    assert m.entries[0].path_glob == "**"


def test_check_mode_does_not_write(tmp_path: Path) -> None:
    """``--check`` prints to stdout and never touches the file system."""
    boot = _load_bootstrap_module()
    fake_root = tmp_path / "fake-root"
    fake_root.mkdir()
    # No ADR/spec dirs → fallback entry path; --check must still succeed
    # without creating a MAINTAINERS file.
    exit_code = boot.main(["--repo-root", str(fake_root), "--check"])
    assert exit_code == 0
    assert not (fake_root / "MAINTAINERS").exists()


@pytest.mark.parametrize("module_path", ["scieasy.qa.tracker", "scieasy.qa.governance"])
def test_bootstrap_attributes_to_correct_adr(module_path: str) -> None:
    """Bootstrap labels entries with the ADR that declared the module."""
    m = _load_maintainers()
    expected_glob = "src/" + module_path.replace(".", "/") + "/**"
    matches = [e for e in m.entries if e.path_glob == expected_glob]
    assert matches, f"no entry for {module_path}"
    # ADR-043 owns scieasy.qa.tracker and scieasy.qa.governance per frontmatter.
    assert any(43 in e.adrs for e in matches), (
        f"expected ADR-043 attribution for {module_path}, got {[e.adrs for e in matches]}"
    )
