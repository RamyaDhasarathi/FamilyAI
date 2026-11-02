"""One web app, one address: /app is the web app (web/, built into web/dist; it replaced the founder's consoles on
29 Oct 2026, their copy is outside the repository). It routes its own addresses, and is served fresh, so a shipped
change is seen."""
import pytest
from fastapi.testclient import TestClient

from familyos import main as main_module
from familyos.main import create_app

needs_build = pytest.mark.skipif(not (main_module.WEB / "index.html").is_file(),
                                 reason="web/dist is not built in this checkout (cd web && FAMILYOS_WEB_BASE=/app/ npm run build)")


@needs_build
async def test_the_web_app_is_served_at_its_address_and_never_cached(family):
    r = await family.client.get("/app/")
    assert r.status_code == 200, r.text[:200]
    assert '<div id="root">' in r.text and 'src="/app/assets/' in r.text
    assert r.headers.get("cache-control") == "no-cache, must-revalidate"


@needs_build
async def test_an_address_the_web_app_routes_itself_answers_its_page(family):
    page = (await family.client.get("/app/")).text
    for path in ("/app/agents/finance", "/app/family/m_1/details/health", "/app/login"):
        r = await family.client.get(path)
        assert r.status_code == 200 and r.text == page, path


@needs_build
async def test_a_missing_file_is_still_not_found(family):
    assert (await family.client.get("/app/assets/no-such-file.js")).status_code == 404


@needs_build
def test_the_front_page_sends_people_into_the_web_app():
    r = TestClient(create_app(with_lifespan=False)).get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/app/"


@needs_build
@pytest.mark.parametrize("path", ["/classic/", "/orbit/", "/cockpit/", "/family-agent/", "/home/", "/kid/", "/pay/", "/guide/"])
async def test_the_founders_other_consoles_are_gone(family, path):
    assert (await family.client.get(path)).status_code == 404
