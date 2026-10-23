"""Whom a circular is about, when it names nobody.

The pure rules first, then the household API that feeds them, then the
extraction path that applies them -- including the two refusals that matter:
a bill is not a school notice, and two schools is a question for a parent.
"""
import datetime as dt
import uuid

import pytest

from familyos.extraction.attribute import attribute, class_matches, is_school_audience

C1, C2, C3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def child(cid, school=None, class_label=None):
    return {"id": cid, "school": school, "class_label": class_label}


# ----------------------------------------------------------------------------
# the rules
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("scope,label,expected", [
    ("Grade 4", "4", True),
    ("Class 4", "Grade 4", True),            # generic words are not the key
    ("Grades 4 and 5", "4", True),
    ("Class IX-B students", "IX-B", True),
    ("Class IX", "IX-B", False),             # the section is part of the key
    ("Grade 14", "4", False),                # 14 is one token, 4 is another
    ("KG II", "KG II", True),
    ("all", "4", False),
    ("parents", "4", False),
    (None, "4", False),
    ("Grade 4", None, False),
    ("Grade 4", "", False),
])
def test_a_class_is_matched_by_its_key_not_its_wording(scope, label, expected):
    assert class_matches(scope, label) is expected


@pytest.mark.parametrize("scope,expected", [
    ("children", True), ("parents", True), ("all parents", True), ("Grade 4", True), ("Class IX", True),
    ("students of KG II", True),
    # "all" on its own is what a bill says too; it names nobody.
    ("all", False), ("account holder", False), ("tenant", False), (None, False), ("", False),
])
def test_what_reads_as_a_school_audience(scope, expected):
    assert is_school_audience(scope) is expected


def test_a_class_named_on_the_notice_finds_the_child_in_it():
    kids = [child(C1, "DPS", "4"), child(C2, "DPS", "7")]
    assert attribute(["Grade 4", "all"], kids) == [C1]


def test_a_class_match_beats_elimination_even_when_one_school():
    """"Grade 4" in a one-school family is Grade 4's, not everyone's."""
    kids = [child(C1, "DPS", "4"), child(C2, "DPS", "7")]
    assert attribute(["Dear Parents of Grade 4"], kids) == [C1]


def test_one_school_and_no_class_named_is_everyone_at_that_school():
    """The PTM circular: "Dear Parents", "children", "all" -- and nothing
    else. Both children are at the one school, so it is about both."""
    kids = [child(C1, "DPS", "4"), child(C2, "DPS", "7")]
    assert set(attribute(["parents", "children", "all"], kids)) == {C1, C2}


def test_two_schools_and_no_class_named_is_nobodys_to_guess():
    kids = [child(C1, "DPS", "4"), child(C2, "NPS", "7")]
    assert attribute(["parents", "all"], kids) == []


def test_school_names_match_however_they_were_typed():
    kids = [child(C1, "DPS Bangalore", "4"), child(C2, " dps  bangalore ", "7")]
    assert set(attribute(["all children"], kids)) == {C1, C2}


def test_a_bill_addressed_to_all_is_not_the_childrens():
    """The electricity bill's claims are scoped to "all". One school, two
    children, and it must still attach to nobody."""
    kids = [child(C1, "DPS", "4"), child(C2, "DPS", "7")]
    assert attribute(["all", None], kids) == []


def test_a_school_named_in_the_notice_picks_that_schools_children():
    """Two schools, no class -- but the notice says which school it is."""
    kids = [child(C1, "Aachi Global", "4-A"), child(C2, "First Cry", "KG-1")]
    assert attribute(["all parents"], kids, ["Aachi Global School, Circular 12", "PTM"]) == [C1]


def test_a_school_name_is_a_phrase_not_a_bag_of_words():
    kids = [child(C1, "Aachi Global", "4-A"), child(C2, "First Cry", "KG-1")]
    assert attribute(["all parents"], kids, ["a global holiday for all"]) == []
    assert attribute(["all parents"], kids, ["AACHI   GLOBAL"]) == [C1]


def test_both_schools_named_is_not_ours_to_pick():
    kids = [child(C1, "Aachi Global", "4-A"), child(C2, "First Cry", "KG-1")]
    assert attribute(["all students"], kids, ["Aachi Global and First Cry joint sports day"]) == []


def test_a_class_match_beats_a_school_name():
    kids = [child(C1, "Aachi Global", "4-A"), child(C2, "Aachi Global", "7")]
    assert attribute(["Grade 7"], kids, ["Aachi Global School"]) == [C2]


def test_a_bill_is_not_a_school_notice():
    """Every child in one school must not be attached to the electricity
    bill. The audience has to read as a school's."""
    kids = [child(C1, "DPS", "4"), child(C2, "DPS", "7")]
    assert attribute(["account holder", None], kids) == []
    assert attribute([None, None], kids) == []


