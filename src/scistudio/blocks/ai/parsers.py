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
    """Extract code from a fenced code block in an LLM response.

    The function tries the following strategies in order:

    1. A fenced block tagged with the requested *language*:
       ````language ... ````
    2. An untagged fenced block: ```` ... ````
    3. The entire *response* stripped of leading/trailing whitespace
       (assumed to be bare code).

    When multiple fenced blocks match, only the **first** is returned.

    Parameters
    ----------
    response:
        Raw LLM text response.
    language:
        Language tag to look for (e.g. ``"python"``, ``"json"``).

    Returns
    -------
    str
        Extracted code, or ``""`` if *response* is empty.
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
    """Extract and parse JSON from an LLM response.

    The function tries the following strategies in order:

    1. A fenced block tagged ``json``: ````json ... ````
    2. An untagged fenced block containing valid JSON.
    3. The first ``{...}`` substring that parses as valid JSON.
    4. The entire *response* as raw JSON.

    Parameters
    ----------
    response:
        Raw LLM text response.

    Returns
    -------
    dict
        Parsed JSON object.

    Raises
    ------
    ValueError
        If no valid JSON can be extracted from *response*.
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
