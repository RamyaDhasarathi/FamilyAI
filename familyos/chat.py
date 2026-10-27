"""The one window: ask the household anything, and say what should happen.

`ask.py` answers a question from the record and cites. This is the same
surface grown into a conversation that can also *propose* -- hand a notice to
Archana with a note, add a to-do for the 20th, accept the fee date -- and the
line that keeps it honest is the same one the action rail drew:

  **The model proposes; a person confirms; the existing endpoint does it.**

A proposal that comes back from the model is resolved here into ids the
member may actually use -- a notice they can see, an adult of this household
-- and handed to the console as a card with a Confirm button. Confirming
calls `/artifacts/{id}/assign`, `/todos` or `/obligations/{id}/decision`, the
same routes the buttons call, with the same refusals (a private notice is not
widened by a chat message; a child is never handed anything). Nothing in this
module writes.

What the model sees is what the member sees: the inbox as the inbox shows
it, the proposed dates, the household's members, the to-dos, the recurring
charges -- every row fetched through the visibility rule, never queried by
the model. It is told the date, the member's name, and that a fact it cannot
point at is not one to state.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass, field
from typing import Protocol
from zoneinfo import ZoneInfo

from familyos import ask, inbox, ledger, todos
from familyos.consent import names_match
from familyos.db import pool
from familyos.extraction.llm import anthropic_headers, loads_answer, schema_in_prompt
from familyos.identity import Invalid, Principal
from familyos.settings import settings

logger = logging.getLogger(__name__)

MAX_MESSAGE = 1000
MAX_HISTORY = 12
MAX_NOTICES = 60

PROMPT_VERSION = "chat-1"

SYSTEM = """You are FamilyOS, the household's administrative assistant, talking with {name} ({role}) on {today}.

You answer only from the FACTS below. Each fact has a reference in brackets, like [n3] or [o2]. When you state
something from a fact, put its reference right after it, e.g. "the Airtel bill is due on 16 Oct [n7]". Never state a
date, an amount or a name that is not in the facts. A notice's line may end with "dates in it": the dates the reader
found on it, including ones already passed; asked when something is or was, answer with that date and say if it has
passed. A date equal to today is today, not passed. Put a reference only after the fact it actually came from: the
notice whose line carries that date, amount or name, never a neighbouring one. If the facts do not cover the
question, say so in one sentence and say what would -- forwarding the notice, connecting the mailbox.

You may PROPOSE actions when the person asks for one or clearly wants one; you never perform them. A proposal is an
object in `proposals`:
- {{"kind": "assign", "notice": "n7", "member": "Archana", "note": "can you pay this?"}} -- hand a notice to an adult.
- {{"kind": "todo", "title": "Book the dentist", "due_date": "2026-10-20", "due_time": "11:00", "member": "Archana",
   "note": null}} -- a to-do the family wrote. `due_date` is ISO or null; work it out from today's date when the person
  says "Monday", "tomorrow" or "next week" (the coming one, never a past day). `due_time` is "HH:MM" (24-hour) when a
  time is said, else null. `member` is an adult's name or null. A meeting or an appointment is a dated to-do: FamilyOS
  cannot book it, but a to-do with its date and time goes to the person's calendar.
- {{"kind": "decide", "obligation": "o2", "status": "accepted"}} or "dismissed" -- answer a proposed date.
- {{"kind": "handled", "notice": "n7", "note": "paid, ref 4471"}} -- say a notice is dealt with (done, paid, sent);
  the person who handed it over is told the note.
- {{"kind": "errand", "service": "urbancompany", "title": "Kitchen deep clean", "what": "kitchen deep clean",
   "details": "Saturday morning, the saved home address", "due_date": "2026-10-11", "due_time": "15:30", "part": "afternoon",
   "max_amount": 3000, "currency": "INR", "look": false}} -- a booking or purchase on a site the family is SIGNED IN to
  (see the SIGNED-IN SITES fact; propose it for no other site). Written down in full and approved by a guardian before
  anything runs; paid after the service, or by a UPI request on the person's own phone. Never a card. When the person
  only asks what is available -- "any slots tomorrow afternoon?" -- set "look": true: it reads the slots and the
  price and buys nothing, so it needs no approval; max_amount may then be an estimate.
- {{"kind": "plan", "title": "A week in Switzerland", "brief": "<the ask, in full, with dates, people and budget>",
   "shape": "trip"}} -- shape is "trip", "meals" (a week of meals and the grocery list) or "other" --
  an open-ended thing to plan (a trip, a move, a wedding, a renovation). FamilyOS writes the plan with this household's
  dates and budget in view, keeps candidate bookings as public pages it re-reads, and turns the legwork into to-dos.
  It never books or pays; the family does that in the provider's own app.
