"""The intake and trust gateway: every channel lands here.

Four steps, in order, for every item:

  1. Receive:  the channel adapter turns what arrived into an InboundEnvelope.
  2. Identify: who sent it? A signed-in member, or an email sender matched
               to a member and authenticated by the receiving provider.
  3. Decide:   accept, quarantine (a guardian must vouch for it) or reject
               (nothing is stored).
  4. Scope:    who may see it. Everything starts private to its sender
               unless the sender chose shared.

Only then is the original stored. No model runs before this point, and
nothing downstream ever sees an item that was not accepted.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

from familyos import artifacts, audit
from familyos.db import pool
from familyos.extraction import service as extraction
from familyos.identity import (
    Principal,
    household_by_inbound_token,
    member_by_email,
    member_by_phone,
    member_by_telegram,
)
from familyos.intake import email as email_adapter
from familyos.intake import telegram as telegram_adapter
from familyos.intake import whatsapp as whatsapp_adapter
from familyos.intake.sniff import ALLOWED, sniff
from familyos.settings import settings


class Rejected(Exception):
    def __init__(self, reason: str, status: int = 422):
        super().__init__(reason)
        self.reason = reason
        self.status = status


@dataclass
class InboundEnvelope:
    channel: str
    data: bytes
    media_type: str
    filename: str | None = None
    source: dict = field(default_factory=dict)
    note: str | None = None


# ----------------------------------------------------------------------------
# share sheet / upload
# ----------------------------------------------------------------------------

async def receive_upload(p: Principal, data: bytes, *, filename: str | None, declared_type: str | None,
                         visibility: str = "private", subject_member_ids: list[uuid.UUID] | None = None,
                         note: str | None = None) -> tuple[dict, bool]:
    envelope = InboundEnvelope(channel="upload", data=data, media_type=sniff(data, declared_type),
                               filename=_clean_filename(filename), note=note)
    if not data:
        await _rejected(p.household_id, p, "empty")
    if len(data) > settings.max_upload_bytes:
        await _rejected(p.household_id, p, "too_large", status=413)
    if envelope.media_type not in ALLOWED:
        await _rejected(p.household_id, p, "unsupported_type", status=415)
    digest = artifacts.sha256(data)
    async with pool().acquire() as conn, conn.transaction():
        artifact, duplicate = await artifacts.create(conn, p.household_id, artifacts.NewArtifact(
            data=data, media_type=envelope.media_type, channel="upload", visibility=visibility, status="accepted",
            submitted_by=p.member_id, filename=envelope.filename, note=note,
            # The same member sending the same bytes again gets the same artifact.
            dedup_key=f"upload:{p.member_id}:{digest}",
            subject_member_ids=tuple(subject_member_ids or ())))
        if not duplicate:
            await extraction.enqueue(conn, p.household_id, [artifact["id"]], member_id=p.member_id)
        return artifact, duplicate


# ----------------------------------------------------------------------------
# the share sheet and shortcuts
# ----------------------------------------------------------------------------

SHARE_TEXT_MAX = 200_000


HEADLINE_MAX = 90
import re as _re  # noqa: E402 - after the module's own names it needs

_DATEISH = _re.compile(r"^\W*\d{1,4}[\s./-]+(?:[A-Za-z]{3,9}|\d{1,2})[\s./-]+\d{2,4}(?:[\s,]+\d{1,2}[:.]\d{2}\s*(?:am|pm)?)?\W*$", _re.I)


def headline_for(*, text: str | None, url: str | None, note: str | None, media_type: str) -> str | None:
    """One line for the Inbox, from the thing itself."""
    if text:
        for line in text.splitlines():
            words = " ".join(line.split())
            # A line that is only a date, a time or punctuation says nothing;
            # neither does one with fewer than two real words.
            if len(words) < 4 or _DATEISH.match(words) or len(_re.findall(r"[A-Za-z]{2,}", words)) < 2:
                continue
            return words[:HEADLINE_MAX].rstrip(" ,;:-")
        return None
    if url:
        host = urlsplit_host(url) or url
        return f"A page from {host}"[:HEADLINE_MAX]
    if media_type.startswith("image/"):
        return (" ".join(note.split())[:HEADLINE_MAX] if note else "A photo")
    return (" ".join(note.split())[:HEADLINE_MAX] if note else None)


async def name_old_shares(limit: int = 500) -> int:
    """Shares from before headlines were kept: named now, from their text,
    the way a new one is. Runs at startup; nothing to do the second time."""
    rows = await pool().fetch(
        "SELECT id, household_id, media_type, blob_id, sha256, size_bytes, source FROM input_artifacts "
        "WHERE channel = 'share' AND media_type LIKE 'text/%' AND parent_id IS NULL AND (source->>'headline') IS NULL "
        "ORDER BY received_at DESC LIMIT $1", limit)
    named = 0
    for row in rows:
        try:
            data = await artifacts.read_bytes(row["household_id"], dict(row))
            said = headline_for(text=data.decode("utf-8", "replace"), url=None, note=None, media_type=row["media_type"])
        except Exception:  # noqa: BLE001 - an unreadable old share keeps its filename
            continue
        if said:
            await pool().execute("UPDATE input_artifacts SET source = COALESCE(source, '{}'::jsonb) || jsonb_build_object('headline', $2::text) WHERE id = $1", row["id"], said)
            named += 1
    return named


async def receive_share(p: Principal, *, data: bytes | None = None, text: str | None = None, url: str | None = None,
                        filename: str | None = None, declared_type: str | None = None,
                        note: str | None = None, visibility: str = "private", tag: str | None = None) -> dict:
    """What a phone handed over: a file or image, a piece of text, or a URL.

    The phone says nothing about where it came from -- no app, no group --
    so this rail is the plainest of all: the bytes, private to the member
    who shared them. A short text that names a child is a tag for what was
    shared just before, the same rule as a word after a Telegram forward. A
    bare URL is read once as a public page (class 1, no credential) and kept
    as text with the URL beside it; a page that needs a login is kept as the
    URL alone, said plainly.

    `tag` is the child's (or school's) name sent along with the share -- the
    shortcut asked "for whom?" -- so the tagging arrives with the notice
    instead of as a second share. Recorded as the parent's own tagging.

    Returns {"tagged": [...]} or {"artifact": row, "duplicate": bool, "tagged": [...]}.
    """
    text = (text or "").strip() or None
    url = (url or "").strip() or None
    if data is None and text and not url:
        tagged = await tag_by_word(p.household_id, p.member_id, "share", text)
        if tagged is not None:
            return {"tagged": tagged}
    source: dict = {"via": "share"}
    if data is not None and data:
        media_type = sniff(data, declared_type)
        name = _clean_filename(filename)
    elif text:
        data, media_type, name = text[:SHARE_TEXT_MAX].encode(), "text/plain", "shared.txt"
        source["shared_as"] = "text"
    elif url:
        from familyos.execution import disposable
        source["url"] = url[:500]
        try:
            page = await disposable.read(url, frozenset({(urlsplit_host(url))}))
            data, media_type, name = page.text.encode(), "text/plain", "page.txt"
            source["shared_as"], source["landed_on"] = "page", page.url
        except Exception as exc:  # noqa: BLE001 - a page that will not read is still a thing the family shared
            data, media_type, name = f"{url}\n\n(This page could not be read without signing in: {exc})".encode(), "text/plain", "link.txt"
            source["shared_as"], source["unreadable"] = "url", str(exc)[:200]
    else:
        await _rejected(p.household_id, p, "empty")
    if len(data) > settings.max_upload_bytes:
        await _rejected(p.household_id, p, "too_large", status=413)
    if media_type not in ALLOWED:
        await _rejected(p.household_id, p, "unsupported_type", status=415)
    # What to call it in a list, from what it is: a text's first line, a
    # page's address, the note that came with a picture. The reader's first
    # claim beats this once there is one; "shared.txt" never shows again.
    said = headline_for(text=text if source.get("shared_as") == "text" else None, url=url, note=note, media_type=media_type)
    if said:
        source["headline"] = said
    digest = artifacts.sha256(data)
    tagged_names: list[str] = []
    async with pool().acquire() as conn, conn.transaction():
        artifact, duplicate = await artifacts.create(conn, p.household_id, artifacts.NewArtifact(
            data=data, media_type=media_type, channel="share", visibility=visibility, status="accepted",
            submitted_by=p.member_id, filename=name, source=source, note=note,
            dedup_key=f"share:{p.member_id}:{digest}"))
        if tag and tag.strip():
            tagged_names = await _tag_artifact(conn, p.household_id, artifact["id"], tag)
            if tagged_names:
                # The tag may have shared it (the household's rule); the reply says what is true now.
                artifact = dict(await conn.fetchrow(artifacts._SELECT + " WHERE a.id = $1", artifact["id"]))
        if not duplicate or tagged_names:
            await extraction.enqueue(conn, p.household_id, [artifact["id"]], member_id=p.member_id)
    return {"artifact": artifact, "duplicate": duplicate, "tagged": tagged_names}


async def _tag_artifact(conn, household_id: uuid.UUID, artifact_id: uuid.UUID, word: str) -> list[str]:
    """The word that came with the share names a child or a school: record it
    as the parent's own tagging on this notice. A word naming nobody is
    ignored -- the shortcut's list only offers names that exist."""
    from familyos.extraction import attribute
    children = [dict(r) for r in await conn.fetch(
        "SELECT m.id, m.display_name, m.school, "
        "EXISTS (SELECT 1 FROM consent_records c WHERE c.subject_member_id = m.id "
        "        AND c.purpose = 'household_records' AND c.withdrawn_at IS NULL) AS consented "
        "FROM members m WHERE m.household_id = $1 AND m.role = 'child'", household_id)]
    found = attribute.named_by_word(word, children)
    if not found:
        return []
    if not all(c["consented"] for c in children if c["id"] in found):
        await _rejected(household_id, None, "consent_required", status=409)
    await conn.execute("DELETE FROM artifact_subjects WHERE artifact_id = $1", artifact_id)
    await conn.executemany("INSERT INTO artifact_subjects (artifact_id, member_id, inferred) VALUES ($1, $2, FALSE)",
                           [(artifact_id, m) for m in found])
    await artifacts.share_for_children(conn, household_id, artifact_id, via="share_tag")
    return [c["display_name"] for c in children if c["id"] in found]


