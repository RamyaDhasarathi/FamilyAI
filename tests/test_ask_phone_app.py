"""Ask can propose a look at an app on the phone, which is not a site and needs no sign-in."""
import pytest

from familyos import chat, clock

pytestmark = pytest.mark.usefixtures("school_apps")


def _facts():
    return chat.Facts()      # nobody signed in to any site


def test_a_look_at_the_school_app_is_proposed_without_a_site_sign_in_or_an_amount():
    out = chat.resolve([{"kind": "errand", "service": "myclassboard", "title": "Read the school app's announcements",
                         "what": "Announcements", "look": True, "bundle": "com.example.oakridgeApp"}], _facts())
    p = out[0]
    assert p["ok"] and p["look"] is True and p["on_phone"] is True and p["service"] == "myclassboard"
    assert p["bundle"] == "com.example.oakridgeApp" and p["max_amount"] is None and p["label"] == "MyClassBoard school app"


def test_a_phone_app_is_always_a_look_even_if_the_model_says_booking_and_the_page_defaults():
    p = chat.resolve([{"kind": "errand", "service": "myclassboard", "title": "Check the school app", "look": False, "max_amount": 5000}], _facts())[0]
    assert p["look"] is True and p["max_amount"] is None and p["what"] == "Announcements"


def test_a_site_still_needs_a_sign_in_and_an_unknown_service_is_refused():
    site = chat.resolve([{"kind": "errand", "service": "urbancompany", "title": "Deep clean", "what": "deep clean", "max_amount": 3000}], _facts())[0]
    assert site["ok"] is False and "signed in" in site["why"] or "nobody is signed in" in site["why"]
    unknown = chat.resolve([{"kind": "errand", "service": "nonesuch", "title": "x", "what": "x"}], _facts())[0]
    assert unknown["ok"] is False and "not one FamilyOS can act on" in unknown["why"]



async def test_a_look_at_the_school_app_reuses_the_school_app_the_household_used_last(family):
    import uuid

    from familyos.errands import propose
    from familyos.identity import Principal
    p = Principal(member_id=uuid.UUID(family.amma["id"]), household_id=uuid.UUID(family.household["id"]), role="guardian", display_name="Amma")
    first = await propose(p, service="myclassboard", kind="look", title="Read the school app", spec={"what": "Announcements", "bundle": "com.example.oakridgeApp"})
    assert first["spec"]["where"]["bundle"] == "com.example.oakridgeApp"
    again = await propose(p, service="myclassboard", kind="look", title="Read it again", spec={"what": "Announcements"})
    assert again["spec"]["where"]["bundle"] == "com.example.oakridgeApp"


async def test_ask_is_given_the_medicines_the_health_page_shows(family, database):
    import datetime as dt
    import uuid

    from familyos import chat
    from familyos.identity import Principal
    p = Principal(member_id=uuid.UUID(family.amma["id"]), household_id=uuid.UUID(family.household["id"]), role="guardian", display_name="Amma")
    r = await family.upload("amma", b"%PDF-1.4 rx " + uuid.uuid4().bytes, filename="rx.pdf", visibility="shared")
    artifact_id = uuid.UUID(r.json()["artifact"]["id"])
    today = clock.today()
    await database.execute(
        "INSERT INTO medications (id, household_id, artifact_id, drug, dose_text, times_per_day, patient_member_id, prescriber, starts_on, ends_on) "
        "VALUES ($1, $2, $3, 'Gliben O', '3 ml', 3, $4, 'Dr Rao', $5, $6)",
        uuid.uuid4(), p.household_id, artifact_id, uuid.UUID(family.younger["id"]), today - dt.timedelta(days=3), today + dt.timedelta(days=4))
    facts = await chat.context(p)
    line = next(ln for ln in facts.lines if ln.startswith("[m1]"))
    assert "Gliben O 3 ml" in line and "3 a day" in line and "Younger one" in line and "prescribed by Dr Rao" in line
    assert facts.plain["m1"][0] == "medicine"


async def test_a_child_whose_school_uses_another_app_is_not_offered_this_one(family, database):
    import uuid

    from familyos import chat
    from familyos.identity import Principal
    p = Principal(member_id=uuid.UUID(family.amma["id"]), household_id=uuid.UUID(family.household["id"]), role="guardian", display_name="Amma")
    await database.execute("UPDATE members SET school = 'Oakridge Global School' WHERE id = $1", uuid.UUID(family.older["id"]))
    await database.execute("UPDATE members SET school = 'Sunrise Public School' WHERE id = $1", uuid.UUID(family.younger["id"]))
    lines = (await chat.context(p)).lines
    apps = next(x for x in lines if x.startswith("PHONE APPS"))
    assert family.older["display_name"].split()[0] in apps and "used by" in apps
    none = next(x for x in lines if x.startswith("NO PHONE APP SET UP FOR"))
    assert family.younger["display_name"].split()[0] in none and family.older["display_name"].split()[0] not in none


