"""HTTP API, v1."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
import uuid
from datetime import date
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import PlainTextResponse, RedirectResponse, StreamingResponse
from starlette.datastructures import UploadFile as StarletteUploadFile

from familyos import (
    actions,
    artifacts,
    ask,
    audit,
    billers,
    brief,
    calendar,
    chat,
    consent,
    db,
    digest,
    documents,
    erasure,
    errands,
    export,
    gaps,
    grants,
    guide,
    identity,
    inbox,
    ledger,
    load,
    offers,
    origin,
    plans,
    publiccontext,
    rails,
    reconcile,
    reminders,
    rules,
    suggest,
    todos,
    watches,
)
from familyos.api.deps import current_member, erasure_reader
from familyos.execution import harvest, sessions, sites
from familyos.extraction import service as extraction
from familyos.identity import Principal
from familyos.intake import gateway, mailbox, wa_bridge
from familyos.intake import google as google_adapter
from familyos.intake import telegram as telegram_adapter
from familyos.intake import whatsapp as whatsapp_adapter
from familyos.models import (
    Action,
    ActionApproveIn,
    ActionIn,
    Amendment,
    AmendmentDecisionIn,
    Answer,
    Artifact,
    ArtifactExtraction,
    AskIn,
    Assigned,
    AssignIn,
    AuditEvent,
    Biller,
    BillerIn,
    Brief,
    CaptureSummary,
    ChatIn,
    ChatTurn,
    Consent,
    ConsentIn,
    Credentials,
    Device,
    DeviceIn,
    DeviceIssued,
    DigestPreview,
    DigestSent,
    Document,
    DocumentCheck,
    Documents,
    Erasure,
    Errand,
    ErrandApproveIn,
    ErrandIn,
    Gap,
    GapIn,
    GapResolveIn,
    Grant,
    GrantIn,
    Handled,
    HandledIn,
    HandleIn,
    Harvest,
    HarvestCandidate,
    HarvestIn,
    Household,
    HouseholdCreated,
    HouseholdEraseIn,
    HouseholdIn,
    HouseholdLocaleIn,
    HouseholdRulesIn,
    InboxRow,
    IntakeResult,
    Load,
    Mailbox,
    MailboxAuthorization,
    Member,
    MemberBirthday,
    MemberClass,
    MemberIn,
    MemberSchool,
    Money,
    Obligation,
    ObligationDecisionIn,
    Offer,
    OfferDone,
    PlaceIn,
    PlaceSuggestion,
    Plan,
    PlanChooseIn,
    PlanIn,
    PlanStatusIn,
    QuarantineAcceptIn,
    Reminder,
    ReplyDraft,
    ReplyDraftIn,
    ReplySendIn,
    ReplySent,
    Rules,
    School,
    SchoolIn,
    Session,
    ShareResult,
    SignedIn,
    SignedInSite,
    SignInIn,
    SignInRedeem,
    SignInRequest,
    SignInSitting,
    SiteOffer,
    SourceSchool,
    SourceSchoolIn,
    Suggestion,
    SuggestionAcceptIn,
    Todo,
    TodoDoneIn,
    TodoIn,
    Visibility,
    VisibilityIn,
    Watch,
    WatchIn,
)
from familyos.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")


def _household(row: dict) -> Household:
    return Household(id=row["id"], name=row["name"], inbound_address=identity.inbound_address(row["inbound_token"], row.get("handle")),
                     whatsapp_number=settings.whatsapp_business_number or None,
                     telegram_bot=(settings.telegram_bot_username
                                   if settings.telegram_bot_username and settings.telegram_bot_token
                                   else None),
                     status=row["status"], created_at=row["created_at"],
                     country=row.get("country") or "IN", timezone=row.get("timezone") or "Asia/Kolkata", currency=row.get("currency") or "INR",
                     childrens_notices_shared=row.get("childrens_notices_shared", True),
                     weekly_digest=row.get("weekly_digest", True),
                     calendar_follows_decisions=row.get("calendar_follows_decisions", True),
                     local_models=row.get("local_models", False),
                     members=[Member(**m) for m in row.get("members", [])])


def _member(row: dict) -> Member:
    fields = {k: row[k] for k in Member.model_fields if k in row}
    if "telegram_chat_id" in row:
        fields["telegram_linked"] = row["telegram_chat_id"] is not None
    return Member(**fields)


def _artifact(row: dict) -> Artifact:
    from familyos import categories
    return Artifact(**{k: row[k] for k in Artifact.model_fields if k in row and k != "category"},
                    source_key=origin.source_key(row.get("channel"), row.get("source")),
                    category=categories.category_of(row.get("channel"), row.get("source")))


def _extraction(body: dict) -> ArtifactExtraction:
    x = body["extraction"]
    if x is not None:
        x = {**x, "claims": [{**c, "location": {k: c[k] for k in ("page", "span_start", "span_end", "boxes", "match")}}
                             for c in x["claims"]]}
        x["claims"] = [{**c, "amount": float(c["amount"]) if c["amount"] is not None else None} for c in x["claims"]]
    return ArtifactExtraction(**{**body, "extraction": x})


# ----------------------------------------------------------------------------
# households and members
# ----------------------------------------------------------------------------

@router.post("/households", response_model=HouseholdCreated, status_code=201, tags=["household"])
async def create_household(body: HouseholdIn):
    try:
        household, member, token = await identity.create_household(body)
    except identity.LinkNotUsable as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    full = await identity.get_household(household["id"])
    return HouseholdCreated(household=_household(full), credentials=Credentials(member=_member(member), token=token))


@router.get("/me", response_model=Member, tags=["household"])
async def me(p: Principal = Depends(current_member)):
    return _member(await identity.get_member(p.household_id, p.member_id))


@router.get("/household", response_model=Household, tags=["household"])
async def get_household(p: Principal = Depends(current_member)):
    return _household(await identity.get_household(p.household_id))


@router.post("/household/members", status_code=201, tags=["household"],
             response_model=Credentials | Member,
             description="Guardians add members. Guardians and adults receive a sign-in token once; children do not sign in.")
async def add_member(body: MemberIn, p: Principal = Depends(current_member)):
    member, token = await identity.add_member(p, body)
    return Credentials(member=_member(member), token=token) if token else _member(member)


@router.post("/harvests", response_model=Harvest, status_code=201, tags=["intake"],
             description="Open a sitting: you sign in to the site yourself, pages are collected for you to "
                         "read, and nothing is stored afterwards but what you pick. No credential is taken.")
async def begin_harvest(body: HarvestIn, p: Principal = Depends(current_member)):
    return Harvest(**await harvest.begin(
        p, label=body.label, allow_hosts=body.allow_hosts, minutes=body.minutes))


@router.get("/harvests", response_model=list[Harvest], tags=["intake"],
            description="Your sittings. A sitting belongs to the member who opened it.")
async def list_harvests(p: Principal = Depends(current_member)):
    return [Harvest(**h) for h in await harvest.list_for(p)]


@router.get("/harvests/{harvest_id}/candidates", response_model=list[HarvestCandidate], tags=["intake"],
            description="What was collected, with the text, so you can see what you are choosing.")
async def list_candidates(harvest_id: uuid.UUID, p: Principal = Depends(current_member)):
    return [HarvestCandidate(**c) for c in await harvest.candidates(p, harvest_id)]


@router.post("/harvest-candidates/{candidate_id}/keep", response_model=Artifact, status_code=201,
             tags=["intake"], description="Keep this page. Only now does it enter the record.")
async def keep_candidate(candidate_id: uuid.UUID, p: Principal = Depends(current_member)):
    return _artifact(await harvest.keep(p, candidate_id))


@router.delete("/harvest-candidates/{candidate_id}", status_code=200, tags=["intake"],
               description="Discard this page. What it held is destroyed.")
async def discard_candidate(candidate_id: uuid.UUID, p: Principal = Depends(current_member)):
    await harvest.discard(p, candidate_id)
    return {"discarded": str(candidate_id)}


@router.post("/harvests/{harvest_id}/finish", response_model=Harvest, tags=["intake"],
             description="End the sitting. Anything not picked goes now.")
async def finish_harvest(harvest_id: uuid.UUID, p: Principal = Depends(current_member)):
    return Harvest(**await harvest.finish(p, harvest_id))


@router.post("/ask", response_model=Answer, tags=["obligations"],
             description="Ask the record a question. It answers from what you may see and cites the "
                         "notices it used; an answer that cites nothing is replaced with one that says so. "
                         "It cannot do anything -- acting goes through the action rail.")
async def ask_question(body: AskIn, p: Principal = Depends(current_member)):
    return Answer(**await ask.ask(p, body.question))


@router.get("/load", response_model=Load, tags=["obligations"],
            description="How the work that arrived was divided, and how much of it nobody has touched. "
                        "Counted from notices rather than from anything a family typed in.")
async def household_load(days: int = 90, p: Principal = Depends(current_member)):
    return Load(**await load.share(p, days=max(7, min(days, 365))))


@router.get("/documents", response_model=Documents, tags=["household"],
            description="The documents the family holds, read from its own notices, with their expiries; and what they say "
                        "about the plans -- a passport that runs out before a trip needs it. Last four of a number only.")
async def list_documents(p: Principal = Depends(current_member)):
    docs = await documents.list_for(p)
    found = await documents.checks(p, docs)
    return Documents(documents=[Document(**{k: v for k, v in d.items() if k in Document.model_fields}) for d in docs],
                     checks=[DocumentCheck(**{k: v for k, v in c.items() if k in DocumentCheck.model_fields}) for c in found])


@router.get("/billers", response_model=list[Biller], tags=["obligations"],
            description="Accounts the family pays. Shared ones, and your own.")
async def list_billers(p: Principal = Depends(current_member)):
    return [Biller(**b) for b in await billers.list_for(p)]


@router.post("/billers", response_model=Biller, status_code=201, tags=["obligations"],
             description="Track an account so a bill that does not arrive can be noticed. The consumer "
                         "number is never stored -- only a keyed digest, and the last four digits.")
async def add_biller(body: BillerIn, p: Principal = Depends(current_member)):
    return Biller(**await billers.add(
        p, label=body.label, provider=body.provider, identifier=body.identifier,
        every_days=body.every_days, grace_days=body.grace_days, visibility=body.visibility))


@router.delete("/billers/{biller_id}", status_code=200, tags=["obligations"],
               description="Stop tracking an account.")
async def forget_biller(biller_id: uuid.UUID, p: Principal = Depends(current_member)):
    await billers.forget(p, biller_id)
    return {"forgotten": str(biller_id)}


@router.get("/bills", tags=["obligations"],
            description="What is owed: obligations you can see whose action is a payment.")
async def list_bills(days: int = 60, p: Principal = Depends(current_member)):
    return await billers.bills(p, days=max(1, min(days, 365)))


@router.get("/watches", response_model=list[Watch], tags=["intake"],
            description="Pages you asked FamilyOS to watch. Your own: a watch is a member's errand, "
                        "not household business.")
async def list_watches(p: Principal = Depends(current_member)):
    return [Watch(**w) for w in await watches.list_for(p)]


@router.post("/watches", response_model=Watch, status_code=201, tags=["intake"],
             description="Watch a public page and be told when what it says changes. It is read without any "
                         "credential, and the answer is mailed to you -- nothing is ever done on your behalf.")
async def create_watch(body: WatchIn, p: Principal = Depends(current_member)):
    return Watch(**await watches.create(
        p, url=str(body.url), look_for=body.look_for, label=body.label,
        every_hours=body.every_hours, days=body.days, allow_hosts=body.allow_hosts))


@router.delete("/watches/{watch_id}", status_code=200, tags=["intake"],
               description="Stop watching.")
async def cancel_watch(watch_id: uuid.UUID, p: Principal = Depends(current_member)):
    await watches.cancel(p, watch_id)
    return {"stopped": str(watch_id)}


@router.put("/household/handle", response_model=Household, tags=["household"],
            description="Name the family address. The generated one keeps working, so anything already "
                        "given to a school never breaks.")
async def set_handle(body: HandleIn, p: Principal = Depends(current_member)):
    await identity.set_handle(p, body.handle)
    return _household(await identity.get_household(p.household_id))


@router.put("/household/locale", response_model=Household, tags=["household"],
            description="Where the household lives: country, time zone, home currency. Guardians only. "
                        "The country picks the school year and the payment rails; the zone times the digest "
                        "and the calendar; the currency is the one totals are said in.")
async def set_household_locale(body: HouseholdLocaleIn, p: Principal = Depends(current_member)):
    from familyos import country as countries
    try:
        await countries.set_locale(p, body.country, body.timezone, body.currency)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return await get_household(p)


@router.get("/household/rules", response_model=Rules, tags=["household"],
            description="The household's rules: each a sentence with a switch, or built in and said so. "
                        "With them, what the household has taught by a tap.")
async def get_rules(p: Principal = Depends(current_member)):
    return Rules(**await rules.list_for(p))


@router.put("/household/rules", response_model=Rules, tags=["household"],
            description="Flip one or more switches. Guardians only. Changes what happens from now.")
async def set_rules(body: HouseholdRulesIn, p: Principal = Depends(current_member)):
    await rules.set_switches(p, body.model_dump(exclude_unset=True))
    return Rules(**await rules.list_for(p))


@router.get("/household/handle/available", tags=["household"],
            description="Is this family address free?")
async def handle_available(handle: str, p: Principal = Depends(current_member)):
    return {"handle": handle, "available": await identity.handle_available(handle)}


@router.get("/calendar/upcoming", tags=["intake"],
            description="What is already in a calendar you can see. Read-only, and only the window the "
                        "brief looks at.")
async def calendar_upcoming(days: int = 7, p: Principal = Depends(current_member)):
    return await calendar.upcoming(p, days=max(1, min(days, 45)))


@router.get("/grants", response_model=list[Grant], tags=["household"],
            description="Every live grant in the household. Readable by any member, not only guardians: "
                        "who can see what about you is yours to know.")
async def list_grants(p: Principal = Depends(current_member)):
    return [Grant(**g) for g in await grants.list_for(p)]


@router.post("/grants", response_model=Grant, status_code=201, tags=["household"],
             description="Delegate part of your own view: which obligations, about whom, for how long, and why. "
                         "Reaches obligations only -- never the notices they were read from.")
async def issue_grant(body: GrantIn, p: Principal = Depends(current_member)):
    return Grant(**await grants.issue(
        p, grantee_member_id=body.grantee_member_id, actions=body.actions,
        reason=body.reason, subject_member_id=body.subject_member_id, days=body.days))


@router.delete("/grants/{grant_id}", status_code=200, tags=["household"],
               description="End a grant now. Recorded at both ends.")
async def revoke_grant(grant_id: uuid.UUID, p: Principal = Depends(current_member)):
    await grants.revoke(p, grant_id)
    return {"revoked": str(grant_id)}


@router.post("/sign-in/request", status_code=202, tags=["household"],
             description="Mail a one-time sign-in link. The answer is the same whether or not the address "
                         "belongs to a family: whether it does is not a stranger's to learn.")
async def request_sign_in(body: SignInRequest):
    await identity.request_sign_in(body.email)
    return {"sent": "If that address can sign in, a link is on its way."}


@router.get("/sign-in/google", tags=["household"],
            description="Where to send someone who chose Continue with Google. Basic scopes only -- "
                        "signing in asks Google for nothing that needs review.")
async def google_sign_in(native: bool = False):
    return {"url": (await identity.google_sign_in_url(native=native))["url"]}


@router.get("/sign-in/google/callback", include_in_schema=False)
async def google_sign_in_callback(state: str = "", code: str = "", error: str | None = None):
    # Back to where it began either way: the console, or the phone app
    # through its URL scheme. A browser that followed Google here should
    # land somewhere a person recognises, not on a JSON body.
    app = identity.began_in_app(state)
    home = f"{identity.APP_SCHEME}://signin" if app else "/app/"
    if error or not code:
        return RedirectResponse(f"{home}?signin=cancelled")
    try:
        _, token = await identity.complete_google_sign_in(state, code)
    except identity.NoHouseholdYet as exc:
        # Nothing to sign into yet, so the console opens Start a household
        # with the verified address already in it. The address rides in the
        # fragment for the same reason the token does: it never reaches a
        # server and is taken out of the address bar at once.
        return RedirectResponse(f"{home}?signin=new#found={quote(exc.ticket or '')}&email={quote(exc.email)}")
    except identity.Invalid:
        return RedirectResponse(f"{home}?signin=failed")
    # The token goes in the fragment: it is never sent to a server, and it does
    # not survive into history the way a query does once the console strips it.
    return RedirectResponse(f"{identity.APP_SCHEME}://signed-in#token={quote(token)}" if app else f"/app/#token={quote(token)}")


@router.post("/sign-in/redeem", response_model=SignedIn, status_code=200, tags=["household"],
             description="Spend a one-time link and receive a session token. A link works once.")
async def redeem_sign_in(body: SignInRedeem):
    member, token = await identity.redeem(body.link)
    return SignedIn(member=Member(**member), token=token)


@router.get("/household/source-schools", response_model=list[SourceSchool], tags=["household"],
            description="Which school each remembered source belongs to.")
async def list_source_schools(p: Principal = Depends(current_member)):
    return [SourceSchool(**r) for r in await origin.list_for(p)]


@router.put("/household/source-schools", response_model=SourceSchool, tags=["household"],
            description="Say which school a source belongs to -- a Telegram group, a sending domain. Guardians "
                        "only. Every later notice from it is attributed on arrival. Saying it again replaces.")
async def set_source_school(body: SourceSchoolIn, p: Principal = Depends(current_member)):
    try:
        return SourceSchool(**await origin.remember(p, body.source_key, body.school))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.delete("/household/source-schools", status_code=200, tags=["household"])
async def forget_source_school(source_key: str, p: Principal = Depends(current_member)):
    return {"forgotten": await origin.forget(p, source_key)}


@router.patch("/members/{member_id}/school", response_model=Member, tags=["household"],
              description="Which school and class a child is in -- the key circulars are addressed by. "
                          "Guardians only, children only. Null clears.")
async def set_member_school(member_id: uuid.UUID, body: MemberSchool, p: Principal = Depends(current_member)):
    return _member(await identity.set_school(p, member_id, body.school, body.class_label, body.since))


@router.get("/places/search", response_model=list[PlaceSuggestion], tags=["household"],
            description="Places for typed words, a pasted Google Maps link or a pair of coordinates, from the public map "
                        "(OpenStreetMap's Nominatim), with the home town as the bias. Nothing of the family's leaves but the words. "
                        "Adults only: it is how home, the office and a school get their point.")
async def search_places(q: str, p: Principal = Depends(current_member)):
    if p.role == "child":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "a child does not set the household's places")
    q = q.strip()[:300]
    if len(q) < 3:
        return []
    home = await db.pool().fetchrow("SELECT home_lat, home_lon FROM households WHERE id = $1", p.household_id)
    near = (home["home_lat"], home["home_lon"]) if home and home["home_lat"] is not None else None
    try:
        return await publiccontext.resolve(q, near)
    except Exception as exc:  # noqa: BLE001 - the public map is a courtesy
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "the map could not be reached just now") from exc


@router.put("/household/places/{key}", response_model=Rules, tags=["household"],
            description="Home or the office (`home` or `work`), as the words and the point picked on the map search. Guardians only. Null clears.")
async def set_household_place(key: str, body: PlaceIn, p: Principal = Depends(current_member)):
    if key not in ("home", "work"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "a place is home or work")
    try:
        await rules.set_place(p, key + "_place", body.label, body.lat, body.lon)
    except identity.NotAllowed as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return Rules(**await rules.list_for(p))


@router.patch("/members/{member_id}/birthday", response_model=Member, tags=["household"],
              description="A member's date of birth. A guardian sets anyone's; an adult their own. Null clears.")
async def set_member_birthday(member_id: uuid.UUID, body: MemberBirthday, p: Principal = Depends(current_member)):
    try:
        return _member(await identity.set_birthday(p, member_id, body.date_of_birth))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("/rails", tags=["household"],
            description="Per school: which rail its notices come by, how many each brought first, echoed or brought empty, "
                        "and a Beta-smoothed score per rail. Computed from the delivery ledger, never stored.")
async def list_rails(p: Principal = Depends(current_member)):
    return await rails.summary(p)


@router.get("/household/schools", response_model=list[School], tags=["household"],
            description="The household's schools: each with the children in it and the groups or senders mapped to it.")
async def list_schools(p: Principal = Depends(current_member)):
    from familyos import schools
    return [School(**r) for r in await schools.list_for(p)]


@router.put("/household/schools/{school_id}", response_model=School, tags=["household"],
            description="Rename a school or set its portal. Guardians only. A rename follows through to the children and the source map.")
async def update_school(school_id: uuid.UUID, body: SchoolIn, p: Principal = Depends(current_member)):
    from familyos import schools
    await schools.update(p, school_id, **body.model_dump(exclude_unset=True))
    return next(School(**r) for r in await schools.list_for(p) if r["id"] == school_id)


@router.get("/members/{member_id}/classes", response_model=list[MemberClass], tags=["household"],
            description="Every school and class a child has been recorded in, latest first, with the day each began.")
async def member_classes(member_id: uuid.UUID, p: Principal = Depends(current_member)):
    return [MemberClass(**r) for r in await identity.class_history(p, member_id)]


@router.post("/members/{member_id}/invite", status_code=202, tags=["household"],
             description="Send a member their way in. Guardians only; a child has nothing to sign in to.")
async def invite_member(member_id: uuid.UUID, p: Principal = Depends(current_member)):
    return {"invited": await identity.invite(p, member_id)}


@router.post("/signout", status_code=200, tags=["household"],
             description="End the token this request arrived on. Other devices stay signed in.")
async def sign_out(p: Principal = Depends(current_member)):
    return {"ended": await identity.sign_out(p)}


@router.post("/errands", response_model=Errand, status_code=201, tags=["errands"],
             description="Write a booking or purchase down in full -- what, when, the most it may cost, how it is "
                         "paid -- fingerprinted. Nothing runs until a guardian approves exactly this.")
async def propose_errand(body: ErrandIn, p: Principal = Depends(current_member)):
    return Errand(**await errands.propose(p, service=body.service, kind=body.kind, title=body.title, spec=body.spec.model_dump()))


@router.get("/errands", response_model=list[Errand], tags=["errands"])
async def list_errands(p: Principal = Depends(current_member)):
    return [Errand(**x) for x in await errands.list_for(p)]


@router.get("/errands/{errand_id}", response_model=Errand, tags=["errands"])
async def get_errand(errand_id: uuid.UUID, p: Principal = Depends(current_member)):
    return Errand(**await errands.get(p, errand_id))


@router.post("/errands/{errand_id}/approve", response_model=Errand, tags=["errands"],
             description="A guardian approves exactly what was shown, by echoing back its fingerprint.")
async def approve_errand(errand_id: uuid.UUID, body: ErrandApproveIn, p: Principal = Depends(current_member)):
    return Errand(**await errands.approve(p, errand_id, body.params_sha256, body.run_on))


@router.post("/errands/{errand_id}/finish", response_model=Errand, tags=["errands"],
             description="I finished it in the browser: the errand is done and the browser released.")
async def finish_errand(errand_id: uuid.UUID, p: Principal = Depends(current_member)):
    return Errand(**await errands.finish(p, errand_id))


@router.post("/errands/{errand_id}/live-ticket", tags=["errands"])
async def errand_live_ticket(errand_id: uuid.UUID, p: Principal = Depends(current_member)):
    ticket = await sessions.issue_errand_live_ticket(p, errand_id)
    return {"path": f"/v1/errands/{errand_id}/live?ticket={ticket}"}


@router.websocket("/errands/{errand_id}/live")
async def errand_live_socket(websocket: WebSocket, errand_id: uuid.UUID, ticket: str = ""):
    from familyos.execution import livebridge
    ws_url = sessions.redeem_errand_live_ticket(ticket, errand_id)
    if not ws_url:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        await livebridge.bridge(websocket, ws_url, origin=str(websocket.base_url).rstrip("/"))
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.info("live view ended for errand %s", errand_id, exc_info=True)
    finally:
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass


@router.websocket("/errands/{errand_id}/phone")
async def errand_phone_socket(websocket: WebSocket, errand_id: uuid.UUID, token: str = ""):
    """The app's web view as the errand's browser. The app connects with its
    session token, answers the runbook's questions (goto, text, buttons,
    press ...) by id, and the run ends when the socket does."""
    from familyos.execution import phone
    p = await identity.authenticate(token) if token else None
    if p is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    driver = phone.attach(errand_id, websocket.send_json)
    run = asyncio.create_task(_run_on_phone(websocket, p, errand_id, driver))
    try:
        while True:
            message = await websocket.receive_json()
            driver.answer(message)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.info("phone socket for errand %s ended", errand_id, exc_info=True)
    finally:
        # The phone is gone: every question still waiting fails with
        # PhoneGone, the runbook writes needs_you on the row, and only a run
        # that does not wind down on its own is cancelled.
        phone.detach(errand_id, driver)
        driver.disconnect()
        if not run.done():
            try:
                await asyncio.wait_for(asyncio.shield(run), 15)
            except (TimeoutError, Exception):  # noqa: BLE001
                run.cancel()


async def _run_on_phone(websocket: WebSocket, p: Principal, errand_id: uuid.UUID, driver) -> None:
    try:
        outcome = await errands.run_on_phone(p, errand_id, driver)
        await websocket.send_json({"op": "ended", "outcome": outcome})
    except Exception as exc:  # noqa: BLE001 - said to the phone, then the socket closes
        try:
            await websocket.send_json({"op": "ended", "error": str(exc)[:300]})
        except Exception:  # noqa: BLE001
            pass


@router.post("/errands/{errand_id}/cancel", response_model=Errand, tags=["errands"])
async def cancel_errand(errand_id: uuid.UUID, p: Principal = Depends(current_member)):
    return Errand(**await errands.cancel(p, errand_id))


@router.get("/sites", response_model=list[SiteOffer], tags=["sessions"],
            description="The sites a member can sign in to for FamilyOS to act on. A short, checked list.")
async def list_sites(p: Principal = Depends(current_member)):
    return [SiteOffer(**x) for x in sites.listing()]


@router.post("/sign-ins", response_model=SignInSitting, status_code=201, tags=["sessions"],
             description="Open a browser on the site's sign-in page. You sign in yourself; no password passes "
                         "through FamilyOS. When you say you are in, what the browser holds for that site is "
                         "sealed under the household key and the browser is released.")
async def begin_sign_in(body: SignInIn, p: Principal = Depends(current_member)):
    return SignInSitting(**await sessions.begin_sign_in(p, body.service))


@router.get("/sign-ins/open", response_model=SignInSitting | None, tags=["sessions"])
async def open_sign_in(p: Principal = Depends(current_member)):
    row = await sessions.open_sign_in(p)
    return SignInSitting(**row) if row else None


@router.post("/sign-ins/{sitting_id}/seal", response_model=SignedInSite, tags=["sessions"],
             description="I am signed in: seal the session and release the browser.")
async def seal_sign_in(sitting_id: uuid.UUID, p: Principal = Depends(current_member)):
    return SignedInSite(**await sessions.seal_sign_in(p, sitting_id))


@router.post("/sign-ins/{sitting_id}/live-ticket", tags=["sessions"],
             description="A one-time ticket for the live view's socket: used once, within a minute.")
async def live_ticket(sitting_id: uuid.UUID, p: Principal = Depends(current_member)):
    ticket = await sessions.issue_live_ticket(p, sitting_id)
    return {"path": f"/v1/sign-ins/{sitting_id}/live?ticket={ticket}"}


@router.websocket("/sign-ins/{sitting_id}/live")
async def live_socket(websocket: WebSocket, sitting_id: uuid.UUID, ticket: str = ""):
    """The live view's wire: relayed to the sitting's browser, nothing kept."""
    from familyos.execution import livebridge
    row = await sessions.redeem_live_ticket(ticket, sitting_id)
    if row is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        await livebridge.bridge(websocket, row["ws_url"], origin=str(websocket.base_url).rstrip("/"))
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - the browser went away; the console says so
        logger.info("live view ended for sitting %s", sitting_id, exc_info=True)
    finally:
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass


@router.delete("/sign-ins/{sitting_id}", status_code=204, tags=["sessions"])
async def abandon_sign_in(sitting_id: uuid.UUID, p: Principal = Depends(current_member)):
    await sessions.abandon_sign_in(p, sitting_id)
    return Response(status_code=204)


@router.get("/signed-in", response_model=list[SignedInSite], tags=["sessions"],
            description="The sites you are signed in to, and nothing of what the sessions hold.")
async def list_signed_in(p: Principal = Depends(current_member)):
    return [SignedInSite(**{**x, "label": sites.get(x["service"])["label"] if x["service"] in sites.SITES else x["service"]})
            for x in await sessions.list_for(p)]


@router.delete("/signed-in/{session_id}", status_code=204, tags=["sessions"],
               description="Sign out: the sealed session is revoked and cannot be opened again.")
async def revoke_signed_in(session_id: uuid.UUID, p: Principal = Depends(current_member)):
    await sessions.revoke(p, session_id)
    return Response(status_code=204)


@router.get("/sessions", response_model=list[Session], tags=["household"],
            description="Live sign-ins. Your own, or any member's if you are a guardian.")
async def list_sessions(member_id: uuid.UUID | None = None, p: Principal = Depends(current_member)):
    return [Session(**s) for s in await identity.sessions(p, member_id)]


@router.post("/members/{member_id}/signout", status_code=200, tags=["household"],
             description="End every token a member holds. Yourself, or anyone in the household if you are a "
                         "guardian -- the answer to a lost phone.")
async def revoke_member_sessions(member_id: uuid.UUID, p: Principal = Depends(current_member)):
    return {"ended": await identity.revoke_all(p, member_id)}


@router.post("/household/erase", response_model=Erasure, status_code=202, tags=["erasure"],
             description="Erase the whole household. Sign-in stops at once; the household key is destroyed, then every "
                         "original, record and audit event is deleted.")
async def erase_household(body: HouseholdEraseIn, p: Principal = Depends(current_member)):
    return Erasure(**await erasure.request_household_erasure(p, body.confirm_name))


@router.post("/members/{member_id}/erase", response_model=Erasure, status_code=202, tags=["erasure"])
async def erase_member(member_id: uuid.UUID, p: Principal = Depends(current_member)):
    return Erasure(**await erasure.request_subject_erasure(p, member_id, reason="member_erased", delete_member=True))


@router.get("/erasures/{erasure_id}", response_model=Erasure, tags=["erasure"],
            description="Progress of an erasure. Readable while a household erasure runs, which is the only "
                        "request an erasing household still answers; once it finishes there is nobody left to ask.")
async def get_erasure(erasure_id: uuid.UUID, p: Principal = Depends(erasure_reader)):
    return Erasure(**await erasure.get(p.household_id, erasure_id))


# ----------------------------------------------------------------------------
# artifacts
# ----------------------------------------------------------------------------

@router.post("/artifacts", response_model=IntakeResult, tags=["intake"],
             responses={201: {"model": IntakeResult}, 200: {"description": "Duplicate: already received"}})
async def upload(response: Response, file: UploadFile = File(...), visibility: Visibility = Form("private"),
                 subject_member_ids: list[uuid.UUID] = Form(default_factory=list), note: str | None = Form(None),
                 p: Principal = Depends(current_member)):
    data = await file.read(settings.max_upload_bytes + 1)
    row, duplicate = await gateway.receive_upload(p, data, filename=file.filename, declared_type=file.content_type,
                                                  visibility=visibility, subject_member_ids=subject_member_ids, note=note)
    response.status_code = 200 if duplicate else 201
    return IntakeResult(duplicate=duplicate, artifact=_artifact(row))


def _field(form, name: str) -> str | None:
    """A plain form value, or None when it is missing, blank, or a file part."""
    v = form.get(name)
    return v if isinstance(v, str) and v.strip() else None


@router.post("/inbound/share", response_model=ShareResult, tags=["intake"],
             description="What a phone handed over through the share sheet or a shortcut: a file, an image, a "
                         "piece of text, or a URL (read once as a public page). Private to the member whose token "
                         "sent it. A short text naming a child tags what was shared just before.")
async def inbound_share(request: Request, response: Response, p: Principal = Depends(current_member)):
    # The form is read by hand rather than declared: Shortcuts sends the
    # shared thing as a file part for a photo or PDF and as a plain value
    # for text or a URL, under the same field name. A declared UploadFile
    # would refuse the plain value before this code ran, as a bare 422 the
    # phone cannot explain.
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type and content_type not in ("multipart/form-data", "application/x-www-form-urlencoded"):
        # The shortcut's other shape: Request Body "File" with Shortcut
        # Input, the file itself as the body, and the tag, note and
        # visibility as headers (X-Tag, X-Note, X-Visibility). A phone
        # that will not put a variable into a File form field can still
        # send the picture this way.
        body = await request.body()
        tag, note = (request.headers.get("x-tag") or "").strip() or None, (request.headers.get("x-note") or "").strip() or None
        visibility = (request.headers.get("x-visibility") or "private").strip().lower()
        if visibility not in ("private", "shared"):
            raise HTTPException(422, "X-Visibility must be private or shared")
        if tag and tag.lower() in ("nobody", "skip", "none", "-", "no one"):
            tag = None
        text = url = None
        data, declared = body, content_type
        filename = None
        if content_type.startswith("text/") and len(body) <= gateway.SHARE_TEXT_MAX:
            text, data = body.decode("utf-8", "replace"), None
            if gateway.urlsplit_host(text.strip()) and "\n" not in text.strip():
                url, text = text.strip(), None
        if not data and not text and not url:
            from fastapi.responses import JSONResponse
            said = "Nothing was shared: the request body was empty."
            return JSONResponse({"detail": said, "message": said}, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        out = await gateway.receive_share(p, data=data, text=text, url=url, filename=filename, declared_type=declared,
                                          note=note, visibility=visibility, tag=tag)
        if "artifact" not in out:
            names = out["tagged"]
            return ShareResult(tagged=names, message=("Tagged: " + ", ".join(names)) if names
                               else "That named a child, but there was nothing recent to attach it to.")
        response.status_code = 200 if out["duplicate"] else 201
        return _share_result(out)
    form = await request.form()
    item, text, url = form.get("item"), _field(form, "text"), _field(form, "url")
    note, tag = _field(form, "note"), _field(form, "tag")
    visibility = _field(form, "visibility") or "private"
    if visibility not in ("private", "shared"):
        raise HTTPException(422, "visibility must be private or shared")
    data = filename = declared = None
    if isinstance(item, StarletteUploadFile):
        data = await item.read(settings.max_upload_bytes + 1)
        filename, declared = item.filename, item.content_type
        # Shortcuts sends shared text as a text part too; treat it as text.
        if (declared or "").startswith("text/plain") and len(data) <= gateway.SHARE_TEXT_MAX and not text:
            text, data = data.decode("utf-8", "replace"), None
    elif isinstance(item, str) and item.strip() and not text and not url:
        # A plain value: a URL if it looks like one, otherwise text.
        if gateway.urlsplit_host(item.strip()):
            url = item.strip()
        else:
            text = item
    # "Nobody" / "Skip" from the shortcut's list means no tag.
    if tag and tag.strip().lower() in ("nobody", "skip", "none", "-", "no one"):
        tag = None
    # A photo shared with the form field typed as Text arrives as the
    # photo's identifier, 36 characters of hex: the phone sent the name of
    # the picture, not the picture. Said precisely, because the phone shows
    # this line.
    import re as _re
    if text and not data and not url and _re.fullmatch(r"\s*[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}(?:/L0/001)?\s*", text):
        from fastapi.responses import JSONResponse
        said = ("The photo's name arrived, not the photo \u2014 in the shortcut's Get Contents of URL, tap the \u2018item\u2019 field's type "
                "and choose File (not Text), with Shortcut Input as its value.")
        return JSONResponse(status_code=422, content={"error": "invalid", "detail": said, "message": said})
    if not data and not text and not url:
        # Said precisely, because the phone shows this line: which fields
        # arrived tells the person which step of the shortcut is unwired.
        got = [k for k, v in (("item", item), ("text", text), ("url", url), ("tag", tag), ("note", note)) if v]
        said = ("Nothing was shared" + (f" (only: {', '.join(got)})" if got else " (no fields at all)")
                + " \u2014 in the shortcut, the form field \u2018item\u2019 should be Shortcut Input.")
        from fastapi.responses import JSONResponse
        # Both keys: `detail` for the API's own error shape, `message` for the phone's banner.
        return JSONResponse({"detail": said, "message": said}, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    out = await gateway.receive_share(p, data=data, text=text, url=url, filename=filename, declared_type=declared,
                                      note=note, visibility=visibility, tag=tag)
    if "artifact" not in out:
        names = out["tagged"]
        return ShareResult(tagged=names, message=("Tagged: " + ", ".join(names)) if names
                           else "That named a child, but there was nothing recent to attach it to.")
    response.status_code = 200 if out["duplicate"] else 201
    return _share_result(out)


def _share_result(out: dict) -> ShareResult:
    art = _artifact(out["artifact"])
    what = art.filename or art.channel
    names = out.get("tagged") or []
    return ShareResult(artifact=art, duplicate=out["duplicate"], tagged=names or None,
                       message=("Already in your Inbox: " if out["duplicate"] else "Saved to your Inbox: ") + what
                       + (" — for " + ", ".join(names) if names else ""))


@router.post("/devices", response_model=DeviceIssued, status_code=201, tags=["household"],
             description="A token for one phone's shortcut or automation. Shown once; never expires; revoke it here.")
async def add_device(body: DeviceIn, p: Principal = Depends(current_member)):
    row, token = await identity.issue_device_token(p, body.label)
    base = settings.console_url.split("/app")[0].rstrip("/")
    return DeviceIssued(device=Device(**row), token=token, share_url=f"{base}/v1/inbound/share")


@router.get("/devices", response_model=list[Device], tags=["household"])
async def list_devices(p: Principal = Depends(current_member)):
    return [Device(**d) for d in await identity.list_devices(p)]


@router.delete("/devices/{token_id}", status_code=204, tags=["household"])
async def revoke_device(token_id: uuid.UUID, p: Principal = Depends(current_member)):
    await identity.revoke_device(p, token_id)
    return Response(status_code=204)


@router.get("/artifacts", response_model=list[Artifact], tags=["artifacts"])
async def list_artifacts(limit: int = 50, p: Principal = Depends(current_member)):
    return [_artifact(r) for r in await artifacts.list_visible(p, limit=min(max(limit, 1), 200))]


@router.post("/plans", response_model=Plan, status_code=202, tags=["obligations"],
             description="Plan something open-ended -- a trip, a move -- with the household's dates and budget in "
                         "view. Answers at once with the plan as \"writing\"; it is written over about a minute, and "
                         "GET /plans/{id} shows it filled in. Candidate bookings are public pages read without "
                         "signing in; the legwork becomes to-dos. Nothing is booked or paid.")
async def draft_plan(body: PlanIn, p: Principal = Depends(current_member)):
    return Plan(**await plans.start(p, body.brief, shape=body.shape))


@router.get("/plans", response_model=list[Plan], tags=["obligations"])
async def list_plans(p: Principal = Depends(current_member)):
    return [Plan(**x) for x in await plans.list_for(p)]


@router.post("/plans/{plan_id}/guide", tags=["plans"],
             description="A guide page for the plan, composed by the model from an allow-listed component library "
                         "and streamed as newline-delimited events: {type: line, text} per line that passed the gate, "
                         "then {type: done}, or {type: error, detail}. A pilot of generative UI.")
async def plan_guide(plan_id: uuid.UUID, p: Principal = Depends(current_member)):
    async def events():
        async for ev in guide.stream(p, plan_id):
            yield json.dumps(ev, default=str) + "\n"
    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/plans/{plan_id}", response_model=Plan, tags=["obligations"])
async def get_plan(plan_id: uuid.UUID, p: Principal = Depends(current_member)):
    return Plan(**await plans.get(p, plan_id))


@router.post("/plans/{plan_id}/choose", response_model=Plan, tags=["obligations"],
             description="Pick an option, or say it was booked (the confirmation arrives by mail; its watch stops).")
async def choose_plan_option(plan_id: uuid.UUID, body: PlanChooseIn, p: Principal = Depends(current_member)):
    return Plan(**await plans.choose(p, plan_id, body.option_id, booked=body.booked))


@router.patch("/plans/{plan_id}", response_model=Plan, tags=["obligations"])
async def set_plan_status(plan_id: uuid.UUID, body: PlanStatusIn, p: Principal = Depends(current_member)):
    return Plan(**await plans.set_status(p, plan_id, body.status))


@router.get("/digest", response_model=DigestPreview, tags=["obligations"],
            description="This week's digest as it would be sent to you: the same words, on demand.")
async def digest_preview(p: Principal = Depends(current_member)):
    subject, body = await digest.compose(p)
    return DigestPreview(subject=subject, body=body, sends_on=digest.describe())


@router.post("/digest/send", response_model=DigestSent, tags=["obligations"],
             description="Send yourself this week's digest now, over Telegram, else email.")
async def digest_send(p: Principal = Depends(current_member)):
    import datetime as _dt
    return DigestSent(**await digest.send_to(p, _dt.date.today(), force=True))


@router.post("/chat", response_model=ChatTurn, tags=["obligations"],
             description="One turn with the household. The model sees what you may see and cites it; it may propose "
                         "handing a notice over, a to-do, or a decision, and nothing happens until you confirm -- "
                         "confirming calls the ordinary endpoint.")
async def chat_turn(body: ChatIn, p: Principal = Depends(current_member)):
    return ChatTurn(**await chat.turn(p, body.message, [h.model_dump() for h in body.history]))


@router.post("/chat/stream", tags=["obligations"],
             description="The same turn, written live: newline-delimited JSON events -- {type: say, delta} as the answer "
                         "is produced, then {type: turn, ...} with the citations and proposals, or {type: error, detail}.")
async def chat_turn_stream(body: ChatIn, p: Principal = Depends(current_member)):
    async def events():
        async for ev in chat.stream_turn(p, body.message, [h.model_dump() for h in body.history]):
            yield json.dumps(ev, default=str) + "\n"
    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/suggestions", response_model=list[Suggestion], tags=["obligations"],
            description="To-dos the calendar implies -- a gift before the party, passports before the trip. "
                        "Suggested only; Add makes a to-do, the cross is remembered.")
async def list_suggestions(p: Principal = Depends(current_member)):
    return [Suggestion(**x) for x in await suggest.for_member(p)]


@router.post("/suggestions/{key}/accept", response_model=Todo, status_code=201, tags=["obligations"])
async def accept_suggestion(key: str, body: SuggestionAcceptIn, p: Principal = Depends(current_member)):
    return Todo(**await suggest.accept(p, key, assigned_to=body.assigned_to))


@router.get("/offers", response_model=list[Offer], tags=["obligations"],
            description="What FamilyOS could start doing, or is about to, said in the family's names: a rule to switch on, "
                        "a question for Ask, or a thing said once. Derived from the record each time; Not now is remembered.")
async def list_offers(p: Principal = Depends(current_member)):
    return [Offer(**{k: v for k, v in x.items() if k != "member_id"}) for x in await offers.for_member(p)]


@router.post("/offers/{key}/accept", response_model=OfferDone, tags=["obligations"])
async def accept_offer(key: str, p: Principal = Depends(current_member)):
    return OfferDone(**await offers.accept(p, key))


@router.post("/offers/{key}/dismiss", status_code=204, tags=["obligations"])
async def dismiss_offer(key: str, p: Principal = Depends(current_member)):
    await offers.dismiss(p, key)
    return Response(status_code=204)


@router.post("/suggestions/{key}/dismiss", status_code=204, tags=["obligations"])
async def dismiss_suggestion(key: str, p: Principal = Depends(current_member)):
    await suggest.dismiss(p, key)
    return Response(status_code=204)


@router.get("/todos", response_model=list[Todo], tags=["obligations"])
async def list_todos(include_done: bool = False, p: Principal = Depends(current_member)):
    return [Todo(**t) for t in await todos.list_for(p, include_done=include_done)]


@router.post("/todos", response_model=Todo, status_code=201, tags=["obligations"],
             description="A to-do the family wrote. Shared with the household's adults; the assignee is told.")
async def add_todo(body: TodoIn, p: Principal = Depends(current_member)):
    return Todo(**await todos.add(p, body.title, due_date=body.due_date, due_time=body.due_time, assigned_to=body.assigned_to, note=body.note))


@router.patch("/todos/{todo_id}", response_model=Todo, tags=["obligations"])
async def set_todo_done(todo_id: uuid.UUID, body: TodoDoneIn, p: Principal = Depends(current_member)):
    return Todo(**await todos.set_done(p, todo_id, body.done))


@router.delete("/todos/{todo_id}", status_code=204, tags=["obligations"])
async def delete_todo(todo_id: uuid.UUID, p: Principal = Depends(current_member)):
    await todos.remove(p, todo_id)
    return Response(status_code=204)


@router.get("/money", response_model=Money, tags=["obligations"],
            description="Money as far as mail can see it: one charge per receipt the member can see, what "
                        "recurs and when it is next expected, this month's spend by category, and home services "
                        "with when each was last done. Derived from claims; nothing is stored.")
async def money_overview(days: int = 90, p: Principal = Depends(current_member)):
    return Money(**await ledger.overview(p, days=days))


@router.get("/inbox", response_model=list[InboxRow], tags=["artifacts"],
            description="Every notice the member can see, as the inbox shows it: a headline, who it came from, "
                        "what it asks for, who is handling it, and whether anything is still open.")
async def inbox_feed(days: int = 30, limit: int = 100, p: Principal = Depends(current_member)):
    return [InboxRow(**r) for r in await inbox.feed(p, days=days, limit=limit)]


@router.post("/artifacts/{artifact_id}/handled", response_model=Handled, tags=["artifacts"],
             description="Say a notice is dealt with, with a word back for whoever handed it over. It becomes done "
                         "whatever its dates say, its pending reminders are cancelled, and the other end of the "
                         "hand-over is told.")
async def mark_handled(artifact_id: uuid.UUID, body: HandledIn, p: Principal = Depends(current_member)):
    return Handled(**await inbox.mark_handled(p, artifact_id, body.note))


@router.delete("/artifacts/{artifact_id}/handled", response_model=Handled, tags=["artifacts"],
               description="Take back handled; the dates stand as they were.")
async def reopen_handled(artifact_id: uuid.UUID, p: Principal = Depends(current_member)):
    return Handled(**await inbox.reopen(p, artifact_id))


@router.post("/artifacts/{artifact_id}/assign", response_model=Assigned, tags=["artifacts"],
             description="Hand a notice to a member with a note, or take it back with a null member. The member "
                         "must already be able to see it; a private notice is shared first, by its owner.")
async def assign_artifact(artifact_id: uuid.UUID, body: AssignIn, p: Principal = Depends(current_member)):
    try:
        return Assigned(**await inbox.assign(p, artifact_id, body.member_id, body.note))
    except inbox.NotVisibleToAssignee as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/artifacts/{artifact_id}/reply/draft", response_model=ReplyDraft, tags=["artifacts"],
             description="Draft a reply to the notice's sender from the notice and what the family decided. "
                         "Nothing is sent; the draft comes back to be read, changed and sent.")
async def draft_reply(artifact_id: uuid.UUID, body: ReplyDraftIn, p: Principal = Depends(current_member)):
    from familyos import replies
    try:
        return ReplyDraft(**await replies.draft(p, artifact_id, stance=body.stance, note=body.note))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except (chat.ModelUnavailable, ask.NoAnswerer) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.post("/artifacts/{artifact_id}/reply", response_model=ReplySent, tags=["artifacts"],
             description="Send a reply the parent approved, to where the notice came from: the sender's mail address, "
                         "or the Telegram group. The text is not kept; the audit records that a reply went.")
async def send_reply(artifact_id: uuid.UUID, body: ReplySendIn, p: Principal = Depends(current_member)):
    from familyos import replies
    try:
        return ReplySent(**await replies.send(p, artifact_id, text=body.text, subject=body.subject))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("/artifacts/{artifact_id}", response_model=Artifact, tags=["artifacts"])
async def get_artifact(artifact_id: uuid.UUID, p: Principal = Depends(current_member)):
    return _artifact(await artifacts.get_visible(p, artifact_id))


@router.get("/artifacts/{artifact_id}/original", tags=["artifacts"], response_class=Response)
async def get_original(artifact_id: uuid.UUID, p: Principal = Depends(current_member)):
    row, data = await artifacts.read_original(p, artifact_id)
    name = row["filename"] or f"{row['id']}{'.eml' if row['media_type'] == 'message/rfc822' else ''}"
    return Response(content=data, media_type=row["media_type"], headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    })


@router.get("/artifacts/{artifact_id}/text", tags=["artifacts"], response_class=PlainTextResponse,
            description="The notice as words: a mail's subject and body without its headers, a text as it is. "
                        "Only for mail and text; a picture or a PDF is read on the page itself.")
async def get_text(artifact_id: uuid.UUID, p: Principal = Depends(current_member)):
    from familyos.extraction import parse
    row, data = await artifacts.read_original(p, artifact_id)
    if row["media_type"] == "message/rfc822":
        doc = parse.parse(data, "message/rfc822")
        # HTML mail stripped to text keeps its layout's indentation; words, not columns.
        lines = [ln.strip() for ln in "\n".join(pg.text for pg in doc.pages).splitlines()]
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    elif row["media_type"].startswith("text/"):
        text = data.decode("utf-8", errors="replace")
    else:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "not a text notice")
    return PlainTextResponse(text, headers={"Cache-Control": "private, no-store"})


@router.get("/artifacts/{artifact_id}/picture", tags=["artifacts"], response_class=Response,
            description="A picture artifact as a JPEG the browser can show, at most 1600px on a side. The original "
                        "is untouched; a phone's HEIC is read through the HEIF plugin.")
async def get_picture(artifact_id: uuid.UUID, full: bool = False, p: Principal = Depends(current_member)):
    row, data = await artifacts.read_original(p, artifact_id)
    if not str(row["media_type"]).startswith("image/"):
        raise HTTPException(status_code=404, detail="not a picture")
    import io

    from PIL import Image, ImageOps

    from familyos.extraction.parse import _heif
    _heif()
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            if not full:
                im.thumbnail((1600, 1600))
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=85, optimize=True)
    except Exception as exc:  # noqa: BLE001 - a picture that cannot be read is said so, not served raw
        raise HTTPException(status_code=422, detail=f"the picture could not be read: {type(exc).__name__}") from exc
    return Response(content=out.getvalue(), media_type="image/jpeg", headers={
        "Content-Disposition": "inline", "X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"})


@router.patch("/artifacts/{artifact_id}", response_model=Artifact, tags=["artifacts"])
async def set_visibility(artifact_id: uuid.UUID, body: VisibilityIn, p: Principal = Depends(current_member)):
    return _artifact(await artifacts.set_visibility(p, artifact_id, body.visibility))


@router.put("/artifacts/{artifact_id}/subjects", response_model=Artifact, tags=["artifacts"])
async def set_subjects(artifact_id: uuid.UUID, member_ids: list[uuid.UUID], p: Principal = Depends(current_member)):
    return _artifact(await artifacts.set_subjects(p, artifact_id, member_ids))


@router.delete("/artifacts/{artifact_id}", status_code=204, tags=["artifacts"])
async def delete_artifact(artifact_id: uuid.UUID, p: Principal = Depends(current_member)):
    await artifacts.delete_by_member(p, artifact_id)


# ----------------------------------------------------------------------------
# extraction and obligations
# ----------------------------------------------------------------------------

@router.get("/artifacts/{artifact_id}/extraction", response_model=ArtifactExtraction, tags=["extraction"])
async def get_extraction(artifact_id: uuid.UUID, p: Principal = Depends(current_member)):
    """The claims read from an artifact, each with where it came from."""
    return _extraction(await extraction.get_for_artifact(p, artifact_id))


@router.post("/artifacts/{artifact_id}/extract", status_code=202, tags=["extraction"])
async def rerun_extraction(artifact_id: uuid.UUID, p: Principal = Depends(current_member)):
    """Read the artifact again, e.g. after the extractor improved."""
    return await extraction.rerun(p, artifact_id)


@router.get("/amendments", response_model=list[Amendment], tags=["extraction"],
            description="Notices that look like they revise an earlier one. Listed only to members who can see "
                        "both notices. `status=` (empty) lists all.")
async def list_amendments(status: str | None = "proposed", limit: int = 100, p: Principal = Depends(current_member)):
    return [Amendment(**r) for r in await reconcile.list_for(p, status or None, min(max(limit, 1), 200))]


@router.post("/amendments/{amendment_id}/decision", tags=["extraction"],
             description="Confirm and the earlier notice's obligations are superseded and stop reminding; "
                         "reject and both stand.")
async def decide_amendment(amendment_id: uuid.UUID, body: AmendmentDecisionIn,
                           p: Principal = Depends(current_member)):
    row = await reconcile.decide(p, amendment_id, body.status)
    return {"id": str(amendment_id), "status": row["status"],
            "obligations_superseded": row["obligations_superseded"]}


@router.get("/reminders", response_model=list[Reminder], tags=["extraction"],
            description="What this member will be told about, and was. A reminder exists only for an obligation "
                        "the member can see, so a private notice reminds nobody else.")
async def list_reminders(limit: int = 100, p: Principal = Depends(current_member)):
    return [Reminder(**r) for r in await reminders.list_for(p, min(max(limit, 1), 500))]


# ----------------------------------------------------------------------------
# what did not arrive
# ----------------------------------------------------------------------------

@router.post("/intake-gaps", response_model=Gap, status_code=201, tags=["intake"],
             description="A member says a notice never reached FamilyOS, and where it actually lived. "
                         "Counted, never read: a gap produces no claims and no obligations.")
async def report_gap(body: GapIn, p: Principal = Depends(current_member)):
    return Gap(**await gaps.report(p, title=body.title, lived_where=body.lived_where,
                                   also_emailed=body.also_emailed, had_date=body.had_date,
                                   noticed_on=body.noticed_on, note=body.note))


@router.get("/intake-gaps", response_model=list[Gap], tags=["intake"])
async def list_gaps(limit: int = 200, p: Principal = Depends(current_member)):
    """A guardian sees the household's reports; anyone else sees their own."""
    return [Gap(**g) for g in await gaps.list_for(p, limit)]


