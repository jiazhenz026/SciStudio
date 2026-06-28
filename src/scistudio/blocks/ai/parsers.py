"""Structured output parsing for LLM responses.

This module provides utilities for extracting structured content from
free-text LLM responses:

* ``extract_code()`` -- pull code from fenced or unfenced blocks.
* ``extract_json()`` -- pull and parse JSON from fenced or raw responses.

These parsers are designed to be resilient to common LLM output
variations (extra whitespace, missing language tags, multiple blocks).
"""

from __future__ import annotations

import json
import re


def extract_code(response: str, language: str = "python") -> str:
    """Extract source code from a fenced block in an LLM response.

    Pulls the code out of a model's reply so you can run or save it. Tries, in
    order: a fenced block tagged with the requested *language*, then any
    untagged fenced block, then the whole response treated as bare code. When
    several fenced blocks match, only the first is returned.

    Args:
        response: Raw text returned by the model.
        language: Language tag to look for, e.g. ``"python"`` or ``"json"``.

    Returns:
        The extracted code, or ``""`` when *response* is empty.

    Example:
        >>> reply = "Here you go:\\n```python\\nprint(1)\\n```"
        >>> extract_code(reply)
        'print(1)'
    """
    if not response or not response.strip():
        return ""

    # Strategy 1: fenced block with language tag.
    pattern_tagged = re.compile(
        rf"```{re.escape(language)}\s*\n(.*?)```",
        re.DOTALL,
    )
    match = pattern_tagged.search(response)
    if match:
        return match.group(1).strip()

    # Strategy 2: untagged fenced block.
    pattern_untagged = re.compile(
        r"```\s*\n(.*?)```",
        re.DOTALL,
    )
    match = pattern_untagged.search(response)
    if match:
        return match.group(1).strip()

    # Strategy 3: bare code (no fences).
    return response.strip()


def extract_json(response: str) -> dict:
    """Extract and parse a JSON object from an LLM response.

    Pulls a JSON object out of a model's reply, even when it is wrapped in
    prose or a code fence. Tries, in order: a fenced block tagged ``json``,
    any untagged fenced block, the first ``{...}`` span that parses, then the
    whole response.

    Args:
        response: Raw text returned by the model.

    Returns:
        The parsed JSON object as a dict.

    Raises:
        ValueError: *response* is empty, or no valid JSON object can be
            extracted from it.

    Example:
        >>> reply = 'Sure:\\n```json\\n{"ok": true}\\n```'
        >>> extract_json(reply)
        {'ok': True}
    """
    if not response or not response.strip():
        raise ValueError("Cannot extract JSON from empty response.")

    # Strategy 1: fenced block with json tag.
    pattern_json = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)
    match = pattern_json.search(response)
    if match:
        return _safe_parse(match.group(1).strip())

    # Strategy 2: untagged fenced block.
    pattern_untagged = re.compile(r"```\s*\n(.*?)```", re.DOTALL)
    match = pattern_untagged.search(response)
    if match:
        candidate = match.group(1).strip()
        try:
            return _safe_parse(candidate)
        except ValueError:
            pass  # Fall through to next strategy.

    # Strategy 3: first {...} substring.
    brace_match = re.search(r"\{.*\}", response, re.DOTALL)
    if brace_match:
        try:
            return _safe_parse(brace_match.group(0))
        except ValueError:
            pass

    # Strategy 4: entire response as raw JSON.
    return _safe_parse(response.strip())


def _safe_parse(text: str) -> dict:
    """Parse *text* as JSON and ensure the result is a dict.

    Raises
    ------
    ValueError
        If *text* is not valid JSON or the top-level value is not an object.
    """
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object (dict), got {type(parsed).__name__}.")
    return parsed
