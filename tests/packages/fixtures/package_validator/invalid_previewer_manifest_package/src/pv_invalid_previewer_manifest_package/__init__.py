from __future__ import annotations

from scistudio.previewers.models import FrontendManifest, OwnerKind, PreviewerSpec


def get_previewers() -> list[PreviewerSpec]:
    return [
        PreviewerSpec(
            previewer_id="pv.invalid.remote.manifest",
            owner_kind=OwnerKind.PACKAGE,
            owner_name="pv-invalid-previewer-manifest-package",
            target_type="DataObject",
            backend_provider=None,
            frontend_manifest=FrontendManifest(
                previewer_id="pv.invalid.remote.manifest",
                module_url="https://example.invalid/remote-previewer.js",
                export_name="render",
                version="0.1.0",
                asset_root="assets",
            ),
        )
    ]