@router.post("/intake-gaps/{gap_id}/arrived", response_model=Gap, tags=["intake"])
async def resolve_gap(gap_id: uuid.UUID, body: GapResolveIn, p: Principal = Depends(current_member)):
    """Point a gap at the notice that eventually arrived."""
    return Gap(**await gaps.resolve(p, gap_id, body.arrived_as))


@router.get("/intake-gaps/summary", response_model=CaptureSummary, tags=["intake"],
            description="Capture rate, and where the misses lived. The breakdown is the part that "
                        "decides anything; the rate is an upper bound, because a family reports "
                        "some of what it misses and never all.")
async def capture_summary(since: date | None = None, p: Principal = Depends(current_member)):
    return CaptureSummary(**await gaps.summary(p, since=since))


# ----------------------------------------------------------------------------
# taking everything with you
# ----------------------------------------------------------------------------

def _zip(data: bytes, filename: str) -> Response:
    return Response(content=data, media_type="application/zip", headers={
        "content-disposition": f'attachment; filename="{filename}"',
        # Built for this request and gone afterwards; nothing should cache a
        # copy of a household on the way past.
        "cache-control": "no-store"})


@router.get("/export", tags=["household"], response_class=Response,
            description="Everything the member can see, as a zip: the originals, a readable page per "
                        "notice, and the same contents as JSON. Generated for this request and never stored.")