Use only member names and references that appear in the facts. Children cannot be assigned anything. Keep `say`
short and plain; it is read on a phone. Do not repeat the proposals in `say`; one line saying what you are proposing is enough.
"""

OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "say": {"type": "string"},
        "proposals": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "kind": {"type": "string", "enum": ["assign", "todo", "decide", "handled", "plan", "errand"]},
                "service": {"type": ["string", "null"]},
                "what": {"type": ["string", "null"]},
                "details": {"type": ["string", "null"]},
                # A nullable enum as anyOf: Anthropic's structured outputs refuse
                # an enum beside a type list; OpenAI's strict mode takes either.
                "part": {"anyOf": [{"type": "string", "enum": ["morning", "afternoon", "evening", "any"]}, {"type": "null"}]},
                "max_amount": {"type": ["number", "null"]},
                "currency": {"type": ["string", "null"]},
                "look": {"type": ["boolean", "null"]},
                "brief": {"type": ["string", "null"]},
                "shape": {"anyOf": [{"type": "string", "enum": ["trip", "meals", "other"]}, {"type": "null"}]},
                "notice": {"type": ["string", "null"]},
                "obligation": {"type": ["string", "null"]},
                "member": {"type": ["string", "null"]},
                "title": {"type": ["string", "null"]},
                "due_date": {"type": ["string", "null"]},
                "due_time": {"type": ["string", "null"]},
                "note": {"type": ["string", "null"]},
                "status": {"anyOf": [{"type": "string", "enum": ["accepted", "dismissed"]}, {"type": "null"}]},
            },
            "required": ["kind", "notice", "obligation", "member", "title", "due_date", "due_time", "note", "status", "brief", "shape",
                         "service", "what", "details", "part", "max_amount", "currency", "look"],
        }},
    },
    "required": ["say", "proposals"],
}


@dataclass
class Facts:
    lines: list[str] = field(default_factory=list)
    notices: dict[str, dict] = field(default_factory=dict)       # n1 -> inbox row
    obligations: dict[str, ask.Fact] = field(default_factory=dict)  # o1 -> fact
    others: dict[str, ask.Fact] = field(default_factory=dict)    # c*, b*
    plain: dict[str, tuple[str, str]] = field(default_factory=dict)  # t*, r*, s* -> (kind, text)
    members: list[dict] = field(default_factory=list)
    signed_in: list[str] = field(default_factory=list)

    def ref(self, key: str) -> dict | ask.Fact | None:
        return self.notices.get(key) or self.obligations.get(key) or self.others.get(key)


# A date the reader found in a notice stays a fact of that notice even when
# it has passed: a tournament last Sunday is not a date to decide, so it is
# no obligation, but "when was it?" still has an answer.
_DATED = """
SELECT COALESCE(a.parent_id, a.id) AS top, c.title, c.kind, c.date, c.end_date, c.time_text, c.optional
FROM claims c JOIN extractions x ON x.id = c.extraction_id JOIN input_artifacts a ON a.id = c.artifact_id
WHERE x.superseded_at IS NULL AND c.date IS NOT NULL AND c.kind <> 'amendment'
  AND (c.artifact_id = ANY($1::uuid[]) OR a.parent_id = ANY($1::uuid[]))
