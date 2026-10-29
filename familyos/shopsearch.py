"""Product options for a suggestion, searched live in Shopify's catalogue (Shop MCP, https://shop.dev).

A suggestion ("a gift for Lily", "eggs are running low") can show real products, each linking to the seller. It stays on the
noticing side of the line: nothing is carted, nothing is bought, no card is involved. The household's guardian switches it on.

Rules we keep because the service's own usage rules and our own principles say so:
- Results are fetched when a person asks and never stored (the usage rules prohibit caching results and re-hosting merchant
  images): nothing here touches the database but one audit row that counts results, and images are the seller's own URLs.
- A product links to its variant's url exactly as returned, with every query parameter; the seller, selected options, price with
  its currency, the rating with its scale and count, and every warning the service sends are shown with it.
- What leaves the server is the words typed and the household's country and currency, nothing else. A query that contains the
  first name of anyone in the household is refused, so a child's name never reaches a shop catalogue.
"""
from __future__ import annotations

import logging
import re

import httpx

from familyos import audit
from familyos.db import pool
from familyos.identity import Invalid, NotAllowed, Principal

logger = logging.getLogger(__name__)

URL = "https://mcp.shop.com/"
PROTOCOL = "2026-07-28"
TIMEOUT = 12.0
MAX_QUERY = 120

# What a suggestion kind is searched as: the thing, never the person.
KIND_QUERY = {"gift": "birthday gift", "occasion": "gift", "kit": "costume", "exam": "revision notes", "outing": "snack box", "travel": "travel packing organiser"}


# The catalogue's country and currency are soft hints (its own schema says "soft relevance/localization"): asked for India it still
# returned mostly Australian sellers (14 Oct 2026). Naming the country in the words, and keeping sellers priced in the
# household's currency first, brought it to 19 of 20 in rupees. A country's name is not personal.
COUNTRY_NAMES = {"IN": "India", "AE": "UAE", "US": "USA", "GB": "UK", "AU": "Australia", "CA": "Canada", "SG": "Singapore", "NZ": "New Zealand",
                 "DE": "Germany", "FR": "France", "SA": "Saudi Arabia", "QA": "Qatar", "KW": "Kuwait", "OM": "Oman", "BH": "Bahrain", "MY": "Malaysia"}
FETCH_FACTOR = 3        # ask for more than shown, so there is something local to keep
MIN_LOCAL = 3           # fewer local results than this and others are added, marked


def query_for(suggestion_key: str) -> str | None:
    return KIND_QUERY.get((suggestion_key or "").rsplit(":", 1)[-1])


async def enabled(household_id) -> bool:
    return bool(await pool().fetchval("SELECT shop_search_enabled FROM households WHERE id = $1", household_id))


async def set_enabled(p: Principal, on: bool) -> dict:
    if not p.is_guardian:
        raise NotAllowed("only a guardian switches product search on")
    await pool().execute("UPDATE households SET shop_search_enabled = $2 WHERE id = $1", p.household_id, on)
    await audit.record(p.household_id, "household.shop_search_set", actor_member_id=p.member_id, detail={"enabled": on})
    return {"enabled": on}


async def _post(query: str, country: str, currency: str, limit: int) -> dict:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "_meta": {"io.modelcontextprotocol/protocolVersion": PROTOCOL, "io.modelcontextprotocol/clientCapabilities": {}},
        "name": "search_catalog",
        "arguments": {"catalog": {"query": query, "context": {"address_country": country, "currency": currency}, "pagination": {"limit": limit}}}}}
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": PROTOCOL,
               "Mcp-Method": "tools/call", "Mcp-Name": "search_catalog"}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(URL, json=body, headers=headers)
        r.raise_for_status()
        return r.json()


def _major(minor: int | float, currency: str) -> float:
    zero = {"JPY", "KRW", "VND", "CLP", "ISK"}
    three = {"KWD", "BHD", "OMR", "JOD", "TND"}
    return round(minor / (1 if currency in zero else 1000 if currency in three else 100), 3 if currency in three else 2)


