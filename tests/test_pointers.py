"""A notification that only points becomes a card to read the app, and nothing else is mistaken for one."""
import uuid

import pytest

from familyos import pointers

pytestmark = pytest.mark.usefixtures("school_apps")


async def _share(family, text, who="amma"):
    d = (await family.client.post("/v1/devices", headers=family.h(who), json={"label": "iPhone"})).json()
    r = await family.client.post("/v1/inbound/share", headers={"Authorization": "Bearer " + d["token"]}, data={"text": text})
    assert r.status_code == 201, r.text
    return r.json()["artifact"]["id"]


async def _cards(family, who="amma"):
    return [c for c in (await family.client.get("/v1/decisions", headers=family.h(who))).json() if c["kind"] == "pointer"]


def test_only_a_headline_that_points_is_a_pointer():
    for yes in ("📢 You Have a New Announcement!", "New message from school", "You have 2 new circulars", "Tap to view"):
        assert pointers.looks_like_a_pointer(yes), yes
    for no in ("Parent-teacher meeting on Friday", "Term 2 fee due 20 October", "Your order was delivered", "", None):
        assert not pointers.looks_like_a_pointer(no), no


async def test_a_pointer_without_a_known_app_says_to_share_a_screenshot(family):
    artifact = await _share(family, "📢 You Have a New Announcement!\nClick to view")
    (card,) = await _cards(family)
    assert card["id"] == f"pointer:{artifact}" and "announcement" in card["happened"].lower() and "screenshot" in card["recommendation"]["text"]
    assert [a["key"] for a in card["actions"]] == ["handled"]
    # nobody else sees a private share
    assert await _cards(family, "appa") == []
    # saying it is seen clears it
    done = card["actions"][0]
    assert (await family.client.post(done["path"], headers=family.h("amma"), json=done["body"])).status_code == 200
    assert await _cards(family) == []


async def test_with_the_childs_school_app_known_the_card_offers_to_read_it_and_goes_once_asked(family, database):
    await database.execute("UPDATE members SET school = 'Bright Start' WHERE id = $1", uuid.UUID(family.younger["id"]))
    await _share(family, "📢 You Have a New Announcement!")
    (card,) = await _cards(family)
    read = next(a for a in card["actions"] if a["key"].startswith("read"))
    assert read["primary"] and read["body"]["service"] == "brightstart" and read["body"]["kind"] == "look" and "Bright Start" in card["title"]
    r = await family.client.post(read["path"], headers=family.h("amma"), json=read["body"])
    assert r.status_code == 201, r.text
    assert await _cards(family) == []                                  # a read was asked for after it arrived


async def test_a_real_notice_or_a_long_text_is_not_a_pointer(family):
    await _share(family, "Dear Parents, the Parent-Teacher Meeting is on Friday 17 October at 4:30 pm. Kindly attend with both parents.")
    await _share(family, "New announcement: " + "the annual day rehearsal moves to the main hall and every child must bring a white shirt. " * 6)
    assert await _cards(family) == []


async def test_two_school_apps_means_two_buttons_not_a_guess(family, database):
    await database.execute("UPDATE members SET school = 'Bright Start' WHERE id = $1", uuid.UUID(family.younger["id"]))
    await database.execute("UPDATE members SET school = 'Oakridge Global School' WHERE id = $1", uuid.UUID(family.older["id"]))
    await _share(family, "📢 You Have a New Announcement!")
    (card,) = await _cards(family)
    reads = [a for a in card["actions"] if a["key"].startswith("read")]
    assert sorted(a["body"]["service"] for a in reads) == ["brightstart", "myclassboard"] and not any(a["primary"] for a in reads)
    assert "does not say which" in card["happened"] and card["title"] == "A school app has something new"
    assert (await family.client.post(reads[0]["path"], headers=family.h("amma"), json=reads[0]["body"])).status_code == 201
    assert await _cards(family) == []


async def test_a_caregiver_is_not_shown_a_shared_notice_that_every_other_path_hides_from_them(family, database):
    artifact = await _share(family, "📢 You Have a New Announcement!\nClick to view")
    await database.execute("UPDATE input_artifacts SET visibility = 'shared' WHERE id = $1", uuid.UUID(artifact))
    await database.execute("UPDATE members SET circle_role = 'caregiver' WHERE id = $1", uuid.UUID(family.paati["id"]))
    assert await _cards(family, "amma") and not await _cards(family, "paati")