def urlsplit_host(url: str) -> str:
    from urllib.parse import urlsplit
    return (urlsplit(url).hostname or "").lower()


# ----------------------------------------------------------------------------
# forwarding email
# ----------------------------------------------------------------------------

def sender_domain(address: str | None) -> str | None:
    if not address or "@" not in address:
        return None
    return address.rsplit("@", 1)[-1].strip().lower() or None


async def _domain_is_trusted(household_id: uuid.UUID, sender: str) -> bool:
    domain = sender_domain(sender)
    if not domain:
        return False
    return bool(await pool().fetchval(
        "SELECT 1 FROM trusted_sender_domains WHERE household_id = $1 AND domain = $2",
        household_id, domain))


async def trust_sender_domain(conn, household_id: uuid.UUID, sender: str | None,
                              added_by: uuid.UUID | None) -> str | None:
    """Vouching for a message vouches for where it came from.

    The school's first circular waits; every one after it is read. Without
    this a guardian accepts the same sender every week, which is the kind of
    chore that teaches people to accept without looking.
    """
    domain = sender_domain(sender)
    if not domain:
        return None
    await conn.execute(
        "INSERT INTO trusted_sender_domains (household_id, domain, added_by) VALUES ($1, $2, $3) "
        "ON CONFLICT (household_id, domain) DO NOTHING", household_id, domain, added_by)
    return domain


