Place hard-installed SciStudio source packages here for the ADR-037 MVP.

Expected shape:

packages/
  scistudio-blocks-example/
    pyproject.toml
    src/scistudio_blocks_example/__init__.py

The MVP does not install dependencies. Packages placed here must be compatible
with the bundled Python environment.
