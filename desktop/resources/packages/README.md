Place bundled SciStudio source packages here for desktop builds.

Expected shape:

packages/
  scistudio-blocks-example/
    pyproject.toml
    src/scistudio_blocks_example/__init__.py

The GUI local package installer writes user-installed packages to the
user-scoped plugin directory instead of this bundled resources directory.
Both locations are scanned by the same package discovery path. Neither path
downloads dependencies; packages must be compatible with the bundled Python
environment.
