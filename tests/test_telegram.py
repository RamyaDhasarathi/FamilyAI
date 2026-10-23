"""Telegram intake: the second rail, and the group it refuses to read.

The interesting tests here are not the happy ones. They are the refusals: a
group message nobody addressed to us, a binding token used as a sign-in link,
and a parent who reinstalled Telegram.
"""
import json
import uuid

import pytest

from familyos import identity
from familyos.db import pool
from familyos.intake import telegram
from familyos.settings import settings
from tests.conftest import pdf

SECRET = "test-webhook-secret"
BOT = "familyos_test_bot"
CHAT = 500100200


def update(*, sender_id=CHAT, chat_id=None, chat_type="private", text=None, caption=None,
           media=None, message_id=11, name="Amma", forwarded=True, reply_to_bot=False,
           is_bot=False, key="message") -> dict:
    """The shape Telegram actually posts."""
    message = {
        "message_id": message_id,
        "date": 1790000000,
        "from": {"id": sender_id, "is_bot": is_bot, "first_name": name},
        "chat": {"id": chat_id if chat_id is not None else sender_id, "type": chat_type},
    }
    if forwarded:
        message["forward_origin"] = {"type": "user", "date": 1789990000}
    if text is not None:
        message["text"] = text
    if caption is not None:
        message["caption"] = caption
    if media:
        message[media["kind"]] = {k: v for k, v in media.items() if k != "kind"}
    if reply_to_bot:
        message["reply_to_message"] = {"message_id": 10, "from": {"id": 7, "is_bot": True,
                                                                  "username": BOT}}
    return {"update_id": 900 + message_id, key: message}


def headers(secret: str | None = SECRET) -> dict:
    out = {"Content-Type": "application/json"}
    if secret is not None:
        out["X-Telegram-Bot-Api-Secret-Token"] = secret
    return out


async def post(family, payload: dict, secret: str | None = SECRET):
    return await family.client.post("/v1/inbound/telegram", content=json.dumps(payload).encode(),
                                    headers=headers(secret))


@pytest.fixture(autouse=True)
def bot(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "telegram_bot_token", "7:TESTTOKEN")
    monkeypatch.setattr(settings, "telegram_bot_username", BOT)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Nothing in these tests may reach api.telegram.org. The replies the bot
    sends are collected instead, because what it says back is part of the
    binding flow and worth asserting on."""
    said: list[tuple[int, str]] = []

    async def send_message(chat_id, text, *, bot_token, api_base, post=None):
        said.append((chat_id, text))

    monkeypatch.setattr(telegram, "send_message", send_message)
    return said


async def _linked(family, who="amma", chat_id=CHAT):
    """Bind a member's Telegram account the way the deep link does."""
    r = await family.client.post("/v1/telegram/link", headers=family.h(who))
    assert r.status_code == 200, r.text
    token = r.json()["url"].split("start=")[1]
    return await identity.bind_telegram(token, chat_id), token


# ----------------------------------------------------------------------------
# the webhook itself
# ----------------------------------------------------------------------------

async def test_a_delivery_without_the_secret_is_refused(family):
    r = await post(family, update(text="hello"), secret=None)
    assert r.status_code == 401


async def test_a_delivery_with_the_wrong_secret_is_refused(family):
    r = await post(family, update(text="hello"), secret="not-it")
    assert r.status_code == 401


async def test_without_a_configured_secret_nothing_is_accepted(family, monkeypatch):
    """An unset secret must not mean an open webhook, which is the one way
    this rail could be worse than Meta's signed one."""
    monkeypatch.setattr(settings, "telegram_webhook_secret", "")
    r = await post(family, update(text="hello"), secret="")
    assert r.status_code == 401


async def test_the_secret_is_checked_constant_time():
    with pytest.raises(telegram.BadSecret):
        telegram.verify_secret("a" * 32, SECRET)
    telegram.verify_secret(SECRET, SECRET)


# ----------------------------------------------------------------------------
# binding an account
# ----------------------------------------------------------------------------

async def test_a_deep_link_binds_the_account_that_opens_it(family, no_network):
    r = await family.client.post("/v1/telegram/link", headers=family.h("amma"))
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.startswith(f"https://t.me/{BOT}?start=")
    token = url.split("start=")[1]
    assert telegram.valid_payload(token), "a token Telegram will not carry is no token"
    assert len(token) <= telegram.PAYLOAD_MAX

    r = await post(family, update(text=f"/start {token}", forwarded=False))
    assert r.status_code == 202 and r.json()["linked"] is True
    assert no_network and "Amma" in no_network[0][1]

    bound = await pool().fetchval("SELECT telegram_chat_id FROM members WHERE id = $1",
                                  uuid.UUID(family.amma["id"]))
    assert bound == CHAT


