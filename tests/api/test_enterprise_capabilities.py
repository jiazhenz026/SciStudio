"""ADR-055 Spec 4 capability extensions (issue #2322).

The identity seam's capability declaration grows to the shared contract of
umbrella #2321: ``identity`` with an optional logout route, ``transfer`` as an
object, ``ai_chat_disabled``, and a dynamic ``update``. These tests cover:

* validation: every URL is a backend route path without the service prefix
  (a leading ``/``, not ``//``, no scheme, no whitespace, control characters or
  backslashes), and the download template carries exactly one ``{path}``;
* the ``transfer`` breaking change: ``False``/``None`` still mean off, ``True``
  is refused with a pointer at :class:`TransferCapability`;
* the served declaration: versioned, one key per capability that is on, for
  every capability present and absent, at the root mount and under
  ``/user/alice/scistudio``, and still script-safe;
* the default: nothing is injected when every capability is off;
* the declared route paths reach an edition's routes under the service prefix,
  which is how the frontend resolves them.

Route paths are neutral fixtures (``/api/test-edition/...``); this repository
implements no enterprise route.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from scistudio.api import app as app_module
from scistudio.api import spa
from scistudio.api.app import create_app
from scistudio.api.seam import Capabilities, IdentityCapability, TransferCapability, UpdateCapability
from tests.api.seam_contract import PREFIXED_MOUNT

MOUNTS = pytest.mark.parametrize("mount_prefix", ["", PREFIXED_MOUNT], ids=["root-mount", "prefixed-mount"])

LOGOUT_URL = "/api/test-edition/session/logout"
DOWNLOAD_TEMPLATE = "/api/test-edition/transfer/download?path={path}"
STATUS_URL = "/api/test-edition/update/status"
RESTART_URL = "/api/test-edition/update/restart"

IDENTITY = IdentityCapability(user="alice", logout_url=LOGOUT_URL)
TRANSFER = TransferCapability(inline_max_bytes=8 * 1024 * 1024, download_url_template=DOWNLOAD_TEMPLATE)
UPDATE = UpdateCapability(status_url=STATUS_URL, restart_url=RESTART_URL)

#: Every URL a route-path field must refuse. Each names a different way out of
#: "a route on this backend": no leading slash, another host, a scheme,
#: whitespace anywhere, control and invisible characters, the backslash
#: browsers read as a slash, and dot segments that climb out of the service
#: prefix once a browser normalizes them, encoded or not.
NOT_ROUTE_PATHS = [
    "/api/test-edition/../x",
    "/api/./x",
    "/../api/x",
    "/api/test-edition/%2e%2e/x",
    "/api/test-edition/%2E/x",
    "/api/test-edition/.%2E/x",
    "/api/%252e%252e/x",
    "/\ufeffapi/test-edition/x",
    "/api/test-edition/x\u200b",
    "/api/test-edition/x\u00ad",
    "/api/test-edition/x\u3000",
    "/api/test-edition/x\u00a0",
    "/api/test-edition/x\u1680",
    "/api/test-edition/x\x85",
    "/api/test-edition/x\x80",
    "",
    "api/test-edition/x",
    "//evil.example/x",
    "https://hub.example.org/hub/logout",
    "javascript:alert(1)",
    " /api/test-edition/x",
    "/api/test-edition/x ",
    "/api/test edition/x",
    "/api/test-edition/\nx",
    "/api/test-edition/\x7fx",
    "/api/test-edition/x\u2028",
    "/\\evil.example/x",
]


# ---------------------------------------------------------------------------
# Fixtures and helpers.
# ---------------------------------------------------------------------------


@pytest.fixture()
def edition_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated home and a built application shell for apps a test creates."""
    from scistudio.api import runtime as runtime_module

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("SCISTUDIO_ROOT_PATH", raising=False)
    spa_dir = tmp_path / "static"
    spa_dir.mkdir()
    (spa_dir / "index.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>',
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "_resolve_spa_static_dir", lambda: spa_dir)
    return spa_dir


def _declaration(shell: str) -> Any:
    match = re.search(r"window\.__SCISTUDIO_CAPABILITIES__ = (.*?);</script>", shell)
    assert match is not None, "the served page carries no capability declaration"
    return json.loads(match.group(1))


def _edition_router() -> APIRouter:
    """Stand-ins for an edition's routes at the declared route paths."""
    router = APIRouter()

    @router.post(LOGOUT_URL)
    async def logout() -> dict[str, str]:
        return {"location": "/hub/logout"}

    @router.get(STATUS_URL)
    async def status() -> dict[str, Any]:
        return {
            "running_version": "0.3.5",
            "installed_version": "0.3.6",
            "update_available": True,
            "runs_active": False,
        }

    @router.post(RESTART_URL)
    async def restart() -> dict[str, str]:
        return {"location": "/hub/spawn-pending/alice"}

    @router.get("/api/test-edition/transfer/download")
    async def download(path: str) -> dict[str, str]:
        return {"path": path}

    return router


