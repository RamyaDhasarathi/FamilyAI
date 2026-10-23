"""Extraction as a durable job after intake, and the records it leaves.

Every accepted artifact gets an `extract_artifact` job in the same
transaction that accepted it (an upload, an authenticated email and its
attachments, or a quarantined item a guardian vouched for). The job reads
the original, extracts grounded claims, and stores them with the
obligations proposed from them.

The model's answer is cached in the job while it runs, so a job that is
interrupted after the call resumes without paying for it again. Once the
claims are stored the cache is cleared: notice text lives in the claims
tables, which cascade with the artifact on erasure, and nowhere else.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import logging
import re
import uuid

import asyncpg

from familyos import artifacts, audit, categories, consent, documents, jobs, paylinks, reconcile
from familyos.db import pool
from familyos.extraction import attribute, obligations, pipeline, sandbox
from familyos.extraction.claims import Extraction
from familyos.extraction.llm import ModelExtractor
from familyos.extraction.obligations import propose
from familyos.identity import Invalid, NotFound, Principal
from familyos.inbox import HEADLINE
from familyos.settings import settings

logger = logging.getLogger(__name__)

KIND = "extract_artifact"
HANDLER_VERSION = "1"

# What a claim is worth when it was relayed rather than issued. The same shape
# as pipeline.UNGROUNDED_PENALTY: kept and shown, trusted less.
HEARSAY_PENALTY = 0.8

# What a claim is worth when its page was read by OCR rather than lifted from a
# text layer. Characters get confused in ways that matter here: a Devanagari
# notice read in testing turned "14 नवंबर" into "44 नवंबर", which on a deadline
# is not a small error.
OCR_PENALTY = 0.9


async def enqueue(conn: asyncpg.Connection, household_id: uuid.UUID, artifact_ids: list[uuid.UUID], *,
                  member_id: uuid.UUID | None = None) -> list[dict]:
    """Queue extraction for accepted artifacts, inside the caller's transaction."""
    if not settings.extraction_enabled:
        return []
    return [await jobs.create(KIND, {"household_id": str(household_id), "artifact_id": str(a)},
                              household_id=household_id, member_id=member_id, conn=conn) for a in artifact_ids]


def _same(title: str | None) -> str:
    return " ".join((title or "").split()).casefold()


def reference_date(artifact: dict) -> dt.date:
    """The day the notice counts as read on: the email's Date header when
    there is one, otherwise the day it arrived."""
    sent = (artifact.get("source") or {}).get("date")
    if sent:
        try:
            return email.utils.parsedate_to_datetime(sent).date()
        except (TypeError, ValueError):
            pass
    return (artifact.get("received_at") or dt.datetime.now(dt.UTC)).date()


# ----------------------------------------------------------------------------
# the job
# ----------------------------------------------------------------------------

