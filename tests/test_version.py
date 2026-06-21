"""Tests for version management (#1742, scistudio.version)."""

from __future__ import annotations

import pytest
from packaging.version import Version

from scistudio import version


@pytest.mark.parametrize(
    ("channel", "build", "pep440", "display"),
    [
        ("alpha", 0, "0.2.1a0", "0.2.1-alpha-build0000"),
        ("alpha", 7, "0.2.1a7", "0.2.1-alpha-build0007"),
        ("beta", 3, "0.2.1b3", "0.2.1-beta-build0003"),
        ("stable", 5, "0.2.1", "0.2.1"),
    ],
)
def test_format_tracks(channel, build, pep440, display):
    assert version.format_pep440("0.2.1", channel, build) == pep440
    assert version.format_display("0.2.1", channel, build) == display
    # The Python track MUST always be valid PEP 440.
    assert str(Version(pep440)) == pep440


def test_invalid_channel_raises():
    with pytest.raises(ValueError):
        version.validate_channel("nightly")
    with pytest.raises(ValueError):
        version.format_pep440("0.2.1", "nightly", 0)


def test_get_version_shape(monkeypatch):
    monkeypatch.setenv("SCISTUDIO_BUILD_NUMBER", "1")
    info = version.get_version()
    assert set(info.as_dict()) == {"base", "channel", "build", "pep440", "semver", "display"}
    assert info.build == 1
    assert info.semver == info.display


def test_env_override_build_number(monkeypatch):
    monkeypatch.setenv("SCISTUDIO_BUILD_NUMBER", "42")
    assert version.read_build_number("alpha") == 42
    assert version.get_version().build == 42


def test_build_counter_roundtrip_and_channel_isolation(tmp_path, monkeypatch):
    counter = tmp_path / ".build-counter.json"
    monkeypatch.setattr(version, "counter_path", lambda: counter)
    monkeypatch.delenv("SCISTUDIO_BUILD_NUMBER", raising=False)

    assert version.read_build_number("alpha") == 0
    assert version.bump_build_number("alpha") == 1
    assert version.bump_build_number("alpha") == 2
    assert version.read_build_number("alpha") == 2
    # A different channel starts at 0 (the "reset on channel change" behavior).
    assert version.read_build_number("beta") == 0
    assert version.write_build_number("beta", 0) == 0


def test_dunder_version_is_pep440():
    # scistudio.__version__ must be importable by packaging (importlib.metadata).
    assert str(Version(version.__version__)) == version.__version__
