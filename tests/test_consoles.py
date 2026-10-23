"""Three consoles, three addresses, one API: /app (the console), /classic
(as it was before the constellation redesign) and /orbit (the Master UI/UX
spec's ambient home). Each is served fresh, so a shipped change is seen."""
import pytest

from familyos import main as main_module


@pytest.mark.parametrize("path,directory", [("/app/", "web"), ("/classic/", "web_classic"), ("/orbit/", "web_orbit")])
async def test_each_console_is_served_at_its_own_address_and_never_cached(family, path, directory):
    if not (main_module.WEB.parent / directory / "index.html").is_file():
        pytest.skip(f"{directory}/index.html is not in this checkout")
    r = await family.client.get(path)
    assert r.status_code == 200, r.text[:200]
    assert "<" in r.text and r.headers.get("cache-control") == "no-cache, must-revalidate"
