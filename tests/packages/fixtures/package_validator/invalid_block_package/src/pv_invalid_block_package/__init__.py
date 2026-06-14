from __future__ import annotations

from scistudio.blocks.base.package_info import PackageInfo


class NotABlock:
    name = "PV Not A Block"


def get_block_package() -> tuple[PackageInfo, list[type]]:
    return (
        PackageInfo(name="pv-invalid-block-package", version="0.1.0"),
        [NotABlock],
    )