async def export_mine(p: Principal = Depends(current_member)):
    data, filename, _ = await export.for_member(p)
    return _zip(data, filename)


@router.get("/members/{member_id}/export", tags=["household"], response_class=Response,
            description="What is held about one child, for a guardian. The counterpart to subject "
                        "erasure: the same scope, handed over instead of destroyed.")
async def export_subject(member_id: uuid.UUID, p: Principal = Depends(current_member)):
    data, filename, _ = await export.for_subject(p, member_id)
    return _zip(data, filename)


# ----------------------------------------------------------------------------
# connected mailboxes
# ----------------------------------------------------------------------------

@router.get("/google/mailboxes", response_model=list[Mailbox], tags=["intake"])
async def list_mailboxes(p: Principal = Depends(current_member)):
    """The member's own connected mailboxes. Nobody sees anyone else's: a
    mailbox is more private than a notice out of it."""
    return [Mailbox(**m) for m in await mailbox.list_for(p)]


@router.post("/google/mailboxes/authorize", response_model=MailboxAuthorization, tags=["intake"],
             description="Start connecting a Gmail account. Send the member to `url`; Google returns them to the "
                         "callback, which finishes it.")
async def authorize_mailbox(p: Principal = Depends(current_member)):
    return MailboxAuthorization(**await mailbox.begin(p))


