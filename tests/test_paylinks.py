"""Phase one of paying: the bill's own link, one tap from the date. Found in
the notice, kept on the pay obligation, shown beside Accept, on Today and
in the digest. Nothing here pays."""
import datetime as dt
import uuid

from familyos import clock, digest, notify, paylinks
from familyos.db import pool
from familyos.extraction import service
from familyos.extraction.claims import Amount, Claim, Extraction, ExtractorInfo
from familyos.identity import Principal
from tests.conftest import pdf
from tests.test_duplicates import GROUNDED


def test_a_upi_intent_wins_then_the_billers_pay_page_then_a_gateway_link():
    assert paylinks.find("Tap upi://pay?pa=airtel@icici&pn=Airtel&am=1940.98&cu=INR to pay. Or https://www.airtel.in/pay") \
        == "upi://pay?pa=airtel@icici&pn=Airtel&am=1940.98&cu=INR"
    assert paylinks.find("Pay now: https://www.airtel.in/s/selfcare/pay-bill?acct=1 . Unsubscribe https://airtel.in/unsubscribe",
                         sender_domain="airtel.in") == "https://www.airtel.in/s/selfcare/pay-bill?acct=1"
    assert paylinks.find("Payment link: https://rzp.io/l/abc123 (expires Friday).") == "https://rzp.io/l/abc123"
    assert paylinks.find("Your invoice is attached. View it at https://portal.school.edu/invoices/88", sender_domain="school.edu") \
        == "https://portal.school.edu/invoices/88"
    # Links every mail has are never it; nor a blog; nor nothing.
    assert paylinks.find("Read https://blog.example.com/post and follow https://facebook.com/x and https://x.com/track/9") is None
    assert paylinks.find("") is None and paylinks.find(None) is None
    # The sender's own domain breaks a tie between two pay-looking links.
    two = "Pay via https://pay.gateway.com/x?id=1 or on our site https://www.airtel.in/pay-bill"
    assert paylinks.find(two, sender_domain="airtel.in") == "https://www.airtel.in/pay-bill"


def _bill(today: dt.date) -> Extraction:
    return Extraction(
        extractor=ExtractorInfo(name="openai", model="openai/gpt-5.6-sol", prompt_version="p", parser_version="p1"),
        reference_date=today, actionable=True, page_count=1,
        claims=[Claim(kind="payment", title="Pay the Airtel Black bill", date=today + dt.timedelta(days=5),
                      amount=Amount(value=1940.98, currency="INR", text="\u20b91,940.98"),
                      quote="pay \u20b91,940.98 by the 16th", location=GROUNDED, confidence=0.9)])


async def test_a_bills_pay_link_rides_the_obligation_to_today_and_the_digest(family, database, monkeypatch):
    async def member(member_id, subject, body):
        return "test"
    monkeypatch.setattr(notify, "member", member)
    today = clock.today()
    household_id = uuid.UUID(family.household["id"])
    r = await family.upload("amma", pdf("airtel"), filename="bill.txt", content_type="text/plain", visibility="shared")
    aid = uuid.UUID(r.json()["artifact"]["id"])
    await pool().execute("UPDATE input_artifacts SET channel = 'gmail', source = $2 WHERE id = $1", aid,
                         {"from": "Airtel <ebill@airtel.in>", "subject": "Your Airtel Black bill", "sender_authenticated": True,
                          "date": today.strftime("%a, %d %b %Y 09:00:00 +0530")})
    text = ("Dear customer, your Airtel Black bill of \u20b91,940.98 is due by the 16th.\n"
            "Pay now: https://www.airtel.in/s/selfcare/pay-bill?acct=9\n"
            "Manage preferences https://www.airtel.in/unsubscribe")
    counts = await service.save(household_id, aid, _bill(today), text=text)
    assert counts["obligations"] == 1 and counts["pay_link"] is True
    [ob] = (await family.client.get("/v1/obligations?status=proposed", headers=family.h("appa"))).json()
    assert ob["action"] == "pay" and ob["pay_url"] == "https://www.airtel.in/s/selfcare/pay-bill?acct=9"
    # The brief carries it to the Today page, the digest to the phone.
    b = (await family.client.get("/v1/brief", headers=family.h("amma"))).json()
    item = next(i for i in b["items"] if i.get("obligation_id") == ob["id"])
    assert item["pay_url"] == ob["pay_url"]
    p = Principal(member_id=uuid.UUID(family.amma["id"]), household_id=household_id, role="guardian", display_name="Amma")
    subject, body = await digest.compose(p, today=today)
    assert "pay: https://www.airtel.in/s/selfcare/pay-bill?acct=9" in body
    # A notice without a link proposes the same obligation with no link; nothing invents one.
    r = await family.upload("amma", pdf("other"), filename="b2.txt", content_type="text/plain", visibility="shared")
    aid2 = uuid.UUID(r.json()["artifact"]["id"])
    await service.save(household_id, aid2, _bill(today), text="Your bill is \u20b91,940.98, due the 16th.")
    rows = await database.fetch("SELECT pay_url FROM obligations WHERE artifact_id = $1", aid2)
    assert rows and all(r["pay_url"] is None for r in rows)


