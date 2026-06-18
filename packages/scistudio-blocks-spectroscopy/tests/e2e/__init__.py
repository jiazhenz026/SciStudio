"""End-to-end workflow tests for ``scistudio-blocks-spectroscopy`` (#1661).

These tests drive whole LOAD -> BLOCK -> SAVE workflows (and multi-block
pipelines) against the real block classes and the package ``_support`` API. They
build deterministic, seeded pseudo-spectra with analytic ground truth (see
:mod:`scistudio_blocks_spectroscopy.tests.e2e.fixtures`) and assert the saved /
output results against the known values, not just shapes.
"""
