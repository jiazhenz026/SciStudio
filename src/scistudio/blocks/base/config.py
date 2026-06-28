"""BlockConfig — validated parameter container (Pydantic)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from scistudio.stability import stable


@stable(since="0.3.1")
class BlockConfig(BaseModel):
    """Holds the parameters a block reads at run time.

    A Pydantic model that allows extra fields, so a block or package can attach
    its own validated parameters without changing this base class, and the
    runtime can inject extra keys (such as ``block_id`` or ``project_dir``) onto
    the same object. Reach for :meth:`get` to read a value by name whether it
    lives in :attr:`params` or was attached as an extra field.

    Example:
        >>> from scistudio.blocks.base import BlockConfig
        >>> config = BlockConfig(params={"threshold": 0.5})
        >>> config.get("threshold")
        0.5
        >>> config.get("missing", default=0)
        0
    """

    model_config = ConfigDict(extra="allow")
    """Pydantic model settings; ``extra="allow"`` keeps any unrecognised fields."""

    params: dict[str, Any] = {}
    """The block's parameters, keyed by parameter name."""

    @stable(since="0.3.1")
    def get(self, key: str, default: Any = None) -> Any:
        """Return the value of parameter *key*, or *default* when it is not set.

        Looks in :attr:`params` first, then in the model's extra fields, so a
        key injected by the runtime is found through the same call as a user
        parameter.

        Args:
            key: Name of the parameter to read.
            default: Value to return when *key* is present in neither place.

        Returns:
            The stored value for *key*, or *default* when it is absent.

        Example:
            >>> BlockConfig(params={"n": 3}).get("n")
            3
        """
        if key in self.params:
            return self.params[key]
        # Runtime-injected keys (block_id, project_dir, …) land in extras (#565).
        extras = self.__pydantic_extra__ or {}
        if key in extras:
            return extras[key]
        return default