async def _handle(job: dict, ctx: jobs.JobContext) -> dict:
    spec = job["spec"]
    household_id, artifact_id = uuid.UUID(spec["household_id"]), uuid.UUID(spec["artifact_id"])
    await ctx.plan(["Read the notice", "Save claims and proposed tasks"])
    artifact = await _accepted_artifact(household_id, artifact_id)
    if artifact is None:
        await ctx.checkpoint(operations={})
        return {"skipped": "artifact no longer available"}
    if ctx.done("1"):
        return dict((ctx.job.get("state") or {}).get("result") or {})

    await ctx.step("0")
    data = await artifacts.read_bytes(household_id, artifact)
    doc = await sandbox.parse_isolated(data, artifact["media_type"])
    seen_by_model = False
    if str(artifact["media_type"]).startswith("image/"):
        # A picture is a photograph or a document; Memories shows the first.
        from familyos import pictures
        verdict = pictures.kind_of(data, ocr_chars=doc.char_count)
        await pool().execute("UPDATE input_artifacts SET source = COALESCE(source, '{}'::jsonb) || jsonb_build_object('picture', $2::text) WHERE id = $1",
                             artifact["id"], verdict)
        # The household's own model may read the picture itself, which beats
        # the OCR on a stamped scan or a phone's photo of a circular.
        if verdict == pictures.DOCUMENT and settings.local_model and await pool().fetchval(
                "SELECT pictures_by_model FROM households WHERE id = $1", household_id):
            # Not cached: what is written on a picture -- a card's number, a
            # passport page -- is read and let go, like OCR text, never kept.
            try:
                said = await pictures.transcribe(data)
            except Exception:  # noqa: BLE001 - the OCR's reading stands
                logger.warning("the household's model could not read picture %s", artifact["id"], exc_info=True)
                said = ""
            if len(said or "") >= pictures.TRANSCRIPTION_MIN and len(said) > doc.char_count:
                doc = pictures.as_document(artifact["media_type"], said, data)
                seen_by_model = True
    ref = reference_date(artifact)
    from familyos import chat, country
    where = (await country.locale(household_id))["country"]
    extractor = pipeline.make_extractor(local=await chat.local_models_on(household_id))
    if isinstance(extractor, ModelExtractor) and doc.char_count:
        response = await ctx.call(
            "extract", lambda: extractor.call(doc, ref, where),
            args={"sha256": artifact["sha256"], "model": extractor.model, "effort": extractor.effort,
                  "prompt": extractor.prompt_version, "parser": doc.parser_version, "ref": ref.isoformat(), "country": where,
                  **({"seen_by": settings.local_model} if seen_by_model else {})})
        extraction = pipeline.from_model_response(doc, response, extractor, ref)
    else:
        extraction = await pipeline.extract(doc, ref, extractor)
    await ctx.finish_step("0")

    await ctx.step("1")
    text = "\n".join(pg.text for pg in doc.pages)
    # Where a bill's pay link actually lives: the mail's hrefs, which the
    # parser's text drops, and the QR code on a statement's PDF.
    links = paylinks.from_email(data) if artifact["media_type"] == "message/rfc822" else []
    codes = paylinks.from_pdf_qr(data) if artifact["media_type"] == "application/pdf" else []
    result = await save(household_id, artifact_id, extraction, job_id=uuid.UUID(ctx.id), text=text, links=links, codes=codes)
    # A receipt's lines, for the household's rhythm. Deterministic, and only
    # for food and shopping mail; the function decides from the category.
    try:
        from familyos.extraction import items
        result["receipt_items"] = await items.record(household_id, artifact_id, text)
    except Exception:  # noqa: BLE001 - the rhythm is a courtesy; the read stands without it
        logger.warning("could not record receipt items for %s", artifact_id, exc_info=True)
    # The cached answer holds notice text; it is stored in the claims now.
    await ctx.checkpoint(operations={}, state={"result": result})
    await ctx.finish_step("1")
    return result


async def _accepted_artifact(household_id: uuid.UUID, artifact_id: uuid.UUID) -> dict | None:
    row = await pool().fetchrow("SELECT * FROM input_artifacts WHERE id = $1 AND household_id = $2 AND status = 'accepted'",
                                artifact_id, household_id)
    return dict(row) if row else None


def _permitted_name(subject_name: str | None, allowed: list[tuple[uuid.UUID, str]]) -> str | None:
    if not subject_name:
        return None
    return subject_name if any(consent.names_match(subject_name, d) for _, d in allowed) else None