ORDER BY c.date, c.ordinal"""


async def _dated_claims(artifact_ids: list) -> dict:
    if not artifact_ids:
        return {}
    out: dict = {}
    for r in await pool().fetch(_DATED, artifact_ids):
        out.setdefault(r["top"], []).append(dict(r))
    return out


def _dates_in(claims: list[dict], preview: list[str] | None, today: dt.date | None = None) -> str:
    """The dates a notice carries, as a tail on its line. Ones the Waiting
    page already shows (the preview) are left out; ones that have passed
    say so, since the question may be about them."""
    today = today or dt.date.today()
    shown = {t for t in (preview or [])}
    bits = []
    for c in claims:
        if c["title"] in shown:
            continue
        when = c["date"].isoformat() + (f" to {c['end_date'].isoformat()}" if c.get("end_date") else "") + (f" {c['time_text']}" if c.get("time_text") else "")
        last = c.get("end_date") or c["date"]
        bits.append(f"{c['title'][:60]} ({c['kind']}, {when}" + (", already passed" if last < today else "") + (", optional" if c.get("optional") else "") + ")")
        if len(bits) == 4:
            break
    return " — dates in it: " + "; ".join(bits) if bits else ""


async def context(p: Principal) -> Facts:
    """Everything the member may see, numbered so the model can point."""
    f = Facts()
    f.members = [dict(r) for r in await pool().fetch(
        "SELECT m.id, m.display_name, m.role, m.school, m.class_label, "
        "(SELECT string_agg(COALESCE(c.class_label, '?') || ' from ' || to_char(c.since, 'Mon YYYY'), ', ' ORDER BY c.since DESC) "
        " FROM member_classes c WHERE c.member_id = m.id) AS classes "
        "FROM members m WHERE household_id = $1 ORDER BY created_at",
        p.household_id)]
    f.plain["MEMBERS"] = ("household", "the household's members")
    f.lines.append("[MEMBERS] " + "; ".join(
        f"{m['display_name']} ({m['role']}" + (f", {m['school']}" if m.get("school") else "")
        + (f" class {m['class_label']}" if m.get("class_label") else "")
        + (f"; classes: {m['classes']}" if m.get("classes") and "," in m["classes"] else "") + ")" for m in f.members))

    rows = [r for r in await inbox.feed(p, days=60, limit=200) if r["category"] not in ("promo", "newsletter", "developer")]
    # What is open or in somebody's hands comes first and is never cut off;
    # the rest newest by the day it was sent, not the day it was imported --
    # a mailbox arrives all at once, and this morning's bill must not hide
    # behind forty older receipts.
    rows.sort(key=lambda r: (bool(r["assigned_to"]) and not r["handled_at"], r["state"] == "todo",
                             ledger._sent_date(r["source"]) or r["received_at"].date()), reverse=True)
    name = {m["id"]: m["display_name"] for m in f.members}
    handed = []
    dated = await _dated_claims([r["id"] for r in rows[:MAX_NOTICES]])
    for n, r in enumerate(rows[:MAX_NOTICES], start=1):
        key = f"n{n}"
        f.notices[key] = r
        to, by, done_by = name.get(r["assigned_to"]), name.get(r["assigned_by"]), name.get(r["handled_by"])
        hands = ""
        if r["handled_at"]:
            hands = f" — handled by {done_by or 'someone'}" + (f": \u201c{r['handled_note']}\u201d" if r["handled_note"] else "")
        elif to:
            hands = f" — handed to {to}" + (f" by {by}" if by else "") + (f": \u201c{r['assigned_note']}\u201d" if r["assigned_note"] else "")
            handed.append(f"{r['headline']} \u2192 {to} [{key}]")
        f.lines.append(
            f"[{key}] notice from {r['from_label']} ({r['category']}, "
            f"{(ledger._sent_date(r['source']) or r['received_at'].date()).isoformat()}): "
            f"{r['headline']}" + (f" — {'; '.join(r['preview'][:2])}" if r["preview"] else "")
            + f" — {r['state']}" + hands + (f" — {r['reason']}" if r["reason"] else "")
            + _dates_in(dated.get(r["id"], []), r["preview"]))
    f.plain["HANDED"] = ("household", "what is handed over and still open")
    f.lines.insert(1, "[HANDED] handed over, still open: " + ("; ".join(handed) if handed else "nothing"))

    for fact in await ask.context(p):
        (f.obligations if fact.kind == "obligation" else f.others)[fact.ref] = fact
        f.lines.append(fact.as_line())

    for n, t in enumerate(await todos.list_for(p), start=1):
        who = next((m["display_name"] for m in f.members if m["id"] == t["assigned_to"]), None)
        text = (f"to-do: {t['title']}" + (f", by {t['due_date'].isoformat()}" if t["due_date"] else "")
                + (f", {who}'s" if who else "") + (f" — {t['note']}" if t["note"] else ""))
        f.plain[f"t{n}"] = ("todo", text)
        f.lines.append(f"[t{n}] {text}")

    from familyos import suggest
    for n, x in enumerate((await suggest.for_member(p))[:6], start=1):
        text = f"suggested to-do (not added): {x['title']} by {x['due_date'].isoformat()} — {x['why']}"
        f.plain[f"g{n}"] = ("suggestion", text)
        f.lines.append(f"[g{n}] {text}")

    money = await ledger.overview(p, days=120)
    for n, r in enumerate(money["recurring"], start=1):
        text = (f"recurring: {r['merchant']} {r['cadence']}, next {r['next_date'].isoformat()} "
                f"{r['next_amount']} {r['currency']}")
        f.plain[f"r{n}"] = ("money", text)
        f.lines.append(f"[r{n}] {text}")
    for n, r in enumerate(money.get("running_low", [])[:8], start=1):
        text = (f"running low: {r['item']} ({r['merchant']}), bought every ~{r['every_days']} days, "
                f"last {r['last_on'].isoformat()}, expected {r['expected_on'].isoformat()}")
        f.plain[f"l{n}"] = ("running_low", text)
        f.lines.append(f"[l{n}] {text}")
    for n, u in enumerate(money.get("usual", [])[:10], start=1):
        text = (f"usual order: {u['item']} ({u['merchant']}, {'a meal' if u['kind'] == 'meal' else 'groceries'}), "
                f"{u['times']} times, last {u['last_on'].isoformat()}"
                + (f", {u['last_amount']:.0f} {u['currency']}" if u.get("last_amount") else ""))
        f.plain[f"u{n}"] = ("usual", text)
        f.lines.append(f"[u{n}] {text}")
    from familyos.execution import sites as _sites
    signed = await pool().fetch(
        "SELECT DISTINCT service FROM sealed_sessions WHERE household_id = $1 AND revoked_at IS NULL AND expires_at > NOW()",
        p.household_id)
    f.signed_in = [r["service"] for r in signed]
    f.lines.append("SIGNED-IN SITES: " + ("; ".join(
        f"{_sites.get(x)['label']} ({x})" if x in _sites.SITES else x for x in f.signed_in) if f.signed_in else "none"))
    for n, e in enumerate(money["services"]["last_done"], start=1):
        text = f"home service: {e['kind']} last done {e['date'].isoformat()} ({e['merchant']}, {e['amount']} {e['currency']})"
        f.plain[f"s{n}"] = ("service", text)
        f.lines.append(f"[s{n}] {text}")
    return f


# ----------------------------------------------------------------------------
# the model seam
# ----------------------------------------------------------------------------

class Model(Protocol):
    name: str

    async def reply(self, system: str, messages: list[dict], schema: dict | None = None) -> dict:
        """Return the parsed JSON answer, shaped by `schema` (OUTPUT_SCHEMA by default)."""


class SayExtractor:
    """The answer arrives as JSON, token by token, and the person should
    read the sentence as it is written rather than wait for the closing
    brace. This follows the "say" string inside the JSON as it streams,
    decoding escapes only once they are complete, and hands back the new
    readable text each time it is fed."""

    def __init__(self) -> None:
        self.raw = ""
        self._in_say = False
        self._done = False
        self._pos = 0          # how far into raw the say string has been read
        self._pending = ""     # an escape sequence cut by a chunk boundary

    _OPEN = re.compile(r'"say"\s*:\s*"')

    def feed(self, chunk: str) -> str:
        self.raw += chunk
        if self._done:
            return ""
        if not self._in_say:
            m = self._OPEN.search(self.raw)
            if not m:
                return ""
            self._in_say = True
            self._pos = m.end()
        out = []
        text = self._pending + self.raw[self._pos:]
        self._pending = ""
        self._pos = len(self.raw)
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\\":
                if i + 1 >= len(text):
                    self._pending = text[i:]
                    break
                nxt = text[i + 1]
                if nxt == "u":
                    if i + 6 > len(text):
                        self._pending = text[i:]
                        break
                    try:
                        out.append(chr(int(text[i + 2:i + 6], 16)))
                    except ValueError:
                        out.append("")
                    i += 6
                    continue
                out.append({"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}.get(nxt, nxt))
                i += 2
                continue
            if ch == '"':
                self._done = True
                break
            out.append(ch)
            i += 1
        return "".join(out)


class ModelUnavailable(RuntimeError):
    """The model's provider would not answer: no credits, a bad key, an
    outage. Said plainly to the person rather than surfacing as a 500."""


def said_by_provider(exc: Exception) -> str:
    """A one-line reason a person can act on, from whatever the SDK raised."""
    text = str(exc)
    if "insufficient_quota" in text or "no credits" in text.lower() or "credit_balance" in text:
        return "the model's provider says the account has no credits remaining; add credits, or point FAMILYOS_CHAT_MODEL at another provider"
    if "invalid_api_key" in text or "authentication" in text.lower() or "401" in text:
        return "the model's provider refused the API key; check it in the environment file"
    if "rate" in text.lower() and "limit" in text.lower():
        return "the model's provider is rate-limiting; try again in a minute"
    return f"the model's provider did not answer ({type(exc).__name__})"


class RefusingModel:
    name = "none"

    async def reply(self, system: str, messages: list[dict], schema: dict | None = None) -> dict:
        raise ask.NoAnswerer("no model is configured to chat on this deployment")


class OpenAIModel:
    name = "openai"

    def __init__(self, *, api_key: str, model: str, client=None, base_url: str | None = None):
        self._api_key, self.model, self._client, self._base_url = api_key, model, client, base_url
        if base_url:
            self.name = "local"

    def _get_client(self):
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(api_key=self._api_key, max_retries=2, base_url=self._base_url)
        return self._client

    def _system(self, system: str, schema: dict | None) -> str:
        """A server of one's own is told the shape in words too: it may not
        enforce response_format."""
        return schema_in_prompt(system, schema or OUTPUT_SCHEMA) if self._base_url else system

    async def reply(self, system: str, messages: list[dict], schema: dict | None = None) -> dict:
        response = await self._get_client().chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": self._system(system, schema)}, *messages],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "chat_turn", "schema": schema or OUTPUT_SCHEMA, "strict": True}},
            max_completion_tokens=8000)
        choice = response.choices[0]
        if getattr(choice.message, "refusal", None) or not choice.message.content:
            raise RuntimeError("the model returned no answer")
        return loads_answer(choice.message.content)

    async def stream(self, system: str, messages: list[dict], schema: dict | None = None):
        """The same answer, as the text deltas the provider sends."""
        response = await self._get_client().chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": self._system(system, schema)}, *messages],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "chat_turn", "schema": schema or OUTPUT_SCHEMA, "strict": True}},
            max_completion_tokens=8000, stream=True)
        async for chunk in response:
            if not chunk.choices:
                continue
            delta = getattr(chunk.choices[0].delta, "content", None)
            if delta:
                yield delta

    async def stream_text(self, system: str, messages: list[dict]):
        """Plain text, streamed: for an answer that is not JSON (a page in a UI language)."""
        response = await self._get_client().chat.completions.create(
            model=self.model, messages=[{"role": "system", "content": system}, *messages],
            max_completion_tokens=8000, stream=True)
        async for chunk in response:
            if not chunk.choices:
                continue
            delta = getattr(chunk.choices[0].delta, "content", None)
            if delta:
                yield delta


ANTHROPIC_MAX_UNIONS = 16      # Anthropic's structured outputs refuse a schema with more union-typed parameters


def _unions(schema) -> int:
    if isinstance(schema, dict):
        own = 1 if isinstance(schema.get("type"), list) or "anyOf" in schema else 0
        return own + sum(_unions(v) for v in schema.values())
    if isinstance(schema, list):
        return sum(_unions(v) for v in schema)
    return 0


def _anthropic_shape(system: str, schema: dict) -> dict:
    """The system prompt and output format for one request. A schema written
    for OpenAI's strict mode can be past what Anthropic's structured outputs
    compile (the chat turn is: 17 nullable fields in an array of objects), so
    that one is described in the instructions and parsed from the reply, as a
    model of one's own is; any other is enforced."""
    if _unions(schema) > ANTHROPIC_MAX_UNIONS:
        return {"system": schema_in_prompt(system, schema)}
    return {"system": system, "output_config": {"format": {"type": "json_schema", "schema": schema}}}