@router.get("/google/callback", include_in_schema=False)
async def google_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    """Where Google sends the member back.

    No FamilyOS token arrives on this request -- it is a browser redirect from
    Google -- so the single-use state row is the only thing tying this consent
    to a member, and a state we did not issue is refused.
    """
    # Back to Home, not Household: the first thing a newly connected mailbox
    # should do is fill the screen, and Home is where that happens.
    if error or not code or not state:
        return RedirectResponse("/app/#/home?mailbox=" + quote(error or "cancelled"))
    try:
        await mailbox.complete(state, code)
    except (identity.Invalid, mailbox.NotConfigured) as exc:
        logger.warning("could not finish connecting a mailbox: %s", exc)
        return RedirectResponse("/app/#/home?mailbox=failed")
    return RedirectResponse("/app/#/home?mailbox=connected")


@router.post("/google/mailboxes/{account_id}/sync", tags=["intake"],
             description="Read one page of the mailbox now rather than at the next sweep. Only the member whose "
                         "mailbox it is may ask. Returns what was stored and whether the first pass is still going, "
                         "so a console can call it again until the backfill is done.")
async def sync_mailbox(account_id: uuid.UUID, p: Principal = Depends(current_member)):
    # Ownership is checked the way list_for scopes it: a mailbox is more
    # private than a notice out of it, so another member's id is a 404.
    if not any(m["id"] == account_id and not m.get("disconnected_at") for m in await mailbox.list_for(p)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "mailbox")
    try:
        result = await mailbox.poll(account_id)
    except google_adapter.GoogleError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return result