async def receive_email(raw: bytes, recipient: str | None = None) -> tuple[dict, bool]:
    """A raw RFC 822 message posted by the mail provider. `recipient` is the
    SMTP envelope recipient when the provider supplies it; otherwise the
    household is found from the To/Cc/Delivered-To headers."""
    if len(raw) > settings.max_email_bytes:
        raise Rejected("too_large", status=413)
    message = email_adapter.parse(raw)
    household = None
    for address in ([recipient] if recipient else []) + message.recipients:
        token = email_adapter.inbound_token(address, settings.inbound_domain)
        if token and (household := await household_by_inbound_token(token)):
            break
    if household is None:
        # Unknown address: no household to hold it, so nothing is kept.
        raise Rejected("unknown_recipient", status=404)
    household_id = household["id"]

    member = await member_by_email(household_id, message.sender) if message.sender else None
    authenticated = message.sender_authenticated or not settings.require_sender_auth
    # Mail *to* the household address is the thing a family writes on a school
    # admission form. The school is not a member and never will be, so judging
    # it by membership quarantined the one flow the address exists for: the
    # circular arrived, said it could not be trusted, and sat there.
    #
    # Who wrote it is still what decides. A stranger is quarantined as before.
    # An institution whose own provider vouched for it -- DKIM or DMARC passing
    # under an authserv-id we trust -- is read, and shared with the household,
    # because a school writing to the family address wrote to the family.
    outsider = bool(member is None and authenticated and message.sender
                    and await _domain_is_trusted(household_id, message.sender))
    if member is None and not outsider:
        status, reason = "quarantined", "unknown_sender"
    elif member is not None and not authenticated:
        status, reason = "quarantined", "sender_not_authenticated"
    else:
        status, reason = "accepted", None
    submitted_by = member["id"] if member and status == "accepted" else None
    # Nobody forwarded it, so it belongs to the household rather than a member.
    visibility = "shared" if outsider and status == "accepted" else "private"

    source = {"from": message.sender, "to": message.recipients, "subject": message.subject,
              "message_id": message.message_id, "date": message.date, "sender_authenticated": message.sender_authenticated,
              "skipped_attachments": [{"media_type": a.media_type, "size_bytes": len(a.data)}
                                      for a in message.attachments if sniff(a.data, a.media_type) not in ALLOWED]}
    dedup_key = f"email:{message.message_id}" if message.message_id else f"email-sha:{artifacts.sha256(raw)}"
    async with pool().acquire() as conn, conn.transaction():
        parent, duplicate = await artifacts.create(conn, household_id, artifacts.NewArtifact(
            data=raw, media_type="message/rfc822", channel="email", visibility=visibility, status=status,
            submitted_by=submitted_by, source=source, dedup_key=dedup_key, quarantine_reason=reason),
            actor_kind="inbound")
        if duplicate:
            return parent, True
        stored = [parent["id"]]
        for attachment in message.attachments:
            media_type = sniff(attachment.data, attachment.media_type)
            if media_type not in ALLOWED or not attachment.data:
                continue
            child, _ = await artifacts.create(conn, household_id, artifacts.NewArtifact(
                # An attachment follows its covering mail, as it does everywhere else.
                data=attachment.data, media_type=media_type, channel="email_attachment", visibility=visibility,
                status=status, submitted_by=submitted_by, filename=_clean_filename(attachment.filename),
                parent_id=parent["id"], quarantine_reason=reason), actor_kind="inbound")
            stored.append(child["id"])
        if status == "accepted":
            # Quarantined mail is not read until a guardian accepts it.
            await extraction.enqueue(conn, household_id, stored, member_id=submitted_by)
        parent = dict(await conn.fetchrow(artifacts._SELECT + " WHERE a.id = $1", parent["id"]))
    return parent, False