class AnthropicModel:
    name = "anthropic"

    def __init__(self, *, api_key: str, model: str, client=None):
        self._api_key, self.model, self._client = api_key, model, client

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key, max_retries=2, default_headers=anthropic_headers())
        return self._client

    async def reply(self, system: str, messages: list[dict], schema: dict | None = None) -> dict:
        message = await self._get_client().messages.create(
            model=self.model, max_tokens=8000, messages=messages, **_anthropic_shape(system, schema or OUTPUT_SCHEMA))
        text = next((b.text for b in message.content if b.type == "text"), None)
        if text is None:
            raise RuntimeError("the model returned no answer")
        return loads_answer(text)

    async def stream(self, system: str, messages: list[dict], schema: dict | None = None):
        async with self._get_client().messages.stream(
                model=self.model, max_tokens=8000, messages=messages, **_anthropic_shape(system, schema or OUTPUT_SCHEMA)) as stream:
            async for text in stream.text_stream:
                if text:
                    yield text

    async def stream_text(self, system: str, messages: list[dict]):
        async with self._get_client().messages.stream(model=self.model, max_tokens=8000, system=system, messages=messages) as stream:
            async for text in stream.text_stream:
                if text:
                    yield text


_model: Model = RefusingModel()


def use_model(model: Model) -> None:
    global _model
    _model = model


