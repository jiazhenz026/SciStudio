"""RunnerRegistry — maps language string to CodeRunner class."""

from __future__ import annotations


class RunnerRegistry:
    """Registry that maps language identifiers to :class:`CodeRunner` classes."""

    def __init__(self) -> None:
        self._runners: dict[str, type] = {}

    def register(self, language: str, runner_class: type) -> None:
        """Register *runner_class* for the given *language*."""
        self._runners[language.lower()] = runner_class

    def get(self, language: str) -> type:
        """Return the runner class registered for *language*.

        Raises :class:`KeyError` if no runner is registered.
        """
        key = language.lower()
        if key not in self._runners:
            raise KeyError(f"No runner registered for language '{language}'")
        return self._runners[key]

    def all_runners(self) -> dict[str, type]:
        """Return a copy of the full language-to-runner mapping."""
        return dict(self._runners)

    def register_defaults(self) -> None:
        """Register the built-in runners shipped with SciStudio."""
        from scistudio.blocks.code.runners.julia_runner import JuliaRunner
        from scistudio.blocks.code.runners.python_runner import PythonRunner
        from scistudio.blocks.code.runners.r_runner import RRunner

        self.register("python", PythonRunner)
        self.register("r", RRunner)
        self.register("julia", JuliaRunner)
