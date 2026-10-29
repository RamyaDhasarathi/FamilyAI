"""The consoles run under `script-src 'self'`: no inline script, no inline handler, so an injected script cannot run."""
import re
from pathlib import Path

import pytest

from familyos.main import _SCRIPT_HOSTS, _csp_for

ROOT = Path(__file__).resolve().parent.parent / "familyos"
CONSOLES = {"app": "web", "classic": "web_classic", "orbit": "web_orbit", "cockpit": "web_cockpit",
            "family-agent": "web_family_agent", "home": "web_home", "kid": "web_kid", "guide": "web_guide", "pay": "web_pay/public"}
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", re.I)
INLINE_HANDLER = re.compile(r"""\son(click|change|input|submit|load|error|keydown|keyup|focus|blur|mouseover)\s*=""", re.I)


@pytest.mark.parametrize("name,folder", CONSOLES.items())
def test_a_covered_console_has_no_inline_script_or_handler(name, folder):
    assert name in _SCRIPT_HOSTS
    for path in (ROOT / folder).glob("*"):
        if path.suffix not in (".html", ".js"):
            continue
        text = path.read_text()
        if path.suffix == ".html":
            assert not INLINE_SCRIPT.search(text), f"{path.name}: move the inline script into a file (scripts/externalize_scripts.py)"
        assert not INLINE_HANDLER.search(text), f"{path.name}: use addEventListener or data-* with a delegated listener, not an on*= attribute"


def test_the_policy_allows_only_our_files_and_the_known_host():
    csp = _csp_for("/app/")
    assert "script-src 'self' https://cdnjs.cloudflare.com;" in csp
    assert "'unsafe-inline'" not in csp and "'unsafe-eval'" not in csp
    assert "object-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert _csp_for("/") .startswith("script-src 'self';")


def test_paths_not_yet_covered_keep_the_frame_rule_only():
    for path in ("/v1/brief", "/redoc"):
        assert _csp_for(path) == "frame-ancestors 'none'"


def test_pay_and_docs_are_under_the_script_policy():
    pay = _csp_for("/pay/")
    assert pay.startswith("script-src 'self';") and "'unsafe-inline'" not in pay and "'unsafe-eval'" not in pay
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


async def test_the_pay_page_is_a_bundle_with_no_inline_script(client):
    r = await client.get("/pay/")
    assert r.status_code == 200 and not INLINE_SCRIPT.search(r.text) and 'src="bundle.js"' in r.text
    assert r.headers["content-security-policy"].startswith("script-src 'self';")