def current_model() -> Model:
    return _model


_local: Model | None = None
_local_on: dict = {}          # household_id -> (flag, read_at)
LOCAL_TTL = 30.0


def local_model() -> Model | None:
    """The model on this machine, when one is named in settings."""
    global _local
    if not settings.local_model:
        return None
    if _local is None or getattr(_local, "model", None) != settings.local_model:
        _local = OpenAIModel(api_key=settings.local_model_key or "local", model=settings.local_model, base_url=settings.local_model_url)
    return _local


async def local_models_on(household_id) -> bool:
    """Whether this household switched to the model on this machine. Read
    from the household's rules, remembered for a short while."""
    import time
    if not settings.local_model or household_id is None:
        return False
    hit = _local_on.get(household_id)
    if hit and time.monotonic() - hit[1] < LOCAL_TTL:
        return hit[0]
    on = bool(await pool().fetchval("SELECT local_models FROM households WHERE id = $1", household_id))
    _local_on[household_id] = (on, time.monotonic())
    return on


def forget_local_choice(household_id=None) -> None:
    if household_id is None:
        _local_on.clear()
    else:
        _local_on.pop(household_id, None)


async def model_for(household_id) -> Model:
    """The model this household's words go to: its own machine's when it
    said so and one is named, else the deployment's."""
    if await local_models_on(household_id):
        return local_model() or _model
    return _model


def configure() -> None:
    """Pick the chat model from settings, the way the extractor is picked:
    named in configuration, never inferred from a key lying around."""
    from familyos.extraction.llm import split_model
    if not settings.ask_enabled:
        use_model(RefusingModel())
        return
    provider, name = split_model(settings.chat_model or settings.extraction_model)
    if provider == "anthropic" and settings.anthropic_api_key:
        use_model(AnthropicModel(api_key=settings.anthropic_api_key, model=name))
    elif provider == "openai" and settings.openai_api_key:
        use_model(OpenAIModel(api_key=settings.openai_api_key, model=name))
    else:
        use_model(RefusingModel())


def describe() -> str:
    if not settings.ask_enabled:
        return "Chat is off (FAMILYOS_ASK_ENABLED=false)."
    if isinstance(_model, RefusingModel):
        return "Chat is on but no model is configured (FAMILYOS_CHAT_MODEL or FAMILYOS_EXTRACTION_MODEL with its key)."
    return (f"Chat is on ({_model.name}/{getattr(_model, 'model', '?')}): the model sees what this member may see "
            "and proposes; a person confirms; the existing endpoints act.")


# ----------------------------------------------------------------------------
# a turn
# ----------------------------------------------------------------------------

_REF = re.compile(r"\[([nobctrslgu]\d{1,3}|MEMBERS|HANDED)\]")


def _adult(name: str | None, members: list[dict]) -> tuple[dict | None, str | None]:
    """The adult this name means, or why not."""
    if not name:
        return None, None
    hits = [m for m in members if names_match(name, m["display_name"])]
    if not hits:
        return None, f"nobody here is called {name}"
    if hits[0]["role"] == "child":
        return None, f"{hits[0]['display_name']} is a child and cannot be handed anything"
    return hits[0], None


def _time(text: str | None) -> dt.time | None:
    """"11:00", "11:00:00", "9:30" -- the model is told HH:MM but is not relied on."""
    if not text:
        return None
    try:
        return dt.time.fromisoformat(text.strip() if ":" in text else text.strip() + ":00").replace(second=0, microsecond=0)
    except ValueError:
        return None


