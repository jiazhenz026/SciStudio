"""Tests for LLM output parsers (extract_code, extract_json)."""

from __future__ import annotations

import pytest

from scistudio.blocks.ai.parsers import extract_code, extract_json

# ---------------------------------------------------------------------------
# extract_code tests
# ---------------------------------------------------------------------------


class TestExtractCode:
    """Verify extract_code() parsing strategies."""

    def test_fenced_python_block(self) -> None:
        """Extracts code from a ```python fenced block."""
        response = "Here is the code:\n```python\nprint('hello')\n```\nDone."
        assert extract_code(response) == "print('hello')"

    def test_fenced_with_language(self) -> None:
        """Extracts code from a block tagged with the requested language."""
        response = "```javascript\nconsole.log('hi')\n```"
        assert extract_code(response, language="javascript") == "console.log('hi')"

    def test_untagged_fenced_block(self) -> None:
        """Falls back to untagged fenced block when language tag is missing."""
        response = "```\ndef foo():\n    return 42\n```"
        assert extract_code(response) == "def foo():\n    return 42"

    def test_bare_code_no_fences(self) -> None:
        """Returns stripped response when no fences are present."""
        response = "  x = 1  \n"
        assert extract_code(response) == "x = 1"

    def test_multiple_blocks_returns_first(self) -> None:
        """When multiple fenced blocks exist, return the first match."""
        response = "```python\nfirst()\n```\nSome text.\n```python\nsecond()\n```"
        assert extract_code(response) == "first()"

    def test_empty_response(self) -> None:
        """Empty response returns empty string."""
        assert extract_code("") == ""

    def test_whitespace_only(self) -> None:
        """Whitespace-only response returns empty string."""
        assert extract_code("   \n  \t  ") == ""

    def test_none_response(self) -> None:
        """None-like empty input returns empty string."""
        assert extract_code("") == ""

    def test_tagged_preferred_over_untagged(self) -> None:
        """Language-tagged block is preferred over untagged."""
        response = "```\nuntagged_code\n```\n```python\ntagged_code\n```"
        assert extract_code(response) == "tagged_code"

    def test_multiline_code(self) -> None:
        """Handles multi-line code blocks correctly."""
        response = "```python\nimport os\n\ndef main():\n    print(os.getcwd())\n```"
        expected = "import os\n\ndef main():\n    print(os.getcwd())"
        assert extract_code(response) == expected

    def test_code_with_backticks_inside(self) -> None:
        """Code containing single backticks inside is handled."""
        response = "```python\ns = `value`\n```"
        assert "value" in extract_code(response)


# ---------------------------------------------------------------------------
# extract_json tests
# ---------------------------------------------------------------------------


class TestExtractJson:
    """Verify extract_json() parsing strategies."""

    def test_fenced_json_block(self) -> None:
        """Extracts JSON from a ```json fenced block."""
        response = '```json\n{"key": "value"}\n```'
        result = extract_json(response)
        assert result == {"key": "value"}

    def test_untagged_fenced_block(self) -> None:
        """Falls back to untagged fenced block containing JSON."""
        response = '```\n{"a": 1}\n```'
        result = extract_json(response)
        assert result == {"a": 1}

    def test_raw_json_in_text(self) -> None:
        """Extracts JSON from inline {...} in prose."""
        response = 'The result is {"status": "ok", "count": 3} as expected.'
        result = extract_json(response)
        assert result == {"status": "ok", "count": 3}

    def test_entire_response_is_json(self) -> None:
        """Parses entire response when it is raw JSON."""
        response = '{"x": 42}'
        result = extract_json(response)
        assert result == {"x": 42}

    def test_nested_json(self) -> None:
        """Handles nested JSON objects."""
        response = '```json\n{"outer": {"inner": [1, 2, 3]}}\n```'
        result = extract_json(response)
        assert result == {"outer": {"inner": [1, 2, 3]}}

    def test_json_with_extra_text(self) -> None:
        """Extracts JSON surrounded by explanatory text."""
        response = 'Here is the configuration:\n```json\n{"model": "gpt-4o", "temp": 0.5}\n```\nUse this config.'
        result = extract_json(response)
        assert result["model"] == "gpt-4o"
        assert result["temp"] == 0.5

    def test_empty_response_raises(self) -> None:
        """Empty response raises ValueError."""
        with pytest.raises(ValueError, match="empty response"):
            extract_json("")

    def test_whitespace_only_raises(self) -> None:
        """Whitespace-only response raises ValueError."""
        with pytest.raises(ValueError, match="empty response"):
            extract_json("   \n  ")

    def test_invalid_json_raises(self) -> None:
        """Malformed JSON raises ValueError."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            extract_json("{not valid json}")

    def test_non_object_json_raises(self) -> None:
        """JSON that is not a dict raises ValueError."""
        with pytest.raises(ValueError, match="Expected a JSON object"):
            extract_json("[1, 2, 3]")

    def test_fenced_json_preferred(self) -> None:
        """Fenced json block is preferred over inline JSON."""
        response = 'Inline: {"a": 1}\n```json\n{"b": 2}\n```'
        result = extract_json(response)
        assert result == {"b": 2}

    def test_multiline_json(self) -> None:
        """Handles multi-line formatted JSON."""
        response = '```json\n{\n    "name": "test",\n    "version": 1\n}\n```'
        result = extract_json(response)
        assert result == {"name": "test", "version": 1}

    def test_json_with_strings_containing_braces(self) -> None:
        """JSON with brace characters in string values."""
        response = '{"pattern": "\\\\{.*\\\\}"}'
        result = extract_json(response)
        assert "pattern" in result
