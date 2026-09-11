"""Isolated browser harness: production app/routes, fixture-owned runtime and files."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pyarrow as pa
import uvicorn
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from tests.api.fake_guard import RecordingFakeGuardFactory
from tests.panels.conftest import make_runtime

from scistudio.api.app import create_app
from scistudio.api.runtime._data import enrich_preview_query
from scistudio.api.runtime.models import DataRecord
from scistudio.core.storage.composite_store import CompositeStore
from scistudio.core.storage.ref import StorageReference
from scistudio.panels.descriptor import parse_descriptor
from scistudio.panels.registry import PanelRegistry
from scistudio.previewers.models import OwnerKind
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.router import PreviewRouter
from scistudio.previewers.session import PreviewSessionManager


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--replacement", action="store_true")
    args = parser.parse_args()
    os.environ["SCISTUDIO_ROOT_PATH"] = args.prefix
    root = Path(__file__).resolve().parents[3]
    build = root / ".workflow/local/panel-browser-build"
    with TemporaryDirectory(prefix="scistudio-panel-browser-") as temporary:
        runtime, _store = make_runtime(Path(temporary))
        runtime.enrich_preview_query = lambda ref, query: enrich_preview_query(runtime, ref, query)
        runtime.data_catalog["data-a"].type_name = "BrowserText"
        runtime.data_catalog["data-a"].type_chain.append("BrowserText")
        storage = CompositeStore().write(
            {"index": ("arrow", pa.table({"a": [1, 2]})), "notes": ("filesystem", "legacy child text")},
            StorageReference(backend="composite", path=str(Path(temporary) / "composite")),
        )
        runtime.data_catalog["comp"] = DataRecord(
            "comp",
            storage,
            "Composite",
            {"slots": {"index": "DataFrame", "notes": "Text"}},
            ["DataObject", "Composite"],
        )
        registry = PreviewerRegistry()
        registry.load_core()
        service = runtime.get_preview_service()
        service.registry, service.router, service.sessions = (
            registry,
            PreviewRouter(registry),
            PreviewSessionManager(registry),
        )
        panels = PanelRegistry()
        fixtures = Path(__file__).parent / "panel-fixtures"
        for name in ("reader", "early", "later", "navigator", "table"):
            directory = Path(temporary) / f"browser.{name}"
            shutil.copytree(fixtures / name, directory)
            panels.register(
                parse_descriptor(
                    directory,
                    owner_kind=OwnerKind.PROJECT,
                    owner_name="browser-test",
                    registered_types={"BrowserText", "Composite", "DataFrame"},
                )[0]
            )
        runtime.get_preview_service().registry.install_panels(panels)
        router = APIRouter()
        @router.get("/__panel_test__/host", response_class=HTMLResponse)
        def host() -> str:
            html = (build / "e2e/helpers/panel-browser-host.html").read_text()
            return html.replace("__PANEL_BASE__", args.prefix).replace('src="/assets/', f'src="{args.prefix}/assets/')

        @router.get("/__panel_test__/health")
        def health() -> dict[str, bool]:
            return {"ready": True}

        app = create_app(guard=RecordingFakeGuardFactory() if args.replacement else None, routers=[router])
        app.state.runtime = runtime
        app.mount("/assets", StaticFiles(directory=build / "assets"))
        # Fixture runtime deliberately has no desktop/session startup side effects.
        # App middleware, guard dispatch, panel/read/token routes remain production.
        uvicorn.run(app, host="127.0.0.1", port=args.port, lifespan="off")


if __name__ == "__main__":
    main()