# ----------------------------------------------------------------------------
# connected Gmail
# ----------------------------------------------------------------------------

async def receive_gmail(household_id: uuid.UUID, member_id: uuid.UUID, raw: bytes, *,
                        gmail_id: str, thread_id: str | None = None) -> tuple[dict, bool]:
    """One message out of a member's own connected mailbox.

    The trust question here is not the one forwarding asks. Forwarded mail
    arrives from a stranger at an address that says which household it was
    aimed at, so the sender has to be matched to a member and authenticated
    before anything is kept. This message was fetched with the member's own
    token out of the member's own mailbox: nobody chose to send it to us, and
    the sender is the school, not the member.

    So it mirrors the WhatsApp bridge rather than forwarding. The member
    *received* it, so it is stored for them, privately, and the school's
    address goes in `source` the way an email's From does. There is no
    quarantine lane: a message we cannot attribute is a message we would not
    have been given.

    Attachments become children, exactly as they do for forwarded mail -- the
    circular is nearly always the PDF, and the covering note is nearly always
    where the date is.
    """
    if len(raw) > settings.max_email_bytes:
        raise Rejected("too_large", status=413)
    message = email_adapter.parse(raw)
    source = {"from": message.sender, "to": message.recipients, "subject": message.subject,
              "message_id": message.message_id, "date": message.date,
              "sender_authenticated": message.sender_authenticated,
              "channel": "gmail", "gmail_id": gmail_id, "thread_id": thread_id,
              "skipped_attachments": [{"media_type": a.media_type, "size_bytes": len(a.data)}
                                      for a in message.attachments if sniff(a.data, a.media_type) not in ALLOWED]}
    async with pool().acquire() as conn, conn.transaction():
        parent, duplicate = await artifacts.create(conn, household_id, artifacts.NewArtifact(
            data=raw, media_type="message/rfc822", channel="gmail", visibility="private", status="accepted",
            submitted_by=member_id, source=source,
            # Gmail's own id, so re-reading an overlapping window stores
            # nothing new and a restarted poller is safe -- scoped to the
            # member, because two of them can connect the same account. A
            # shared family mailbox would otherwise store one private copy
            # belonging to whoever polled first, and the other would never see
            # it. Each gets their own; identical bytes arriving twice is
            # already handled downstream, where the later copy's tasks are
            # superseded by the first.
            dedup_key=f"gmail:{member_id}:{gmail_id}"), actor_kind="inbound")
        if duplicate:
            return parent, True
        stored = [parent["id"]]
        for attachment in message.attachments:
            media_type = sniff(attachment.data, attachment.media_type)
            if media_type not in ALLOWED or not attachment.data:
                continue
            child, _ = await artifacts.create(conn, household_id, artifacts.NewArtifact(
                data=attachment.data, media_type=media_type, channel="gmail_attachment", visibility="private",
                status="accepted", submitted_by=member_id,
                filename=_clean_filename(attachment.filename), parent_id=parent["id"]), actor_kind="inbound")
            stored.append(child["id"])
        await extraction.enqueue(conn, household_id, stored, member_id=member_id)
        parent = dict(await conn.fetchrow(artifacts._SELECT + " WHERE a.id = $1", parent["id"]))
    return parent, False