@router.post("/google/mailboxes/{account_id}/disconnect", response_model=Mailbox, tags=["intake"])
async def disconnect_mailbox(account_id: uuid.UUID, p: Principal = Depends(current_member)):
    """Stop reading it, overwrite the stored token and tell Google. Only the
    member whose mailbox it is may do this."""
    return Mailbox(**await mailbox.disconnect(p, account_id))


# ----------------------------------------------------------------------------
# doing something about a notice
# ----------------------------------------------------------------------------

@router.post("/obligations/{obligation_id}/actions", response_model=Action, status_code=201, tags=["actions"],
             description="Work out what would be sent, and to whom, without sending it. There is no "
                         "recipient parameter: a reply goes to the school that wrote, and a calendar "
                         "entry to the member who asked.")
async def propose_action(obligation_id: uuid.UUID, body: ActionIn, p: Principal = Depends(current_member)):
    return Action(**await actions.propose(p, obligation_id, body.kind, body.body))


@router.get("/actions", response_model=list[Action], tags=["actions"])
async def list_actions(limit: int = 100, p: Principal = Depends(current_member)):
    """Actions on notices this member can see."""
    return [Action(**a) for a in await actions.list_for(p, limit)]


@router.post("/actions/{action_id}/approve", response_model=Action, tags=["actions"],
             description="Approve exactly what was shown, by echoing back its fingerprint. A mismatch "
                         "means the stored action changed in between and the approval is refused.")
