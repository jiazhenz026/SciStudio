from __future__ import annotations

from scistudio.previewers.models import OwnerKind, PreviewerSpec


def get_previewers() -> list[PreviewerSpec]:
    return [
        PreviewerSpec(
            previewer_id="pv.unknown.target",
            owner_kind=OwnerKind.PACKAGE,
            owner_name="pv-unknown-cross-surface-target-package",
            target_type="MissingFixtureType",
            backend_provider=None,
        )
    ]
