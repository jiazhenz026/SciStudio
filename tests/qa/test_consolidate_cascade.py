"""Tests for ``scripts/audit/consolidate_cascade.py``.

ADR-042 §27.5 mandates the consolidator must:

* Walk every addendum's ``amends`` frontmatter field.
* Produce deterministic output (re-runs yield identical bytes).
* Provide ``--verify`` mode that exits non-zero on drift.

Coverage target: ≥95% per the dispatch DoD. The tests below build
small fake ADR fixtures under ``tmp_path`` so we exercise every code
path without depending on the real ADR-042/043/044 contents (which
would change as the cascade evolves).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from scripts.audit import consolidate_cascade as cc

# --------------------------------------------------------------- helpers


def _write_adr(
    dir_: Path,
    num: int,
    *,
    title: str,
    status: str = "Accepted",
    amends: list[tuple[str, str, str]] | None = None,
    body: str = "## 1. Body\n\nSome prose.\n",
) -> Path:
    """Write a minimal ADR fixture file and return its path."""
    fm_lines: list[str] = [
        "---",
        f"adr: {num}",
        f'title: "{title}"',
        f"status: {status}",
    ]
    if amends:
        fm_lines.append("amends:")
        for target, kind, summary in amends:
            fm_lines.append(f'  - target: "{target}"')
            fm_lines.append(f"    kind: {kind}")
            fm_lines.append(f'    summary: "{summary}"')
    else:
        fm_lines.append("amends: []")
    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append(body)
    path = dir_ / f"ADR-{num:03d}.md"
    path.write_text("\n".join(fm_lines), encoding="utf-8")
    return path


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Build a minimal repo skeleton with one base ADR and two amenders."""
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)

    _write_adr(
        adr_dir,
        42,
        title="QA Infrastructure",
        body="# ADR-042: QA\n\n## 1. Body\n\nBase prose.\n",
    )
    _write_adr(
        adr_dir,
        43,
        title="Addendum A",
        amends=[
            ("ADR-042 §17 Required Skills", "extend", "Adds test-author skill"),
            ("ADR-042 §11", "constrain", "Tightens closure requirement"),
        ],
        body="# ADR-043: Addendum A\n\n## 1. Stuff\n\nAddendum A prose.\n",
    )
    _write_adr(
        adr_dir,
        44,
        title="Addendum B",
        amends=[
            ("ADR-042 §21 Tool Stack", "extend", "Adds 9 Sphinx tools"),
            (
                "ADR-042 §23.1 (component: furo theme bullet)",
                "replace",
                "Replaces furo with pydata_sphinx_theme",
            ),
        ],
        body="# ADR-044: Addendum B\n\n## 1. Stuff\n\nAddendum B prose.\n",
    )
    return tmp_path


# ------------------------------------------------------ frontmatter parser


def test_strip_inline_comment_handles_basic_case():
    assert cc._strip_inline_comment("key: value  # comment") == "key: value"


def test_strip_inline_comment_preserves_hash_in_quoted_string():
    assert cc._strip_inline_comment('key: "value with # not a comment"') == 'key: "value with # not a comment"'


def test_strip_inline_comment_first_char_hash():
    # Leading-# treats whole line as comment, returns empty.
    assert cc._strip_inline_comment("# whole line is comment") == ""


def test_unquote_double_quotes():
    assert cc._unquote('"hello"') == "hello"


def test_unquote_single_quotes():
    assert cc._unquote("'hello'") == "hello"


def test_unquote_no_quotes():
    assert cc._unquote("hello") == "hello"


def test_unquote_mismatched_quotes_passes_through():
    # Mismatched quotes are not stripped (parser passes raw value).
    assert cc._unquote("\"hello'") == "\"hello'"


def test_parse_frontmatter_extracts_title_status():
    fm = textwrap.dedent(
        """\
        adr: 42
        title: "Hello"
        status: Accepted
        amends: []
        """
    )
    parsed = cc._parse_frontmatter_for_amends(fm)
    assert parsed["title"] == "Hello"
    assert parsed["status"] == "Accepted"
    assert parsed["amends"] == []


def test_parse_frontmatter_parses_amendments_list():
    fm = textwrap.dedent(
        """\
        adr: 43
        title: "Add A"
        status: Accepted
        amends:
          - target: "ADR-042 §17"
            kind: extend
            summary: "Adds skill X"
          - target: "ADR-042 §11"
            kind: constrain
            summary: "Tightens closure"
        """
    )
    parsed = cc._parse_frontmatter_for_amends(fm)
    amends = parsed["amends"]
    assert len(amends) == 2
    assert amends[0].target == "ADR-042 §17"
    assert amends[0].kind == "extend"
    assert amends[0].summary == "Adds skill X"
    assert amends[1].kind == "constrain"


def test_parse_frontmatter_skips_unknown_keys_and_comments():
    fm = textwrap.dedent(
        """\
        # leading comment
        adr: 43
        title: "Title"  # inline comment
        unrelated_key: foo
        status: Draft
        amends: []
        """
    )
    parsed = cc._parse_frontmatter_for_amends(fm)
    assert parsed["title"] == "Title"
    assert parsed["status"] == "Draft"


def test_parse_frontmatter_empty_input():
    parsed = cc._parse_frontmatter_for_amends("")
    assert parsed["title"] == ""
    assert parsed["amends"] == []


def test_parse_frontmatter_amends_terminator_flushes_record():
    # An amends block followed by another top-level key must flush the
    # in-flight record.
    fm = textwrap.dedent(
        """\
        adr: 43
        amends:
          - target: "ADR-042 §X"
            kind: extend
            summary: "S"
        status: Accepted
        """
    )
    parsed = cc._parse_frontmatter_for_amends(fm)
    assert len(parsed["amends"]) == 1
    assert parsed["status"] == "Accepted"