async def approve_action(action_id: uuid.UUID, body: ActionApproveIn, p: Principal = Depends(current_member)):
    return Action(**await actions.approve(p, action_id, body.params_sha256))


@router.post("/actions/{action_id}/cancel", response_model=Action, tags=["actions"])
async def cancel_action(action_id: uuid.UUID, p: Principal = Depends(current_member)):
    return Action(**await actions.cancel(p, action_id))


@router.get("/brief", response_model=Brief, tags=["extraction"])
async def daily_brief(limit: int = brief.DEFAULT_LIMIT, on: date | None = None,
                      p: Principal = Depends(current_member)):
    """The few things that matter today, worst first. Derived on every request
    from what the member can see; nothing about it is stored."""
    return Brief(**await brief.today(p, on=on, limit=limit))


@router.get("/obligations", response_model=list[Obligation], tags=["extraction"])
async def list_obligations(status: str | None = "proposed", limit: int = 100, p: Principal = Depends(current_member)):
    """Obligations from artifacts the member can see. `status=` (empty) lists all."""
    return [Obligation(**r) for r in await extraction.list_obligations(p, status or None, limit)]


@router.post("/obligations/{obligation_id}/decision", response_model=Obligation, tags=["extraction"])
async def decide_obligation(obligation_id: uuid.UUID, body: ObligationDecisionIn, p: Principal = Depends(current_member)):
    return Obligation(**await extraction.decide(p, obligation_id, body.status))