def _mail(html: str) -> bytes:
    from email.message import EmailMessage
    m = EmailMessage()
    m["From"] = "Airtel <ebill@airtel.com>"
    m["To"] = "x@example.com"
    m["Subject"] = "Bill"
    m.set_content("Your bill is attached.")
    m.add_alternative(html, subtype="html")
    return bytes(m)


def test_a_mails_hrefs_are_read_with_the_words_they_hang_on():
    links = paylinks.from_email(_mail('<p>Dear customer</p><a href="https://www.airtel.in/s/pay?acct=9">Pay now</a> '
                                      '<a href="https://www.airtel.in/unsubscribe">Unsubscribe</a> '
                                      '<a href="https://i.airtel.in/x"><img alt="E-Bill" src="x.png"></a>'))
    assert links == [("Pay now", "https://www.airtel.in/s/pay?acct=9"), ("Unsubscribe", "https://www.airtel.in/unsubscribe"),
                     ("E-Bill", "https://i.airtel.in/x")]
    assert paylinks.find("Dear customer", sender_domain="airtel.com", links=links) == "https://www.airtel.in/s/pay?acct=9"
    # A subscription that renews itself has no pay link; its help pages are not one.
    apple = [("review your subscription", "https://apps.apple.com/account/subscriptions"), ("Apple Support", "https://support.apple.com/en-gb/billing")]
    assert paylinks.find("Your subscription renews", sender_domain="email.apple.com", links=apple) is None
    # A biller whose mail says nothing but whose pay page is known.
    assert paylinks.find("Your Airtel bill is attached", sender_domain="airtel.com") == "https://www.airtel.in/pay-bill"
    assert paylinks.from_email(b"not a mail at all") == []


def test_the_upi_qr_on_a_statements_pdf_is_read_and_wins():
    import pymupdf
    import zxingcpp
    from PIL import Image
    intent = "upi://pay?pa=airtel@icici&pn=Airtel&am=1940.98&cu=INR&tn=Oct2026"
    bitmap = zxingcpp.write_barcode(zxingcpp.BarcodeFormat.QRCode, intent, width=300, height=300)
    img = Image.fromarray(bitmap) if hasattr(Image, "fromarray") and hasattr(bitmap, "__array_interface__") else None
    if img is None:
        import pytest
        pytest.skip("the decoder's writer gives no image buffer here")
    import io
    png = io.BytesIO()
    img.save(png, format="PNG")
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((72, 72), "Scan and pay via any UPI app")
    page.insert_image(pymupdf.Rect(72, 100, 372, 400), stream=png.getvalue())
    data = pdf.tobytes()
    assert paylinks.from_pdf_qr(data) == [intent]
    assert paylinks.find("Scan and pay via any UPI app", sender_domain="airtel.com", codes=[intent]) == intent
    assert paylinks.from_pdf_qr(b"%PDF-1.4 broken") == []


async def test_a_link_read_off_the_attachment_serves_the_mails_own_pay_obligation(family, database, monkeypatch):
    async def member(member_id, subject, body):
        return "test"
    monkeypatch.setattr(notify, "member", member)
    today = clock.today()
    household_id = uuid.UUID(family.household["id"])
    mail = uuid.UUID((await family.upload("amma", pdf("mail"), filename="m.txt", content_type="text/plain", visibility="shared")).json()["artifact"]["id"])
    statement = uuid.UUID((await family.upload("amma", pdf("stmt"), filename="s.pdf", visibility="shared")).json()["artifact"]["id"])
    await pool().execute("UPDATE input_artifacts SET channel = 'gmail', source = $2 WHERE id = $1", mail,
                         {"from": "Airtel <ebill@airtel.com>", "subject": "Bill", "sender_authenticated": True, "date": today.strftime("%a, %d %b %Y 09:00:00 +0530")})
    await pool().execute("UPDATE input_artifacts SET parent_id = $2, channel = 'gmail_attachment' WHERE id = $1", statement, mail)
    # The mail is read first, with no link in its words or hrefs; then the PDF, with the QR.
    await service.save(household_id, mail, _bill(today), text="Your bill is attached.", links=[("Previous bills", "https://i.airtel.in/previous-bills")])
    intent = "upi://pay?pa=20002486758.FL@mairtel&pn=Bharti%20Airtel&am=1940.98&cu=INR"
    await service.save(household_id, statement, _bill(today), text="Scan and pay via any UPI app", codes=[intent])
    rows = {r["artifact_id"]: r["pay_url"] for r in await database.fetch("SELECT artifact_id, pay_url FROM obligations WHERE action = 'pay'")}
    # The PDF's obligation was the same ask twice and was dropped; the mail's own
    # row, which first got Airtel's general pay page, now carries the intent.
    assert rows == {mail: intent}