async def test_a_binding_link_is_single_use(family):
    _, token = await _linked(family)
    with pytest.raises(identity.LinkNotUsable):
        await identity.bind_telegram(token, CHAT)


async def test_asking_again_invalidates_the_last_link(family):
    first = await family.client.post("/v1/telegram/link", headers=family.h("amma"))
    second = await family.client.post("/v1/telegram/link", headers=family.h("amma"))
    stale = first.json()["url"].split("start=")[1]
    fresh = second.json()["url"].split("start=")[1]
    with pytest.raises(identity.LinkNotUsable):
        await identity.bind_telegram(stale, CHAT)
    assert await identity.bind_telegram(fresh, CHAT)


async def test_a_binding_token_cannot_buy_a_console_session(family):
    """The token travels through a chat. If it also redeemed for a session,
    whoever saw it over a shoulder would be signed in as that parent."""
    r = await family.client.post("/v1/telegram/link", headers=family.h("amma"))
    token = r.json()["url"].split("start=")[1]
    with pytest.raises(identity.LinkNotUsable):
        await identity.redeem(token)


async def test_a_sign_in_link_cannot_bind_an_account(family):
    """And the other way: a mailed sign-in link must not silently attach
    whoever pastes it into the bot."""
    async with pool().acquire() as conn:
        token = await identity._issue_link(conn, uuid.UUID(family.amma["id"]), purpose="sign_in")
    with pytest.raises(identity.LinkNotUsable):
        await identity.bind_telegram(token, CHAT)


async def test_a_bad_token_is_said_plainly_and_binds_nothing(family, no_network):
    r = await post(family, update(text="/start lnk_nothingatall", forwarded=False))
    assert r.status_code == 202 and r.json()["reason"] == "link_not_usable"
    assert "expired" in no_network[0][1]


async def test_a_reinstalled_telegram_takes_the_binding_with_it(family):
    """A parent who reinstalls Telegram comes back as a different id. The
    unique index must not turn that into a support ticket."""
    await _linked(family, "amma", chat_id=CHAT)
    await _linked(family, "amma", chat_id=CHAT + 1)
    rows = await pool().fetch(
        "SELECT telegram_chat_id FROM members WHERE telegram_chat_id IS NOT NULL")
    assert [r["telegram_chat_id"] for r in rows] == [CHAT + 1]


async def test_one_telegram_account_cannot_be_two_members(family):
    """The second binding wins and the first is dropped, rather than both
    rows claiming the same account."""
    await _linked(family, "amma", chat_id=CHAT)
    await _linked(family, "appa", chat_id=CHAT)
    amma = await pool().fetchval("SELECT telegram_chat_id FROM members WHERE id = $1",
                                 uuid.UUID(family.amma["id"]))
    appa = await pool().fetchval("SELECT telegram_chat_id FROM members WHERE id = $1",
                                 uuid.UUID(family.appa["id"]))
    assert amma is None and appa == CHAT


async def test_unlinking_stops_the_bot_reaching_them(family):
    await _linked(family)
    r = await family.client.delete("/v1/telegram/link", headers=family.h("amma"))
    assert r.status_code == 200 and r.json()["unlinked"] is True
    assert await identity.member_by_telegram(CHAT) is None
    # Saying it twice is not an error; it is the same end state.
    r = await family.client.delete("/v1/telegram/link", headers=family.h("amma"))
    assert r.json()["unlinked"] is False


# ----------------------------------------------------------------------------
# the group it will not read
# ----------------------------------------------------------------------------

async def test_a_group_message_nobody_addressed_to_us_is_refused(family):
    """The test this rail exists or dies by. Telegram will hand a bot every
    message in a group once privacy mode is off -- or once somebody makes the
    bot an admin, which overrides the setting entirely. None of it is kept."""
    await _linked(family)
    r = await post(family, update(chat_id=-100200300, chat_type="supergroup",
                                  text="is anyone else's child not eating lunch"))
    assert r.status_code == 202
    assert r.json() == {"received": 0, "refused": 1, "reason": "not_addressed"}
    assert await pool().fetchval("SELECT count(*) FROM input_artifacts") == 0