# "3.30PM" as often as "3:30 pm": a dot between the hour and the minutes is how many people type it.
_SAID_TIME = re.compile(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)\b|\b(\d{1,2}):(\d{2})\s*(?:hrs|hours|h)?\b", re.I)


def _time_in(*texts: str | None) -> dt.time | None:
    """A time said in words -- "11 AM", "5.30pm" written "5:30pm", "1545 hrs" is
    not attempted -- from the title or the person's own message, for when the
    model keeps the date and drops the hour."""
    for text in texts:
        m = _SAID_TIME.search(text or "")
        if not m:
            continue
        if m.group(1):
            hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower().replace(".", "")
            if hour > 12 or minute > 59:
                continue
            hour = hour % 12 + (12 if ampm == "pm" else 0)
        else:
            hour, minute = int(m.group(4)), int(m.group(5))
            if hour > 23 or minute > 59:
                continue
        return dt.time(hour, minute)
    return None


def _date(text: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text) if text else None
    except ValueError:
        return None


def resolve(raw: list[dict], facts: Facts, said: str | None = None) -> list[dict]:
    """Model proposals into things the console can confirm, or say why not."""
    out = []
    for r in raw or []:
        kind = r.get("kind")
        if kind == "assign":
            notice = facts.notices.get(r.get("notice") or "")
            member, why = _adult(r.get("member"), facts.members)
            if notice is None:
                why = why or "that notice is not one you can see"
            out.append({"kind": "assign", "ok": why is None, "why": why,
                        "artifact_id": notice["id"] if notice else None,
                        "headline": notice["headline"] if notice else None,
                        "member_id": member["id"] if member else None,
                        "member_name": member["display_name"] if member else r.get("member"),
                        "note": (r.get("note") or "")[:500] or None})
        elif kind == "todo":
            member, why = _adult(r.get("member"), facts.members)
            title = " ".join((r.get("title") or "").split())[:200]
            if not title:
                why = why or "a to-do needs a few words"
            out.append({"kind": "todo", "ok": why is None, "why": why, "title": title,
                        "due_date": _date(r.get("due_date")),
                        "due_time": (_time(r.get("due_time")) or _time_in(title, said)) if _date(r.get("due_date")) else None,
                        "member_id": member["id"] if member else None,
                        "member_name": member["display_name"] if member else None,
                        "note": (r.get("note") or "")[:500] or None})
        elif kind == "errand":
            from familyos.execution import sites as _sites
            service = (r.get("service") or "").strip().lower()
            why = None
            if service not in _sites.SITES:
                why = "that site is not one FamilyOS can act on"
            elif service not in facts.signed_in:
                why = f"nobody is signed in to {_sites.get(service)['label']} \u2014 sign in on the Household page first"
            amount = r.get("max_amount")
            look = bool(r.get("look"))
            if look and not (isinstance(amount, (int, float)) and amount > 0):
                amount = 100000          # a look spends nothing; the limit only stops a booking
            if why is None and not (isinstance(amount, (int, float)) and amount > 0):
                why = "say the most this may cost"
            out.append({"kind": "errand", "ok": why is None, "why": why, "service": service,
                        "label": _sites.get(service)["label"] if service in _sites.SITES else service,
                        "title": " ".join((r.get("title") or r.get("what") or "").split())[:160],
                        "what": " ".join((r.get("what") or r.get("title") or "").split())[:200],
                        "details": (r.get("details") or "")[:600] or None,
                        "due_date": _date(r.get("due_date")),
                        "due_time": (_time(r.get("due_time")) or _time_in(r.get("details"), r.get("title"), said)) if _date(r.get("due_date")) else None,
                        "part": r.get("part") if r.get("part") in ("morning", "afternoon", "evening", "any") else "any",
                        "max_amount": float(amount) if isinstance(amount, (int, float)) else None,
                        "currency": (r.get("currency") or "INR").upper()[:3], "look": look})
        elif kind == "plan":
            brief = " ".join((r.get("brief") or "").split())[:2000]
            out.append({"kind": "plan", "ok": bool(brief), "why": None if brief else "say what to plan",
                        "title": (r.get("title") or "A plan")[:160], "brief": brief or None,
                        "shape": r.get("shape") if r.get("shape") in ("trip", "meals", "other") else "trip"})
        elif kind == "handled":
            notice = facts.notices.get(r.get("notice") or "")
            why = None if notice else "that notice is not one you can see"
            out.append({"kind": "handled", "ok": why is None, "why": why,
                        "artifact_id": notice["id"] if notice else None,
                        "headline": notice["headline"] if notice else None,
                        "note": (r.get("note") or "")[:500] or None})
        elif kind == "decide":
            fact = facts.obligations.get(r.get("obligation") or "")
            status = r.get("status") if r.get("status") in ("accepted", "dismissed") else None
            why = None if (fact and status) else "that date is not one you can see"
            out.append({"kind": "decide", "ok": why is None, "why": why, "status": status,
                        "obligation_id": fact.obligation_id if fact else None,
                        "title": fact.text if fact else None})
    return out


_QUESTION = re.compile(r"\?\s*$|^\s*(?:/ask\b|ask\b)", re.I)


def is_question(text: str | None) -> bool:
    """What a message to the bot must look like to be a question rather than
    a notice: it ends with a question mark, or starts with "ask". A forwarded
    circular that happens to ask something is a forward, which the caller
    checks first."""
    return bool(text) and bool(_QUESTION.search(text.strip()))


