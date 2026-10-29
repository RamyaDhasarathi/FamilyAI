"""Four consoles, four addresses, one API: /app (the console), /classic
(as it was before the constellation redesign), /orbit (the Master UI/UX
spec's ambient home) and /cockpit (the web redesign's decision queue). Each is served fresh, so a shipped change is seen."""
import pytest

from familyos import main as main_module


@pytest.mark.parametrize("path,directory", [("/app/", "web"), ("/classic/", "web_classic"), ("/orbit/", "web_orbit"), ("/cockpit/", "web_cockpit")])
async def test_each_console_is_served_at_its_own_address_and_never_cached(family, path, directory):
    if not (main_module.WEB.parent / directory / "index.html").is_file():
        pytest.skip(f"{directory}/index.html is not in this checkout")
    r = await family.client.get(path)
    assert r.status_code == 200, r.text[:200]
    assert "<" in r.text and r.headers.get("cache-control") == "no-cache, must-revalidate"


def test_the_front_page_is_the_welcome_page_and_sends_people_into_the_console():
    from fastapi.testclient import TestClient

    from familyos.main import create_app
    r = TestClient(create_app(with_lifespan=False)).get("/", follow_redirects=False)
    assert r.status_code == 200 and "FamilyOS" in r.text
    assert '<script src="/home/boot.js">' in r.text and "data-start" in r.text and "data-signin" in r.text
    boot = TestClient(create_app(with_lifespan=False)).get("/home/boot.js")
    assert "window.FOS_CONSOLE = '/app/'" in boot.text          # moved out of the page so the console can forbid inline scripts
    assert "Cache-Control" in r.headers and "no-cache" in r.headers["Cache-Control"]


def test_the_first_run_screens_load_before_the_console_script_where_the_console_runs():
    """render() asks firstRunDue() by name, so the file that defines it has to be on the page ahead of app.js, in /app and in /cockpit."""
    web = main_module.WEB.parent
    for page, app in (("web/index.html", '<script src="app.js">'), ("web_cockpit/index.html", '<script src="/app/app.js">')):
        html = (web / page).read_text()
        assert "firstrun.js" in html and html.index("firstrun.js") < html.index(app), page
    assert "async function firstRunDue" in (web / "web" / "firstrun.js").read_text()
    assert "firstRunDue" in (web / "web" / "app.js").read_text()
