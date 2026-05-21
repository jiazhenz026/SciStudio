"""Command validation for AppBlock — prevents shell injection."""

from __future__ import annotations

import re
import shlex
import shutil
import sys
from pathlib import Path

# Shell metacharacters that indicate injection attempts.
_SHELL_META = re.compile(r"[;|&$`><{}\n\r]")


def validate_app_command(command: str | list[str]) -> list[str]:
    """Validate and normalise an app command into a safe argument list.

    Accepts either a single command string (executable name or absolute path)
    or a pre-split argument list.  Rejects commands containing shell
    metacharacters and verifies the executable can be resolved.

    Parameters
    ----------
    command:
        The raw command from workflow YAML config.

    Returns
    -------
    list[str]
        A validated, split argument list safe for ``subprocess.Popen``.

    Raises
    ------
    ValueError
        If the command contains shell metacharacters or cannot be resolved.
    """
    if isinstance(command, list):
        parts = list(command)
    else:
        # Check for shell metacharacters before splitting.
        if _SHELL_META.search(command):
            raise ValueError(f"Command contains shell metacharacters and was rejected: {command!r}")
        # If the string is a bare filesystem path (e.g. selected via
        # file_browser widget), treat it as a single executable token
        # so shlex.split does not break paths with spaces like
        # "C:\Program Files\Fiji\fiji.exe".
        parts = [command] if Path(command).is_file() else shlex.split(command)

    if not parts:
        raise ValueError("Empty command")

    # Validate each part for shell metacharacters.
    for part in parts:
        if _SHELL_META.search(part):
            raise ValueError(f"Command argument contains shell metacharacters: {part!r}")

    # Resolve the executable.
    exe = parts[0]
    resolved = shutil.which(exe)
    is_valid = resolved is not None or Path(exe).is_file()
    # macOS .app bundles are directories, not files (#483).
    if not is_valid and sys.platform == "darwin" and exe.endswith(".app"):
        is_valid = Path(exe).is_dir()
    if not is_valid:
        raise ValueError(f"Command executable not found: {exe!r}. Ensure it is on PATH or provide an absolute path.")

    return parts
