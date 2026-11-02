"""A browser on this machine with Steel's contract: a sealed session's
cookies go in, a page is driven, what the browser holds comes back out,
and the release leaves nothing behind."""
import asyncio
import http.server
import threading

import pytest

from familyos.execution import agent, local, runbooks

pytestmark = pytest.mark.skipif(not local.available(), reason="Playwright's Chromium is not installed here")


class _Echo(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        cookie = self.headers.get("Cookie", "none")
        agent = self.headers.get("User-Agent", "none")
        body = (f"<html><body><h1>Hello</h1><p id='c'>cookie: {cookie}</p><p id='ua'>agent: {agent}</p><button>Add</button>"
                "<script>localStorage.setItem('seen', 'yes')</script></body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quiet
        pass


@pytest.fixture
def site():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Echo)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


def test_the_token_rides_on_the_real_user_agent_once():
    chrome = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/145.0 Safari/537.36"
    said = agent.announce(chrome)
    assert said.startswith("Mozilla/5.0 (Macintosh)") and "HeadlessChrome" not in said and said.endswith(agent.TOKEN)
    assert agent.announce(said) == said and agent.is_announced(said) and not agent.is_announced(chrome)
    assert agent.announce(None) is None


async def test_the_local_browser_says_what_it_is_to_the_site(site):
    """A sitting and a run both carry the token on the browser's own user
    agent: a site can tell the household's agent from a person without
    guessing from the address, and the string tells one story."""
    browser = local.LocalBrowser()
    session = await browser.open_with({"cookies": []}, user_agent=None, minutes=2)
    assert agent.is_announced(session["user_agent"]) and "HeadlessChrome" not in session["user_agent"]
    driver = runbooks.PlaywrightDriver(session["websocket_url"], session.get("storage"))
    try:
        await driver.goto(site)
        text = await driver.text()
        assert "agent: Mozilla/5.0" in text and agent.TOKEN in text and "HeadlessChrome" not in text
    finally:
        await driver.close()
        await browser.release(session["session_id"])


async def test_a_sealed_session_goes_in_and_what_the_browser_holds_comes_out(site):
    browser = local.LocalBrowser()
    session = await browser.open_with({"cookies": [{"name": "sid", "value": "abc123", "domain": "127.0.0.1", "path": "/"}]}, user_agent=None, minutes=2)
    assert session["session_id"].startswith("local-") and session["websocket_url"].startswith("http://127.0.0.1:") and session["live_url"] is None
    driver = runbooks.PlaywrightDriver(session["websocket_url"], session.get("storage"))
    try:
        await driver.goto(site)
        text = await driver.text()
        assert "Hello" in text and "cookie: sid=abc123" in text
        assert (await driver.url()).startswith(site)
        assert isinstance(await driver.screenshot(), bytes)
        assert [b["index"] for b in await driver.buttons("Add")] == [0]
        held = await browser.context(session["session_id"])
        assert any(c["name"] == "sid" for c in held["cookies"])
        assert held["localStorage"].get(site.rstrip("/"), {}).get("seen") == "yes"
    finally:
        await driver.close()
        await browser.release(session["session_id"])
    assert browser._sessions == {}
    # Released means gone: the next read says so.
    with pytest.raises(Exception, match="gone"):
        await browser.context(session["session_id"])
    await asyncio.sleep(0)
