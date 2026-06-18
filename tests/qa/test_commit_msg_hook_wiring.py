"""Regression test for issue #1609 Defect 4 (commit-msg hook wiring).

On the ``commit-msg`` stage, pre-commit appends the commit-message file path to
the hook entry. The ``check`` subparser has no positional for it, so
``gate_record check --mode commit-msg <FILE>`` exits 2 (``unrecognized
arguments``) and fails every ``git commit``. The purpose-built ``commit-msg
<message-file>`` alias accepts that path. This test pins both halves: the config
must call the alias, and the CLI contract that makes the alias necessary.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scistudio.qa.governance.gate_record import cli

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRECOMMIT_CONFIG = _REPO_ROOT / ".pre-commit-config.yaml"


def _commit_msg_hook_entry() -> str:
    config = yaml.safe_load(_PRECOMMIT_CONFIG.read_text(encoding="utf-8"))
    for repo in config["repos"]:
        for hook in repo.get("hooks", []):
            if hook.get("id") == "scistudio-gate-record-commit-msg":
                return str(hook["entry"])
    raise AssertionError("scistudio-gate-record-commit-msg hook not found in .pre-commit-config.yaml")


class TestConfigWiring:
    def test_commit_msg_hook_calls_the_commit_msg_alias(self) -> None:
        entry = _commit_msg_hook_entry()
        # Must invoke the ``commit-msg`` subcommand, which accepts the appended
        # message-file path (trailing flags such as --no-record are allowed)...
        assert "scistudio.qa.governance.gate_record commit-msg" in entry
        # ...and must NOT use ``check --mode commit-msg`` (the form that rejects
        # the appended file with exit 2).
        assert "check --mode commit-msg" not in entry


class TestCliContract:
    """Why the alias is required: ``check`` rejects the positional; the alias accepts it."""

    def test_commit_msg_alias_accepts_message_file(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["commit-msg", "/tmp/COMMIT_EDITMSG"])
        assert args.message_file == "/tmp/COMMIT_EDITMSG"
        assert getattr(args, "_alias_to", None) == "check"
        assert getattr(args, "_alias_mode", None) == "commit-msg"

    def test_check_subcommand_rejects_appended_message_file(self) -> None:
        parser = cli.build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["check", "--mode", "commit-msg", "/tmp/COMMIT_EDITMSG"])
        # argparse exits 2 on unrecognized arguments -- the Defect-4 failure mode.
        assert exc.value.code == 2
