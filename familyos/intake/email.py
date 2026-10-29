"""Forwarding-email adapter: parse a raw message into what the gateway needs.

Sender authentication is read from the Authentication-Results header that
the receiving mail provider adds (RFC 8601). The webhook that delivers the
message is authenticated with a shared secret, so this header is the
provider's, not the sender's; any copy the sender forged sits below it and
is ignored because only the topmost header is read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr

from familyos.settings import settings

# An inline image this large is a photo someone pasted, not a signature logo.
INLINE_IMAGE_MIN_BYTES = 20 * 1024

# Each attachment becomes an artifact and an extraction job, and a few hundred kilobytes of mail can carry thousands of tiny ones. A school
# circular has a handful; the rest are counted and left out.
MAX_ATTACHMENTS = 25


@dataclass
class Attachment:
    filename: str | None
    media_type: str
    data: bytes


@dataclass
class ParsedEmail:
    sender: str | None
    recipients: list[str]
    subject: str | None
    message_id: str | None
    date: str | None
    sender_authenticated: bool
    attachments: list[Attachment] = field(default_factory=list)
    text: str = ""          # the body as plain words (HTML stripped), for the one-time-code check only
    attachments_over: int = 0     # how many more than MAX_ATTACHMENTS the mail carried, left out


def _text(value, limit: int) -> str:
    """A header as text that is safe to store: no NUL (Postgres jsonb cannot hold U+0000, and a mail that cannot be stored stalls a Gmail
    mailbox for good), no other control characters, and no longer than a header has any need to be."""
    return "".join(ch for ch in str(value) if ch == "\t" or ch >= " " and ch != "\x7f")[:limit]


def parse(raw: bytes, *, authserv_id: str | None = None) -> ParsedEmail:
    msg: EmailMessage = BytesParser(policy=policy.default).parsebytes(raw)
    sender = _text(parseaddr(_text(msg.get("From", ""), 1000))[1], 320).lower() or None
    recipients = [_text(addr, 320).lower() for _, addr in getaddresses(
        [_text(v, 4000) for h in ("Delivered-To", "X-Original-To", "To", "Cc") for v in list(msg.get_all(h, []))[:20]]) if addr][:100]
    message_id = _text(msg.get("Message-ID", ""), 998).strip().strip("<>") or None
    attachments: list[Attachment] = []
    over = 0
    for attachment in _attachments(msg):
        if len(attachments) < MAX_ATTACHMENTS:
            attachments.append(attachment)       # the rest are counted and dropped as they come, never all held at once
        else:
            over += 1
    return ParsedEmail(
        sender=sender,
        recipients=list(dict.fromkeys(recipients)),
        subject=_text(msg.get("Subject", ""), 1000) or None,
        message_id=message_id,
        date=_text(msg.get("Date", ""), 100) or None,
        sender_authenticated=sender_authenticated(msg, sender, authserv_id),
        attachments=attachments,
        attachments_over=over,
        text=_body_text(msg),
    )


def _body_text(msg: EmailMessage) -> str:
    """The body as words, cheaply and only as far as a one-time-code check needs."""
    from familyos import htmltext
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is None:
            return ""
        text = part.get_content()
        if part.get_content_type() == "text/html":
            text = htmltext.text_of(text)      # linear: the patterns this replaced were quadratic on an unclosed tag
        return text[:20000]
    except Exception:  # noqa: BLE001 - a body that will not decode is not a code
        return ""


def inbound_token(address: str, domain: str) -> str | None:
    """The household token in <token>[+tag]@<domain>, or None."""
    local, _, host = (address or "").lower().rpartition("@")
    if host != domain.lower() or not local:
        return None
    return local.split("+", 1)[0]


def authserv_id(header: str) -> str:
    """The authserv-id naming who made the verdict: the first token of the
    header, before the version and the first ';' (RFC 8601 s.2.2)."""
    first = header.split(";", 1)[0].strip().split()
    return first[0].lower() if first else ""


def sender_authenticated(msg: EmailMessage, sender: str | None, trusted_id: str | None = None) -> bool:
    """True when *our* provider's verdict says the From domain is genuine:
    DMARC passed, or DKIM passed for the From domain exactly.

    Only a header whose authserv-id matches `settings.inbound_authserv_id` is
    read (RFC 8601 s.5): anyone can add an Authentication-Results header, so
    the id is what separates the receiving provider's verdict from one the
    sender wrote themselves. Without that setting nothing is authenticated
    and mail waits in quarantine for a guardian, which is the safe failure.

    A parent domain's signature does not authenticate a subdomain here; that
    is relaxed DMARC alignment, and the dmarc=pass branch already covers it.
    """
    if not sender or "@" not in sender:
        return False
    trusted = (trusted_id or settings.inbound_authserv_id or "").strip().lower()
    if not trusted:
        return False
    domain = sender.rsplit("@", 1)[1]
    for raw in msg.get_all("Authentication-Results") or []:
        header = str(raw)
        if authserv_id(header) != trusted:
            continue
        # The provider prepends its own verdict, so the first header bearing
        # our authserv-id is genuine; a forged copy sits below it, unread.
        return _passes(header.lower(), domain)
    return False


def _passes(verdict: str, domain: str) -> bool:
    if re.search(r"\bdmarc=pass\b", verdict):
        return True
    return any(match.group(1).rstrip(".") == domain
               for match in re.finditer(r"\bdkim=pass\b[^;]*?header\.d=([a-z0-9.-]+)", verdict))


def _attachments(msg: EmailMessage):
    # walk() descends into attached messages too, so a notice forwarded "as
    # attachment" still yields its PDF.
    for part in msg.walk():
        if part.is_multipart():
            continue
        disposition = part.get_content_disposition()
        content_type = part.get_content_type()
        if disposition == "attachment":
            pass
        elif content_type.startswith("image/") and (disposition == "inline" or part.get_filename()):
            payload = part.get_payload(decode=True) or b""
            if len(payload) < INLINE_IMAGE_MIN_BYTES:
                continue
        else:
            continue
        data = part.get_payload(decode=True) or b""
        yield Attachment(filename=part.get_filename(), media_type=content_type, data=data)