# ----------------------------------------------------------------------------
# WhatsApp (forwarded to the household's business number)
# ----------------------------------------------------------------------------

async def tag_by_word_whatsapp(message: whatsapp_adapter.Message) -> list[str] | None:
    """The word, on WhatsApp. Nothing is said back -- a reply there costs a
    template outside the 24-hour window -- but the tagging is the same."""
    if message.media:
        return None
    member = await member_by_phone(message.sender)
    if member is None:
        return None
    return await tag_by_word(member["household_id"], member["id"], "whatsapp", message.text)


async def receive_whatsapp(message: whatsapp_adapter.Message, *, fetch=None,
                           extra_source: dict | None = None) -> list[tuple[dict, bool]]:
    """One forwarded message. Text becomes an artifact; each attachment becomes
    a child of it, the way an email's attachments do.

    The sender is already verified by Meta, so there is no quarantine lane
    here: either the number belongs to a member, in which case it is as trusted
    as an upload, or it belongs to nobody and there is no household to put it
    in. Email can quarantine because the address on it says which household it
    was aimed at; a WhatsApp message carries no such thing."""
    member = await member_by_phone(message.sender)
    if member is None:
        # Nothing is stored, and nothing is said back: a stranger messaging the
        # business number learns only that it exists.
        raise Rejected("unknown_sender", status=404)
    household_id, member_id = member["household_id"], member["id"]

    source = {"from": message.sender, "from_name": message.sender_name,
              "message_id": message.message_id, "sent_at": message.sent_at,
              "forwarded": message.forwarded, "channel": "whatsapp",
              **(extra_source or {})}

    downloaded: list[tuple[whatsapp_adapter.Media, bytes, str]] = []
    for media in message.media:
        data, media_type = await whatsapp_adapter.download(
            media.media_id, access_token=settings.whatsapp_access_token,
            api_base=settings.whatsapp_api_base, fetch=fetch)
        if not data or len(data) > settings.max_upload_bytes:
            continue
        sniffed = sniff(data, media_type)
        if sniffed not in ALLOWED:
            continue
        downloaded.append((media, data, sniffed))

    body = (message.text or "").strip()
    if not body and not downloaded:
        raise Rejected("empty")

    out: list[tuple[dict, bool]] = []
    async with pool().acquire() as conn, conn.transaction():
        # The message itself, even when it only carried a file: the words
        # around a forwarded photo are often where the date is.
        parent, duplicate = await artifacts.create(conn, household_id, artifacts.NewArtifact(
            data=(body or "(no text)").encode(), media_type="text/plain", channel="whatsapp",
            visibility="private", status="accepted", submitted_by=member_id, source=source,
            dedup_key=f"whatsapp:{message.message_id}"), actor_kind="inbound")
        out.append((parent, duplicate))
        if duplicate:
            return out
        stored = [parent["id"]]
        for media, data, media_type in downloaded:
            child, _ = await artifacts.create(conn, household_id, artifacts.NewArtifact(
                data=data, media_type=media_type, channel="whatsapp_media", visibility="private",
                status="accepted", submitted_by=member_id, filename=_clean_filename(media.filename),
                parent_id=parent["id"], source={"caption": media.caption}), actor_kind="inbound")
            stored.append(child["id"])
            out.append((child, False))
        await extraction.enqueue(conn, household_id, stored, member_id=member_id)
    return out