def test_a_child_with_no_school_recorded_is_not_attached_by_elimination():
    """Only the children whose school is known are at the one school."""
    kids = [child(C1, "DPS", "4"), child(C2)]
    assert attribute(["children"], kids) == [C1]


def test_no_children_with_a_school_is_no_school_to_eliminate_to():
    assert attribute(["children"], [child(C1), child(C2)]) == []


def test_a_child_is_attached_once_however_many_claims_name_their_class():
    kids = [child(C1, "DPS", "4")]
    assert attribute(["Grade 4", "Class 4 students", "4"], kids) == [C1]


def test_the_source_the_notice_arrived_from_decides_when_the_text_does_not():
    """The real case: two schools, "Dear Parents", nothing else -- pasted from
    the Grade 4 parents' group. The group is the answer."""
    kids = [child(C1, "Aachi Global", "4-A"), child(C2, "First Cry", "KG-1")]
    assert attribute(["all parents"], kids, [], source_school="First Cry") == [C2]
    assert attribute(["all parents"], kids, [], source_school="first  cry") == [C2]


def test_the_text_naming_a_school_beats_the_source():
    """Forwarded into the wrong group: the notice says Aachi, the group is
    First Cry's. The notice is about what it says it is about."""
    kids = [child(C1, "Aachi Global", "4-A"), child(C2, "First Cry", "KG-1")]
    assert attribute(["all parents"], kids, ["Aachi Global School circular"], source_school="First Cry") == [C1]


def test_a_source_school_nobody_attends_falls_through():
    kids = [child(C1, "Aachi Global", "4-A"), child(C2, "First Cry", "KG-1")]
    assert attribute(["all children"], kids, [], source_school="Some Other School") == []


# ----------------------------------------------------------------------------
# where a notice came from
# ----------------------------------------------------------------------------

def test_only_an_institutional_origin_gets_a_key():
    from familyos.origin import source_key
    assert source_key("telegram", {"chat_type": "supergroup", "chat_id": -100123}) == "telegram:chat:-100123"
    assert source_key("telegram", {"chat_type": "private", "chat_id": 555}) is None
    assert source_key("email", {"from": "Office <office@firstcry.edu.in>"}) == "email:firstcry.edu.in"
    assert source_key("gmail_attachment", {"from": "x@aachi.org"}) == "email:aachi.org"
    assert source_key("whatsapp", {"forwarded": True}) is None
    assert source_key("whatsapp", {"group_name": "Grade 4 Parents"}) == "whatsapp:group:grade 4 parents"
    assert source_key("upload", {}) is None
    assert source_key("telegram", None) is None


async def test_a_guardian_says_which_school_a_group_is_and_it_sticks(family):
    r = await family.client.put("/v1/household/source-schools", headers=family.h("amma"),
                                json={"source_key": "telegram:chat:-100123", "school": " First  Cry "})
    assert r.status_code == 200, r.text
    assert r.json()["school"] == "First Cry"
    r = await family.client.get("/v1/household/source-schools", headers=family.h("appa"))
    assert [m["source_key"] for m in r.json()] == ["telegram:chat:-100123"]
    r = await family.client.put("/v1/household/source-schools", headers=family.h("amma"),
                                json={"source_key": "telegram:chat:-100123", "school": "Aachi Global"})
    assert r.json()["school"] == "Aachi Global"
    r = await family.client.delete("/v1/household/source-schools?source_key=telegram:chat:-100123",
                                   headers=family.h("amma"))
    assert r.json()["forgotten"] is True


async def test_an_adult_cannot_say_which_school_a_source_is(family):
    r = await family.client.put("/v1/household/source-schools", headers=family.h("paati"),
                                json={"source_key": "telegram:chat:-1", "school": "X"})
    assert r.status_code == 403


async def test_a_notice_from_a_remembered_group_is_attributed_on_arrival(family, database):
    """End to end: two schools, the group is remembered as First Cry's, a
    "Dear Parents" arrives from that group, the younger one is attached."""
    from familyos.extraction import service
    from tests.test_telegram import BOT, CHAT, post, update

    await _two_at_dps(family, second_school="NPS")           # older: DPS 4, younger: NPS 7
    await family.client.put("/v1/household/source-schools", headers=family.h("amma"),
                            json={"source_key": "telegram:chat:-100200300", "school": "NPS"})
    # The telegram tests' fixtures: bind amma, then a group message naming the bot.
    from familyos import identity
    from familyos.settings import settings
    settings.telegram_webhook_secret, settings.telegram_bot_token, settings.telegram_bot_username = \
        "test-webhook-secret", "7:TESTTOKEN", BOT
    r = await family.client.post("/v1/telegram/link", headers=family.h("amma"))
    await identity.bind_telegram(r.json()["url"].split("start=")[1], CHAT)
    r = await post(family, update(chat_id=-100200300, chat_type="supergroup",
                                  text=f"@{BOT} Dear Parents, PTM on Friday for all"))
    assert r.json()["received"] == 1
    artifact_id = await database.fetchval("SELECT id FROM input_artifacts WHERE channel = 'telegram'")
    a = (await family.client.get(f"/v1/artifacts/{artifact_id}", headers=family.h("amma"))).json()
    assert a["source_key"] == "telegram:chat:-100200300"
    await service.save(uuid.UUID(family.household["id"]), artifact_id, _circular("all parents"))
    assert await _subjects_of(family, artifact_id) == {family.younger["id"]}


