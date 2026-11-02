"""Medications, read from a prescription or a doctor's note.

A medication is a record with its dates, kept the way a document is: the
original stays on the notice, and each medicine is one row with the drug, the
dose as written, how many times a day, the patient, the prescriber and the
last day of the supply. What it is for:

- A refill is proposed a few days before the supply runs out, as a task a
  person accepts, so the pharmacy is not remembered on the last day.
- Today's doses are *derived*: what the person takes today, from the dose and
  the times a day, for as long as the supply lasts. Nothing is marked taken
  here; a caregiver's acknowledgement is a separate thing (docs/todo.md).
- Nothing is a diagnosis and nothing is advice. The words are the doctor's, as
  written on the notice, and a medicine that was not read cleanly is not
  guessed: it stays a claim on the notice.

A medicine read from a *photograph* (handwriting on a clinic's pad, read by the
household's own model) is flagged `from_picture`: the drug's name is a reading
of handwriting, and the page says to check it against the paper.

Of a patient only a name matched to a member (a child only with consent).
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from familyos import clock, consent
from familyos.artifacts import VISIBLE_TO_MEMBER
from familyos.db import pool
from familyos.identity import Principal

logger = logging.getLogger(__name__)

REFILL_LEAD_DAYS = 5     # a refill is proposed this many days before the supply ends


async def record(conn, household_id: uuid.UUID, artifact_id: uuid.UUID, claim_ids: list[uuid.UUID], claims) -> int:
    """Keep each medication claim of a fresh extraction as a record. Reading
    the same notice again replaces its rows; a newer prescription of the same
    drug for the same patient supersedes the older."""
    meds = [(claim_ids[i], c) for i, c in enumerate(claims) if getattr(c, "kind", None) == "medication" and getattr(c, "grounded", True)]
    await conn.execute("UPDATE medications SET superseded_at = NOW() WHERE artifact_id = $1 AND superseded_at IS NULL", artifact_id)
    if not meds:
        return 0
    adults = {r["id"]: r["display_name"] for r in await conn.fetch(
        "SELECT id, display_name FROM members WHERE household_id = $1 AND role <> 'child'", household_id)}
    children = dict(await consent.consented_children(conn, household_id))
    kept = 0
    for claim_id, c in meds:
        patient_id = None
        if c.subject_name:
            for member_id, name in {**adults, **children}.items():
                if consent.names_match(c.subject_name, name):
                    patient_id = member_id
                    break
        med_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO medications (id, household_id, artifact_id, claim_id, drug, dose_text, times_per_day, patient_member_id, "
            "prescriber, starts_on, ends_on, clinic) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)",
            med_id, household_id, artifact_id, claim_id, c.title[:200], (c.dose_text or None) and c.dose_text[:200],
            c.times_per_day if c.times_per_day and 1 <= c.times_per_day <= 12 else None, patient_id,
            (c.issuer or None) and c.issuer[:120], c.date, c.end_date, (c.place or None) and c.place[:160])
        await conn.execute(
            "UPDATE medications SET superseded_at = NOW(), superseded_by = $1 WHERE household_id = $2 AND id <> $1 AND superseded_at IS NULL "
            "AND artifact_id <> $3 AND lower(drug) = lower($4) AND patient_member_id IS NOT DISTINCT FROM $5",
            med_id, household_id, artifact_id, c.title[:200], patient_id)
        kept += 1
    return kept


def status_of(ends_on: dt.date | None, today: dt.date | None = None) -> tuple[str, int | None]:
    today = today or clock.today()
    if ends_on is None:
        return "ongoing", None
    left = (ends_on - today).days
    if left < 0:
        return "finished", left
    if left <= REFILL_LEAD_DAYS:
        return "refill", left
    return "active", left


_LIST = f"""
SELECT m.id, m.artifact_id, m.drug, m.dose_text, m.times_per_day, m.patient_member_id, m.prescriber, m.clinic, m.starts_on, m.ends_on,
       COALESCE(m.patient_member_id, (SELECT s.member_id FROM artifact_subjects s WHERE s.artifact_id = m.artifact_id
                AND (SELECT count(*) FROM artifact_subjects t WHERE t.artifact_id = m.artifact_id) = 1)) AS patient_id,
       a.received_at::date AS received_on,
       p.display_name AS patient_name,
       EXISTS (SELECT 1 FROM extractions x WHERE x.artifact_id = m.artifact_id AND x.superseded_at IS NULL
               AND x.notes::text LIKE '%from the picture%') AS from_picture