async def save(household_id: uuid.UUID, artifact_id: uuid.UUID, extraction: Extraction, *,
               job_id: uuid.UUID | None = None, text: str | None = None,
               links: list[tuple[str, str]] | None = None, codes: list[str] | None = None) -> dict:
    """Store an extraction, its claims and proposed obligations; supersede the
    previous extraction and replace its still-proposed obligations. With the
    notice's text, a bill's own pay link is kept on its pay obligation."""
    proposed = propose(extraction.claims, extraction.reference_date)
    async with pool().acquire() as conn, conn.transaction():
        artifact = await conn.fetchrow("SELECT id, parent_id, channel, source FROM input_artifacts WHERE id = $1 "
                                       "AND household_id = $2 FOR KEY SHARE", artifact_id, household_id)
        if artifact is None:
            return {"skipped": "artifact deleted"}
        # What kind of mail this is, from the message it arrived in: an
        # attachment is whatever its message is. A promotion or newsletter
        # is read and kept, and nothing in it becomes a task -- the first real
        # mailbox put a life insurer's "lock in before the 21st" on the brief
        # beside the income-tax notice that had a real deadline.
        origin = artifact
        if artifact["parent_id"]:
            origin = await conn.fetchrow("SELECT channel, source FROM input_artifacts WHERE id = $1",
                                         artifact["parent_id"]) or artifact
        category = categories.category_of(origin["channel"], origin["source"])
        child_tagged = bool(await conn.fetchval(
            "SELECT 1 FROM artifact_subjects s JOIN members m ON m.id = s.member_id "
            "WHERE s.artifact_id IN ($1, $2) AND NOT s.inferred AND m.role = 'child' LIMIT 1",
            artifact_id, artifact["parent_id"]))
        standing = dict(await conn.fetchrow(
            "SELECT holidays_accepted, receipts_close_bills, bills_handed_to, investments_quiet FROM households WHERE id = $1", household_id))
        filtered = obligations.for_category(proposed, obligations.category_for_filter(category, tagged_with_child=child_tagged),
                                            extraction.reference_date)
        if category == "trading" and standing.get("investments_quiet", True):
            # The household's rule: investment mail is filed, and asks nothing.
            filtered = obligations.Filtered([], 0, filtered.recorded + len(filtered.kept))
        # The bill's own way to pay, from the words of the notice: the
        # sender's domain says which of several links is the biller's.
        pay_url = paylinks.find(text, sender_domain=categories.sender_domain(origin["source"]) or None,
                                links=links, codes=codes)
        # A statement's PDF and the mail it came in are one bill: the link
        # found on either serves both, whichever was read first.
        if pay_url is None and artifact["parent_id"]:
            pay_url = await conn.fetchval("SELECT pay_url FROM obligations WHERE artifact_id = $1 AND pay_url IS NOT NULL LIMIT 1",
                                          artifact["parent_id"])
        # A UPI intent -- the payee and the amount -- beats a biller's general
        # pay page found earlier on the other half of the same bill.
        better = "(pay_url IS NULL OR (pay_url NOT LIKE 'upi://%' AND $2 LIKE 'upi://%'))"
        if pay_url and artifact["parent_id"] is None:
            await conn.execute(f"UPDATE obligations SET pay_url = $2 WHERE action = 'pay' AND {better} AND artifact_id IN "
                               "(SELECT id FROM input_artifacts WHERE parent_id = $1)", artifact_id, pay_url)
        if pay_url and artifact["parent_id"] is not None:
            # The QR was on the PDF; the mail's own "pay the bill" gets the same link.
            await conn.execute(f"UPDATE obligations SET pay_url = $2 WHERE action = 'pay' AND {better} AND artifact_id = $1",
                               artifact["parent_id"], pay_url)
        proposed, withheld, recorded = filtered.kept, filtered.withheld, filtered.recorded
        actionable, reason = extraction.actionable, extraction.non_actionable_reason
        if withheld:
            actionable, reason = False, categories.WITHHELD_REASON
        # A message and its attachments often say the same thing twice -- the
        # receipt in the body and the PDF of it. One proposal per message --
        # which needs the body and the PDF to be saved one after the other,
        # not side by side on two workers, each blind to the other's rows.
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", str(artifact["parent_id"] or artifact_id))
        family_ids = [artifact["parent_id"]] if artifact["parent_id"] else []
        family_ids += [r["id"] for r in await conn.fetch(
            "SELECT id FROM input_artifacts WHERE parent_id = $1 AND id <> $2",
            artifact["parent_id"] or artifact_id, artifact_id)]
        # The same ask twice is the same title, or the same action on the same
        # day: the PDF says "pay the monthly statement" where the body said
        # "pay the bill", both by the 16th.
        said_rows = await conn.fetch(
            "SELECT title, action, due_date FROM obligations WHERE artifact_id = ANY($1::uuid[]) AND superseded_at IS NULL",
            family_ids) if family_ids else []
        said_titles = {(_same(r["title"]), r["due_date"]) for r in said_rows}
        said_days = {(r["action"], r["due_date"]) for r in said_rows if r["due_date"] is not None}
        duplicates = [o for o in proposed
                      if (_same(o.title), o.due_date) in said_titles or (o.action, o.due_date) in said_days]
        proposed = [o for o in proposed if o not in duplicates]
        # Whom the notice is about. A person's tagging wins outright; failing
        # that, the claims' own audience is matched to the children's classes
        # and school (extraction/attribute.py). The attachment is on the
        # artifact -- a notice about two children is one notice -- and an
        # obligation names a single subject only when there is exactly one.
        tagged = [r["member_id"] for r in await conn.fetch(
            "SELECT DISTINCT member_id FROM artifact_subjects "
            "WHERE (artifact_id = $1 OR artifact_id = $2) AND NOT inferred", artifact_id, artifact["parent_id"])]
        inferred: list[uuid.UUID] = []
        if not tagged:
            inferred = await attribute.infer(
                conn, household_id, artifact_id, [c.applies_to for c in extraction.claims],
                # The school's name is looked for in what the notice said, as
                # far as the claims quote it: the quote, the title, the place.
                [t for c in extraction.claims for t in (c.quote, c.title, c.place)],
                # And where it arrived from, which a household may have said
                # belongs to one school.
                channel=artifact["channel"], source=artifact["source"],
                on=extraction.reference_date or (artifact["received_at"].date() if artifact.get("received_at") else None))
        subjects = tagged or inferred
        subject = subjects[0] if len(subjects) == 1 else None
        # A claim may name a child only when that child has active consent,
        # the same rule artifact_subjects enforces. An extractor that reads a
        # name off the notice does not get to record it otherwise, and a name
        # matching nobody is dropped rather than kept on the chance it is safe.
        # A message a parent forwarded from their own group is second-hand.
        # It is usually the fastest way a family hears anything -- and it is
        # still somebody’s retelling, so it is not worth as much as the
        # school’s own circular saying the same thing.
        hearsay = bool((artifact["source"] or {}).get("forwarded"))
        from_ocr = extraction.ocr_pages > 0
        confidence_factor = (HEARSAY_PENALTY if hearsay else 1.0) * (OCR_PENALTY if from_ocr else 1.0)
        allowed = await consent.consented_children(conn, household_id)
        named = [c.subject_name for c in extraction.claims if c.subject_name]
        dropped = sum(1 for n in named if not any(consent.names_match(n, d) for _, d in allowed))
        await conn.execute("UPDATE extractions SET superseded_at = NOW() WHERE artifact_id = $1 AND superseded_at IS NULL",
                           artifact_id)
        # What a person already decided on this notice, and is still live: a
        # proposal that says the same thing (the same words, or longer ones,
        # on the same date) is not asked again. A decision this same notice
        # superseded earlier does not block anything.
        live = [dict(r) for r in await conn.fetch(
            "SELECT title, action, due_date FROM obligations WHERE artifact_id = $1 AND status <> 'proposed' AND superseded_at IS NULL",
            artifact_id)]
        live_said = [(_same(r["title"]), r["due_date"]) for r in live]
        await conn.execute("DELETE FROM obligations WHERE artifact_id = $1 AND status = 'proposed'", artifact_id)
        extraction_id = uuid.uuid4()
        x = extraction.extractor
        await conn.execute(
            "INSERT INTO extractions (id, household_id, artifact_id, job_id, extractor, model, prompt_version, parser_version, "
            "reference_date, actionable, non_actionable_reason, page_count, ocr_pages, notes) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)",
            extraction_id, household_id, artifact_id, job_id, x.name, x.model, x.prompt_version, x.parser_version,
            extraction.reference_date, actionable, reason, extraction.page_count,
            extraction.ocr_pages, extraction.notes)
        claim_ids = [uuid.uuid4() for _ in extraction.claims]
        await conn.executemany(
            "INSERT INTO claims (id, extraction_id, household_id, artifact_id, ordinal, kind, title, date, end_date, date_text, "
            "time_text, place, amount, currency, amount_text, applies_to, subject_name, requires, optional, uncertain, amends, "
            "change, quote, page, span_start, span_end, boxes, match, confidence, document_kind, issuer, identifier_tail) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, "
            "$10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32)",
            [(claim_ids[i], extraction_id, household_id, artifact_id, i, c.kind, c.title, c.date, c.end_date, c.date_text,
              c.time, c.place, c.amount.value if c.amount else None, c.amount.currency if c.amount else None,
              c.amount.text if c.amount else None, c.applies_to, _permitted_name(c.subject_name, allowed),
              list(c.requires), c.optional, c.uncertain,
              c.amends, c.change, documents.mask_numbers(c.quote) if c.kind == "document" else c.quote, c.page, (c.location or {}).get("start"), (c.location or {}).get("end"),
              (c.location or {}).get("boxes"), (c.location or {}).get("match"),
              round(c.confidence * confidence_factor, 3), c.document_kind, c.issuer, documents.tail(c.identifier_tail))
             for i, c in enumerate(extraction.claims)])
        # A document among the claims is kept as the household's record of it.
        kept_documents = await documents.record(conn, household_id, artifact_id, claim_ids, extraction.claims)
        rows = [(uuid.uuid4(), household_id, artifact_id, claim_ids[o.claim_index], subject, o.kind, o.action, o.title,
                 o.due_date, o.end_date, o.due_time, o.optional, pay_url if o.action == "pay" else None)
                for o in proposed if not _supported({"title": o.title, "action": o.action, "due_date": o.due_date}, live_said)]
        await conn.executemany(
            "INSERT INTO obligations (id, household_id, artifact_id, claim_id, subject_member_id, kind, action, title, due_date, "
            "end_date, due_time, optional, pay_url) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)", rows)
        # What the household decided once, applied as the notice is read.
        ruled = await _standing_rules(conn, household_id, artifact, rows, proposed, standing,
                                      school=obligations.category_for_filter(category, tagged_with_child=child_tagged) in categories.KEEPS_TODAY)
        unsupported = await _supersede_unsupported(conn, household_id, artifact_id, filtered.kept, extraction.claims)
        # Now the claims exist, see whether any of them revises an earlier
        # notice, and whether this is simply the same notice arriving again.
        amendments = await reconcile.propose(conn, household_id, artifact_id)
        merged = await reconcile.merge_exact_duplicate(conn, household_id, artifact_id)
        # Which rail brought this notice, and was it first: the ledger the
        # capture number and the rail scores are computed from (rails.py).
        try:
            from familyos import rails
            await rails.record(conn, household_id, dict(artifact), list(subjects), rows)
        except Exception:  # noqa: BLE001 - a ledger must never stop a notice being read
            logger.warning("rail delivery not recorded for %s", artifact_id, exc_info=True)
        # A receipt among the claims settles the bill it pays for: the bill's
        # notice is marked handled with the receipt as the reason.
        from familyos import loops
        closed = (await loops.close_from_receipt(conn, household_id, dict(artifact), extraction.claims,
                                                 sent_on=extraction.reference_date, source=origin["source"], category=category)
                  if standing.get("receipts_close_bills", True) else [])
        counts = {"amendments_proposed": amendments, "extraction_id": str(extraction_id), "claims": len(claim_ids),
                  "grounded": sum(1 for c in extraction.claims if c.grounded), "obligations": len(rows),
                  "actionable": actionable, "extractor": x.name, "model": x.model,
                  "category": category, "obligations_withheld": withheld, "records_kept": recorded,
                  "pay_link": bool(pay_url) and any(o.action == "pay" for o in proposed),
                  "duplicates_in_message": len(duplicates),
                  "prompt_version": x.prompt_version, "names_dropped": dropped, "hearsay": hearsay,
                  "scripts": extraction.scripts, "from_ocr": from_ocr,
                  "accepted_superseded": unsupported,
                  "loops_closed": [str(c["artifact_id"]) for c in closed],
                  "holidays_accepted": ruled["accepted"], "handed_to": ruled["handed_to"],
                  "documents": kept_documents,
                  "subjects_inferred": len(inferred),
                  "duplicate_of": (merged or {}).get("first_artifact_id"),
                  "obligations_superseded": (merged or {}).get("obligations_superseded", 0)}
        await audit.record(household_id, "extraction.completed", actor_kind="system", target_type="artifact",
                           target_id=artifact_id, detail=counts, conn=conn)
    if closed:
        await loops.tell(closed)
    if ruled.get("tell"):
        from familyos import notify
        for member_id, headline in ruled["tell"]:
            try:
                await notify.member(member_id, f"A bill for you: {headline}",
                                    f"A bill arrived and the household's rule hands bills to you: {headline}\n\nOpen FamilyOS to pay it.")
            except Exception:  # noqa: BLE001 - the hand-over stands; the telling is best effort
                logger.warning("could not tell %s about a bill", member_id, exc_info=True)
    return counts


