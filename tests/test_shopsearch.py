"""Product options for a suggestion: off by default, live, never stored, names refused, links exactly as returned."""
from familyos import shopsearch

SAMPLE = {"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": {"products": [{
    "id": "p1", "title": "Board game", "rating": {"value": 4.6, "scale_min": 1, "scale_max": 5, "count": 120},
    "variants": [{"id": "v1", "title": "Board game, large", "url": "https://shop.example/products/game?variant=1&_gsid=abc&utm_source=shopify",
                  "price": {"amount": 129900, "currency": "INR"}, "availability": {"available": True},
                  "options": [{"name": "Size", "label": "Large"}], "media": [{"type": "image", "url": "https://cdn.example/g.jpg"}],
                  "seller": {"name": "Example Games", "domain": "example.myshopify.com"}}]}], "messages": ["Prices may change."]}}}


async def _on(family):
    r = await family.client.put("/v1/household/shop-search", headers=family.h("amma"), json={"enabled": True})
    assert r.status_code == 200, r.text


def _fake(monkeypatch, seen=None, fail=False):
    async def post(query, country, currency, limit):
        if seen is not None:
            seen.append((query, country, currency, limit))
        if fail:
            import httpx
            raise httpx.ConnectError("down")
        return SAMPLE
    monkeypatch.setattr(shopsearch, "_post", post)


async def test_it_is_off_until_a_guardian_switches_it_on(family, monkeypatch):
    _fake(monkeypatch)
    assert (await family.client.get("/v1/shop/status", headers=family.h("amma"))).json() == {"enabled": False}
    assert (await family.client.get("/v1/shop/search?q=board game", headers=family.h("amma"))).status_code == 403
    assert (await family.client.put("/v1/household/shop-search", headers=family.h("paati"), json={"enabled": True})).status_code == 403


async def test_results_carry_what_the_service_asks_us_to_show_and_the_link_is_untouched(family, monkeypatch):
    seen = []
    _fake(monkeypatch, seen)
    await _on(family)
    r = (await family.client.get("/v1/shop/search?q=board game for a 7 year old", headers=family.h("amma"))).json()
    p = r["products"][0]
    assert p["url"] == "https://shop.example/products/game?variant=1&_gsid=abc&utm_source=shopify"
    assert p["seller"]["name"] == "Example Games" and p["price"] == {"amount": 1299.0, "currency": "INR"}
    assert p["rating"] == {"value": 4.6, "scale_max": 5, "count": 120} and p["options"] == "Size: Large"
    assert r["messages"] == ["Prices may change."] and "not kept" in r["note"]
    assert seen[0] == ("board game for a 7 year old India", "IN", "INR", 18)      # the country in the words, and more asked for than shown


async def test_a_household_members_name_never_leaves(family, monkeypatch):
    seen = []
    _fake(monkeypatch, seen)
    await _on(family)
    r = await family.client.get(f"/v1/shop/search?q=gift for {family.younger['display_name'].split()[0]}", headers=family.h("amma"))
    assert r.status_code in (400, 422) and "names out" in r.text and seen == []


async def test_a_suggestion_is_searched_as_the_thing_not_the_person(family, monkeypatch):
    seen = []
    _fake(monkeypatch, seen)
    await _on(family)
    await family.client.get("/v1/shop/search?suggestion=abc-123:gift", headers=family.h("amma"))
    assert seen[0][0] == "birthday gift India"


async def test_nothing_is_stored_and_a_failure_is_one_plain_line(family, database, monkeypatch):
    _fake(monkeypatch, fail=True)
    await _on(family)
    r = (await family.client.get("/v1/shop/search?q=board game", headers=family.h("amma"))).json()
    assert r["products"] == [] and "could not be reached" in r["error"]
    _fake(monkeypatch)
    before = await database.fetchval("SELECT count(*) FROM audit_events WHERE action = 'shop.searched' AND detail::text LIKE '%board%'")
    await family.client.get("/v1/shop/search?q=board game", headers=family.h("amma"))
    assert before == 0 and await database.fetchval("SELECT count(*) FROM audit_events WHERE action = 'shop.searched' AND detail::text LIKE '%board%'") == 0   # counts only, never the words


def _prod(i, currency):
    return {"id": f"p{i}", "title": f"Gift {i}", "variants": [{"id": f"v{i}", "title": f"Gift {i}", "url": f"https://shop.example/p/{i}", "price": {"amount": 50000, "currency": currency},
                                                                "seller": {"name": "S", "domain": "s.example"}}]}


async def test_local_sellers_come_first_and_others_only_fill_a_thin_result(family, monkeypatch):
    mixed = {"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": {"products": [_prod(1, "AUD"), _prod(2, "INR"), _prod(3, "NZD"), _prod(4, "INR"), _prod(5, "INR"), _prod(6, "USD")]}}}
    thin = {"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": {"products": [_prod(1, "AUD"), _prod(2, "INR"), _prod(3, "NZD")]}}}
    await _on(family)
    for payload, titles in ((mixed, ["Gift 2", "Gift 4", "Gift 5"]), (thin, ["Gift 2", "Gift 1", "Gift 3"])):
        async def post(query, country, currency, limit, payload=payload):
            return payload
        monkeypatch.setattr(shopsearch, "_post", post)
        r = (await family.client.get("/v1/shop/search?q=gift", headers=family.h("amma"))).json()
        assert [x["title"] for x in r["products"]] == titles
        assert [x["local"] for x in r["products"]] == [x["price"]["currency"] == "INR" for x in r["products"]]
