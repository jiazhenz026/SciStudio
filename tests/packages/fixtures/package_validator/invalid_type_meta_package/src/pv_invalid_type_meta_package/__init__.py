from __future__ import annotations

from pydantic import BaseModel, PrivateAttr

from scistudio.core.types.base import DataObject


class InvalidMetaType(DataObject):
    class Meta(BaseModel):
        label: str = "invalid"
        _secret: str = PrivateAttr(default="not-serializable-contract")


def get_types() -> list[type]:
    return [InvalidMetaType]
