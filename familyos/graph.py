"""The household as a graph of what touches what: people, notices, dates, documents, warranties, medicines, shops and clinics.

This is a projection, not a store. Nothing is written: each call builds the graph from the tables that already hold the facts, as the
signed-in person may see them, so it can be thrown away and rebuilt, and an erasure removes it along with its sources. Every edge
carries the notice it came from, and an edge without one is only allowed where the fact is the family's own entry (a warranty
somebody typed in). Visibility is the same as everywhere else: a private notice's edges are not in another adult's graph, and a child
is a node only with active consent.

The questions it answers: what does this affect, everything about this thing, who is this person's life made of, and (later) what
patterns run through it. It is deliberately small: a family has a few thousand nodes, so it is built in memory per request.
"""
from __future__ import annotations

import re
import uuid
from collections import deque

from familyos import clock, consent, grants
from familyos.artifacts import VISIBLE_TO_MEMBER
from familyos.db import pool
from familyos.identity import Invalid, NotFound, Principal

MAX_DEPTH = 2
MAX_NODES = 60
PHRASE = {"from": "comes from", "about": "is about", "held_by": "is held by", "issued_by": "was issued by", "bought_at": "was bought at",
          "for": "is for", "prescribed_at": "was prescribed at"}
TYPES = ("person", "artifact", "obligation", "document", "warranty", "medication", "org")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60]


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self._adj: dict[str, list[dict]] = {}

    def node(self, ref: str, label: str, **extra) -> str:
        self.nodes.setdefault(ref, {"ref": ref, "type": ref.split(":", 1)[0], "label": (label or "").strip()[:160] or ref, **extra})
        return ref

    def edge(self, src: str, rel: str, dst: str, artifact_id=None, quote: str | None = None) -> None:
        if src not in self.nodes or dst not in self.nodes:
            return
        e = {"from": src, "relation": rel, "to": dst, "source_artifact_id": str(artifact_id) if artifact_id else None, "quote": (quote or None) and quote[:200]}
        self.edges.append(e)
        self._adj.setdefault(src, []).append(e)
        self._adj.setdefault(dst, []).append(e)

    def around(self, ref: str, depth: int = 1) -> list[dict]:
        """Every node within `depth` steps of ref, nearest first, each with the path of edges that reaches it."""
        seen = {ref}
        out: list[dict] = []
        queue: deque[tuple[str, list[dict]]] = deque([(ref, [])])
        while queue and len(out) < MAX_NODES:
            here, path = queue.popleft()
            if len(path) >= depth:
                continue
            for e in self._adj.get(here, []):
                there = e["to"] if e["from"] == here else e["from"]
                if there in seen:
                    continue
                seen.add(there)
                step = {**e, "phrase": f"{self.nodes[e['from']]['label']} {PHRASE.get(e['relation'], e['relation'])} {self.nodes[e['to']]['label']}"}
                out.append({"node": self.nodes[there], "distance": len(path) + 1, "path": [*path, step]})
                queue.append((there, [*path, step]))
        return out