async def test_naming_the_bot_in_a_group_is_addressing_it(family):
    await _linked(family)
    r = await post(family, update(chat_id=-100200300, chat_type="supergroup",
                                  text=f"@{BOT} sports day is on the 14th"))
    assert r.status_code == 202 and r.json()["received"] == 1


async def test_replying_to_the_bot_in_a_group_is_addressing_it(family):
    await _linked(family)
    r = await post(family, update(chat_id=-100200300, chat_type="supergroup",
                                  text="this one too", reply_to_bot=True))
    assert r.status_code == 202 and r.json()["received"] == 1


async def test_replying_to_a_different_bot_is_not(family):
    await _linked(family)
    payload = update(chat_id=-100200300, chat_type="supergroup", text="thanks")
    payload["message"]["reply_to_message"] = {"message_id": 10, "from": {
        "id": 99, "is_bot": True, "username": "some_other_bot"}}
    r = await post(family, payload)
    assert r.json()["reason"] == "not_addressed"


async def test_a_private_chat_is_wholly_addressed_to_us(family):
    """Writing to the bot is the act of forwarding, so nothing needs naming."""
    await _linked(family)
    r = await post(family, update(text="school is shut tomorrow"))
    assert r.status_code == 202 and r.json()["received"] == 1


# ----------------------------------------------------------------------------
# what gets stored
# ----------------------------------------------------------------------------

async def test_a_forwarded_notice_becomes_an_artifact(family):
    await _linked(family)
    r = await post(family, update(text="Sports day moved to the 14th. Bring a water bottle."))
    assert r.status_code == 202 and r.json()["received"] == 1
    row = await pool().fetchrow(
        "SELECT channel, visibility, status, submitted_by, source FROM input_artifacts")
    assert row["channel"] == "telegram"
    assert (row["visibility"], row["status"]) == ("private", "accepted")
    assert row["submitted_by"] == uuid.UUID(family.amma["id"])
    source = json.loads(row["source"]) if isinstance(row["source"], str) else row["source"]
    assert source["forwarded"] is True and source["from_id"] == CHAT


async def test_an_account_belonging_to_nobody_is_refused_and_stored_nowhere(family):
    r = await post(family, update(sender_id=999777555, text="hello?"))
    assert r.status_code == 202
    assert r.json() == {"received": 0, "refused": 1, "reason": "unknown_sender"}
    assert await pool().fetchval("SELECT count(*) FROM input_artifacts") == 0


async def test_the_same_message_delivered_twice_is_stored_once(family):
    """Telegram redelivers anything that is not answered 2xx, so this is the
    ordinary case rather than the strange one."""
    await _linked(family)
    await post(family, update(text="one notice", message_id=41))
    r = await post(family, update(text="one notice", message_id=41))
    assert r.status_code == 202
    assert await pool().fetchval("SELECT count(*) FROM input_artifacts") == 1


async def test_the_same_id_in_two_chats_is_two_messages(family):
    """A Telegram message_id is unique only within its chat. Keying on the id
    alone would swallow the second of these as a duplicate."""
    await _linked(family)
    await post(family, update(text="from the private chat", message_id=7))
    await post(family, update(chat_id=-100200300, chat_type="supergroup", message_id=7,
                              text=f"@{BOT} from the group"))
    assert await pool().fetchval("SELECT count(*) FROM input_artifacts") == 2


async def test_an_attachment_becomes_a_child_of_the_message(family, monkeypatch):
    await _linked(family)

    async def fetch(file_id):
        return pdf("circular")

    monkeypatch.setattr(telegram, "download", lambda file_id, **kw: fetch(file_id))
    payload = update(caption="The circular, as promised", media={
        "kind": "document", "file_id": "BQACAgQAAx", "file_name": "circular.pdf",
        "mime_type": "application/pdf", "file_size": 400})
    r = await post(family, payload)
    assert r.status_code == 202 and r.json()["received"] == 2
    rows = await pool().fetch(
        "SELECT channel, filename, parent_id FROM input_artifacts ORDER BY channel")
    assert [row["channel"] for row in rows] == ["telegram", "telegram_media"]
    assert rows[1]["filename"] == "circular.pdf" and rows[1]["parent_id"] is not None
    # The caption is where the date usually is, so it is the parent's text too.
    assert rows[0]["parent_id"] is None


