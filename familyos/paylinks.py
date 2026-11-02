"""Phase one of paying: the bill's own link, one tap from the date.

A bill mail almost always carries its own way to pay -- the biller's pay
page, a payment-gateway link, or on Indian mail a UPI intent. FamilyOS finds
that link in the notice and keeps it on the obligation, so "Pay" sits beside
"Accept" on the date, on the Today page and in the Sunday digest. Tapping
it opens the biller's page or the UPI app with the amount filled in; the
person pays there, and the receipt comes back through the mailbox.

Nothing here pays. The function is pure and holds no credential; what it
returns is a URL that was already in the person's own mail.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

_UPI = re.compile(r"\bupi://pay\?[^\s<>\"')\]]+", re.I)
_URL = re.compile(r"\bhttps://[^\s<>\"')\]]+", re.I)
# Words that mark a link as the way to pay, in the path or the query.
_PAY_WORDS = re.compile(r"pay|bill|invoice|checkout|quickpay|recharge|premium|dues|fees?\b", re.I)
# Payment gateways and biller portals seen on Indian and Gulf bills.
_PAY_HOSTS = ("billdesk", "razorpay", "rzp.io", "paytm", "phonepe", "payu", "ccavenue", "instamojo", "cashfree",
              "airpay", "atom", "easebuzz", "juspay", "payzapp", "sbiepay", "network.ae", "payfort", "checkout.com")
# "Pay now:", "Payment link:" -- the words a mail puts right before the link.
_LEAD = re.compile(r"(pay(ment)?\s*(now|here|link|online)?|click here to pay|make (the )?payment)\s*[:\-\u2014]?\s*$", re.I)
# Links that are in every mail and never the way to pay.
_NOT = re.compile(r"unsubscribe|optout|opt-out|privacy|terms|preferences|list-manage|mailtrack|track(ing)?[./]|"
                  r"click\.|pixel|\.(png|jpe?g|gif|svg|css|js)(\?|$)|facebook|twitter|instagram|youtube|linkedin|"
                  r"play\.google|apps\.apple|whatsapp\.com|"
                  # Help pages about billing are not the way to pay.
                  r"//(support|help|docs|legal)\.|/legal/|/help/|/support/", re.I)
_TRAIL = ".,;:!?)]}'\""


def _clean(url: str) -> str:
    return url.rstrip(_TRAIL)


# Billers whose mail carries no pay link in words -- the bill is a QR in a
# PDF, or "pay in the app" -- but whose pay page is one, known, public URL.
# Checked by hand; add only what has been opened and seen to be the pay page.
KNOWN_PAY_PAGES = {
    "airtel.com": "https://www.airtel.in/pay-bill",
    "airtel.in": "https://www.airtel.in/pay-bill",
}


def from_email(raw: bytes) -> list[tuple[str, str]]:
    """Every link in a mail's HTML with the words it was hung on: "Pay now"
    => https://... The text the parser keeps drops the hrefs, which is where
    a bill's pay link almost always lives."""
    import email
    from email import policy
    try:
        msg = email.message_from_bytes(raw, policy=policy.default)
    except Exception:  # noqa: BLE001 - not a mail, then; nothing to find
        return []
    out: list[tuple[str, str]] = []
    for part in msg.walk():
        if part.get_content_type() != "text/html":
            continue
        try:
            html = part.get_content()
        except Exception:  # noqa: BLE001
            continue
        from familyos import htmltext
        out.extend(htmltext.anchors(html))       # linear; the pattern this replaced was quadratic on anchors that never close
    return out[:200]


def from_pdf_qr(data: bytes, *, max_pages: int = 3) -> list[str]:
    """What the QR codes on a bill say. Indian statements carry "scan and
    pay via any UPI app": a upi://pay intent with the payee and amount. Pages
    are rendered at modest resolution and read with a bundled decoder; a PDF
    with no codes, or a decoder that is not installed, is simply no link."""
    try:
        import pymupdf
        import zxingcpp
        from PIL import Image
    except ImportError:
        return []
    out: list[str] = []
    try:
        pdf = pymupdf.open(stream=data, filetype="pdf")
        for page in list(pdf)[:max_pages]:
            pix = page.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
            img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            for r in zxingcpp.read_barcodes(img):
                if r.text and r.text not in out:
                    out.append(r.text[:500])
    except Exception:  # noqa: BLE001 - a bill that will not render is a bill without a code
        return out
    return out


def upi_trusted(channel: str | None, source: dict | None) -> bool:
    """Whether a UPI payee may be taken from this notice: only mail whose sender the provider authenticated (DMARC or
    DKIM for the From domain). A WhatsApp group, a shared screenshot or an unauthenticated mail can say anything."""
    return channel in ("email", "gmail") and bool((source or {}).get("sender_authenticated"))


async def upi_sender_ok(household_id, channel: str | None, source: dict | None) -> bool:
    """`upi_trusted`, and for a mailbox the sender as well. Mail forwarded to the household's address is let in only from a member or a
    domain the household vouched for, so its authentication means something. A mailbox takes anything: any domain passes DMARC for itself, so
    a phisher's own bill would carry a payee of their choosing. There, the payee is kept only from a domain the household vouched for or a
    biller, bank, insurer or institution the code lists (`categories`)."""
    if not upi_trusted(channel, source):
        return False
    if channel == "email":
        return True
    from familyos import categories
    from familyos.db import pool
    domain = categories.sender_domain(source)
    if not domain:
        return False
    if any(domain == suffix or domain.endswith("." + suffix) for suffix, category in categories._DOMAINS if category not in categories.NEVER_OBLIGATES):
        return True
    return bool(await pool().fetchval("SELECT 1 FROM trusted_sender_domains WHERE household_id = $1 AND domain = $2", household_id, domain))