# ----------------------------------------------------------------------------
# quarantine
# ----------------------------------------------------------------------------

@router.get("/quarantine", response_model=list[Artifact], tags=["intake"])
async def list_quarantine(p: Principal = Depends(current_member)):
    return [_artifact(r) for r in await artifacts.list_quarantine(p)]


@router.post("/quarantine/{artifact_id}/accept", response_model=Artifact, tags=["intake"])
async def accept_quarantined(artifact_id: uuid.UUID, body: QuarantineAcceptIn, p: Principal = Depends(current_member)):
    # Nobody forwarded a circular the school sent, so it is the vouching
    # guardian's unless they say otherwise.
    return _artifact(await artifacts.accept_quarantined(p, artifact_id, body.member_id or p.member_id, body.visibility))


@router.post("/quarantine/{artifact_id}/reject", status_code=204, tags=["intake"])
async def reject_quarantined(artifact_id: uuid.UUID, p: Principal = Depends(current_member)):
    await artifacts.reject_quarantined(p, artifact_id)


# ----------------------------------------------------------------------------
# forwarding email (called by the mail provider)
# ----------------------------------------------------------------------------

@router.post("/inbound/email", tags=["intake"], status_code=202,
             description="The mail provider posts the raw RFC 822 message as the request body, with the shared secret "
                         "in X-FamilyOS-Webhook-Secret and the SMTP envelope recipient in X-FamilyOS-Recipient.")
