"""End-to-end tests for ``scripts/translate_docs.py`` — ADR-042 §22.3.

Runs the script via ``runpy``/import using a subprocess to exercise
``main()`` with controlled argv. Uses the offline ``manual`` provider
exclusively so the tests never touch the network.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "translate_docs.py"


def _load_script_module() -> object:
    """Load ``scripts/translate_docs.py`` as an importable module.

    The script is not on ``sys.path`` by default; we load it via
    ``importlib.util.spec_from_file_location`` so we can call ``main()``
    directly with controlled argv.
    """
    spec = importlib.util.spec_from_file_location("translate_docs_under_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["translate_docs_under_test"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script_main(monkeypatch: pytest.MonkeyPatch) -> object:
    # Force offline provider regardless of inherited env.
    for key in list(__import__("os").environ):
        if key.startswith("SCIEASY_TRANSLATION_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SCIEASY_TRANSLATION_PROVIDER", "manual")
    module = _load_script_module()
    return module.main  # type: ignore[attr-defined]


def test_cli_translates_single_file(
    tmp_path: Path,
    script_main,  # type: ignore[no-untyped-def]
    capsys: pytest.CaptureFixture[str],
) -> None:
    src = tmp_path / "ADR-X.md"
    src.write_text("# Title\n\nBody.\n", encoding="utf-8")
    target = tmp_path / "out"

    rc = script_main(
        [
            "--provider=manual",
            f"--source={src}",
            f"--target={target}",
        ]
    )
    assert rc == 0
    out_file = target / "ADR-X.md"
    assert out_file.exists()
    body = out_file.read_text(encoding="utf-8")
    assert "source_sha:" in body
    assert "translation_status: needs-manual" in body
    captured = capsys.readouterr()
    assert "translated=1" in captured.out


def test_cli_translates_directory(
    tmp_path: Path,
    script_main,  # type: ignore[no-untyped-def]
) -> None:
    src_root = tmp_path / "docs"
    src_root.mkdir()
    (src_root / "a.md").write_text("A.\n", encoding="utf-8")
    (src_root / "sub").mkdir()
    (src_root / "sub" / "b.md").write_text("B.\n", encoding="utf-8")

    rc = script_main(
        [
            "--provider=manual",
            f"--source={src_root}",
            f"--target={tmp_path / 'zh-CN'}",
        ]
    )
    assert rc == 0
    assert (tmp_path / "zh-CN" / "a.md").exists()
    assert (tmp_path / "zh-CN" / "sub" / "b.md").exists()


def test_cli_incremental_skips_unchanged(
    tmp_path: Path,
    script_main,  # type: ignore[no-untyped-def]
    capsys: pytest.CaptureFixture[str],
) -> None:
    src = tmp_path / "x.md"
    src.write_text("Body.\n", encoding="utf-8")
    target_dir = tmp_path / "out"

    # First pass: translates.
    rc = script_main(["--provider=manual", f"--source={src}", f"--target={target_dir}"])
    assert rc == 0

    # Second pass with --incremental: should skip.
    capsys.readouterr()  # drain
    rc = script_main(
        [
            "--provider=manual",
            f"--source={src}",
            f"--target={target_dir}",
            "--incremental",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "skipped=1" in out
    assert "translated=0" in out


def test_cli_incremental_re_translates_when_source_changes(
    tmp_path: Path,
    script_main,  # type: ignore[no-untyped-def]
    capsys: pytest.CaptureFixture[str],
) -> None:
    src = tmp_path / "x.md"
    src.write_text("First.\n", encoding="utf-8")
    target_dir = tmp_path / "out"
    script_main(["--provider=manual", f"--source={src}", f"--target={target_dir}"])
    capsys.readouterr()
    # Mutate source.
    src.write_text("Second.\n", encoding="utf-8")
    rc = script_main(
        [
            "--provider=manual",
            f"--source={src}",
            f"--target={target_dir}",
            "--incremental",
        ]
    )
    assert rc == 0
    assert "translated=1" in capsys.readouterr().out


def test_cli_dry_run_writes_nothing(
    tmp_path: Path,
    script_main,  # type: ignore[no-untyped-def]
    capsys: pytest.CaptureFixture[str],
) -> None:
    src = tmp_path / "x.md"
    src.write_text("body", encoding="utf-8")
    target = tmp_path / "out"
    rc = script_main(
        [
            "--provider=manual",
            f"--source={src}",
            f"--target={target}",
            "--dry-run",
        ]
    )
    assert rc == 0
    assert not (target / "x.md").exists()


def test_cli_missing_source_returns_2(
    tmp_path: Path,
    script_main,  # type: ignore[no-untyped-def]
) -> None:
    rc = script_main(
        [
            "--provider=manual",
            f"--source={tmp_path / 'nope.md'}",
            f"--target={tmp_path / 'out'}",
        ]
    )
    assert rc == 2


def test_cli_empty_source_dir_returns_0(
    tmp_path: Path,
    script_main,  # type: ignore[no-untyped-def]
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = script_main(
        [
            "--provider=manual",
            f"--source={empty}",
            f"--target={tmp_path / 'out'}",
        ]
    )
    assert rc == 0