def test_a_look_at_the_app_is_made_only_when_they_ask_for_the_app():
    raw = [{"kind": "errand", "service": "myclassboard", "title": "Read the school app", "what": "Circulars", "look": True}]
    assert chat.resolve(raw, _facts(), "Find Noah's latest school circular") == []
    assert chat.resolve(raw, _facts(), "Get Noah's latest circular from the app")[0]["on_phone"] is True
    assert chat.resolve(raw, _facts(), "check MyClassBoard")[0]["look"] is True


def test_the_preschool_app_is_registered_for_its_own_school_only():
    from familyos.execution import apps
    a = apps.APPS["brightstart"]
    assert a["bundle"] == "com.example.brightstart.parentapp" and "bright start" in a["schools"]
    assert "bright start" not in apps.APPS["myclassboard"]["schools"]
    p = chat.resolve([{"kind": "errand", "service": "brightstart", "title": "Read the classwork", "what": "Today's Highlights", "look": True}], _facts(), "get it from the app")[0]
    assert p["ok"] and p["on_phone"] is True and p["label"] == "Bright Start school app"


def test_the_childs_own_schools_app_is_used_whatever_the_model_keyed():
    facts = chat.Facts()
    facts.members = [{"id": "a", "display_name": "Noah Hart", "role": "child", "school": "Oakridge Global School"},
                     {"id": "b", "display_name": "Lily Hart", "role": "child", "school": "Bright Start"},
                     {"id": "c", "display_name": "Kiran", "role": "child", "school": "Sunrise Public School"}]
    raw = [{"kind": "errand", "service": "myclassboard", "title": "Read circulars", "what": "Circulars", "look": True, "bundle": "com.example.oakridgeApp"}]
    lily = chat.resolve(raw, facts, "Get Lily's latest circular from the app")[0]
    assert lily["service"] == "brightstart" and lily["bundle"] is None      # None: the errand takes the app's own bundle
    assert chat.resolve(raw, facts, "Get Noah's latest circular from the app")[0]["service"] == "myclassboard"
    assert chat.resolve(raw, facts, "Get Kiran's latest circular from the app") == []


def _two_schools():
    facts = chat.Facts()
    facts.members = [{"id": "a", "display_name": "Noah Hart", "role": "child", "school": "Oakridge Global School"},
                     {"id": "b", "display_name": "Lily Hart", "role": "child", "school": "Bright Start"},
                     {"id": "c", "display_name": "Kiran", "role": "child", "school": "Sunrise Public School"}]
    return facts


def test_two_children_named_get_one_look_each_in_their_own_apps():
    raw = [{"kind": "errand", "service": "myclassboard", "title": "Circulars", "what": "Circulars", "look": True}]
    out = chat.resolve(raw, _two_schools(), "Get Noah's and Lily's latest circulars from the app")
    assert sorted(p["service"] for p in out) == ["brightstart", "myclassboard"]


def test_no_child_named_and_different_apps_asks_whose_instead_of_guessing():
    raw = [{"kind": "errand", "service": "myclassboard", "title": "Circulars", "what": "Circulars", "look": True}]
    out = chat.resolve(raw, _two_schools(), "Get the latest circular from the app")
    assert len(out) == 1 and out[0]["ok"] is False and "say whose" in out[0]["why"]


def test_a_name_inside_another_word_does_not_name_a_child():
    raw = [{"kind": "errand", "service": "myclassboard", "title": "Circulars", "what": "Circulars", "look": True}]
    # "Kiran" inside "kirana" must not select Kiran's school (which has no app): both real kids are possible, so it asks whose
    out = chat.resolve(raw, _two_schools(), "Get the kirana shop notice from the app")
    assert len(out) == 1 and out[0]["ok"] is False


def test_the_model_cannot_point_a_look_at_an_app_nobody_set_up():
    out = chat.resolve([{"kind": "errand", "service": "myclassboard", "title": "Read it", "what": "Announcements", "look": True,
                           "bundle": "com.example.bank"}], _facts())
    assert out[0]["bundle"] is None
