"""CodeBlock -- user-provided scripts in Python, R, or Julia."""

from __future__ import annotations

from scistudio.blocks.code.code_block import (
    CodeBlock,
    CodeBlockBackend,
    CodeBlockRuntimeContext,
    ensure_codeblock_backends_loaded,
    list_codeblock_backends,
    register_codeblock_backend,
    resolve_codeblock_backend,
    run_codeblock_process,
    unregister_codeblock_backend,
)
from scistudio.blocks.code.lazy_list import LazyList

__all__ = [
    "CodeBlock",
    "CodeBlockBackend",
    "CodeBlockRuntimeContext",
    "LazyList",
    "ensure_codeblock_backends_loaded",
    "list_codeblock_backends",
    "register_codeblock_backend",
    "resolve_codeblock_backend",
    "run_codeblock_process",
    "unregister_codeblock_backend",
]
