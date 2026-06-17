"""Format handler functions for spectroscopy IO blocks.

The four load/save utility blocks declare ADR-043 ``FormatCapability`` records
whose ``handler`` field names a method on the block class. Those methods
delegate to the stub functions in :mod:`.spectrum_formats` and
:mod:`.dataset_formats`. Implementers fill the handler bodies per the spec
capability matrix (FR-132..FR-143).
"""

from __future__ import annotations

__all__: list[str] = []