# ----------------------------------------------------------------------------
# recording the school
# ----------------------------------------------------------------------------

async def test_a_child_is_added_with_a_school_and_class(family):
    r = await family.client.post("/v1/household/members", headers=family.h("amma"),
                                 json={"display_name": "Third", "role": "child",
                                       "school": "  DPS   Bangalore ", "class_label": "IX-B"})
    assert r.status_code == 201, r.text
    assert (r.json()["school"], r.json()["class_label"]) == ("DPS Bangalore", "IX-B")


async def test_an_adult_cannot_carry_a_school(family):
    r = await family.client.post("/v1/household/members", headers=family.h("amma"),
                                 json={"display_name": "Uncle", "role": "adult",
                                       "email": "uncle@example.com", "school": "DPS"})
    assert r.status_code == 422


async def test_a_guardian_sets_a_childs_school_later(family):
    r = await family.client.patch(f"/v1/members/{family.older['id']}/school", headers=family.h("amma"),
                                  json={"school": "DPS", "class_label": "4"})
    assert r.status_code == 200, r.text
    assert (r.json()["school"], r.json()["class_label"]) == ("DPS", "4")
    # Shown on the household, where a parent looks.
    h = await family.client.get("/v1/household", headers=family.h("amma"))
    older = next(m for m in h.json()["members"] if m["id"] == family.older["id"])
    assert older["class_label"] == "4"


async def test_null_clears_it(family):
    await family.client.patch(f"/v1/members/{family.older['id']}/school", headers=family.h("amma"),
                              json={"school": "DPS", "class_label": "4"})
    r = await family.client.patch(f"/v1/members/{family.older['id']}/school", headers=family.h("amma"),
                                  json={"school": None, "class_label": None})
    assert r.status_code == 200 and r.json()["school"] is None and r.json()["class_label"] is None


async def test_an_adult_member_cannot_set_a_school(family):
    r = await family.client.patch(f"/v1/members/{family.older['id']}/school", headers=family.h("paati"),
                                  json={"school": "DPS"})
    assert r.status_code == 403


async def test_a_school_cannot_be_set_on_a_guardian(family):
    r = await family.client.patch(f"/v1/members/{family.appa['id']}/school", headers=family.h("amma"),
                                  json={"school": "DPS"})
    assert r.status_code == 404


# ----------------------------------------------------------------------------
# through extraction
# ----------------------------------------------------------------------------

def _circular(*scopes: str | None):
    """What the model extractor produces for a circular that names no child:
    one claim per scope it was addressed to."""
    from familyos.extraction.claims import Claim, Extraction, ExtractorInfo
    from tests.test_duplicates import GROUNDED
    from tests.test_extraction import PROMPT_VERSION
    return Extraction(
        extractor=ExtractorInfo(name="openai", model="openai/gpt-5.6-sol",
                                prompt_version=PROMPT_VERSION, parser_version="p1"),
        reference_date=None, actionable=True, page_count=1,
        # Dated and grounded, so each becomes a calendar note and the
        # obligations can be checked for whom they name: an undated or
        # ungrounded claim proposes nothing.
        claims=[Claim(kind="event", title=f"Thing {i}", date=dt.date(2030, 1, 10 + i), applies_to=s,
                      quote=f"thing {i}", location=GROUNDED, confidence=0.9)
                for i, s in enumerate(scopes)])


async def _two_at_dps(family, second_school="DPS"):
    await family.consent(family.older)
    await family.consent(family.younger)
    for kid, cls, school in ((family.older, "4", "DPS"), (family.younger, "7", second_school)):
        await family.client.patch(f"/v1/members/{kid['id']}/school", headers=family.h("amma"),
                                  json={"school": school, "class_label": cls})


async def _subjects_of(family, artifact_id):
    r = await family.client.get(f"/v1/artifacts/{artifact_id}", headers=family.h("amma"))
    return set(r.json()["subject_member_ids"])