async def build(p: Principal) -> Graph:
    g = Graph()
    hid, me = p.household_id, p.member_id
    async with pool().acquire() as conn:
        allowed_children = {r[0] for r in await consent.consented_children(conn, hid)}
    for m in await pool().fetch("SELECT id, display_name, role FROM members WHERE household_id = $1", hid):
        if m["role"] != "child" or m["id"] in allowed_children:
            g.node(f"person:{m['id']}", m["display_name"], role=m["role"])

    def person(member_id):
        return f"person:{member_id}" if member_id and f"person:{member_id}" in g.nodes else None

    # the notices that carry anything below, as this person may see them
    for a in await pool().fetch(
            f"SELECT a.id, COALESCE(a.source->>'headline', a.source->>'subject', a.filename, 'a notice') AS label, a.received_at "
            f"FROM input_artifacts a WHERE {VISIBLE_TO_MEMBER} AND a.received_at > NOW() - interval '400 days'", hid, me):
        g.node(f"artifact:{a['id']}", a["label"], received_at=a["received_at"].isoformat())
    for s in await pool().fetch(f"SELECT s.artifact_id, s.member_id FROM artifact_subjects s JOIN input_artifacts a ON a.id = s.artifact_id WHERE {VISIBLE_TO_MEMBER}", hid, me):
        if (who := person(s["member_id"])):
            g.edge(f"artifact:{s['artifact_id']}", "about", who, s["artifact_id"])

    for o in await pool().fetch(
            f"SELECT o.id, o.title, o.due_date, o.status, o.subject_member_id, o.artifact_id, c.quote FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id "
            f"LEFT JOIN claims c ON c.id = o.claim_id WHERE {grants.VISIBLE_OBLIGATION} AND o.superseded_at IS NULL", hid, me):
        ref = g.node(f"obligation:{o['id']}", o["title"], due=o["due_date"].isoformat() if o["due_date"] else None, status=o["status"])
        g.edge(ref, "from", f"artifact:{o['artifact_id']}", o["artifact_id"], o["quote"])
        if (who := person(o["subject_member_id"])):
            g.edge(ref, "about", who, o["artifact_id"], o["quote"])

    for d in await pool().fetch(
            f"SELECT d.id, d.title, d.kind, d.holder_member_id, d.issuer, d.artifact_id, d.expires_on FROM documents d JOIN input_artifacts a ON a.id = d.artifact_id "
            f"WHERE {VISIBLE_TO_MEMBER} AND d.superseded_at IS NULL", hid, me):
        # A holder who exists but is not shown (a child without consent) is not "nobody": the insight asks only when no one at all is named.
        ref = g.node(f"document:{d['id']}", d["title"], kind=d["kind"], expires_on=d["expires_on"].isoformat() if d["expires_on"] else None,
                     holder_hidden=bool(d["holder_member_id"] and not person(d["holder_member_id"])))
        g.edge(ref, "from", f"artifact:{d['artifact_id']}", d["artifact_id"])
        if (who := person(d["holder_member_id"])):
            g.edge(ref, "held_by", who, d["artifact_id"])
        if d["issuer"]:
            g.edge(ref, "issued_by", g.node(f"org:{_slug(d['issuer'])}", d["issuer"]), d["artifact_id"])

    for w in await pool().fetch(
            f"SELECT w.id, w.title, w.merchant, w.artifact_id, w.warranty_until, w.return_by FROM warranties w LEFT JOIN input_artifacts a ON a.id = w.artifact_id "
            f"WHERE w.household_id = $1 AND w.closed_at IS NULL AND (w.artifact_id IS NULL OR {VISIBLE_TO_MEMBER})", hid, me):
        ref = g.node(f"warranty:{w['id']}", w["title"], warranty_until=w["warranty_until"].isoformat() if w["warranty_until"] else None,
                     return_by=w["return_by"].isoformat() if w["return_by"] else None)
        if w["artifact_id"]:
            g.edge(ref, "from", f"artifact:{w['artifact_id']}", w["artifact_id"])
        if w["merchant"]:
            g.edge(ref, "bought_at", g.node(f"org:{_slug(w['merchant'])}", w["merchant"]), w["artifact_id"])

    for m in await pool().fetch(
            f"SELECT m.id, m.drug, m.dose_text, COALESCE(m.patient_member_id, (SELECT s.member_id FROM artifact_subjects s WHERE s.artifact_id = m.artifact_id "
            f"AND (SELECT count(*) FROM artifact_subjects t WHERE t.artifact_id = m.artifact_id) = 1)) AS patient_member_id, m.clinic, m.artifact_id FROM medications m JOIN input_artifacts a ON a.id = m.artifact_id "
            f"WHERE {VISIBLE_TO_MEMBER} AND m.superseded_at IS NULL", hid, me):
        ref = g.node(f"medication:{m['id']}", f"{m['drug']} {m['dose_text'] or ''}".strip(),
                     patient_hidden=bool(m["patient_member_id"] and not person(m["patient_member_id"])))
        g.edge(ref, "from", f"artifact:{m['artifact_id']}", m["artifact_id"])
        if (who := person(m["patient_member_id"])):
            g.edge(ref, "for", who, m["artifact_id"])
        if m["clinic"]:
            g.edge(ref, "prescribed_at", g.node(f"org:{_slug(m['clinic'])}", m["clinic"]), m["artifact_id"])
    return g


# --- the graph looking at itself: what nobody asked about ----------------------------------------------------------

BUSY_DAYS = 7
BUSY_ITEMS = 3
WARRANTY_DAYS = 30


