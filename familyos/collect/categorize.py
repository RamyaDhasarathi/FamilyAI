"""Qwen sorts what the phone sent (ported from the collector app's categorize.js and deviceDataWorker.js, decided 2 Nov
2026): each SMS and notification gets a category (bank_debit, otp, message, …), a one-line summary and, for money, the
amount, merchant and account -- on this Mac's own Qwen3.5 (the model server's /categorize), no cloud model. One member's
items per batch (never mixed in a prompt), newest first, eight at a time, in the background after the phone sends them.
An OTP's summary never shows the code (the full text is still kept). A batch Qwen answers unusably counts a try for each
item; after three, an item stays as it is. The server down is not the items' fault: no try is counted.

It shares the one model with the decision layer and the phone agent (decide._model_lock): one question at a time.
"""
from __future__ import annotations

import asyncio
import logging
import re

from familyos.collect import decide, store
from familyos.settings import settings

logger = logging.getLogger(__name__)

MAX_TRIES = 3
BATCH = 8
KINDS = ("sms", "notifications")


class Unavailable(RuntimeError):
    pass


def _item(kind: str, row: dict) -> dict:
    if kind == "notifications":
        return {"id": row["id"][:40], "kind": "notification", "from": row.get("app_label") or row.get("package") or "",
                "text": " — ".join(t for t in (row.get("title"), row.get("text")) if t)}
    return {"id": row["id"][:40], "kind": "sms", "from": row.get("sender") or "", "text": row.get("body") or ""}


async def _ask(items: list[dict]) -> list[dict]:
    import httpx
    try:
        async with decide._model_lock(), httpx.AsyncClient(timeout=settings.collect_model_timeout_s) as client:
            r = await client.post(settings.collect_model_url.rstrip("/") + "/categorize", json={"items": items})
    except httpx.TransportError as exc:
        raise Unavailable(str(exc)) from exc
    body = r.json() if r.content else {}
    if r.status_code >= 400 or not body.get("success"):
        raise RuntimeError(f"categorize: {(body.get('error') or {}).get('message') or r.status_code}")
    return [x for x in body.get("items") or [] if isinstance(x, dict)]


async def run(email: str) -> int:
    """Sort what is not sorted yet for one member; how many were sorted."""
    done = 0
    for kind in KINDS:
        while True:
            rows = store.uncategorized(email, kind, BATCH, MAX_TRIES)
            if not rows:
                break
            by_short = {r["id"][:40]: r["id"] for r in rows}
            try:
                answers = await _ask([_item(kind, r) for r in rows])
            except Unavailable:
                logger.info("categorize: the model server is not reachable; later")
                return done
            except Exception as exc:  # noqa: BLE001 -- an unusable answer counts a try for each item
                logger.warning("categorize: %s", exc)
                store.count_try(email, kind, [r["id"] for r in rows])
                continue
            answered = set()
            for a in answers:
                full = by_short.get(str(a.get("id")))
                if not full:
                    continue
                category = str(a.get("category") or "other")
                summary = str(a.get("summary") or "") or None
                if summary and category == "otp":
                    summary = re.sub(r"\b\d{4,8}\b", "••••", summary)
                store.set_category(email, kind, full, category, summary, a.get("extracted") if isinstance(a.get("extracted"), dict) else None)
                answered.add(full)
                done += 1
            missed = [r["id"] for r in rows if r["id"] not in answered]
            if missed:
                store.count_try(email, kind, missed)
    return done


_running: dict[str, asyncio.Task] = {}


def start(email: str) -> bool:
    """Sort in the background (after the phone sent something); False when it is already going for this member."""
    key = (email or "").strip().lower()
    going = _running.get(key)
    if going and not going.done():
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    task = loop.create_task(run(key))
    _running[key] = task
    task.add_done_callback(lambda t: t.cancelled() or not t.exception() or logger.warning("categorize failed: %s", t.exception()))
    return True
