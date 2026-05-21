"""Test fixtures package — non-production helpers used by the test suite.

Modules under :mod:`tests.fixtures` are intentionally not part of the
production ``scistudio`` package. They host things like the smoke-test
``NoopBlock`` (relocated from ``src/scistudio/blocks/process/builtins/transform.py``
in T-TRK-003) and end-to-end test image path constants (Q6).
"""