HOLIDAY = re.compile(r"\b(holiday|holidays|vacation|closed|closure|reopen\w*|last working day|break|half[- ]?day)\b", re.I)


async def _standing_rules(conn, household_id: uuid.UUID, artifact, rows: list, proposed: list, standing: dict, *, school: bool) -> dict:
    """What the household decided once, applied as the notice is read: a
    school's holiday accepted and sent to the calendar; a bill handed to
    the adult named. Each is audited as the rule's doing, not a person's."""
    out = {"accepted": 0, "handed_to": None, "tell": []}
    # rows and proposed are aligned by construction (one row per kept proposal).
    if standing.get("holidays_accepted") and school:
        ids = [r[0] for r in rows if r[5] == "calendar" and r[6] == "note" and not r[11] and HOLIDAY.search(r[7] or "")]
        if ids:
            await conn.execute("UPDATE obligations SET status = 'accepted', decided_by = NULL, decided_at = NOW() WHERE id = ANY($1::uuid[])", ids)
            for oid in ids:
                await audit.record(household_id, "obligation.accepted", actor_kind="system", target_type="obligation", target_id=oid,
                                   detail={"rule": "holidays_accepted"}, conn=conn)
            from familyos import calendar
            await calendar.enqueue_obligations(conn, household_id, ids)
            out["accepted"] = len(ids)
    to = standing.get("bills_handed_to")
    if to and any(r[6] == "pay" for r in rows):
        top = artifact["parent_id"] or artifact["id"]
        row = await conn.fetchrow("SELECT assigned_to, visibility, submitted_by FROM input_artifacts WHERE id = $1 FOR UPDATE", top)
        member = await conn.fetchrow("SELECT display_name, role FROM members WHERE id = $1 AND household_id = $2", to, household_id)
        if row and member and member["role"] != "child" and row["assigned_to"] is None and (row["visibility"] == "shared" or row["submitted_by"] == to):
            note = f"by the household\u2019s rule: bills go to {member['display_name']}"
            await conn.execute("UPDATE input_artifacts SET assigned_to = $2, assigned_by = NULL, assigned_note = $3, assigned_at = NOW() WHERE id = $1", top, to, note)
            headline = await conn.fetchval(f"SELECT {HEADLINE} FROM input_artifacts a WHERE a.id = $1", top)
            await audit.record(household_id, "artifact.assigned", actor_kind="system", target_type="artifact", target_id=top,
                               detail={"member_id": str(to), "rule": "bills_handed_to"}, conn=conn)
            out["handed_to"] = str(to)
            out["tell"].append((to, headline))
    return out