# ----------------------------------------------------------------------------
# one word after a forward: whom it was for
# ----------------------------------------------------------------------------

# How long after forwarding a parent can still say whose it was. Long enough
# to forward three things and then type a name; short enough that tonight's
# word does not land on this morning's circular.
TAG_WINDOW = dt.timedelta(minutes=30)


async def tag_by_word(household_id: uuid.UUID, member_id: uuid.UUID, channel: str,
                      text: str | None) -> list[str] | None:
    """A parent forwards a circular, then types "varali". The circular is
    Varali's.

    This is the cheapest place a forward's subject can be said: the moment of
    forwarding, by the person who knows, in the app they are already in. A
    forward carries no group and often no class, so something has to say it;
    a tap in the console later is the wrong something.

    The word is matched to the children's names and schools. It applies to
    every notice this member sent on this channel in the last TAG_WINDOW that
    no person has tagged yet -- or, when there is none that recent, to the
    single most recent untagged one -- and is recorded as the parent's own tagging --
    not an inference -- so a re-read never undoes it. The tagged notices are
    read again, so their obligations name the child too.

    Returns the display names tagged, [] when the word named a child but
    there was nothing recent to attach it to, or None when the text was not
    a name at all and is a notice like any other. A child without consent is
    refused outright: their name is known, and still not usable.
    """
    from familyos.extraction import attribute
    async with pool().acquire() as conn, conn.transaction():
        children = [dict(r) for r in await conn.fetch(
            "SELECT m.id, m.display_name, m.school, m.role, "
            "EXISTS (SELECT 1 FROM consent_records c WHERE c.subject_member_id = m.id "
            "        AND c.purpose = 'household_records' AND c.withdrawn_at IS NULL) OR m.role <> 'child' AS consented "
            "FROM members m WHERE m.household_id = $1", household_id)]
        # An adult's name tags too -- a passport, a policy, a bill that is
        # theirs -- and an adult needs no consent to be named.
        found = attribute.named_by_word(text, children)
        if found:
            # An adult's name counts only on its own ("archana"), never inside a
            # sentence: "only amma forwarded this" is a message, not a tag.
            short = len((text or "").split()) <= 2
            found = [m for m in found if short or any(c["id"] == m and c["role"] == "child" for c in children)]
        if not found:
            return None
        if not all(c["consented"] for c in children if c["id"] in found):
            await _rejected(household_id, None, "consent_required", status=409)
        untagged = ("SELECT a.id, a.received_at > NOW() - $4::interval AS recent FROM input_artifacts a "
                    "WHERE a.household_id = $1 AND a.submitted_by = $2 AND a.channel = $3 "
                    "AND a.parent_id IS NULL AND a.status = 'accepted' "
                    "AND NOT EXISTS (SELECT 1 FROM artifact_subjects s WHERE s.artifact_id = a.id AND NOT s.inferred) "
                    "ORDER BY a.received_at DESC LIMIT 50")
        rows = await conn.fetch(untagged, household_id, member_id, channel, TAG_WINDOW)
        # Everything forwarded in the window; failing that, the one most
        # recent untagged forward, however old. A name typed an hour after
        # the forward, with one obvious thing to land on, is not ambiguous --
        # it is only when there are several that recency has to decide.
        recent = [r["id"] for r in rows if r["recent"]] or [r["id"] for r in rows[:1]]
        if not recent:
            return []
        await conn.execute("DELETE FROM artifact_subjects WHERE artifact_id = ANY($1::uuid[])", recent)
        await conn.executemany(
            "INSERT INTO artifact_subjects (artifact_id, member_id, inferred) VALUES ($1, $2, FALSE)",
            [(a, m) for a in recent for m in found])
        await extraction.enqueue(conn, household_id, recent, member_id=member_id)
        adults = [c["id"] for c in children if c["id"] in found and c["role"] != "child" and c["id"] != member_id]
        for a in recent:
            await audit.record(household_id, "artifact.subjects_set", actor_member_id=member_id,
                               target_type="artifact", target_id=a,
                               detail={"member_ids": sorted(map(str, found)), "via": channel + "_word"}, conn=conn)
            await artifacts.share_for_children(conn, household_id, a, actor_member_id=member_id, via=channel + "_word")
            if adults:
                # Named for another adult, it is shared so they can see it.
                shared = await conn.fetchval("UPDATE input_artifacts SET visibility = 'shared' WHERE id = $1 AND visibility = 'private' RETURNING id", a)
                if shared:
                    await audit.record(household_id, "artifact.shared", actor_member_id=member_id, target_type="artifact", target_id=a,
                                       detail={"via": channel + "_word", "for": sorted(map(str, adults))}, conn=conn)
    return [c["display_name"] for c in children if c["id"] in found]


