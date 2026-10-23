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
from urllib.parse import urlsplit

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
        for m in re.finditer(r'<a\b[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
            anchor = " ".join(re.sub(r"<[^>]+>", " ", m.group(2)).split())[:80]
            alt = re.search(r'alt\s*=\s*["\']([^"\']*)["\']', m.group(2), re.I)
            out.append((anchor or (alt.group(1) if alt else ""), m.group(1).strip()))
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


def find(text: str | None, *, sender_domain: str | None = None,
         links: list[tuple[str, str]] | None = None, codes: list[str] | None = None) -> str | None:
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