async def inbound_email(request: Request, x_familyos_webhook_secret: str = Header(""),
                        x_familyos_recipient: str | None = Header(None)):
    if not settings.inbound_webhook_secret or not hmac.compare_digest(
            x_familyos_webhook_secret.encode(), settings.inbound_webhook_secret.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad webhook secret")
    raw = await request.body()
    row, duplicate = await gateway.receive_email(raw, recipient=x_familyos_recipient)
    # The sender is not told whether their mail was accepted or quarantined.
    return {"received": True, "duplicate": duplicate, "status": row["status"], "id": str(row["id"])}


# ----------------------------------------------------------------------------
# WhatsApp (called by Meta)
# ----------------------------------------------------------------------------

@router.get("/inbound/whatsapp", include_in_schema=False)
async def whatsapp_verify(request: Request):
    """Meta's one-time subscription handshake: echo the challenge when the
    token matches."""
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and settings.whatsapp_verify_token and hmac.compare_digest(
            (q.get("hub.verify_token") or "").encode(), settings.whatsapp_verify_token.encode()):
        return Response(content=q.get("hub.challenge") or "", media_type="text/plain")
    raise HTTPException(status.HTTP_403_FORBIDDEN, "bad verify token")


@router.post("/inbound/whatsapp", status_code=202, tags=["intake"],
             description="Meta Cloud API webhook. Every delivery is checked against the app secret before it is "
                         "read. A message from a number that belongs to no member is refused and not stored.")
async def inbound_whatsapp(request: Request, x_hub_signature_256: str | None = Header(None)):
    raw = await request.body()
    try:
        whatsapp_adapter.verify_signature(raw, x_hub_signature_256, settings.whatsapp_app_secret)
    except whatsapp_adapter.BadSignature as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    received, refused = 0, 0
    for message in whatsapp_adapter.parse(json.loads(raw or b"{}")):
        try:
            # A child's name on its own, after a forward, says whose it was.
            if await gateway.tag_by_word_whatsapp(message) is not None:
                continue
            stored = await gateway.receive_whatsapp(message)
            received += len(stored)
        except gateway.Rejected:
            # Meta retries anything that is not 2xx, and a message we cannot
            # place will never become placeable: take it and drop it.
            refused += 1
    return {"received": received, "refused": refused}


@router.post("/inbound/whatsapp/bridge", status_code=202, tags=["intake"], include_in_schema=False,
             description="Development only. Accepts messages relayed by an unofficial WhatsApp client so a real "
                         "class group can be read during development. Off unless FAMILYOS_WHATSAPP_BRIDGE_ENABLED.")
async def inbound_whatsapp_bridge(request: Request, x_familyos_bridge_secret: str = Header("")):
    if not settings.whatsapp_bridge_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    if not settings.whatsapp_bridge_secret or not hmac.compare_digest(
            x_familyos_bridge_secret.encode(), settings.whatsapp_bridge_secret.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad bridge secret")
    payload = await request.json()
    try:
        message, extra = wa_bridge.parse(payload)
    except wa_bridge.BadBridgePayload as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    try:
        stored = await gateway.receive_whatsapp(message, fetch=wa_bridge.media_fetcher(payload), extra_source=extra)
    except gateway.Rejected as exc:
        return {"received": 0, "refused": 1, "reason": exc.reason}
    return {"received": len(stored), "refused": 0}


# ----------------------------------------------------------------------------
# Telegram (called by Telegram, and by a member linking their account)
# ----------------------------------------------------------------------------

@router.post("/telegram/link", tags=["intake"],
             description="A one-time deep link the member opens in Telegram to bind their account. "
                         "Asking again invalidates the last one.")
async def telegram_link(p: Principal = Depends(current_member)):
    if not (settings.telegram_bot_token and settings.telegram_bot_username):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram is not configured here")
    token = await identity.issue_telegram_link(p)
    return {"url": telegram_adapter.deep_link(settings.telegram_bot_username, token),
            "bot_username": settings.telegram_bot_username,
            "expires_in_minutes": settings.sign_in_link_minutes}


@router.delete("/telegram/link", status_code=200, tags=["intake"],
               description="Unbind this member's Telegram account. The bot stops reaching them.")
async def telegram_unlink(p: Principal = Depends(current_member)):
    return {"unlinked": await identity.unbind_telegram(p)}


async def _telegram_reply(chat_id: int, text: str) -> None:
    """Said back into the chat, which is the only place a parent binding an
    account is looking. Best effort: a failed courtesy must not fail the
    webhook, because Telegram would redeliver the update and the binding would
    be spent twice."""
    try:
        await telegram_adapter.send_message(
            chat_id, text, bot_token=settings.telegram_bot_token,
            api_base=settings.telegram_api_base)
    except Exception:  # noqa: BLE001
        logger.warning("could not reply in telegram chat", exc_info=True)


@router.post("/inbound/telegram", status_code=202, tags=["intake"],
             description="Telegram Bot API webhook. Every delivery is checked against the webhook secret "
                         "before it is read. In a group, only a message that names the bot or replies to it "
                         "is read; the rest of the group is refused even when Telegram sends it. A message "
                         "from an account bound to no member is refused and not stored.")
async def inbound_telegram(request: Request,
                           x_telegram_bot_api_secret_token: str | None = Header(None)):
    try:
        telegram_adapter.verify_secret(x_telegram_bot_api_secret_token,
                                       settings.telegram_webhook_secret)
    except telegram_adapter.BadSecret as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    message = telegram_adapter.parse(await request.json(),
                                     bot_username=settings.telegram_bot_username)
    if message is None:
        # An edit, a channel post, somebody joining: taken and dropped, because
        # Telegram redelivers anything that is not 2xx.
        return {"received": 0, "refused": 0}

    # Binding comes first and is the one thing handled before the sender is
    # known -- the whole point of the token is that nobody is known yet.
    if message.start_payload:
        try:
            member = await identity.bind_telegram(message.start_payload, message.sender_id)
        except identity.Invalid as exc:
            await _telegram_reply(message.chat_id, str(exc))
            return {"received": 0, "refused": 1, "reason": "link_not_usable"}
        await _telegram_reply(
            message.chat_id,
            f"Linked to {member['display_name']}. Forward anything here and it will be read. "
            f"Ask me a question ending with ? and I answer from what you can see. "
            f"In a group, mention me or reply to me -- I do not read the rest of it.")
        return {"received": 0, "refused": 0, "linked": True}

    # A child's name on its own, right after a forward, is not a notice: it
    # says whose the forward was. The parent is told what it landed on.
    try:
        tagged = await gateway.tag_by_word_telegram(message)
    except gateway.Rejected as exc:
        if exc.reason == "consent_required":
            await _telegram_reply(message.chat_id, "I know that name, but there is no consent recorded "
                                  "for them yet, so I cannot attach anything. A guardian can add it in the console.")
        return {"received": 0, "refused": 1, "reason": exc.reason}
    if tagged is not None:
        await _telegram_reply(message.chat_id, ("Attached to " + ", ".join(tagged) + ".") if tagged
                              else "Nothing recent to attach that to. Forward the notice first, then the name.")
        return {"received": 0, "refused": 0, "tagged": tagged}

    # A question typed in a private chat -- ending with "?", or starting
    # with "ask" -- goes to Ask and the answer comes back as a reply. Only
    # the member's own chat, only their own words (a forward is a notice
    # whatever it asks), and nothing is done from it: what the model would
    # propose is offered for the console to confirm.
    if (message.chat_type == "private" and message.text and not message.media and not message.forwarded
            and chat.is_question(message.text)):
        member = await identity.member_by_telegram(message.sender_id)
        if member is None:
            return {"received": 0, "refused": 1, "reason": "unknown_sender"}
        asker = Principal(member_id=member["id"], household_id=member["household_id"],
                          role=member["role"], display_name=member["display_name"])
        await _telegram_reply(message.chat_id, await chat.answer_for_phone(asker, message.text))
        return {"received": 0, "refused": 0, "answered": True}

    try:
        stored = await gateway.receive_telegram(message)
    except gateway.Rejected as exc:
        # Nothing is said back for either refusal. A group that is not read
        # should not be told it is being watched, and a stranger should learn
        # nothing but that the bot exists.
        return {"received": 0, "refused": 1, "reason": exc.reason}
    return {"received": len(stored), "refused": 0}


# ----------------------------------------------------------------------------
# consent and audit
# ----------------------------------------------------------------------------

@router.post("/consents", response_model=Consent, status_code=201, tags=["consent"])
async def grant_consent(body: ConsentIn, p: Principal = Depends(current_member)):
    return Consent(**await consent.grant(p, body))


@router.get("/consents", response_model=list[Consent], tags=["consent"])
async def list_consents(p: Principal = Depends(current_member)):
    return [Consent(**r) for r in await consent.list_for(p.household_id)]


@router.post("/consents/{consent_id}/withdraw", response_model=Erasure, status_code=202, tags=["consent"],
             description="Withdraw consent. Everything that names the child is erased; the child stays a member.")
async def withdraw_consent(consent_id: uuid.UUID, p: Principal = Depends(current_member)):
    return Erasure(**await erasure.withdraw_consent(p, consent_id))


@router.get("/audit", response_model=list[AuditEvent], tags=["audit"])
async def list_audit(limit: int = 100, before_id: int | None = None, p: Principal = Depends(current_member)):
    if not p.is_guardian:
        raise identity.NotAllowed("only a guardian can read the audit trail")
    return [AuditEvent(**r) for r in await audit.describe_for(p, min(max(limit, 1), 500), before_id)]