async def test_the_largest_photo_is_the_one_taken(family, monkeypatch):
    """A circular photographed on a noticeboard is only legible at full size,
    and Telegram offers the thumbnail first."""
    asked: list[str] = []

    async def fetch(file_id):
        asked.append(file_id)
        return pdf("photo")

    await _linked(family)
    monkeypatch.setattr(telegram, "download", lambda file_id, **kw: fetch(file_id))
    payload = update(caption="noticeboard", media=None)
    payload["message"]["photo"] = [
        {"file_id": "small", "file_size": 900, "width": 90, "height": 120},
        {"file_id": "big", "file_size": 90000, "width": 900, "height": 1200},
    ]
    await post(family, payload)
    assert asked == ["big"]


async def test_a_member_can_see_what_they_forwarded(family):
    await _linked(family)
    await post(family, update(text="only amma forwarded this"))
    mine = await family.client.get("/v1/artifacts", headers=family.h("amma"))
    theirs = await family.client.get("/v1/artifacts", headers=family.h("appa"))
    assert len(mine.json()) == 1 and theirs.json() == []


# ----------------------------------------------------------------------------
# what is not a notice
# ----------------------------------------------------------------------------

async def test_an_edit_is_not_a_second_notice(family):
    await _linked(family)
    r = await post(family, update(text="corrected", key="edited_message"))
    assert r.json() == {"received": 0, "refused": 0}
    assert await pool().fetchval("SELECT count(*) FROM input_artifacts") == 0


async def test_a_channel_post_has_nobody_to_attribute_it_to(family):
    await _linked(family)
    r = await post(family, update(text="from the school channel", key="channel_post"))
    assert r.json() == {"received": 0, "refused": 0}


async def test_another_bot_in_the_group_is_never_a_notice(family):
    await _linked(family)
    r = await post(family, update(text=f"@{BOT} hello", is_bot=True))
    assert r.json() == {"received": 0, "refused": 0}


async def test_a_sticker_carries_nothing(family):
    await _linked(family)
    payload = update(media={"kind": "sticker", "file_id": "x", "emoji": "\U0001f389"})
    r = await post(family, payload)
    assert r.json() == {"received": 0, "refused": 0}


def test_parse_takes_nothing_from_an_empty_update():
    assert telegram.parse({}) is None
    assert telegram.parse({"update_id": 1}) is None


def test_a_payload_telegram_will_not_carry_is_not_a_payload():
    assert not telegram.valid_payload("has spaces")
    assert not telegram.valid_payload("x" * (telegram.PAYLOAD_MAX + 1))
    assert not telegram.valid_payload("")
    assert telegram.valid_payload("lnk_AbC-123_x")


def test_the_start_command_is_read_the_way_a_group_writes_it():
    """In a group Telegram appends the bot's name to the command."""
    m = telegram.parse(update(text=f"/start@{BOT} lnk_abc", chat_id=-1, chat_type="supergroup",
                              forwarded=False), bot_username=BOT)
    assert m is not None and m.start_payload == "lnk_abc"
    m = telegram.parse(update(text="/startgroup lnk_abc", forwarded=False), bot_username=BOT)
    assert m is not None and m.start_payload is None


# ----------------------------------------------------------------------------
# reminders out
# ----------------------------------------------------------------------------

async def test_a_reminder_reaches_a_linked_member_with_no_template_and_no_window(family, no_network):
    """The whole reason to offer this rail: WhatsApp needs an approved utility
    template to say anything to a parent who did not message us yesterday, and
    this needs nothing."""
    from familyos import reminders

    await _linked(family)
    row = {"id": uuid.uuid4(), "member_id": uuid.UUID(family.amma["id"]),
           "telegram_chat_id": CHAT}
    await reminders.CHANNELS["telegram"](row, "Sports day", "Tomorrow, 8am.")
    assert no_network == [(CHAT, "Sports day\n\nTomorrow, 8am.")]


async def test_a_reminder_to_an_unlinked_member_fails_loudly(family):
    from familyos import reminders

    with pytest.raises(RuntimeError, match="not linked Telegram"):
        await reminders.CHANNELS["telegram"]({"id": uuid.uuid4(), "telegram_chat_id": None},
                                             "Sports day", "Tomorrow.")


# ----------------------------------------------------------------------------
# one word after a forward
# ----------------------------------------------------------------------------

async def _consented_kids(family):
    await family.consent(family.older)
    await family.consent(family.younger)
    for kid, school in ((family.older, "First Cry"), (family.younger, "Aachi Global")):
        await family.client.patch(f"/v1/members/{kid['id']}/school", headers=family.h("amma"),
                                  json={"school": school, "class_label": "x"})


async def _subjects(family, artifact_id):
    r = await family.client.get(f"/v1/artifacts/{artifact_id}", headers=family.h("amma"))
    return set(r.json()["subject_member_ids"])


