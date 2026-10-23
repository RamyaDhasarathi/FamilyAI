"""A child's class, with history. The record keeps every school and class a
child was in and when each began; a circular is matched to the class the
child was in on the notice's own date; at the start of a school year the
brief nudges a guardian whose record is a year old."""
import datetime as dt
import uuid

from familyos import brief
from familyos.extraction import service
from familyos.extraction.claims import Claim, Extraction, ExtractorInfo
from familyos.identity import Principal
from tests.conftest import pdf

GROUNDED = {"page": 1, "start": 0, "end": 16, "boxes": [[60.0, 78.0, 300.0, 93.0]], "match": "exact"}
TODAY = dt.date.today()


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


def _circular(applies_to, on):
    return Extraction(extractor=ExtractorInfo(name="openai", model="openai/x", prompt_version="p", parser_version="p1"),
                      reference_date=on, actionable=True, page_count=1, claims=[
                          Claim(kind="event", title=f"Sports day for {applies_to}", date=on + dt.timedelta(days=10), applies_to=applies_to,
                                quote="Dear parents of " + applies_to, location=GROUNDED, confidence=0.9)])


async def test_a_class_change_is_kept_with_the_day_it_began(family, database):
    child = family.older
    r = await family.client.patch(f"/v1/members/{child['id']}/school", headers=family.h("amma"),
                                  json={"school": "Aachi Global", "class_label": "4-A", "since": "2025-06-02"})
    assert r.status_code == 200, r.text
    r = await family.client.patch(f"/v1/members/{child['id']}/school", headers=family.h("amma"),
                                  json={"school": "Aachi Global", "class_label": "5-A", "since": "2026-06-01"})
    assert r.status_code == 200 and r.json()["class_label"] == "5-A"
    # Saying the same thing again adds nothing.
    await family.client.patch(f"/v1/members/{child['id']}/school", headers=family.h("amma"), json={"school": "Aachi Global", "class_label": "5-A"})
    r = await family.client.get(f"/v1/members/{child['id']}/classes", headers=family.h("appa"))
    assert r.status_code == 200
    assert [(c["class_label"], c["since"]) for c in r.json()] == [("5-A", "2026-06-01"), ("4-A", "2025-06-02")]


async def test_a_circular_is_matched_to_the_class_of_its_own_date(family, database):
    child = family.older
    await family.consent(child)
    h = family.h("amma")
    await family.client.patch(f"/v1/members/{child['id']}/school", headers=h, json={"school": "Aachi Global", "class_label": "4", "since": "2025-06-02"})
    await family.client.patch(f"/v1/members/{child['id']}/school", headers=h, json={"school": "Aachi Global", "class_label": "5", "since": "2026-06-01"})
    hid = uuid.UUID(family.household["id"])

    async def read(applies_to, on):
        r = await family.upload("amma", pdf(f"{applies_to} circular {on}"), filename="c.pdf", visibility="shared")
        aid = uuid.UUID(r.json()["artifact"]["id"])
        await service.save(hid, aid, _circular(applies_to, on))
        return await database.fetch("SELECT member_id FROM artifact_subjects WHERE artifact_id = $1", aid)

    # Last term's Grade 4 circular is still hers; a Grade 5 one dated then is nobody's.
    assert [r["member_id"] for r in await read("Grade 4", dt.date(2026, 3, 10))] == [uuid.UUID(child["id"])]
    assert await read("Grade 5", dt.date(2026, 3, 10)) == []
    # This term it is the other way round.
    assert [r["member_id"] for r in await read("Grade 5", dt.date(2026, 7, 1))] == [uuid.UUID(child["id"])]
    assert await read("Grade 4", dt.date(2026, 7, 1)) == []


async def test_the_brief_nudges_a_guardian_at_the_start_of_a_school_year(family, database):
    child = family.older
    h = family.h("amma")
    await family.client.patch(f"/v1/members/{child['id']}/school", headers=h, json={"school": "Aachi Global", "class_label": "4-A", "since": "2025-06-02"})
    june = dt.date(2026, 6, 15)
    out = await brief.today(_p(family), on=june, limit=50)
    [item] = [i for i in out["items"] if i["reason"] == "school_year"]
    assert item["title"] == f"{child['display_name']} is still recorded in class 4-A. New year?"
    assert item["subject_member_id"] == uuid.UUID(child["id"])
    # Not in October, not to an adult who is not a guardian, and not once updated.
    assert not [i for i in (await brief.today(_p(family), on=dt.date(2026, 10, 15), limit=50))["items"] if i["reason"] == "school_year"]
    await family.client.patch(f"/v1/members/{child['id']}/school", headers=h, json={"school": "Aachi Global", "class_label": "5-A", "since": "2026-06-01"})
    assert not [i for i in (await brief.today(_p(family), on=june, limit=50))["items"] if i["reason"] == "school_year"]