FROM medications m JOIN input_artifacts a ON a.id = m.artifact_id LEFT JOIN members p ON p.id = COALESCE(m.patient_member_id, (SELECT s.member_id FROM artifact_subjects s WHERE s.artifact_id = m.artifact_id AND (SELECT count(*) FROM artifact_subjects t WHERE t.artifact_id = m.artifact_id) = 1))
WHERE {VISIBLE_TO_MEMBER} AND m.superseded_at IS NULL
ORDER BY m.ends_on NULLS LAST, m.drug
"""


async def list_for(p: Principal, today: dt.date | None = None, member_id: uuid.UUID | None = None) -> list[dict]:
    today = today or clock.today()
    out = []
    for r in await pool().fetch(_LIST, p.household_id, p.member_id):
        row = dict(r)
        row["patient_member_id"] = row.pop("patient_id", None) or row["patient_member_id"]
        if member_id and row["patient_member_id"] != member_id:
            continue
        row["status"], row["days_left"] = status_of(row["ends_on"], today)
        row["today"] = bool(row["status"] in ("active", "refill", "ongoing") and (row["starts_on"] is None or row["starts_on"] <= today))
        row["doses_today"] = row["times_per_day"] if row["today"] else None
        out.append(row)
    return out


async def grouped(p: Principal, today: dt.date | None = None) -> list[dict]:
    """The household's prescriptions for a reader: by person, the person with the
    most recent prescription first; within a person, one entry per prescription
    (a notice), newest first, with its medicines. A prescription is its date (the
    first day of its medicines, else the day it arrived) and its prescriber. A
    medicine with no person it can be matched to is grouped under nobody, last."""
    today = today or clock.today()
    by_person: dict[uuid.UUID | None, dict] = {}
    for m in await list_for(p, today):
        who = m["patient_member_id"]
        group = by_person.setdefault(who, {"member_id": who, "name": m["patient_name"], "prescriptions": {}})
        rx = group["prescriptions"].setdefault(m["artifact_id"], {"artifact_id": m["artifact_id"], "date": None, "prescriber": None, "clinic": None,
                                                                   "from_picture": False, "medicines": []})
        rx["date"] = min([d for d in (rx["date"], m["starts_on"]) if d] or [m["received_on"]])
        rx["prescriber"] = rx["prescriber"] or m["prescriber"]
        rx["clinic"] = rx["clinic"] or m["clinic"]
        rx["from_picture"] = rx["from_picture"] or bool(m.get("from_picture"))
        rx["medicines"].append(m)
    out = []
    for group in by_person.values():
        rxs = sorted(group["prescriptions"].values(), key=lambda r: r["date"] or dt.date.min, reverse=True)
        for r in rxs:
            live = [m for m in r["medicines"] if m["status"] in ("active", "refill", "ongoing")]
            r["status"] = "refill" if any(m["status"] == "refill" for m in live) else "current" if live else "finished"
            r["date"] = r["date"] or dt.date.min
        out.append({"member_id": group["member_id"], "name": group["name"], "prescriptions": rxs})
    out.sort(key=lambda g: (g["member_id"] is None, -(g["prescriptions"][0]["date"].toordinal() if g["prescriptions"] else 0)))
    return out


async def correct_date(p: Principal, artifact_id: uuid.UUID, new_start: dt.date) -> int:
    """A person says the date read from a prescription is wrong: every medicine of
    that prescription moves so the first day is the date they give, keeping each
    one's length (handwriting is where a year is misread: 24/4/26 read as 2022).
    Only a prescription the member can see; the audit records the shift, not the drugs."""
    from familyos import audit
    from familyos.identity import Invalid, NotFound
    if not 2000 <= new_start.year <= clock.today().year + 1:
        raise Invalid("that date is not a plausible prescription date")
    rows = [r for r in await list_for(p) if r["artifact_id"] == artifact_id]
    if not rows:
        raise NotFound("prescription")
    first = min([r["starts_on"] for r in rows if r["starts_on"]] or [new_start])
    shift = new_start - first
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute(
            "UPDATE medications SET starts_on = COALESCE(starts_on, $2) + CASE WHEN starts_on IS NULL THEN 0 ELSE $3::int END, "
            "ends_on = CASE WHEN ends_on IS NULL THEN NULL ELSE ends_on + $3::int END "
            "WHERE artifact_id = $1 AND household_id = $4 AND superseded_at IS NULL", artifact_id, new_start, shift.days, p.household_id)
        await audit.record(p.household_id, "medication.date_corrected", actor_member_id=p.member_id, target_type="artifact", target_id=artifact_id,
                           detail={"shift_days": shift.days, "medicines": len(rows)}, conn=conn)
    return len(rows)


async def set_clinic(p: Principal, artifact_id: uuid.UUID, clinic: str | None) -> int:
    """Say which clinic or hospital a prescription came from (the pad's letterhead
    is easy to read and easy to miss). Empty clears it."""
    from familyos import audit
    from familyos.identity import NotFound
    if not [r for r in await list_for(p) if r["artifact_id"] == artifact_id]:
        raise NotFound("prescription")
    clinic = " ".join((clinic or "").split())[:160] or None
    done = await pool().execute("UPDATE medications SET clinic = $2 WHERE artifact_id = $1 AND household_id = $3 AND superseded_at IS NULL",
                                artifact_id, clinic, p.household_id)
    await audit.record(p.household_id, "medication.clinic_set", actor_member_id=p.member_id, target_type="artifact", target_id=artifact_id)
    return int(done.split()[-1])


async def set_patient(p: Principal, artifact_id: uuid.UUID, member_id: uuid.UUID | None) -> int:
    """Say whose prescription this is, when the pad's Name field was not matched and the photo was tagged to someone else.
    Only the medicines of this prescription change; the notice's own tags do not."""
    from familyos import audit
    from familyos.identity import NotFound
    if not [r for r in await list_for(p) if r["artifact_id"] == artifact_id]:
        raise NotFound("prescription")
    if member_id is not None and not await pool().fetchval("SELECT 1 FROM members WHERE id = $1 AND household_id = $2", member_id, p.household_id):
        raise NotFound("member")
    done = await pool().execute("UPDATE medications SET patient_member_id = $2 WHERE artifact_id = $1 AND household_id = $3 AND superseded_at IS NULL",
                                artifact_id, member_id, p.household_id)
    await audit.record(p.household_id, "medication.patient_set", actor_member_id=p.member_id, target_type="artifact", target_id=artifact_id,
                       detail={"member": str(member_id) if member_id else None})
    return int(done.split()[-1])