def shape(result: dict) -> dict:
    """The fields a person needs, exactly as the service gave them where it asked for exactness (the link)."""
    res = result.get("result") or {}
    sc = res.get("structuredContent")
    if sc is None and res.get("content"):
        import json
        try:
            sc = json.loads(res["content"][0]["text"])
        except (ValueError, KeyError, IndexError):
            sc = {}
    sc = sc or {}
    out = []
    for p in sc.get("products", []):
        v = (p.get("variants") or [{}])[0]
        price = v.get("price") or (p.get("price_range") or {}).get("min") or {}
        cur = price.get("currency")
        rating = p.get("rating") or v.get("rating")
        media = (v.get("media") or p.get("media") or [{}])[0]
        out.append({
            "title": v.get("title") or p.get("title"),
            "seller": {"name": (v.get("seller") or {}).get("name"), "domain": (v.get("seller") or {}).get("domain")},
            "price": {"amount": _major(price["amount"], cur), "currency": cur} if price.get("amount") is not None and cur else None,
            "url": v.get("url"),                                   # exactly as returned, every query parameter kept
            "image_url": media.get("url"),                         # the seller's own address, never re-hosted
            "rating": {"value": rating["value"], "scale_max": rating.get("scale_max"), "count": rating.get("count")} if rating and "value" in rating else None,
            "options": ", ".join(f"{o.get('name')}: {o.get('label')}" for o in v.get("options", []) if o.get("label")),
            "available": (v.get("availability") or {}).get("available"),
        })
    return {"products": [x for x in out if x["url"]], "messages": [m if isinstance(m, str) else (m.get("text") or m.get("content") or str(m)) for m in sc.get("messages", [])]}


def localise(shaped: dict, currency: str, want: int) -> dict:
    """Sellers priced in the household's currency first. Others only if too few are local, and marked so the page can say to check delivery."""
    products = shaped["products"]
    for x in products:
        x["local"] = bool(x["price"]) and x["price"]["currency"] == currency
    local = [x for x in products if x["local"]]
    others = [x for x in products if not x["local"]]
    kept = local[:want] if len(local) >= MIN_LOCAL else (local + others)[:want]
    return {**shaped, "products": kept}


async def search(p: Principal, query: str, limit: int = 6) -> dict:
    if p.role == "child":
        raise NotAllowed("not for children")
    if not await enabled(p.household_id):
        raise NotAllowed("product search is off; a guardian can switch it on")
    q = " ".join((query or "").split())[:MAX_QUERY]
    if len(q) < 2:
        raise Invalid("say what to look for")
    names = {w.lower() for r in await pool().fetch("SELECT display_name FROM members WHERE household_id = $1", p.household_id) for w in re.findall(r"[^\W\d_]{3,}", r["display_name"])}
    if any(w in names for w in re.findall(r"[^\W\d_]{3,}", q.lower())):
        raise Invalid("leave names out: this is sent to a shop catalogue. Say what it is, for example “board game for a 7 year old”.")
    h = await pool().fetchrow("SELECT country, currency FROM households WHERE id = $1", p.household_id)
    country, currency = (h["country"] or "IN").strip().upper()[:2], (h["currency"] or "INR").strip().upper()
    try:
        want = max(1, min(limit, 10))
        place = COUNTRY_NAMES.get(country)
        sent = f"{q} {place}" if place and place.lower() not in q.lower() else q
        shaped = localise(shape(await _post(sent, country, currency, min(want * FETCH_FACTOR, 30))), currency, want)
    except (httpx.HTTPError, ValueError):
        logger.warning("shop search failed", exc_info=True)
        return {"query": q, "products": [], "messages": [], "error": "The shop catalogue could not be reached just now."}
    await audit.record(p.household_id, "shop.searched", actor_member_id=p.member_id, detail={"results": len(shaped["products"])})
    return {"query": q, **shaped, "error": None, "note": "Fetched just now and not kept. Prices and stock change; check the seller's page."}