def _offer(x: dict) -> str:
    kind, title, head, who = x.get("kind"), x.get("title") or "", x.get("headline") or "", x.get("member_name") or ""
    when = f" by {x['due_date']}" if x.get("due_date") else ""
    if kind == "todo":
        return f"add the to-do \u201c{title}\u201d{when}" + (f" for {who}" if who else "")
    if kind == "assign":
        return f"hand \u201c{head}\u201d to {who or 'someone'}"
    if kind == "decide":
        return f"{x.get('status') or 'decide'} \u201c{title or head}\u201d"
    if kind == "handled":
        return f"mark \u201c{head}\u201d handled"
    if kind == "plan":
        return f"plan \u201c{title}\u201d"
    if kind == "errand":
        return f"{'look up' if x.get('look') else 'book'} \u201c{title}\u201d on {x.get('label') or x.get('service') or 'the site'}"
    return kind or "that"


def for_phone(turn_: dict) -> str:
    """An answer as one plain message: the references stripped, and what
    the model would propose said as an offer to confirm in the console,
    because nothing is done from a chat message."""
    say = re.sub(r"\s*\[[a-z]\d+\]", "", turn_.get("say") or "").strip()
    offers = [_offer(x) for x in turn_.get("proposals") or [] if x.get("ok")]
    if offers:
        say += "\n\nI could also " + "; ".join(offers) + ". Confirm it in the console: " + settings.console_url.rstrip("/") + "#/chat"
    return say or "I have nothing to say to that."


async def answer_for_phone(p: Principal, text: str) -> str:
    """A question from a member's own phone, answered from what they may
    see. A failure is said in one line, never a stack."""
    text = re.sub(r"^\s*/?ask\b[:\s]*", "", text.strip(), flags=re.I) or text.strip()
    try:
        return for_phone(await turn(p, text))
    except ask.NoAnswerer as exc:
        return f"I cannot answer here: {exc}"
    except ModelUnavailable as exc:
        return f"I could not reach the model: {exc}"
    except Invalid as exc:
        return str(exc)


async def turn(p: Principal, message: str, history: list[dict] | None = None) -> dict:
    text = _check(message)
    facts, system, past = await _prepare(p, history)
    try:
        answer = await (await model_for(p.household_id)).reply(system, [*past, {"role": "user", "content": text}])
    except ask.NoAnswerer:
        raise
    except Exception as exc:  # noqa: BLE001 - whatever the SDK raised, the person gets a sentence
        logger.warning("chat model failed", exc_info=True)
        raise ModelUnavailable(said_by_provider(exc)) from exc
    return _finish(answer, facts, text)


async def _prepare(p: Principal, history: list[dict] | None) -> tuple[Facts, str, list[dict]]:
    facts = await context(p)
    from familyos import country
    today = dt.datetime.now(ZoneInfo((await country.locale(p.household_id))["timezone"])).date()
    system = SYSTEM.format(name=p.display_name, role=p.role, today=f"{today.strftime('%A')} {today.isoformat()}") \
        + "\n\nFACTS:\n" + "\n".join(facts.lines)
    past = [{"role": h["role"], "content": str(h.get("content") or "")[:MAX_MESSAGE]}
            for h in (history or [])[-MAX_HISTORY:] if h.get("role") in ("user", "assistant")]
    return facts, system, past


def _check(message: str) -> str:
    text = " ".join((message or "").split())
    if not text:
        raise Invalid("say something")
    if len(text) > MAX_MESSAGE:
        raise Invalid(f"keep a message under {MAX_MESSAGE} characters")
    if not settings.ask_enabled:
        raise ask.NoAnswerer("chat is off on this deployment (FAMILYOS_ASK_ENABLED=false)")
    return text