def test_a_upi_payee_is_taken_only_from_authenticated_mail():
    upi = "upi://pay?pa=scammer@bank&pn=School&am=4000"
    assert paylinks.upi_trusted("email", {"sender_authenticated": True}) and paylinks.upi_trusted("gmail", {"sender_authenticated": True})
    for channel, source in (("email", {"sender_authenticated": False}), ("email", {}), ("whatsapp", {"sender_authenticated": True}),
                            ("share", None), (None, None)):
        assert not paylinks.upi_trusted(channel, source)
    assert paylinks.find(f"Fees due: {upi}") == upi
    assert paylinks.find(f"Fees due: {upi}", allow_upi=False) is None
    assert paylinks.find("Pay at https://rzp.io/l/abc123", codes=[upi], allow_upi=False) == "https://rzp.io/l/abc123"


def test_a_pay_link_is_kept_only_from_a_source_that_may_choose_the_payee():
    text = "Pay at https://rzp.io/l/abc123 before Friday"
    assert paylinks.find(text) == "https://rzp.io/l/abc123"
    assert paylinks.find(text, allow_links=False) is None
    assert paylinks.find("upi://pay?pa=x@bank&am=1", allow_links=False) is None


async def test_a_pay_link_to_a_site_the_household_has_not_paid_through_is_flagged(family, database):
    import uuid
    rows = [{"pay_url": "https://pay.some-new-site.example/x"}, {"pay_url": "https://rzp.io/l/abc"}, {"pay_url": "upi://pay?pa=a@b"}, {"pay_url": None}]
    out = await paylinks.annotate(uuid.UUID(family.household["id"]), rows)
    assert out[0]["pay_host"] == "pay.some-new-site.example" and out[0]["pay_host_new"] is True
    assert out[1]["pay_host"] == "rzp.io" and out[1]["pay_host_new"] is False       # a gateway the code lists
    assert out[2]["pay_host"] == "a@b" and out[2]["pay_host_new"] is True          # a UPI intent: the payee, first seen
    assert "pay_host" not in out[3]
    await database.execute("INSERT INTO trusted_sender_domains (household_id, domain, added_by) VALUES ($1, 'some-new-site.example', $2)",
                           uuid.UUID(family.household["id"]), uuid.UUID(family.amma["id"]))
    again = await paylinks.annotate(uuid.UUID(family.household["id"]), [{"pay_url": "https://pay.some-new-site.example/x"}])
    assert again[0]["pay_host_new"] is False


async def test_a_upi_payee_is_shown_and_flagged_until_the_household_has_paid_that_id(family, database):
    import uuid
    hid = uuid.UUID(family.household["id"])
    link = "upi://pay?pa=Landlord@okbank&pn=R%20Kumar&am=1000"
    assert paylinks.payee_of(link) == ("landlord@okbank", "R Kumar (landlord@okbank)")
    assert paylinks.payee_of("upi://pay?pn=NoId") is None and paylinks.payee_of("https://x.example") is None
    first = (await paylinks.annotate(hid, [{"pay_url": link}]))[0]
    assert first["pay_host"] == "R Kumar (landlord@okbank)" and first["pay_host_new"] is True
    aid = (await family.upload("amma", __import__("tests.conftest", fromlist=["pdf"]).pdf("rent"), filename="r.pdf", visibility="shared")).json()["artifact"]["id"]
    import datetime as dt

    from tests.test_brief import _obligation
    await _obligation(database, family, artifact_id=aid, due=dt.date(2030, 1, 5), title="Rent", status="accepted")
    await database.execute("UPDATE obligations SET pay_url = $2 WHERE artifact_id = $1", uuid.UUID(aid), link)
    again = (await paylinks.annotate(hid, [{"pay_url": "upi://pay?pa=landlord@okbank&pn=Someone%20Else"}]))[0]
    assert again["pay_host_new"] is False                                              # same UPI id, paid before
    other = (await paylinks.annotate(hid, [{"pay_url": "upi://pay?pa=scammer@okbank&pn=R%20Kumar"}]))[0]
    assert other["pay_host_new"] is True                                               # the same name on another id is not the same payee
