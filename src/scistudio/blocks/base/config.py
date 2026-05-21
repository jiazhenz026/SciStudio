"""BlockConfig — validated parameter container (Pydantic)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class BlockConfig(BaseModel):
    """Configuration container for a block instance.

    Uses Pydantic's ``extra="allow"`` so that subclasses and plugins can
    attach arbitrary validated fields without modifying this base class.
    """

    model_config = ConfigDict(extra="allow")

    params: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        """Return a parameter value by *key*, falling back to *default*.

        Checks ``params`` first, then Pydantic extra fields so that
        runtime-enriched keys (``block_id``, ``project_dir``, …) injected
        by the scheduler are discoverable via the same accessor (#565).
        """
        if key in self.params:
            return self.params[key]
        extras = self.__pydantic_extra__ or {}
        if key in extras:
            return extras[key]
        return default