async def stream_turn(p: Principal, message: str, history: list[dict] | None = None):
    """The same turn, as it is written: `say` deltas as the model produces
    them, then the finished turn with its citations and proposals, which are
    only known once the whole answer is in. A model that cannot stream
    answers whole, as one delta. Errors arrive as an event too, since the
    response has already started."""
    try:
        text = _check(message)
        facts, system, past = await _prepare(p, history)
        model = await model_for(p.household_id)
        messages = [*past, {"role": "user", "content": text}]
        extractor = SayExtractor()
        answer = None
        if hasattr(model, "stream"):
            try:
                async for delta in model.stream(system, messages):
                    said = extractor.feed(delta)
                    if said:
                        yield {"type": "say", "delta": said}
                answer = loads_answer(extractor.raw)
            except Exception:  # noqa: BLE001 - a provider that will not stream answers whole instead
                if extractor.raw:
                    raise
                logger.info("chat model would not stream; answering whole", exc_info=True)
        if answer is None:
            answer = await model.reply(system, messages)
            yield {"type": "say", "delta": str(answer.get("say") or "").strip()}
        yield {"type": "turn", **_finish(answer, facts, text)}
    except (Invalid, ask.NoAnswerer, ModelUnavailable) as exc:
        yield {"type": "error", "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 - whatever the SDK raised, the person gets a sentence
        logger.warning("chat model failed", exc_info=True)
        yield {"type": "error", "detail": said_by_provider(exc)}


def _finish(answer: dict, facts: Facts, text: str) -> dict:
    say = str(answer.get("say") or "").strip()
    cited = []
    for ref in dict.fromkeys(_REF.findall(say)):
        hit = facts.ref(ref)
        if isinstance(hit, dict):
            cited.append({"ref": ref, "kind": "notice", "text": hit["headline"], "artifact_id": hit["id"]})
        elif hit is not None:
            cited.append({"ref": ref, "kind": hit.kind, "text": hit.text, "artifact_id": hit.artifact_id,
                          "obligation_id": hit.obligation_id, "quote": hit.quote})
        elif ref in facts.plain:
            # Money, services and to-dos: real facts with a page, not a notice.
            cited.append({"ref": ref, "kind": facts.plain[ref][0], "text": facts.plain[ref][1]})
    unverified = verify_citations(say, cited, facts)
    proposals = resolve(answer.get("proposals") or [], facts, text)
    grounded = bool(cited) and not unverified
    note = None
    if unverified:
        note = ("Check before relying on it: " + ", ".join(f"[{r}]" for r in unverified)
                + (" does not seem to say what the answer attributes to it." if len(unverified) == 1
                   else " do not seem to say what the answer attributes to them."))
    logger.info("chat turn: model=%s grounded=%s cites=%d unverified=%d proposals=%d question=%d chars answer=%d chars%s",
                getattr(_model, "name", "none"), grounded, len(cited), len(unverified), len(proposals), len(text), len(say),
                f" | Q: {text[:200]} | A: {say[:300]}" if settings.chat_log_text else "")
    return {"say": say, "grounded": grounded, "citations": cited, "proposals": proposals, "note": note,
            "model": getattr(_model, "name", "none")}


_CLAIMISH = re.compile(r"\b(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*|\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}|"
                       r"(?:₹|rs\.?|inr|aed|\$)\s?[\d,]+(?:\.\d+)?|[\d,]+(?:\.\d{2}))\b", re.I)
_STOP = {"the", "this", "that", "also", "and", "it", "we", "you", "your", "our", "next", "last", "parent", "teacher", "meeting",
         "term", "holiday", "school", "bill", "receipt", "today", "tomorrow", "monday", "tuesday", "wednesday", "thursday",
         "friday", "saturday", "sunday", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec"}
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _fact_text(ref: str, entry: dict, facts: Facts) -> str:
    """Everything the facts say under this reference, lowercased."""
    for line in facts.lines:
        if line.startswith(f"[{ref}]"):
            return line.casefold()
    return str(entry.get("text") or "").casefold()


def _day_in(fact: str, day: str, mon: str) -> bool:
    mon = mon[:3]
    if mon not in _MONTHS:
        return False
    d = int(day)
    return (f"-{_MONTHS.index(mon) + 1:02d}-{d:02d}" in fact) or f"{d} {mon}" in fact or f"{d:02d} {mon}" in fact


def verify_citations(say: str, cited: list[dict], facts: Facts) -> list[str]:
    """References the answer puts after a claim the cited fact does not carry.

    For each [ref], the clause before it is read for the things a wrong
    citation gets wrong -- a date, a time, an amount, a capitalised name --
    and at least one must appear in that fact's own line. A clause that
    names nothing checkable passes. A clause whose date, amount and names
    are all absent from the cited fact fails, and the reader is told.
    """
    by_ref = {c["ref"]: c for c in cited}
    bad: list[str] = []
    clause = ""
    for piece in re.split(r"(\[[A-Za-z]+\d*\])", say):
        m = re.fullmatch(r"\[([A-Za-z]+\d*)\]", piece)
        if not m:
            clause = piece
            continue
        ref = m.group(1)
        if ref not in by_ref or ref in bad:
            continue
        fact = _fact_text(ref, by_ref[ref], facts)
        tail = re.split(r"[.;!?]\s+", clause)[-1]
        checks = []
        for hit in _CLAIMISH.findall(tail):
            token = hit.casefold().replace(",", "")
            for sym in ("rs.", "rs", "inr", "aed", "₹", "$"):
                token = token.replace(sym, "")
            token = token.strip()
            if re.fullmatch(r"\d{1,2}\s+[a-z]+", token):
                day, mon = token.split()
                checks.append(lambda f, d=day, mo=mon: _day_in(f, d, mo))
            elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", token):
                checks.append(lambda f, t=token: t in f)
            elif re.fullmatch(r"\d{1,2}:\d{2}", token):
                checks.append(lambda f, t=token: t in f or t.lstrip("0") in f)
            else:
                n = token.replace(" ", "")
                checks.append(lambda f, n=n: n in f.replace(",", "") or (n.endswith(".00") and n[:-3] in f.replace(",", "")))
        # A capitalised word that merely starts the sentence is not a name.
        names = re.findall(r"\b([A-Z][a-zA-Z]{2,})\b", tail)
        if names and tail.lstrip().startswith(names[0]):
            names = names[1:]
        for name in names:
            if name.casefold() not in _STOP:
                checks.append(lambda f, n=name.casefold(): n in f)
        if checks and not any(c(fact) for c in checks):
            bad.append(ref)
        clause = ""
    return bad
