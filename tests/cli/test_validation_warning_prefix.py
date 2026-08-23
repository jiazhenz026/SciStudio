"""#1988 — an advisory diagnostic must not stop a CLI command.

``validate_workflow`` returns one list in which a leading ``Warning:`` marks an
advisory. The API layer has always split on that prefix; the CLI treated the
list as all-or-nothing, so an advisory made ``scistudio run`` refuse to
dispatch. That was latent until #1988 widened the unregistered-block-type report
to nodes with no edges — which is every node whose block failed to resolve,
because such a node has no ports and therefore no edges.
"""

from __future__ import annotations

import pytest
import typer

from scistudio.cli.main import _report_validation_errors


def test_warnings_alone_do_not_stop_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    _report_validation_errors(
        [
            "Warning: node 'orphan' uses block type 'srs_baseline_block', which is not registered in this project",
        ]
    )

    out = capsys.readouterr().out
    assert "Validation warnings:" in out
    assert "srs_baseline_block" in out
    assert "Validation errors:" not in out


def test_a_hard_error_still_stops_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(typer.Exit) as excinfo:
        _report_validation_errors(["Workflow contains a cycle"])

    assert excinfo.value.exit_code == 1
    assert "Validation errors:" in capsys.readouterr().out


def test_a_hard_error_alongside_a_warning_still_stops(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(typer.Exit) as excinfo:
        _report_validation_errors(
            [
                "Warning: node 'orphan' uses block type 'ghost_block', which is not registered in this project",
                "Duplicate node id: 'a'",
            ]
        )

    assert excinfo.value.exit_code == 1
    out = capsys.readouterr().out
    # Both are reported; only the hard error decides the exit.
    assert "ghost_block" in out
    assert "Duplicate node id" in out


def test_no_diagnostics_prints_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    _report_validation_errors([])
    assert capsys.readouterr().out == ""
