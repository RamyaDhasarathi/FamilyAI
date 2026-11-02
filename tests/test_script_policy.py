"""The web app runs under `script-src 'self'`: no inline script, no inline handler, so an injected script cannot run.
(The founder's consoles it replaced on 29 Oct 2026 were held to the same rule.)"""
import re
from pathlib import Path

import pytest

from familyos.main import _SCRIPT_HOSTS, _csp_for

ROOT = Path(__file__).resolve().parent.parent
CONSOLES = {"app": "web/dist"}
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", re.I)
INLINE_HANDLER = re.compile(r"""\son(click|change|input|submit|load|error|keydown|keyup|focus|blur|mouseover)\s*=""", re.I)


@pytest.mark.parametrize("name,folder", CONSOLES.items())
def test_a_covered_console_has_no_inline_script_or_handler(name, folder):
    assert name in _SCRIPT_HOSTS
    if not (ROOT / folder / "index.html").is_file():
        pytest.skip(f"{folder} is not built in this checkout")
    for path in (ROOT / folder).glob("*"):
        if path.suffix not in (".html", ".js"):
            continue
        text = path.read_text()
        if path.suffix == ".html":
            assert not INLINE_SCRIPT.search(text), f"{path.name}: move the inline script into a file (scripts/externalize_scripts.py)"
        assert not INLINE_HANDLER.search(text), f"{path.name}: use addEventListener or data-* with a delegated listener, not an on*= attribute"


def test_the_policy_allows_only_our_files_and_the_known_host():
    csp = _csp_for("/app/")
    assert "script-src 'self';" in csp
    assert "'unsafe-inline'" not in csp and "'unsafe-eval'" not in csp
    assert "object-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert _csp_for("/") .startswith("script-src 'self';")


def test_paths_not_yet_covered_keep_the_frame_rule_only():
    for path in ("/v1/brief", "/redoc"):
        assert _csp_for(path) == "frame-ancestors 'none'"


def test_docs_are_under_the_script_policy():
    docs = _csp_for("/docs")
    assert docs.startswith("script-src 'self' https://cdn.jsdelivr.net;") and "'unsafe-inline'" not in docs


async def test_the_api_reference_is_served_without_an_inline_script_and_from_a_pinned_checked_copy(client):
    r = await client.get("/docs")
    assert r.status_code == 200
    assert not INLINE_SCRIPT.search(r.text), "Swagger's start-up script must be in /docs/init.js"
    assert 'src="/docs/init.js"' in r.text
    # Not the floating @5 of FastAPI's own page: one version, with its integrity hash.
    assert re.search(r"swagger-ui-dist@\d+\.\d+\.\d+/swagger-ui-bundle\.js\" integrity=\"sha384-", r.text)
    assert r.headers["content-security-policy"].startswith("script-src 'self' https://cdn.jsdelivr.net;")
    init = await client.get("/docs/init.js")
    assert init.status_code == 200 and "javascript" in init.headers["content-type"] and "SwaggerUIBundle" in init.text
    assert (await client.get("/openapi.json")).status_code == 200

