"""A place name for a location the phone sent (ported from the collector app's geocode.js, decided 2 Nov 2026): reverse
geocoding by Nominatim (OpenStreetMap), free and keyless, at most one request a second as its usage policy asks, with a
User-Agent naming the app. The suburb, neighbourhood, village, town, city or county, else the full display name. In the
background after the phone sends a location; a fix it cannot name is tried three times at most.
"""
from __future__ import annotations

import asyncio
import logging

from familyos.collect import store

logger = logging.getLogger(__name__)

URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "FamilyOS-collect/0.2 (local family assistant)"
MAX_TRIES = 3
BATCH = 20


async def reverse(lat: float, lon: float) -> str | None:
    import httpx
    async with httpx.AsyncClient(timeout=8, headers={"User-Agent": USER_AGENT}) as client:
        r = await client.get(URL, params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 14, "addressdetails": 1})
    r.raise_for_status()
    data = r.json()
    a = data.get("address") or {}
    return (a.get("suburb") or a.get("neighbourhood") or a.get("village") or a.get("town") or a.get("city")
            or a.get("county") or data.get("display_name") or None)


async def run(email: str) -> int:
    named = 0
    for row in store.unplaced(email, BATCH, MAX_TRIES):
        try:
            place = await reverse(row["lat"], row["lon"])
        except Exception as exc:  # noqa: BLE001 -- counted as a try; the fix stays as coordinates
            logger.info("geocode: %s", exc)
            place = None
        store.set_place(email, row["id"], place)
        named += bool(place)
        await asyncio.sleep(1.1)                 # Nominatim: one request a second
    return named


_running: dict[str, asyncio.Task] = {}


def start(email: str) -> bool:
    key = (email or "").strip().lower()
    going = _running.get(key)
    if going and not going.done():
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    _running[key] = loop.create_task(run(key))
    return True