# ----------------------------------------------------------------------------
# reading and deciding
# ----------------------------------------------------------------------------

async def _supersede_unsupported(conn: asyncpg.Connection, household_id: uuid.UUID, artifact_id: uuid.UUID,
                                 proposed: list, claims: list) -> int:
    """A re-read of the same notice can disagree with a decision already made.

    Deleting the still-proposed obligations is safe -- nobody answered them.
    An *accepted* one is different: a person said yes to it, and that decision
    is theirs, not ours to drop. But leaving it untouched is not safe either.
    If the new reading moves the date, or no longer finds the claim at all, the
    accepted row goes on naming a date the notice no longer gives -- and goes
    on reminding about it, which is the one thing this is all for.

    So neither: an accepted obligation the new reading no longer supports is
    superseded, by this same notice. Superseded means reminders stop (the
    scheduler skips it and the sweep cancels what is pending), the row stays
    where the family can see what happened to it, and the corrected date
    arrives beside it as a fresh proposal to accept. What a person decided is
    recorded; what the notice says now is what the family is reminded of.
    """
    accepted = await conn.fetch(
        "SELECT id, title, action, due_date FROM obligations WHERE household_id = $1 AND artifact_id = $2 "
        "AND status = 'accepted' AND superseded_at IS NULL", household_id, artifact_id)
    if not accepted:
        return 0
    # What the new reading says, as the claims say it -- grounded or not,
    # since a quote the grounding could not place is still the reading
    # finding the thing -- and as the proposals made from them.
    said = [(_same(c.title), c.date) for c in claims] + [(_same(o.title), o.due_date) for o in proposed]
    unsupported = [r["id"] for r in accepted if not _supported(r, said)]
    if unsupported:
        await conn.execute("UPDATE obligations SET superseded_at = NOW(), superseded_by_artifact_id = $2 WHERE id = ANY($1::uuid[])",
                           unsupported, artifact_id)
        # The date that was put on the calendar comes off it: the reconciler
        # sees a superseded row and removes its event. Whatever the switch
        # says now -- an event for a date the notice no longer gives is wrong
        # on any setting. (Before 11 Oct 2026 the event stayed, and a family
        # saw "School reopens" three times on 26 October.)
        from familyos import calendar
        await calendar.enqueue_obligations(conn, household_id, unsupported, force=True)
    return len(unsupported)