def find(text: str | None, *, sender_domain: str | None = None,
         links: list[tuple[str, str]] | None = None, codes: list[str] | None = None, allow_upi: bool = True, allow_links: bool = True) -> str | None:
    """The one link to pay from, or None.

    A UPI intent wins outright -- in the words, in a link, or read off a QR
    code: it is the amount and the payee, and the phone opens the UPI app on
    it. Otherwise the https link that most looks like the way to pay: pay
    words in its path or in the words it was hung on, a gateway or biller
    portal as its host, the sender's own domain. Links that are in every
    mail -- unsubscribe, social, app stores, tracking pixels -- are never it.
    Failing all that, a biller whose pay page is known by its sending domain.
    """
    text = text or ""
    if not allow_links:
        return None        # a notice from a source that can say anything (a group message, a share, unauthenticated mail) does not choose where the family pays
    # A UPI intent names who gets the money. Anyone can write one into a group message or a forwarded text, so the
    # caller says whether this notice came from a source that may name a payee (see `upi_trusted`).
    if allow_upi:
        for code in codes or []:
            if code.lower().startswith("upi://pay?"):
                return _clean(code)
        upi = _UPI.search(text)
        if upi:
            return _clean(upi.group(0))
        for _, url in links or []:
            if url.lower().startswith("upi://pay?"):
                return _clean(url)
    best, best_score = None, 0
    seen: set[str] = set()

    def consider(url: str, score: int) -> None:
        nonlocal best, best_score
        url = _clean(url)
        if url in seen or len(url) > 500 or not url.lower().startswith("https://"):
            return
        seen.add(url)
        if _NOT.search(url):
            return
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        rest = (parts.path or "") + "?" + (parts.query or "")
        if _PAY_WORDS.search(rest):
            score += 3
        if any(h in host for h in _PAY_HOSTS):
            score += 3
        if sender_domain and (host == sender_domain or host.endswith("." + sender_domain)):
            score += 2
        if score > best_score:
            best, best_score = url, score

    for m in _URL.finditer(text):
        consider(m.group(0), 3 if _LEAD.search(text[max(0, m.start() - 40):m.start()]) else 0)
    for anchor, url in links or []:
        consider(url, 3 if _PAY_WORDS.search(anchor or "") or _LEAD.search((anchor or "") + " ") else 0)
    for code in codes or []:
        if code.lower().startswith("https://"):
            consider(code, 3)
    if best_score >= 3:
        return best
    if sender_domain:
        for suffix, page in KNOWN_PAY_PAGES.items():
            if sender_domain == suffix or sender_domain.endswith("." + suffix):
                return page
    return None


def host_of(url: str | None) -> str | None:
    """The site a pay link opens, or None for a UPI intent or anything that is not https."""
    if not url or not url.lower().startswith("https://"):
        return None
    return (urlsplit(url).hostname or "").lower() or None


def payee_of(url: str | None) -> tuple[str, str] | None:
    """(UPI id, label to show) for a upi://pay intent, else None. The label is the name the intent carries with the id in brackets: the
    name is only what the sender typed, the id is what the money goes to."""
    if not url or not url.lower().startswith("upi://pay"):
        return None
    q = parse_qs(urlsplit(url).query)
    pa = ((q.get("pa") or [""])[0]).strip().lower()
    if not pa:
        return None
    pn = " ".join(((q.get("pn") or [""])[0]).split())[:60]
    return pa, f"{pn} ({pa})" if pn else pa


async def annotate(household_id, rows: list[dict]) -> list[dict]:
    """Adds `pay_host` (where the money goes) and `pay_host_new` to every row with a pay link, and the person is warned on a first-seen one.
    For an https link `pay_host` is the site Pay opens: new unless it is a payment gateway the code lists, a domain the household vouched
    for, or one they have already accepted a bill from. For a UPI intent it is the payee (name and UPI id): new unless the household has
    already accepted a bill paid to that id."""
    hosts = {h for h in (host_of(r.get("pay_url")) for r in rows) if h}
    payees = {x[0] for x in (payee_of(r.get("pay_url")) for r in rows) if x}
    if not hosts and not payees:
        return rows
    from familyos.db import pool
    known, trusted, paid = set(), set(), set()
    if hosts:
        known = {r["h"] for r in await pool().fetch(
            "SELECT DISTINCT lower(split_part(split_part(pay_url, '://', 2), '/', 1)) AS h FROM obligations "
            "WHERE household_id = $1 AND status = 'accepted' AND pay_url LIKE 'https://%'", household_id)}
        trusted = {r["domain"] for r in await pool().fetch("SELECT domain FROM trusted_sender_domains WHERE household_id = $1", household_id)}
    if payees:
        for r in await pool().fetch("SELECT DISTINCT pay_url FROM obligations WHERE household_id = $1 AND status = 'accepted' AND pay_url ILIKE 'upi://%'", household_id):
            got = payee_of(r["pay_url"])
            if got:
                paid.add(got[0])
    for r in rows:
        host = host_of(r.get("pay_url"))
        if host is not None:
            r["pay_host"] = host
            r["pay_host_new"] = not (any(g in host for g in _PAY_HOSTS) or host in known
                                     or any(host == d or host.endswith("." + d) for d in trusted))
            continue
        payee = payee_of(r.get("pay_url"))
        if payee is not None:
            r["pay_host"] = payee[1]
            r["pay_host_new"] = payee[0] not in paid
    return rows
