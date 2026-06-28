"""Post-rc terminal shim: bundled Python bin must win after dotfiles (#1838).

The embedded user terminal previously opened in whatever the user's shell rc
files activated (conda ``base`` for a typical conda user), shadowing the app's
bundled interpreter so ``pip install X`` had no effect on the app. The shim
sources the user's own config first, then re-prepends the bundled bin so it is
the last writer of ``PATH``.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from scistudio.desktop import paths as desktop_paths


def _env(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    bin_dir = tmp_path / "env" / "bin"
    python = tmp_path / "env" / "py" / "python"
    env = {
        "SCISTUDIO_USER_PYTHON_BIN": str(bin_dir),
        "SCISTUDIO_PYTHON": str(python),
        "ZDOTDIR": "/user/zdot",
    }
    return env, bin_dir, python


def test_zsh_invocation_writes_zdotdir_that_reprepends_after_user_rc(tmp_path: Path) -> None:
    env, bin_dir, python = _env(tmp_path)

    argv, new_env = desktop_paths.user_terminal_post_rc_invocation(["/bin/zsh"], env)

    # The shell binary itself is unchanged; the redirection is via ZDOTDIR.
    assert argv == ["/bin/zsh"]
    zdotdir = Path(new_env["ZDOTDIR"])
    assert zdotdir.is_dir()
    # The user's real dotfiles location is preserved for the shim to source.
    assert new_env["SCISTUDIO_USER_ZDOTDIR"] == "/user/zdot"

    zshrc = (zdotdir / ".zshrc").read_text(encoding="utf-8")
    # Sources the user's own .zshrc first (preserve aliases/env)...
    assert 'source "${SCISTUDIO_USER_ZDOTDIR}/.zshrc"' in zshrc
    # ...then re-prepends the bundled bin + the interpreter dir, last.
    expected = f'export PATH={shlex.quote(str(bin_dir))}:{shlex.quote(str(python.parent))}:"$PATH"'
    assert expected in zshrc
    # The re-prepend line comes after the user-source line.
    assert zshrc.index("export PATH=") > zshrc.index("source ")

    # Other startup files exist and chain to the user's counterparts.
    assert 'source "${SCISTUDIO_USER_ZDOTDIR}/.zshenv"' in (zdotdir / ".zshenv").read_text("utf-8")


def test_bash_invocation_uses_rcfile_that_reprepends(tmp_path: Path) -> None:
    env, bin_dir, python = _env(tmp_path)

    argv, new_env = desktop_paths.user_terminal_post_rc_invocation(["/bin/bash"], env)

    # bash reaches the shim via --rcfile, not env rewriting, so env is unchanged.
    assert new_env == env
    assert argv[0] == "/bin/bash"
    assert "--rcfile" in argv
    assert "-i" in argv
    rcfile = Path(argv[argv.index("--rcfile") + 1])
    body = rcfile.read_text(encoding="utf-8")
    assert 'source "$HOME/.bashrc"' in body
    expected = f'export PATH={shlex.quote(str(bin_dir))}:{shlex.quote(str(python.parent))}:"$PATH"'
    assert expected in body
    assert body.index("export PATH=") > body.index("source ")


def test_unshimmed_shell_is_unchanged(tmp_path: Path) -> None:
    env, _, _ = _env(tmp_path)
    argv, new_env = desktop_paths.user_terminal_post_rc_invocation(["/bin/sh"], env)
    assert argv == ["/bin/sh"]
    assert new_env == env
    assert "ZDOTDIR" not in {k for k in new_env if k == "SCISTUDIO_USER_ZDOTDIR"}


def test_missing_bundled_bin_falls_back_unchanged(tmp_path: Path) -> None:
    argv, new_env = desktop_paths.user_terminal_post_rc_invocation(["/bin/zsh"], {})
    assert argv == ["/bin/zsh"]
    assert new_env == {}
