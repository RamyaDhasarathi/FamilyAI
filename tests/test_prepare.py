"""The night before an event: what the notice said it still needs, in one
line -- the slip to return, the fee, what to bring -- gone once each is done."""
import datetime as dt
import uuid

from familyos import brief
from familyos.extraction import service
from familyos.extraction.claims import Amount, Claim, Extraction, ExtractorInfo
from familyos.identity import Principal
from tests.conftest import pdf

GROUNDED = {"page": 1, "start": 0, "end": 16, "boxes": [[60.0, 78.0, 300.0, 93.0]], "match": "exact"}
TODAY = dt.date.today()


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


async def test_the_night_before_says_what_the_event_still_needs(family, database):
    tomorrow = TODAY + dt.timedelta(days=1)
    r = await family.upload("amma", pdf("Sports day circular"), filename="c.pdf", visibility="shared")
    aid = uuid.UUID(r.json()["artifact"]["id"])
    hid = uuid.UUID(family.household["id"])
    await service.save(hid, aid, Extraction(
        extractor=ExtractorInfo(name="openai", model="openai/x", prompt_version="p", parser_version="p1"),
        reference_date=TODAY - dt.timedelta(days=5), actionable=True, page_count=1, claims=[
            Claim(kind="event", title="Annual sports day", date=tomorrow, time="08:30", requires=["parent_attendance", "items_to_bring"],
                  quote="Sports day", location=GROUNDED, confidence=0.95),
            Claim(kind="deadline", title="Return the consent slip", date=TODAY, requires=["form_return"], quote="slip", location=GROUNDED, confidence=0.9),
            Claim(kind="deadline", title="Pay the sports fee", date=TODAY, requires=["payment"], amount=Amount(value=300, currency="INR", text="₹300"),
                  quote="fee", location=GROUNDED, confidence=0.9),
            Claim(kind="instruction", title="Wear white canvas shoes and bring a water bottle", quote="wear", location=GROUNDED, confidence=0.9)]))
    rows = {r["title"]: r for r in await database.fetch("SELECT id, title, action FROM obligations WHERE artifact_id = $1", aid)}
    assert rows["Annual sports day"]["action"] == "attend"
    for o in rows.values():
        await family.client.post(f"/v1/obligations/{o['id']}/decision", headers=family.h("amma"), json={"status": "accepted"})
    out = await brief.today(_p(family), on=TODAY, limit=50)
    [item] = [i for i in out["items"] if i["reason"] == "prepare"]
    assert item["title"] == "Before Annual sports day tomorrow: 3 things"
    assert "Return the consent slip" in item["why"] and "Pay the sports fee" in item["why"] and "white canvas shoes" in item["why"]
    # The slip returned and the fee dismissed as not ours: only the instruction is left.
    await family.client.post(f"/v1/obligations/{rows['Return the consent slip']['id']}/decision", headers=family.h("amma"), json={"status": "dismissed"})
    await family.client.post(f"/v1/obligations/{rows['Pay the sports fee']['id']}/decision", headers=family.h("amma"), json={"status": "dismissed"})
    out = await brief.today(_p(family), on=TODAY, limit=50)
    [item] = [i for i in out["items"] if i["reason"] == "prepare"]
    assert item["title"] == "Before Annual sports day tomorrow: 1 thing"
    # A week before, nothing is said yet.
    assert not [i for i in (await brief.today(_p(family), on=TODAY - dt.timedelta(days=6), limit=50))["items"] if i["reason"] == "prepare"]