def _supported(row, said: list[tuple[str, object]]) -> bool:
    """A reading agrees with a row when it gives the same date under the
    same words, or words that contain them ("School reopens" read again as
    "School reopens for a regular working day"). A changed date, or no sign
    of the thing, is disagreement."""
    mine = _same(row["title"])
    for title, date in said:
        if date != row["due_date"]:
            continue
        if title == mine or (len(mine) >= 8 and mine in title) or (len(title) >= 8 and title in mine):
            return True
    return False


async def get_for_artifact(p: Principal, artifact_id: uuid.UUID) -> dict:
    """The current extraction of an artifact the member can see, with its
    claims; or the state of the job still working on it."""
    await artifacts.get_visible(p, artifact_id)
    row = await pool().fetchrow("SELECT * FROM extractions WHERE artifact_id = $1 AND superseded_at IS NULL", artifact_id)
    job = await pool().fetchrow("SELECT id, status, error FROM jobs WHERE kind = $1 AND household_id = $2 "
                                "AND spec->>'artifact_id' = $3 ORDER BY created_at DESC LIMIT 1",
                                KIND, p.household_id, str(artifact_id))
    job_state = {"job_id": job["id"], "job_status": job["status"], "job_error": job["error"]} if job else \
        {"job_id": None, "job_status": None, "job_error": None}
    if row is None:
        return {"artifact_id": artifact_id, "extraction": None, **job_state}
    claims = await pool().fetch("SELECT * FROM claims WHERE extraction_id = $1 ORDER BY ordinal", row["id"])
    return {"artifact_id": artifact_id, "extraction": {**dict(row), "claims": [dict(c) for c in claims]}, **job_state}


