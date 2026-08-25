"""Post-#2150 contract for the removed commit-msg git hook.

The commitizen / gate_record commit-msg hooks are gone: `git commit` runs
nothing, and the final commit's Conventional Commits subject is validated by
the evaluator at the pre-pr/ci modes instead (see
``tests/qa/test_gate_commit_checks.py``). What remains here is the CLI
compatibility contract that made the ``commit-msg`` alias necessary (issue
#1609 Defect 4): the alias still accepts the message-file positional, and the
``check`` subcommand still rejects it — the alias stays for manual/legacy
callers even though no hook invokes it anymore.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scistudio.qa.governance.gate_record import cli

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRECOMMIT_CONFIG = _REPO_ROOT / ".pre-commit-config.yaml"


class TestConfigWiring:
    def test_no_commit_msg_stage_hook_remains(self) -> None:
        config = yaml.safe_load(_PRECOMMIT_CONFIG.read_text(encoding="utf-8"))
        for repo in config["repos"]:
            for hook in repo.get("hooks", []):
                assert "commit-msg" not in hook.get("stages", []), hook


class TestCliContract:
    """Why the alias exists: ``check`` rejects the positional; the alias accepts it."""

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
