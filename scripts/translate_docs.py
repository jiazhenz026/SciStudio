#!/usr/bin/env python3
"""Translate English source docs to ``docs/zh-CN/**`` — ADR-042 §22.3.

Examples
--------

Translate a single ADR with the offline ``manual`` provider (no
network calls; emits a ``needs-manual`` stub)::

    python scripts/translate_docs.py \\
        --provider=manual \\
        --source docs/adr/ADR-042.md \\
        --target docs/zh-CN/adr/

Run the full incremental translation against the entire docs tree
(used by ``.github/workflows/translation.yml``)::

    python scripts/translate_docs.py --incremental

Translate via DeepL with the key from the env::

    SCIEASY_TRANSLATION_DEEPL_API_KEY=... \\
        python scripts/translate_docs.py --provider=deepl

Behaviour
---------

- Recursively walks ``--source`` (default ``docs``) and pairs each
  Markdown file with its mirror under ``--target``
  (default ``docs/zh-CN``).
- The ``--target`` subtree is skipped when it is nested under
  ``--source`` (so ``docs -> docs/zh-CN`` doesn't recurse forever).
- ``--incremental`` (ADR-042 §22.6) re-translates only files whose
  source SHA has changed. Each translated file carries
  ``source_sha: <sha>`` in its frontmatter; the SHA is the first 16
  hex chars of SHA-256 over the source file bytes.
- The script writes each translation to disk and prints a summary at
  the end. Exit code is non-zero only on provider failure.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from scieasy.qa.translation.client import (
    TranslatorClient,
    file_sha,
    translation_is_up_to_date,
    walk_pairs,
    write_translation,
)
from scieasy.qa.translation.settings import TranslationSettings


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="translate_docs",
        description="Translate English source docs to docs/zh-CN/** (ADR-042 §22.3).",
    )
    parser.add_argument(
        "--provider",
        choices=["deepl", "google", "azure", "manual"],
        default=None,
        help="Translation provider (default: read from SCIEASY_TRANSLATION_PROVIDER, falls back to 'deepl').",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("docs"),
        help="Source docs root (file or directory).",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("docs/zh-CN"),
        help="Target translations root (directory).",
    )
    parser.add_argument(
        "--locale",
        default="zh-CN",
        help="Target language code (default: zh-CN).",
    )
    parser.add_argument(
        "--source-lang",
        default="en",
        help="Source language code (default: en).",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only translate files whose source SHA changed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be translated; do not call the provider.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Emit per-file progress to stderr.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    log = logging.getLogger("translate_docs")

    settings = TranslationSettings()
    if args.provider:
        settings = settings.model_copy(update={"provider": args.provider})

    client = TranslatorClient.from_settings(settings)

    source: Path = args.source
    target_root: Path = args.target

    if not source.exists():
        log.error("Source path does not exist: %s", source)
        return 2

    # ``walk_pairs`` is robust whether ``source`` is a file or a dir.
    # When it's a single file, the target path is target_root/<name>.
    pairs = list(walk_pairs(source, target_root))
    if not pairs:
        log.warning("No source files found under %s", source)
        return 0

    translated_count = 0
    skipped_count = 0
    failed: list[Path] = []

    for src_path, target_path in pairs:
        if args.incremental and translation_is_up_to_date(src_path, target_path):
            log.info("up-to-date: %s", src_path)
            skipped_count += 1
            continue
        if args.dry_run:
            log.info("would translate: %s -> %s", src_path, target_path)
            translated_count += 1
            continue
        log.info("translating: %s", src_path)
        try:
            translated = client.translate_file(
                src_path,
                source_lang=args.source_lang,
                target_lang=args.locale,
            )
        except Exception as exc:  # pragma: no cover — exercised in integ
            log.error("FAILED %s: %s", src_path, exc)
            failed.append(src_path)
            continue
        write_translation(
            target_path,
            translated,
            source_sha=file_sha(src_path),
        )
        translated_count += 1

    summary = (
        f"translate_docs: provider={client.provider.name} "
        f"translated={translated_count} skipped={skipped_count} "
        f"failed={len(failed)}"
    )
    print(summary)
    if failed:
        for path in failed:
            print(f"  FAILED: {path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