async def insights(p: Principal, today=None) -> list[dict]:
    """Things worth saying that the shape of the record shows, nobody having asked: a person with a pile of dated things coming, a document or
    prescription tied to no one, a warranty about to end. Each carries the entities it is about, so it can be opened on the map, and a stable
    key, so a dismissed one stays dismissed. Nothing here is a guess: each is a fact read off the graph."""
    import datetime as dt
    today = today or clock.today()
    g = await build(p)
    out: list[dict] = []
    horizon = today + dt.timedelta(days=BUSY_DAYS)
    week = f"{today.isocalendar().year}-{today.isocalendar().week}"
    for ref, person in g.nodes.items():
        if person["type"] != "person":
            continue
        items = []
        for e in g._adj.get(ref, []):
            other = g.nodes[e["to"] if e["from"] == ref else e["from"]]
            if other["type"] == "obligation" and other.get("status") in ("accepted", "proposed") and other.get("due"):
                due = dt.date.fromisoformat(other["due"])
                if today <= due <= horizon:
                    items.append({"ref": other["ref"], "label": other["label"], "due": other["due"]})
        seen, unique = set(), []
        for i in sorted(items, key=lambda i: i["due"]):
            # the same date worded twice ("School reopening", "Reopening of School") is one thing
            key = (" ".join(sorted(set(re.findall(r"[a-z0-9]+", i["label"].lower())) - {"of", "the", "a", "an", "for", "to", "on", "in"})), i["due"])
            if key not in seen:
                seen.add(key)
                unique.append(i)
        items = unique
        if len(items) >= BUSY_ITEMS:
            first = person["label"].split()[0]
            out.append({"kind": "busy_person", "key": f"busy:{ref}:{week}", "ref": ref, "title": f"{first} has {len(items)} things in the next {BUSY_DAYS} days",
                        "why": "; ".join(f"{i['label']} ({dt.date.fromisoformat(i['due']).strftime('%a %-d %b')})" for i in items[:4]), "items": items})
    sheets: dict[str, list[dict]] = {}
    for ref, n in g.nodes.items():
        linked = {e["relation"] for e in g._adj.get(ref, [])}
        if n["type"] == "medication" and "for" not in linked and not n.get("patient_hidden"):
            sheet = next((e["to"] for e in g._adj.get(ref, []) if e["relation"] == "from"), ref)
            sheets.setdefault(sheet, []).append(n)
        elif n["type"] == "document" and "held_by" not in linked and not n.get("holder_hidden"):
            out.append({"kind": "unattached", "key": f"unattached:{ref}", "ref": ref, "title": f"Whose is this {n.get('kind', 'document').replace('_', ' ')}?",
                        "why": f"“{n['label']}” is not tied to anyone, so nobody is told when it expires."})
        elif n["type"] == "warranty" and n.get("warranty_until"):
            end = dt.date.fromisoformat(n["warranty_until"])
            if 0 <= (end - today).days <= WARRANTY_DAYS:
                out.append({"kind": "warranty_ending", "key": f"warranty_ending:{ref}", "ref": ref, "title": f"The warranty on {n['label']} ends {end.strftime('%-d %b')}",
                            "why": "If anything is wrong with it, now is the time to claim; after that it is on you."})
    for sheet, meds in list(sheets.items())[:3]:
        names = ", ".join(m["label"] for m in meds[:3]) + (f" and {len(meds) - 3} more" if len(meds) > 3 else "")
        out.append({"kind": "unattached", "key": f"unattached:{sheet}", "ref": sheet if sheet.startswith("artifact:") else meds[0]["ref"],
                    "title": (f"Whose is this prescription ({len(meds)} medicines)?" if len(meds) > 1 else f"Whose is {meds[0]['label']}?"),
                    "why": f"{names}: not tied to anyone, so no refill reminder has anyone to go to."})
    return out


def _check(ref: str) -> str:
    kind, _, ident = (ref or "").partition(":")
    if kind not in TYPES or not ident:
        raise Invalid("name the thing as type:id, for example person:<id> or org:croma")
    if kind != "org":
        try:
            uuid.UUID(ident)
        except ValueError:
            raise Invalid("that is not a valid id") from None
    return ref


async def find(p: Principal, text: str, limit: int = 8) -> list[dict]:
    """Entities whose name contains the words, so a person can start from "Croma" or "Lily" and not an id."""
    q = " ".join((text or "").lower().split())
    if len(q) < 2:
        raise Invalid("type at least two letters")
    g = await build(p)
    hits = [n for n in g.nodes.values() if q in n["label"].lower() and n["type"] != "artifact"]
    hits.sort(key=lambda n: (not n["label"].lower().startswith(q), TYPES.index(n["type"]), n["label"]))
    return hits[:max(1, min(limit, 20))]


async def touches(p: Principal, ref: str, depth: int = 1) -> dict:
    """What touches this entity, as this person may see it: each connected node with how it connects and the notice it comes from."""
    ref = _check(ref)
    g = await build(p)
    if ref not in g.nodes:
        raise NotFound("that")
    around = g.around(ref, max(1, min(depth, MAX_DEPTH)))
    return {"entity": g.nodes[ref], "connections": around, "count": len(around),
            "note": "Built just now from the household's own record. Every link cites the notice it came from."}