# ---------------------------------------------------------------------------
# Validation.
# ---------------------------------------------------------------------------


def test_identity_logout_url_is_optional() -> None:
    identity = IdentityCapability(user="alice")
    assert identity.logout_url is None
    assert Capabilities(identity=identity).to_bootstrap() == {"version": 1, "identity": {"user": "alice"}}


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda url: IdentityCapability(user="alice", logout_url=url), id="identity.logout_url"),
        pytest.param(
            lambda url: TransferCapability(inline_max_bytes=1, download_url_template=f"{url}{{path}}"),
            id="transfer.download_url_template",
        ),
        pytest.param(lambda url: UpdateCapability(status_url=url, restart_url=RESTART_URL), id="update.status_url"),
        pytest.param(lambda url: UpdateCapability(status_url=STATUS_URL, restart_url=url), id="update.restart_url"),
    ],
)
@pytest.mark.parametrize("url", NOT_ROUTE_PATHS)
def test_every_capability_url_must_be_a_backend_route_path(build: Any, url: str) -> None:
    with pytest.raises(ValueError):
        build(url)


@pytest.mark.parametrize(
    "template",
    [
        "/api/test-edition/transfer/download",
        "/api/test-edition/transfer/download?path={path}&again={path}",
        "/api/test-edition/transfer/download?path={PATH}",
    ],
    ids=["no-marker", "two-markers", "wrong-marker"],
)
def test_download_template_needs_exactly_one_path_marker(template: str) -> None:
    with pytest.raises(ValueError, match=r"\{path\}"):
        TransferCapability(inline_max_bytes=1, download_url_template=template)


def test_download_template_may_place_the_path_in_the_route() -> None:
    template = "/api/test-edition/transfer/files/{path}"
    assert TransferCapability(inline_max_bytes=0, download_url_template=template).download_url_template == template


@pytest.mark.parametrize("value", [-1, True, 1.5, "10", None])
def test_inline_max_bytes_is_a_non_negative_integer(value: Any) -> None:
    with pytest.raises(ValueError):
        TransferCapability(inline_max_bytes=value, download_url_template=DOWNLOAD_TEMPLATE)


def test_transfer_false_and_none_both_mean_off() -> None:
    assert Capabilities(transfer=False) == Capabilities() == Capabilities(transfer=None)
    assert Capabilities(transfer=False).transfer is None
    assert Capabilities(transfer=False).any_enabled is False


def test_transfer_true_is_refused_with_a_pointer_at_the_new_shape() -> None:
    """The ADR-052 provisional break: ``transfer`` is an object now (CHANGELOG)."""
    with pytest.raises(TypeError, match="TransferCapability"):
        Capabilities(transfer=True)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"transfer": "yes"},
        {"transfer": {"inline_max_bytes": 1, "download_url_template": DOWNLOAD_TEMPLATE}},
        {"ai_chat_disabled": 1},
        {"ai_chat_disabled": "true"},
        {"update": {"status_url": STATUS_URL, "restart_url": RESTART_URL}},
    ],
)
def test_capabilities_reject_wrong_types(kwargs: dict[str, Any]) -> None:
    with pytest.raises(TypeError):
        Capabilities(**kwargs)


# ---------------------------------------------------------------------------
# The declaration, one capability at a time.
# ---------------------------------------------------------------------------

#: (capabilities, the keys the declaration carries besides ``version``). Each
#: case turns exactly one capability on, so the others are asserted absent.
CAPABILITY_CASES: dict[str, tuple[Capabilities, dict[str, Any]]] = {
    "identity": (
        Capabilities(identity=IDENTITY),
        {"identity": {"user": "alice", "logoutUrl": LOGOUT_URL}},
    ),
    "identity-without-logout": (
        Capabilities(identity=IdentityCapability(user="alice")),
        {"identity": {"user": "alice"}},
    ),
    "transfer": (
        Capabilities(transfer=TRANSFER),
        {"transfer": {"inlineMaxBytes": 8 * 1024 * 1024, "downloadUrlTemplate": DOWNLOAD_TEMPLATE}},
    ),
    "ai_chat_disabled": (
        Capabilities(ai_chat_disabled=True),
        {"aiChatDisabled": True},
    ),
    "update": (
        Capabilities(update=UPDATE),
        {"update": {"statusUrl": STATUS_URL, "restartUrl": RESTART_URL}},
    ),
}
CASE_IDS = list(CAPABILITY_CASES)


@pytest.mark.parametrize("case", CASE_IDS)
def test_each_capability_alone_turns_the_declaration_on(case: str) -> None:
    capabilities, expected = CAPABILITY_CASES[case]
    assert capabilities.any_enabled is True
    assert capabilities.to_bootstrap() == {"version": 1, **expected}