async def rerun(p: Principal, artifact_id: uuid.UUID) -> dict:
    await artifacts.get_visible(p, artifact_id)
    async with pool().acquire() as conn, conn.transaction():
        created = await enqueue(conn, p.household_id, [artifact_id], member_id=p.member_id)
    if not created:
        raise Invalid("extraction is turned off")
    return jobs.public(created[0])


_VISIBLE_OBLIGATIONS = ("SELECT o.* FROM obligations o JOIN input_artifacts a ON a.id = o.artifact_id "
                        f"WHERE {artifacts.VISIBLE_TO_MEMBER}")


async def list_obligations(p: Principal, status: str | None = "proposed", limit: int = 100) -> list[dict]:
    rows = await pool().fetch(
        # A handled notice's dates are done with: they are listed nowhere as coming up.
        _VISIBLE_OBLIGATIONS + " AND ($3::text IS NULL OR o.status = $3) "
        "AND (SELECT t.handled_at FROM input_artifacts t WHERE t.id = COALESCE(a.parent_id, a.id)) IS NULL "
        "ORDER BY o.due_date NULLS LAST, o.created_at LIMIT $4",
        p.household_id, p.member_id, status, limit)
    return [dict(r) for r in rows]


async def decide(p: Principal, obligation_id: uuid.UUID, status: str) -> dict:
    if status not in ("accepted", "dismissed"):
        raise Invalid("status must be accepted or dismissed")
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(_VISIBLE_OBLIGATIONS + " AND o.id = $3 FOR UPDATE OF o", p.household_id, p.member_id,
                                  obligation_id)
        if row is None:
            raise NotFound("obligation")
        row = await conn.fetchrow("UPDATE obligations SET status = $2, decided_by = $3, decided_at = NOW() WHERE id = $1 "
                                  "RETURNING *", obligation_id, status, p.member_id)
        await audit.record(p.household_id, f"obligation.{status}", actor_member_id=p.member_id, target_type="obligation",
                           target_id=obligation_id, detail={"artifact_id": str(row["artifact_id"])}, conn=conn)
        # The member's own calendar follows the decision, when they let it; a
        # dismissal takes an event off even after the switch was turned off.
        from familyos import calendar
        await calendar.enqueue_obligations(conn, p.household_id, [obligation_id], force=status == "dismissed")
    return dict(row)