# ----------------------------------------------------------------------------
# Telegram (a bot the family writes to)
# ----------------------------------------------------------------------------

async def tag_by_word_telegram(message: telegram_adapter.Message) -> list[str] | None:
    """The word, on Telegram. The same refusals as a notice -- undirected
    group traffic, an unbound account -- then `tag_by_word`. A bot mention
    is not part of the word."""
    if not message.directed or message.media:
        return None
    member = await member_by_telegram(message.sender_id)
    if member is None:
        return None
    text = " ".join(t for t in (message.text or "").split() if not t.startswith("@"))
    return await tag_by_word(member["household_id"], member["id"], "telegram", text)


async def receive_telegram(message: telegram_adapter.Message, *, fetch=None,
                           extra_source: dict | None = None) -> list[tuple[dict, bool]]:
    """One message to the bot. The same shape as WhatsApp -- the words become
    an artifact, each file becomes a child of it -- with one extra refusal in
    front of it.

    **Undirected group traffic is refused here.** A bot whose privacy mode has
    been turned off, or which someone made a group admin, is handed every
    message in that group by Telegram. We decline all of it: `Message.directed`
    is false and nothing is stored, so a parents' group stays a parents' group
    even when the platform is willing to sell us the contents. This is the
    refusal that makes the rail safe to offer, and it belongs next to the other
    trust decisions rather than in a setting someone can undo.

    After that the logic is WhatsApp's. The sender is already authenticated --
    Telegram does not forge a from.id -- so there is no quarantine lane: either
    the account is bound to a member and is as trusted as an upload, or it is
    bound to nobody and there is no household to put it in.
    """
    if not message.directed:
        # Said by status, not by message: a group never learns the bot is
        # listening, because it is not.
        raise Rejected("not_addressed", status=403)
    member = await member_by_telegram(message.sender_id)
    if member is None:
        # Nothing stored and nothing said back, as on WhatsApp: a stranger who
        # finds the bot learns only that it exists.
        raise Rejected("unknown_sender", status=404)
    household_id, member_id = member["household_id"], member["id"]

    source = {"from_id": message.sender_id, "from_name": message.sender_name,
              "message_id": message.message_id, "chat_id": message.chat_id,
              "chat_type": message.chat_type, "sent_at": message.sent_at,
              "forwarded": message.forwarded, "channel": "telegram",
              **(extra_source or {})}

    downloaded: list[tuple[telegram_adapter.Media, bytes, str]] = []
    for media in message.media:
        data = await telegram_adapter.download(
            media.file_id, bot_token=settings.telegram_bot_token,
            api_base=settings.telegram_api_base, fetch=fetch)
        if not data or len(data) > settings.max_upload_bytes:
            continue
        sniffed = sniff(data, media.media_type)
        if sniffed not in ALLOWED:
            continue
        downloaded.append((media, data, sniffed))

    body = (message.text or "").strip()
    if not body and not downloaded:
        raise Rejected("empty")

    out: list[tuple[dict, bool]] = []
    async with pool().acquire() as conn, conn.transaction():
        parent, duplicate = await artifacts.create(conn, household_id, artifacts.NewArtifact(
            data=(body or "(no text)").encode(), media_type="text/plain", channel="telegram",
            visibility="private", status="accepted", submitted_by=member_id, source=source,
            # A Telegram message_id is unique within its chat and nowhere else,
            # so the chat is part of the key. Without it the same id from a
            # group and a private chat would collide and the second would be
            # silently swallowed as a duplicate.
            dedup_key=f"telegram:{message.chat_id}:{message.message_id}"), actor_kind="inbound")
        out.append((parent, duplicate))
        if duplicate:
            return out
        stored = [parent["id"]]
        for media, data, media_type in downloaded:
            child, _ = await artifacts.create(conn, household_id, artifacts.NewArtifact(
                data=data, media_type=media_type, channel="telegram_media", visibility="private",
                status="accepted", submitted_by=member_id, filename=_clean_filename(media.filename),
                parent_id=parent["id"], source={"caption": media.caption}), actor_kind="inbound")
            stored.append(child["id"])
            out.append((child, False))
        await extraction.enqueue(conn, household_id, stored, member_id=member_id)
    return out


# ----------------------------------------------------------------------------

async def _rejected(household_id: uuid.UUID, p: Principal | None, reason: str, status: int = 422):
    await audit.record(household_id, "intake.rejected", actor_member_id=p.member_id if p else None,
                       actor_kind="member" if p else "inbound", detail={"reason": reason})
    raise Rejected(reason, status)


def _clean_filename(name: str | None) -> str | None:
    if not name:
        return None
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[:255] or None