# ---------------------------------------------------------- parse_adr


def test_parse_adr_returns_none_for_non_adr_filename(tmp_path: Path):
    p = tmp_path / "ADR.md"
    p.write_text("---\nadr: 1\n---\n\nbody", encoding="utf-8")
    assert cc.parse_adr(p) is None


def test_parse_adr_returns_none_when_no_frontmatter(tmp_path: Path):
    p = tmp_path / "ADR-099.md"
    p.write_text("just body, no frontmatter\n", encoding="utf-8")
    assert cc.parse_adr(p) is None


def test_parse_adr_extracts_fields(tmp_path: Path):
    adr = _write_adr(tmp_path, 42, title="Test", body="body content here\n")
    result = cc.parse_adr(adr)
    assert result is not None
    assert result.adr_num == 42
    assert result.title == "Test"
    assert result.status == "Accepted"
    assert "body content here" in result.body


# ---------------------------------------------------- discover + render


def test_discover_adrs_returns_empty_for_missing_dir(tmp_path: Path):
    assert cc.discover_adrs(tmp_path) == []


def test_discover_adrs_finds_and_orders(fake_repo: Path):
    adrs = cc.discover_adrs(fake_repo)
    nums = [a.adr_num for a in adrs]
    assert nums == [42, 43, 44]


def test_render_cascade_includes_base_and_amenders(fake_repo: Path):
    adrs = cc.discover_adrs(fake_repo)
    out = cc.render_cascade(adrs)

    assert "## Base ADR-042 — QA Infrastructure" in out
    assert "### ADR-043 — Addendum A" in out
    assert "### ADR-044 — Addendum B" in out
    # Amendment records are surfaced
    assert "ADR-042 §17 Required Skills" in out
    assert "Replaces furo with pydata_sphinx_theme" in out
    # Bodies appear
    assert "Base prose" in out
    assert "Addendum A prose" in out
    assert "Addendum B prose" in out


def test_render_cascade_handles_no_amenders(tmp_path: Path):
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    _write_adr(adr_dir, 42, title="Base only")
    adrs = cc.discover_adrs(tmp_path)
    out = cc.render_cascade(adrs)
    assert "_(no amending addenda)_" in out


def test_render_cascade_raises_if_base_missing(tmp_path: Path):
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    _write_adr(adr_dir, 99, title="Some other ADR")
    adrs = cc.discover_adrs(tmp_path)
    with pytest.raises(RuntimeError, match="Base ADR-42 not found"):
        cc.render_cascade(adrs)


def test_render_cascade_is_deterministic(fake_repo: Path):
    adrs = cc.discover_adrs(fake_repo)
    first = cc.render_cascade(adrs)
    second = cc.render_cascade(adrs)
    assert first == second
    assert cc._hash(first) == cc._hash(second)


# -------------------------------------------------------------- CLI


def test_main_emits_to_default_path(fake_repo: Path, capsys: pytest.CaptureFixture):
    rc = cc.main(["--repo-root", str(fake_repo)])
    assert rc == 0
    expected = fake_repo / "docs" / "adr" / "_consolidated" / "cascade-current.md"
    assert expected.is_file()
    out = capsys.readouterr().out
    assert "Wrote" in out


def test_main_emits_to_custom_output(fake_repo: Path, tmp_path: Path):
    custom = tmp_path / "out.md"
    rc = cc.main(["--repo-root", str(fake_repo), "--output", str(custom)])
    assert rc == 0
    assert custom.is_file()
    assert "## Base ADR-042" in custom.read_text(encoding="utf-8")


def test_main_returns_2_when_no_adrs(tmp_path: Path, capsys: pytest.CaptureFixture):
    rc = cc.main(["--repo-root", str(tmp_path)])
    assert rc == 2
    assert "no ADRs discovered" in capsys.readouterr().err


def test_main_returns_2_when_base_missing(tmp_path: Path, capsys: pytest.CaptureFixture):
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    _write_adr(adr_dir, 99, title="Other")
    rc = cc.main(["--repo-root", str(tmp_path)])
    assert rc == 2
    assert "Base ADR-42 not found" in capsys.readouterr().err


def test_main_verify_passes_on_match(fake_repo: Path, capsys: pytest.CaptureFixture):
    # Generate, then re-verify
    cc.main(["--repo-root", str(fake_repo)])
    rc = cc.main(["--repo-root", str(fake_repo), "--verify"])
    assert rc == 0
    assert "matches in-memory render" in capsys.readouterr().out


def test_main_verify_fails_if_file_missing(fake_repo: Path, capsys: pytest.CaptureFixture):
    rc = cc.main(["--repo-root", str(fake_repo), "--verify"])
    assert rc == 1
    assert "does not exist" in capsys.readouterr().err


def test_main_verify_fails_on_drift(fake_repo: Path, capsys: pytest.CaptureFixture):
    cc.main(["--repo-root", str(fake_repo)])
    out_path = fake_repo / "docs" / "adr" / "_consolidated" / "cascade-current.md"
    # Mutate the on-disk file
    out_path.write_text(
        out_path.read_text(encoding="utf-8") + "\nDRIFT INJECTION\n",
        encoding="utf-8",
    )
    rc = cc.main(["--repo-root", str(fake_repo), "--verify"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "differs from re-rendered" in err


def test_hash_is_stable():
    a = cc._hash("hello")
    b = cc._hash("hello")
    c = cc._hash("hello!")
    assert a == b
    assert a != c