async def file_the_past(conn, today: dt.date) -> int:
    """Two dates that have passed are not misses, and say so themselves.

    A date the reader marked *optional* -- register to speak at the EGM, enter
    the contest -- was never going to be taken up by most households; once it
    has gone, it is dismissed with an audit row saying why, rather than sitting
    at the top of Home as the worst thing in the house. A date whose action is
    only *note* -- the meeting itself, the result's declaration -- was history
    the moment it passed: there was nothing to do, so there was nothing to
    miss. A real deadline the reader believed applied stays, and stays missed,
    until a person dismisses it: that one is theirs to look at.
    """
    rows = await conn.fetch(
        "UPDATE obligations SET status = 'dismissed', decided_by = NULL, decided_at = NOW() "
        "WHERE status = 'proposed' AND superseded_at IS NULL AND due_date IS NOT NULL "
        "AND COALESCE(end_date, due_date) < $1 AND (optional OR action = 'note') "
        "RETURNING id, household_id, artifact_id, optional, action", today)
    for r in rows:
        await audit.record(r["household_id"], "obligation.filed", actor_kind="system", target_type="obligation",
                           target_id=r["id"], detail={"artifact_id": str(r["artifact_id"]),
                                                      "reason": "optional_passed" if r["optional"] else "note_passed"}, conn=conn)
    return len(rows)


def register() -> None:
    jobs.register(KIND, _handle, version=HANDLER_VERSION,
                  settings_keys=("extractor", "extraction_model", "extraction_effort"))