async def test_a_childs_name_after_a_forward_says_whose_it_was(family, no_network):
    await _linked(family)
    await _consented_kids(family)
    await post(family, update(text="Dear Parents, PTM on Friday for all.", message_id=50))
    r = await post(family, update(text=family.older["display_name"], message_id=51, forwarded=False))
    assert r.status_code == 202 and r.json()["tagged"] == [family.older["display_name"]]
    assert "Attached to " + family.older["display_name"] in no_network[-1][1]
    artifact_id = await pool().fetchval("SELECT id FROM input_artifacts WHERE channel = 'telegram'")
    assert await _subjects(family, artifact_id) == {family.older["id"]}
    # The parent's word, not an inference: a re-read leaves it alone.
    assert await pool().fetchval("SELECT bool_and(NOT inferred) FROM artifact_subjects WHERE artifact_id = $1", artifact_id)
    # And the name itself was never stored as a notice.
    assert await pool().fetchval("SELECT count(*) FROM input_artifacts") == 1
    # The notice is read again so its obligations name the child.
    assert await pool().fetchval("SELECT count(*) FROM jobs WHERE kind = 'extract_artifact'") >= 2


async def test_a_school_name_after_a_forward_is_everyone_there(family, no_network):
    await _linked(family)
    await _consented_kids(family)
    await post(family, update(text="Holiday on Monday.", message_id=60))
    r = await post(family, update(text="first cry", message_id=61, forwarded=False))
    assert r.json()["tagged"] == [family.older["display_name"]]


async def test_one_word_covers_the_last_few_forwards(family, no_network):
    """Three circulars, then the name: all three are the same child's."""
    await _linked(family)
    await _consented_kids(family)
    for i in range(3):
        await post(family, update(text=f"Circular {i}: something on a date.", message_id=70 + i))
    await post(family, update(text=family.younger["display_name"], message_id=79, forwarded=False))
    rows = await pool().fetch("SELECT artifact_id FROM artifact_subjects WHERE member_id = $1",
                              uuid.UUID(family.younger["id"]))
    assert len(rows) == 3


async def test_the_word_does_not_touch_a_notice_a_parent_already_tagged(family, no_network):
    await _linked(family)
    await _consented_kids(family)
    await post(family, update(text="For the older one.", message_id=80))
    first = await pool().fetchval("SELECT id FROM input_artifacts WHERE channel = 'telegram'")
    await family.client.put(f"/v1/artifacts/{first}/subjects", headers=family.h("amma"), json=[family.older["id"]])
    await post(family, update(text="For the younger one.", message_id=81))
    await post(family, update(text=family.younger["display_name"], message_id=82, forwarded=False))
    assert await _subjects(family, first) == {family.older["id"]}


async def test_a_name_with_nothing_recent_attaches_nothing_and_says_so(family, no_network):
    await _linked(family)
    await _consented_kids(family)
    r = await post(family, update(text=family.older["display_name"], message_id=90, forwarded=False))
    assert r.json()["tagged"] == []
    assert "Nothing recent" in no_network[-1][1]
    assert await pool().fetchval("SELECT count(*) FROM input_artifacts") == 0


async def test_a_child_without_consent_cannot_be_attached_by_name_either(family, no_network):
    await _linked(family)
    await post(family, update(text="Dear Parents, something.", message_id=95))
    r = await post(family, update(text=family.older["display_name"], message_id=96, forwarded=False))
    assert r.json()["reason"] == "consent_required"
    assert "no consent" in no_network[-1][1]
    artifact_id = await pool().fetchval("SELECT id FROM input_artifacts WHERE channel = 'telegram'")
    assert await _subjects(family, artifact_id) == set()


async def test_a_circular_that_starts_with_a_name_is_still_a_circular(family, no_network):
    await _linked(family)
    await _consented_kids(family)
    r = await post(family, update(text=family.older["display_name"] + " has been selected for the inter-school "
                                       "quiz on 14 November. Kindly send the consent slip by Monday.", message_id=97))
    assert r.json()["received"] == 1
    assert await pool().fetchval("SELECT count(*) FROM input_artifacts") == 1


