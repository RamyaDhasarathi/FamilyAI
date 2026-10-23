"""Birthdays and schools as facts the record holds: a birthday is on the
brief the week before with the age, a child of age is said to guardians,
and a school is one record with its children and its groups."""
import datetime as dt
import uuid

from familyos import brief
from familyos.identity import Principal

TODAY = dt.date.today()


def _p(family, who="amma"):
    m = getattr(family, who)
    return Principal(member_id=uuid.UUID(m["id"]), household_id=uuid.UUID(family.household["id"]), role=m["role"], display_name=m["display_name"])


async def test_a_birthday_is_on_the_brief_the_week_before_with_the_age(family, database):
    child = family.older
    born = (TODAY + dt.timedelta(days=3)).replace(year=TODAY.year - 9)
    r = await family.client.patch(f"/v1/members/{child['id']}/birthday", headers=family.h("amma"), json={"date_of_birth": born.isoformat()})
    assert r.status_code == 200 and r.json()["date_of_birth"] == born.isoformat()
    out = await brief.today(_p(family, "appa"), on=TODAY, limit=50)
    [item] = [i for i in out["items"] if i["reason"] == "birthday"]
    assert item["title"].startswith(f"{child['display_name']} turns 9") and item["subject_member_id"] == uuid.UUID(child["id"])
    # Not ten days ahead; and the digest carries the line.
    assert not [i for i in (await brief.today(_p(family), on=TODAY - dt.timedelta(days=10), limit=50))["items"] if i["reason"] == "birthday"]
    r = await family.client.get("/v1/digest", headers=family.h("amma"))
    assert r.status_code == 200 and "Birthdays:" in r.json()["body"]
    # A future date is refused; an adult may set their own and not a child's.
    assert (await family.client.patch(f"/v1/members/{child['id']}/birthday", headers=family.h("amma"), json={"date_of_birth": (TODAY + dt.timedelta(days=1)).isoformat()})).status_code == 422
    assert (await family.client.patch(f"/v1/members/{family.appa['id']}/birthday", headers=family.h("appa"), json={"date_of_birth": "1984-02-29"})).status_code == 200
    if family.appa["role"] != "guardian":
        assert (await family.client.patch(f"/v1/members/{child['id']}/birthday", headers=family.h("appa"), json={"date_of_birth": "2017-01-01"})).status_code == 403


async def test_a_child_of_age_is_said_to_guardians(family, database):
    child = family.older
    await family.client.patch(f"/v1/members/{child['id']}/birthday", headers=family.h("amma"), json={"date_of_birth": TODAY.replace(year=TODAY.year - 18).isoformat()})
    out = await brief.today(_p(family), on=TODAY, limit=50)
    [item] = [i for i in out["items"] if i["reason"] == "majority"]
    assert item["title"] == f"{child['display_name']} is 18: their records are their own now"


async def test_a_school_is_one_record_with_its_children_and_its_groups(family, database):
    h = family.h("amma")
    for who in (family.older, family.younger):
        r = await family.client.patch(f"/v1/members/{who['id']}/school", headers=h, json={"school": "Aachi Global", "class_label": "4"})
        assert r.status_code == 200, r.text
    r = await family.client.put("/v1/household/source-schools", headers=h, json={"source_key": "telegram:group:-100123", "school": "aachi global"})
    assert r.status_code == 200, r.text
    r = await family.client.get("/v1/household/schools", headers=family.h("appa"))
    assert r.status_code == 200
    [school] = r.json()
    assert school["name"] == "Aachi Global" and sorted(school["children"]) == sorted([family.older["display_name"], family.younger["display_name"]])
    assert school["sources"] == ["telegram:group:-100123"]
    # Renaming follows through to the children and the map.
    r = await family.client.put(f"/v1/household/schools/{school['id']}", headers=h, json={"name": "Aachi Global School", "portal_url": "https://myclassboard.example"})
    assert r.status_code == 200 and r.json()["portal_url"] == "https://myclassboard.example"
    assert await database.fetchval("SELECT school FROM members WHERE id = $1", uuid.UUID(family.older["id"])) == "Aachi Global School"
    assert await database.fetchval("SELECT school FROM source_schools WHERE source_key = $1", "telegram:group:-100123") == "Aachi Global School"