async def test_the_ptm_circular_is_about_both_children_at_the_one_school(family, database):
    """The real one: "Dear Parents", a holiday "for the children", dates for
    "all". No school, no class, no name. Both children are at DPS, so it is
    DPS's circular and it is about both of them."""
    from familyos.extraction import service
    from tests.test_extraction import TRIP, make_pdf
    await _two_at_dps(family)
    artifact_id = uuid.UUID((await family.upload("amma", make_pdf(TRIP))).json()["artifact"]["id"])
    counts = await service.save(uuid.UUID(family.household["id"]), artifact_id, _circular("parents", "children", "all"))
    assert counts["subjects_inferred"] == 2
    assert await _subjects_of(family, artifact_id) == {family.older["id"], family.younger["id"]}
    # Two children, so no single subject on the obligations; the artifact
    # carries the pair.
    tasks = (await family.client.get("/v1/obligations", headers=family.h("amma"))).json()
    assert tasks and all(t["subject_member_id"] is None for t in tasks)
    assert await database.fetchval("SELECT bool_and(inferred) FROM artifact_subjects WHERE artifact_id = $1", artifact_id)


async def test_a_class_on_the_circular_picks_one_child_and_names_them_on_the_task(family, database):
    from familyos.extraction import service
    from tests.test_extraction import TRIP, make_pdf
    await _two_at_dps(family)
    artifact_id = uuid.UUID((await family.upload("amma", make_pdf(TRIP))).json()["artifact"]["id"])
    await service.save(uuid.UUID(family.household["id"]), artifact_id, _circular("Dear Parents of Grade 4"))
    assert await _subjects_of(family, artifact_id) == {family.older["id"]}
    tasks = (await family.client.get("/v1/obligations", headers=family.h("amma"))).json()
    assert tasks and all(t["subject_member_id"] == family.older["id"] for t in tasks)


async def test_two_schools_and_no_class_leaves_it_for_a_parent(family, database):
    from familyos.extraction import service
    from tests.test_extraction import TRIP, make_pdf
    await _two_at_dps(family, second_school="NPS")
    artifact_id = uuid.UUID((await family.upload("amma", make_pdf(TRIP))).json()["artifact"]["id"])
    counts = await service.save(uuid.UUID(family.household["id"]), artifact_id, _circular("parents", "all"))
    assert counts["subjects_inferred"] == 0
    assert await _subjects_of(family, artifact_id) == set()


async def test_a_parents_own_tagging_is_never_overridden(family, database):
    """The parent said it is the older one's. The extractor's "all" does not
    get to add the younger one."""
    from familyos.extraction import service
    from tests.test_extraction import TRIP, make_pdf
    await _two_at_dps(family)
    artifact_id = uuid.UUID((await family.upload("amma", make_pdf(TRIP), subjects=[family.older])).json()["artifact"]["id"])
    counts = await service.save(uuid.UUID(family.household["id"]), artifact_id, _circular("all children"))
    assert counts["subjects_inferred"] == 0
    assert await _subjects_of(family, artifact_id) == {family.older["id"]}
    tasks = (await family.client.get("/v1/obligations", headers=family.h("amma"))).json()
    assert tasks and all(t["subject_member_id"] == family.older["id"] for t in tasks)


async def test_a_re_read_replaces_what_it_inferred_and_leaves_nothing_stale(family, database):
    from familyos.extraction import service
    from tests.test_extraction import TRIP, make_pdf
    await _two_at_dps(family)
    artifact_id = uuid.UUID((await family.upload("amma", make_pdf(TRIP))).json()["artifact"]["id"])
    hh = uuid.UUID(family.household["id"])
    await service.save(hh, artifact_id, _circular("all children"))
    assert await _subjects_of(family, artifact_id) == {family.older["id"], family.younger["id"]}
    await service.save(hh, artifact_id, _circular("Grade 7"))
    assert await _subjects_of(family, artifact_id) == {family.younger["id"]}
    await service.save(hh, artifact_id, _circular("account holder"))
    assert await _subjects_of(family, artifact_id) == set()


async def test_a_child_without_consent_is_not_attached_by_any_rule(family, database):
    """One school, one class match, and still nothing: consent is the same
    gate here that it is for a name read off the page."""
    from familyos.extraction import service
    from tests.test_extraction import TRIP, make_pdf
    await family.client.patch(f"/v1/members/{family.older['id']}/school", headers=family.h("amma"),
                              json={"school": "DPS", "class_label": "4"})
    artifact_id = uuid.UUID((await family.upload("amma", make_pdf(TRIP))).json()["artifact"]["id"])
    counts = await service.save(uuid.UUID(family.household["id"]), artifact_id, _circular("Grade 4", "children"))
    assert counts["subjects_inferred"] == 0
    assert await _subjects_of(family, artifact_id) == set()
