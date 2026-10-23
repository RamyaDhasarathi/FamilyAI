"""The audit trail in words: each row said as who did what to which
record, with a notice's headline only when the reader may see it."""
import uuid

from familyos import audit
from familyos.db import pool
from tests.conftest import pdf


async def test_the_trail_is_said_in_sentences(family, database):
    r = await family.upload("amma", pdf("Sports day circular"), filename="sports.pdf", visibility="shared")
    aid = uuid.UUID(r.json()["artifact"]["id"])
    await pool().execute("UPDATE input_artifacts SET source = $2 WHERE id = $1", aid, {"subject": "Sports day circular"})
    r = await family.client.post(f"/v1/artifacts/{aid}/assign", headers=family.h("amma"), json={"member_id": family.appa["id"], "note": "yours"})
    assert r.status_code == 200
    r = await family.client.post(f"/v1/artifacts/{aid}/handled", headers=family.h("appa"), json={"note": "done"})
    assert r.status_code == 200
    r = await family.client.get("/v1/audit?limit=50", headers=family.h("amma"))
    assert r.status_code == 200
    said = {e["action"]: e["said"] for e in r.json()}
    assert said["artifact.assigned"] == "Amma handed “Sports day circular” to Appa, with a note"
    assert said["artifact.handled"].startswith("Appa marked “Sports day circular” handled")
    assert said["artifact.received"].startswith("“Sports day circular” arrived by upload")
    # The note's text is nowhere in the trail.
    assert "yours" not in r.text and "done\"" not in r.text.replace("handled", "")


async def test_a_private_notice_is_not_named_to_another_reader(family, database):
    r = await family.upload("appa", pdf("Appa's private letter"), filename="letter.pdf", visibility="private")
    aid = uuid.UUID(r.json()["artifact"]["id"])
    await pool().execute("UPDATE input_artifacts SET source = $2 WHERE id = $1", aid, {"subject": "A letter only Appa sees"})
    r = await family.client.get("/v1/audit?limit=50", headers=family.h("amma"))
    rows = [e for e in r.json() if e["target_id"] == str(aid)]
    assert rows and all("only Appa sees" not in e["said"] and "a private notice" in e["said"].lower() for e in rows)


def test_every_known_action_has_words():
    names = {}
    for action in ("artifact.received", "extraction.completed", "obligation.accepted", "reminder.sent", "errand.needs_you",
                   "household.rules_set", "reply.sent", "member.signed_in", "something.new"):
        e = {"action": action, "detail": {"channel": "gmail", "claims": 2, "obligations": 1, "service": "urbancompany", "set": ["holidays_accepted"], "via": "google"}, "target_type": "artifact", "actor_kind": "member"}
        s = audit.say(e, who="Amma", about="“A notice”", names=names)
        assert s and (s[0].isupper() or s[0] == "“")
        assert "." not in s.split(" ")[0]   # a sentence, not the action code