@MOUNTS
@pytest.mark.parametrize("case", CASE_IDS)
def test_each_capability_reaches_the_served_page_and_nothing_else_does(
    edition_env: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str, case: str
) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    capabilities, expected = CAPABILITY_CASES[case]
    app = create_app(capabilities=capabilities)
    with TestClient(app, root_path=mount_prefix) as client:
        shell = client.get(f"{mount_prefix}/projects/deep/route").text
    # Exact equality: every capability this case does not turn on is absent,
    # and the route paths are declared as given, without the mount prefix.
    assert _declaration(shell) == {"version": 1, **expected}


@MOUNTS
def test_every_capability_together(edition_env: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    app = create_app(
        capabilities=Capabilities(identity=IDENTITY, transfer=TRANSFER, ai_chat_disabled=True, update=UPDATE)
    )
    with TestClient(app, root_path=mount_prefix) as client:
        shell = client.get(f"{mount_prefix}/").text
    expected: dict[str, Any] = {"version": 1}
    for name in ("identity", "transfer", "ai_chat_disabled", "update"):
        expected.update(CAPABILITY_CASES[name][1])
    assert _declaration(shell) == expected


@MOUNTS
@pytest.mark.parametrize(
    "capabilities",
    [None, Capabilities(), Capabilities(transfer=False), Capabilities(identity=None, transfer=None, update=None)],
    ids=["omitted", "default", "transfer-false", "explicit-none"],
)
def test_nothing_is_injected_when_every_capability_is_off(
    edition_env: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str, capabilities: Capabilities | None
) -> None:
    """Default unchanged: the open-source shell carries no declaration."""
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    app = create_app() if capabilities is None else create_app(capabilities=capabilities)
    with TestClient(app, root_path=mount_prefix) as client:
        shell = client.get(f"{mount_prefix}/").text
    assert "__SCISTUDIO_CAPABILITIES__" not in shell
    assert "__SCISTUDIO_WEBMCP_TOKEN__" in shell


def test_route_paths_in_the_declaration_are_script_safe(edition_env: Path) -> None:
    template = "/api/test-edition/</script><script>alert(1)</script>&x={path}"
    app = create_app(
        capabilities=Capabilities(transfer=TransferCapability(inline_max_bytes=1, download_url_template=template))
    )
    with TestClient(app) as client:
        shell = client.get("/").text
    assert "<script>alert(1)" not in shell
    assert shell.count("</script>") == 1, "only the bootstrap script element closes"
    assert _declaration(shell)["transfer"]["downloadUrlTemplate"] == template


# ---------------------------------------------------------------------------
# The declared route paths reach the edition's routes under the service prefix.
# ---------------------------------------------------------------------------


@MOUNTS
def test_declared_route_paths_resolve_under_the_service_prefix(
    edition_env: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str
) -> None:
    """The frontend prefixes each declared path exactly as it prefixes API calls."""
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    app = create_app(
        capabilities=Capabilities(identity=IDENTITY, transfer=TRANSFER, update=UPDATE),
        routers=[_edition_router()],
    )
    with TestClient(app, root_path=mount_prefix) as client:
        declared = _declaration(client.get(f"{mount_prefix}/").text)

        logout = client.post(f"{mount_prefix}{declared['identity']['logoutUrl']}")
        assert logout.status_code == 200
        assert logout.json() == {"location": "/hub/logout"}

        status = client.get(f"{mount_prefix}{declared['update']['statusUrl']}").json()
        assert set(status) == {"running_version", "installed_version", "update_available", "runs_active"}
        assert client.post(f"{mount_prefix}{declared['update']['restartUrl']}").json()["location"]

        relative_path = "data/raw/scan 1 & 2.tif"
        template = declared["transfer"]["downloadUrlTemplate"]
        download_url = template.replace("{path}", quote(relative_path, safe=""))
        assert client.get(f"{mount_prefix}{download_url}").json() == {"path": relative_path}


def test_the_base_path_and_token_bootstrap_is_script_safe(tmp_path: Path) -> None:
    """An operator-configured prefix cannot close the bootstrap script (no-context audit P3-2)."""
    index = tmp_path / "index.html"
    index.write_text("<!doctype html><html><head></head><body></body></html>", encoding="utf-8")
    prefix = "/user/</script><script>alert(1)</script>"
    response = spa._templated_index_response(str(index), prefix, "token</script>")
    shell = bytes(response.body).decode("utf-8")
    assert "<script>alert(1)" not in shell
    assert shell.count("</script>") == 1, "only the bootstrap script element closes"
    base = re.search(r"window\.__SCISTUDIO_BASE_PATH__ = (.*?);", shell)
    token = re.search(r"window\.__SCISTUDIO_WEBMCP_TOKEN__ = (.*?);", shell)
    assert base is not None and json.loads(base.group(1)) == prefix
    assert token is not None and json.loads(token.group(1)) == "token</script>"
