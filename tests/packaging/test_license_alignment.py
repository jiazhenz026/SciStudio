"""Regression tests pinning the project's declared license to the LICENSE file.

SciStudio relicensed from MIT to Apache-2.0 (#2018). The license is stated in
four independent places -- ``LICENSE``, the ``pyproject.toml`` metadata that
lands on PyPI, and the badge plus license section of each README -- with
nothing linking them. These tests make the four agree by construction so a
future edit to one cannot silently leave the others advertising a license the
project no longer grants.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_LICENSE = "Apache-2.0"


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_license_file_is_the_apache_2_0_text() -> None:
    """``LICENSE`` must carry the Apache-2.0 body, not just a name."""
    license_text = _read("LICENSE")

    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "http://www.apache.org/licenses/" in license_text
    # Clauses unique to Apache-2.0 (absent from MIT): patent grant and the
    # redistribution conditions that make it more than a permissive one-liner.
    assert "Grant of Patent License" in license_text
    assert "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION" in license_text

    # The appendix placeholder must be filled in, or the copyright line is void.
    assert "[yyyy] [name of copyright owner]" not in license_text
    assert "Copyright 2026 Jiazhen Zhang" in license_text


def test_pyproject_declares_the_same_license() -> None:
    """Package metadata (and therefore PyPI) must match ``LICENSE``."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        pyproject = tomllib.load(fh)

    assert pyproject["project"]["license"] == {"text": EXPECTED_LICENSE}


def test_readmes_advertise_the_same_license() -> None:
    """Both READMEs must name Apache-2.0 and must not still claim MIT.

    The badge and the license section are separate strings in each file, so a
    partial edit is the realistic failure mode; both are checked.
    """
    for rel in ("README.md", "README.zh-CN.md"):
        readme = _read(rel)

        assert "badge/License-Apache_2.0" in readme, f"{rel} license badge is stale"
        assert "Apache License 2.0" in readme, f"{rel} license section is stale"
        assert "MIT" not in readme, f"{rel} still claims MIT somewhere"


def test_block_package_scaffold_keeps_the_permissive_default() -> None:
    """Scaffolded user packages stay MIT; the relicense is deliberately not propagated.

    ``scistudio new-block-package`` writes this template into a package that
    belongs to the *user*, not to SciStudio. Per the owner decision on #2018 the
    default there stays MIT -- the most permissive choice -- rather than
    inheriting whatever license the runtime happens to ship under. This test
    exists so that decision has to be revisited explicitly rather than swept
    along by a future project-wide relicense.
    """
    template = _read("src/scistudio/cli/templates/block_package/pyproject.toml.tpl")

    assert 'license = {{text = "MIT"}}' in template