async def test_a_name_an_hour_after_the_forward_still_lands_on_it(family, no_network):
    """The real case: forwarded at tea, named after dinner. One untagged
    notice is not ambiguous at any age."""
    await _linked(family)
    await _consented_kids(family)
    await post(family, update(text="Dear Parents, PTM on Friday.", message_id=100))
    await pool().execute("UPDATE input_artifacts SET received_at = NOW() - interval '3 hours'")
    r = await post(family, update(text=family.older["display_name"], message_id=101, forwarded=False))
    assert r.json()["tagged"] == [family.older["display_name"]]
    artifact_id = await pool().fetchval("SELECT id FROM input_artifacts WHERE channel = 'telegram'")
    assert await _subjects(family, artifact_id) == {family.older["id"]}


async def test_outside_the_window_only_the_latest_forward_takes_the_name(family, no_network):
    """Two old untagged forwards: the name goes on the later one only. Which
    of several things from yesterday it meant is a guess, and guesses are
    not made."""
    await _linked(family)
    await _consented_kids(family)
    await post(family, update(text="Older circular.", message_id=110))
    await post(family, update(text="Newer circular.", message_id=111))
    await pool().execute("UPDATE input_artifacts SET received_at = NOW() - interval '3 hours' WHERE source->>'message_id' = '110'")
    await pool().execute("UPDATE input_artifacts SET received_at = NOW() - interval '2 hours' WHERE source->>'message_id' = '111'")
    await post(family, update(text=family.younger["display_name"], message_id=112, forwarded=False))
    tagged = await pool().fetch("SELECT a.source->>'message_id' AS mid FROM artifact_subjects s "
                                "JOIN input_artifacts a ON a.id = s.artifact_id")
    assert [r["mid"] for r in tagged] == ["111"]


# ----------------------------------------------------------------------------
# Ask, from the phone
# ----------------------------------------------------------------------------

class _Scripted:
    name = "scripted"

    def __init__(self, answer): self.answer, self.seen = answer, []

    async def reply(self, system, messages, schema=None):
        self.seen.append(messages[-1]["content"])
        return self.answer


async def test_a_question_in_a_private_chat_is_answered_not_filed(family, no_network, monkeypatch):
    from familyos import chat
    monkeypatch.setattr(settings, "ask_enabled", True)
    monkeypatch.setattr(settings, "console_url", "https://home.example/app/")
    model = _Scripted({"say": "The Airtel bill is due on 16 Oct [n1].", "proposals": [
        {"kind": "todo", "title": "Pay the Airtel bill", "due_date": "2026-10-16", "due_time": None, "member": "Amma", "note": None}]})
    chat.use_model(model)
    try:
        await _linked(family)
        r = await post(family, update(text="when is the airtel bill due?", forwarded=False, message_id=31))
        assert r.status_code in (200, 202) and r.json().get("answered") is True, r.text
        said = no_network[-1][1]
        assert said.startswith("The Airtel bill is due on 16 Oct.") and "[n1]" not in said
        assert "I could also add the to-do \u201cPay the Airtel bill\u201d by 2026-10-16" in said and "https://home.example/app#/chat" in said
        assert model.seen == ["when is the airtel bill due?"]
        assert await pool().fetchval("SELECT count(*) FROM input_artifacts WHERE channel = 'telegram'") == 0
        # "ask ..." works without the question mark; the word itself is not sent.
        await post(family, update(text="ask what is still undecided", forwarded=False, message_id=32))
        assert model.seen[-1] == "what is still undecided"
    finally:
        chat.use_model(chat.RefusingModel())


async def test_a_forward_that_asks_something_is_still_a_notice_and_a_group_question_is_not_answered(family, no_network, monkeypatch):
    from familyos import chat
    monkeypatch.setattr(settings, "ask_enabled", True)
    model = _Scripted({"say": "x", "proposals": []})
    chat.use_model(model)
    try:
        await _linked(family)
        r = await post(family, update(text="Will the school reopen on 26 Oct?", forwarded=True, message_id=41))
        assert r.status_code in (200, 202) and r.json().get("received") == 1
        assert model.seen == []
        r = await post(family, update(text="@familyos_test_bot when is the PTM?", forwarded=False, chat_type="supergroup", chat_id=-100555, message_id=42))
        assert model.seen == [] and r.json().get("answered") is None
    finally:
        chat.use_model(chat.RefusingModel())


async def test_without_a_model_the_phone_is_told_plainly(family, no_network, monkeypatch):
    monkeypatch.setattr(settings, "ask_enabled", True)
    await _linked(family)
    r = await post(family, update(text="what is due this week?", forwarded=False, message_id=51))
    assert r.status_code in (200, 202) and r.json().get("answered") is True
    assert no_network[-1][1].startswith("I cannot answer here:")
