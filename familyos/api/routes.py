"""HTTP API, v1."""
from __future__ import annotations

import asyncio
import decimal
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
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from starlette.datastructures import UploadFile as StarletteUploadFile

from familyos import (
    actions,
    activity,
    agents,
    artifacts,
    ask,
    assistant_tasks,
    audit,
    balance,
    billers,
    brief,
    calendar,
    cards,
    chat,
    chat_actions,
    circle,
    clock,
    consent,
    db,
    decisions,
    digest,
    documents,
    emergency,
    erasure,
    errands,
    export,
    familykey,
    feedback,
    finance,
    gaps,
    grants,
    graph,
    guide,
    handoffs,
    health,
    identity,
    inbox,
    interruptions,
    kid,
    ledger,
    load,
    locations,
    mcp_client,
    medications,
    memory,
    modelroute,
    myday,
    offers,
    onboarding,
    origin,
    passkeys,
    payments,
    plans,
    profile,
    publiccontext,
    rails,
    ratelimit,
    reconcile,
    reminders,
    routines,
    rules,
    scenarios,
    schoolday,
    semantic,
    session_cookie,
    shopsearch,
    standing,
    suggest,
    taught,
    telegram_group,
    todos,
    voice,
    watches,
    whatsapp_watch,
)
from familyos.api.deps import current_kid, current_member, erasure_reader
from familyos.execution import harvest, sessions, sites
from familyos.extraction import service as extraction
from familyos.identity import Principal
from familyos.intake import gateway, mailbox, wa_bridge
from familyos.intake import google as google_adapter
from familyos.intake import telegram as telegram_adapter
from familyos.intake import whatsapp as whatsapp_adapter
from familyos.models import (
    AbsenceNoteIn,
    AcknowledgeIn,
    Action,
    ActionApproveIn,
    ActionIn,
    AgentIn,
    Amendment,
    AmendmentDecisionIn,
    Answer,
    Artifact,
    ArtifactExtraction,
    AskIn,
    Assigned,
    AssignIn,
    AssistantConnectionIn,
    AssistantTaskIn,
    AuditEvent,
    BalanceDismissIn,
    BalanceIn,
    Biller,
    BillerIn,
    Brief,
    BudgetIn,
    CaptureSummary,
    CareView,
    ChatIn,
    ChatOpening,
    ChatTurn,
    CheckinIn,
    CirclePresetIn,
    CircleRoleIn,
    Consent,
    ConsentIn,
    Constitution,
    ContributeIn,
    Credentials,
    Device,
    DeviceIn,
    DeviceIssued,
    DigestPreview,
    DigestSent,
    Document,
    DocumentCheck,
    Documents,
    EmergencyProfileIn,
    EmergencyShareIn,
    Erasure,
    Errand,
    ErrandApproveIn,
    ErrandIn,
    FamilyKeyBeginIn,
    FamilyKeyContributeIn,
    FamilyKeyDeviceIn,
    FamilyKeyDoneIn,
    FamilyKeyRecoverIn,
    FamilyKeyReshareIn,
    FamilyKeySealShareIn,
    FamilyKeySharesIn,
    FamilyKeySimpleIn,
    Gap,
    GapIn,
    GapResolveIn,
    GoalIn,
    Grant,
    GrantIn,
    Handled,
    HandledIn,
    HandleIn,
    Harvest,
    HarvestCandidate,
    HarvestIn,
    HealthStatus,
    HealthSyncIn,
    HealthUpload,
    Household,
    HouseholdCreated,
    HouseholdEraseIn,
    HouseholdIn,
    HouseholdLocaleIn,
    HouseholdRename,
    HouseholdRulesIn,
    InboxRow,
    IntakeResult,
    InterruptionPrefs,
    InterruptionPrefsOut,
    InviteIn,
    KidAnswerIn,
    KidAskIn,
    KidCheckIn,
    KidJournalIn,
    KidKeyIn,
    KidRoutineIn,
    Load,
    LocationFamily,
    LocationFix,
    LocationSharing,
    LocationSharingIn,
    Mailbox,
    MailboxAuthorization,
    MailboxFinishIn,
    McpAllowIn,
    McpCallIn,
    McpServerIn,
    Medication,
    Member,
    MemberBirthday,
    MemberClass,
    MemberIn,
    MemberLimitIn,
    MemberLocale,
    MemberLocaleIn,
    MemberMedicalIn,
    MemberSchool,
    MemoryCorrectIn,
    MemoryVerifyIn,
    ModelRoutingIn,
    Money,
    Obligation,
    ObligationDecisionIn,
    Offer,
    OfferDone,
    PasskeyAddIn,
    PasskeyLoginIn,
    PaymentMethodIn,
    PaymentsSession,
    PaymentsStatus,
    PhoneIn,
    PhoneReminder,
    PlaceIn,
    PlaceSuggestion,
    Plan,
    PlanChooseIn,
    PlanIn,
    PlanStatusIn,
    PrescriptionDateIn,
    PrescriptionEditIn,
    PrescriptionsOf,
    Purchase,
    PurchaseDecisionIn,
    PurchaseIn,
    QuarantineAcceptIn,
    Reminder,
    ReplyDraft,
    ReplyDraftIn,
    ReplySendIn,
    ReplySent,
    Routine,
    RoutineIn,
    RoutinePauseIn,
    Rules,
    ScamReading,
    ScamReportIn,
    ScenarioIn,
    School,
    SchoolIn,
    SearchResult,
    Session,
    SessionIn,
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
    SplitIn,
    Standing,
    StandingIn,
    Suggestion,
    SuggestionAcceptIn,
    TeachSaveIn,
    TeachStartIn,
    TeachStepIn,
    Todo,
    TodoDoneIn,
    TodoIn,
    Visibility,
    VisibilityIn,
    VoiceTranscript,
    WarrantyIn,
    Watch,
    WatchIn,
    WhatsAppChats,
    WhatsAppEnable,
    WorkIn,
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
async def create_household(body: HouseholdIn, request: Request, response: Response):
    ratelimit.enforce([(f"household:ip:{ratelimit.client_ip(request)}", settings.rate_household_per_ip)])
    try:
        household, member, token = await identity.create_household(body)
    except identity.LinkNotUsable as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    full = await identity.get_household(household["id"])
    if session_cookie.wants_cookie(request):
        session_cookie.set_for(response, request, token)       # a console is signed in by a cookie; a native app keeps the token from the body
    return HouseholdCreated(household=_household(full), credentials=Credentials(member=_member(member), token=token))


@router.get("/me", response_model=Member, tags=["household"])
async def me(p: Principal = Depends(current_member)):
    return _member(await identity.get_member(p.household_id, p.member_id))


@router.get("/household", response_model=Household, tags=["household"])
async def get_household(p: Principal = Depends(current_member)):
    return _household(await identity.get_household(p.household_id))


@router.patch("/household", response_model=Household, tags=["household"],
              description="A guardian renames the home (the first-run screens ask for the name; this is where it is saved).")
async def rename_household(body: HouseholdRename, p: Principal = Depends(current_member)):
    try:
        return _household(await identity.rename_household(p, body.name))
    except identity.NotAllowed as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except identity.Invalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


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


@router.post("/voice/transcribe", response_model=VoiceTranscript, tags=["intake"],
             description="Turn a short recording (the body is the audio, any common type) into words, on this machine by default. "
                         "The audio is not kept; the audit records that it happened, never the words. Nothing is done from the words.")
async def transcribe_voice(request: Request, p: Principal = Depends(current_member)):
    try:
        out = await voice.transcribe(p, await request.body(), request.headers.get("content-type"), via="api")
    except voice.VoiceUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return VoiceTranscript(text=out.text, language=out.language, seconds=out.seconds, engine=out.engine)


@router.get("/search", response_model=SearchResult, tags=["artifacts"],
            description="Search the notices the member can see by meaning, with a small model on this machine "
                        "(the plumber finds the pipe repair), falling back to the question's words when it is off or "
                        "unreachable. Nothing leaves the machine and no vector is stored.")
async def search_notices(q: str, limit: int = 12, p: Principal = Depends(current_member)):
    return SearchResult(**await semantic.search(p, q, limit))


@router.get("/medications", response_model=list[Medication], tags=["household"],
            description="The medicines read from the family's prescriptions, with the doctor's own dose words, the last day of "
                        "the supply, and what is due today. A reading, never advice; nothing is marked taken here.")
async def list_medications(member_id: uuid.UUID | None = None, p: Principal = Depends(current_member)):
    return [Medication(**{k: v for k, v in m.items() if k in Medication.model_fields}) for m in await medications.list_for(p, member_id=member_id)]


@router.put("/prescriptions/{artifact_id}/date", status_code=200, tags=["household"],
            description="Correct the date read from a prescription (a handwritten year is easily misread). Every medicine of it "
                        "moves so its first day is this date, keeping each one's length.")
async def correct_prescription_date(artifact_id: uuid.UUID, body: PrescriptionDateIn, p: Principal = Depends(current_member)):
    return {"medicines": await medications.correct_date(p, artifact_id, body.date)}


@router.patch("/prescriptions/{artifact_id}", status_code=200, tags=["household"],
              description="Correct a prescription: its date, the clinic or hospital named on it, and whose it is. Only what is sent changes.")
async def edit_prescription(artifact_id: uuid.UUID, body: PrescriptionEditIn, p: Principal = Depends(current_member)):
    sent = body.model_fields_set
    if "date" in sent and body.date:
        await medications.correct_date(p, artifact_id, body.date)
    if "clinic" in sent:
        await medications.set_clinic(p, artifact_id, body.clinic)
    if "patient_member_id" in sent:
        await medications.set_patient(p, artifact_id, body.patient_member_id)
    return {"ok": True}


@router.get("/prescriptions", response_model=list[PrescriptionsOf], tags=["household"],
            description="The family's prescriptions grouped by person (the one with the newest prescription first), "
                        "each person's newest first, with its medicines. Medicines that match nobody come last.")
async def list_prescriptions(p: Principal = Depends(current_member)):
    return [PrescriptionsOf(**g) for g in await medications.grouped(p)]


@router.get("/standing", response_model=list[Standing], tags=["household"],
            description="Payments the household owes on a rhythm no notice announces, such as rent. Each month's obligation is made by itself.")
async def list_standing(p: Principal = Depends(current_member)):
    return [Standing(**{k: v for k, v in r.items() if k in Standing.model_fields}) for r in await standing.list_for(p)]


@router.post("/standing", response_model=Standing, status_code=201, tags=["household"],
             description="Write a standing payment once: what, whom, how much, on which day. FamilyOS makes each month's obligation "
                         "and reminds; it never pays.")
async def add_standing(body: StandingIn, p: Principal = Depends(current_member)):
    row = await standing.create(p, **body.model_dump())
    return Standing(**{k: v for k, v in {**row, "next_due": standing.due_in(row["day_of_month"], clock.today()), "subject_name": None}.items() if k in Standing.model_fields})


@router.delete("/standing/{standing_id}", status_code=204, tags=["household"])
async def stop_standing(standing_id: uuid.UUID, p: Principal = Depends(current_member)):
    await standing.stop(p, standing_id)


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
        await countries.set_locale(p, body.country, body.timezone, body.currency, body.language)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return await get_household(p)


@router.get("/me/locale", response_model=MemberLocale, tags=["household"],
            description="The zone and language that apply to you: your own where you set them, else the household's.")
async def my_locale(p: Principal = Depends(current_member)):
    from familyos import country as countries
    return await countries.my_locale(p)


@router.put("/me/locale", response_model=MemberLocale, tags=["household"],
            description="Set your own time zone and language (a zone name like Asia/Dubai; a tag like ta or en-IN). `clear` goes back to the household's.")
async def set_my_locale(body: MemberLocaleIn, p: Principal = Depends(current_member)):
    from familyos import country as countries
    try:
        return await countries.set_my_locale(p, body.timezone, body.language, clear=body.clear)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


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


@router.get("/location/sharing", response_model=LocationSharing, tags=["household"],
            description="Whether you share your location with the household's other adults. Yours alone to change.")
async def get_location_sharing(p: Principal = Depends(current_member)):
    return LocationSharing(**await locations.sharing(p))


@router.put("/location/sharing", response_model=LocationSharing, tags=["household"],
            description="Switch your own location sharing on or off. Off deletes the point kept for you; "
                        "no guardian can switch it on for anyone else.")
async def set_location_sharing(body: LocationSharingIn, p: Principal = Depends(current_member)):
    return LocationSharing(**await locations.set_sharing(p, body.sharing))


@router.post("/location", status_code=200, tags=["household"],
             description="The phone's latest fix. Only the latest is kept, never a trail. Refused when you are not sharing.")
async def post_location(body: LocationFix, p: Principal = Depends(current_member)):
    return await locations.record(p, body.lat, body.lon, body.accuracy_m, body.at)


@router.get("/location/family", response_model=LocationFamily, tags=["household"],
            description="Where the adults who share are, if you share too. Without sharing yourself you see no one.")
async def location_family(p: Principal = Depends(current_member)):
    return LocationFamily(**await locations.family(p))


@router.get("/health/sync", response_model=HealthStatus, tags=["household"],
            description="Whether your phone's Health summaries are kept for you, and the latest day held. Yours alone.")
async def get_health_sync(p: Principal = Depends(current_member)):
    return HealthStatus(**await health.status(p))


@router.put("/health/sync", response_model=HealthStatus, tags=["household"],
            description="Switch your own Health sync on or off. Off deletes every day kept for you. Nobody else can switch it on.")
async def set_health_sync(body: HealthSyncIn, p: Principal = Depends(current_member)):
    return HealthStatus(**await health.set_sync(p, body.sync))


@router.post("/health/daily", status_code=200, tags=["household"],
             description="The phone's daily summaries (steps, sleep, resting heart rate, workouts). Refused while sync is off.")
async def post_health_daily(body: HealthUpload, p: Principal = Depends(current_member)):
    return {"stored": await health.upload(p, [d.model_dump() for d in body.days])}


@router.get("/health/daily", tags=["household"], description="Your own recent daily summaries, newest first. No one else's.")
async def get_health_daily(days: int = 14, p: Principal = Depends(current_member)):
    return await health.recent(p, days=max(1, min(days, 90)))


@router.post("/artifacts/{artifact_id}/acknowledge", tags=["artifacts"],
             description="Answer a hand-off: accept it, or decline (and, if you can, suggest someone). Only the person it was handed to, "
                         "once; the sender is told either way.")
async def acknowledge_handoff(artifact_id: uuid.UUID, body: AcknowledgeIn, p: Principal = Depends(current_member)):
    return await handoffs.acknowledge(p, artifact_id, body.response, body.propose_member_id, body.note)


@router.get("/handoffs", tags=["artifacts"],
            description="What you handed over and are waiting on, and what is handed to you, with each one's answer so far.")
async def my_handoffs(p: Principal = Depends(current_member)):
    return await handoffs.waiting(p)


@router.get("/workload", tags=["household"],
            description="Open hand-offs and what each adult handled in the last 30 days, as plain counts the adults can see together.")
async def household_workload(p: Principal = Depends(current_member)):
    if p.role == "child":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not for children")
    return await handoffs.workload(p)


@router.get("/memory", tags=["household"],
            description="What FamilyOS holds about the household, each fact with its source, how it is known, who corrected it, when it was last "
                        "confirmed and when to look at it again. Derived from where the fact lives; guardians see the children's.")
async def memory_facts(p: Principal = Depends(current_member)):
    return await memory.facts(p)


@router.get("/memory/why", tags=["household"], description="Why FamilyOS thinks that: the fact, its source and the steps, in words.")
async def memory_why(key: str, p: Principal = Depends(current_member)):
    return await memory.why(p, key)


@router.post("/memory/correct", tags=["household"], description="Correct a child's school (and optionally class). A guardian only; recorded with before and after.")
async def memory_correct(body: MemoryCorrectIn, p: Principal = Depends(current_member)):
    return await memory.correct(p, body.key, body.value, body.class_label)


@router.post("/memory/verify", tags=["household"], description="Say a fact is right as of today; 'last confirmed' moves and the review date with it.")
async def memory_verify(body: MemoryVerifyIn, p: Principal = Depends(current_member)):
    return await memory.verify(p, body.key)


@router.get("/emergency/card", tags=["household"], description="The emergency card as the household holds it: contacts, who may collect each child, allergies and current medicines, insurance and travel documents, home access.")
async def emergency_card(p: Principal = Depends(current_member)):
    return await emergency.card(p)


@router.put("/emergency/profile", tags=["household"], description="A guardian edits the contacts, the pickup authorisations and the home access note. Fields left out are kept.")
async def emergency_profile(body: EmergencyProfileIn, p: Principal = Depends(current_member)):
    return await emergency.set_profile(p, contacts=[c.model_dump() for c in body.contacts] if body.contacts is not None else None,
                                       pickup=[c.model_dump() for c in body.pickup] if body.pickup is not None else None, home_access=body.home_access)


@router.put("/members/{member_id}/medical", tags=["household"], description="A guardian records a member's allergies and blood group for the emergency card.")
async def member_medical(member_id: uuid.UUID, body: MemberMedicalIn, p: Principal = Depends(current_member)):
    return await emergency.set_member_medical(p, member_id, body.allergies, body.blood_group)


@router.post("/emergency/share", status_code=201, tags=["household"],
             description="A guardian shares the card by a link that expires (1 to 72 hours) and can be revoked. Home access is included only if asked for. The link is shown once.")
async def emergency_share(body: EmergencyShareIn, p: Principal = Depends(current_member)):
    return await emergency.share(p, body.label, body.hours, body.include_home)


@router.get("/emergency/shares", tags=["household"], description="The links shared, whether each is still open, and how many times it was opened.")
async def emergency_shares(p: Principal = Depends(current_member)):
    return await emergency.shares(p)


@router.delete("/emergency/shares/{share_id}", status_code=204, tags=["household"], description="Revoke a link at once.")
async def emergency_revoke(share_id: uuid.UUID, p: Principal = Depends(current_member)):
    await emergency.revoke(p, share_id)


@router.get("/emergency/open", tags=["household"], description="What a shared link shows, as data. No sign-in; an unknown, expired or revoked link says the same thing.")
async def emergency_open(token: str):
    try:
        return await emergency.open_shared(token)
    except identity.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "that link is not open") from exc


@router.post("/emergency/checkin", tags=["household"], description="Say you are safe, or need help. Needing help tells the guardians at once.")
async def emergency_checkin(body: CheckinIn, p: Principal = Depends(current_member)):
    return await emergency.checkin(p, body.status, body.note)


@router.get("/emergency/checkins", tags=["household"], description="Each member's latest check-in, for the household.")
async def emergency_checkins(p: Principal = Depends(current_member)):
    return await emergency.checkins(p)


# ---- child and teen mode: a guardian's side, and the child's own key
@router.post("/members/{member_id}/kid-key", status_code=201, tags=["household"],
             description="A guardian gives a child their own key (1 to 365 days, revocable): it reaches only the child's own day, never the household. Shown once.")
async def issue_kid_key(member_id: uuid.UUID, body: KidKeyIn, p: Principal = Depends(current_member)):
    return await kid.issue_token(p, member_id, body.days)


@router.get("/members/{member_id}/kid-keys", tags=["household"], description="A child's keys, whether each still works, and when it was last used.")
async def list_kid_keys(member_id: uuid.UUID, p: Principal = Depends(current_member)):
    return await kid.tokens(p, member_id)


@router.delete("/kid-keys/{key_id}", status_code=204, tags=["household"], description="Revoke a child's key at once.")
async def revoke_kid_key(key_id: uuid.UUID, p: Principal = Depends(current_member)):
    await kid.revoke_token(p, key_id)


@router.put("/members/{member_id}/kid-routine", tags=["household"], description="Set a child's morning and evening routine (replaces it). A guardian only.")
async def set_kid_routine(member_id: uuid.UUID, body: KidRoutineIn, p: Principal = Depends(current_member)):
    return await kid.set_routine(p, member_id, [i.model_dump() for i in body.items])


@router.get("/kid-requests", tags=["household"], description="What children have asked a parent and nobody has answered yet. Guardians only.")
async def kid_requests(p: Principal = Depends(current_member)):
    return await kid.requests_for_guardians(p)


@router.post("/kid-requests/{request_id}/answer", tags=["household"], description="Answer a child's question: yes, no or later, with an optional word. The child sees it.")
async def answer_kid_request(request_id: uuid.UUID, body: KidAnswerIn, p: Principal = Depends(current_member)):
    return await kid.answer(p, request_id, body.answer, body.note)


@router.get("/members/{member_id}/kid-journal", tags=["household"], description="Only the journal entries a child chose to share. The rest is theirs.")
async def shared_kid_journal(member_id: uuid.UUID, p: Principal = Depends(current_member)):
    return await kid.shared_journal(p, member_id)


@router.get("/kid/day", tags=["kid"], description="The child's own day: today and tomorrow, what to bring, their routine, their ticks, what they asked and the answers, their goals.")
async def kid_day(k=Depends(current_kid)):
    return await kid.day(k)


@router.post("/kid/check", tags=["kid"], description="Tick something off, or untick it.")
async def kid_check(body: KidCheckIn, k=Depends(current_kid)):
    return await kid.check(k, body.key, body.done)


@router.post("/kid/ask", status_code=201, tags=["kid"], description="Ask a parent something. It reaches the guardians as a card to answer yes, no or later.")
async def kid_ask(body: KidAskIn, k=Depends(current_kid)):
    try:
        return await kid.ask_parent(k, body.text)
    except identity.NotAllowed as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc


@router.post("/kid/help", tags=["kid"], description="“I need a grown-up”: tells the household's adults now. The one escalation, and the child presses it.")
async def kid_help(k=Depends(current_kid)):
    return await kid.need_grownup(k)


@router.get("/kid/journal", tags=["kid"], description="The child's private journal.")
async def kid_journal(k=Depends(current_kid)):
    return await kid.journal(k)


@router.post("/kid/journal", status_code=201, tags=["kid"])
async def kid_write_journal(body: KidJournalIn, k=Depends(current_kid)):
    return await kid.write_journal(k, body.text)


@router.post("/kid/journal/{entry_id}/share", tags=["kid"], description="Share one entry with the guardians. Only the child can.")
async def kid_share_entry(entry_id: uuid.UUID, k=Depends(current_kid)):
    return await kid.share_entry(k, entry_id)


@router.get("/finance/timeline", tags=["household"],
            description="What is expected to go out in the coming weeks, by day and by week and per currency: bills with a due date, subscriptions and "
                        "rhythms with their next date, standing payments, and return and warranty deadlines. From receipts and bills; nothing estimated.")
async def finance_timeline(days: int = 45, p: Principal = Depends(current_member)):
    return await finance.timeline(p, days)


@router.get("/finance/budgets", tags=["household"], description="Monthly budgets by category with what has been spent so far this month.")
async def finance_budgets(p: Principal = Depends(current_member)):
    return await finance.budgets(p)


@router.put("/finance/budgets", tags=["household"], description="A guardian sets a monthly budget for a category.")
async def finance_set_budget(body: BudgetIn, p: Principal = Depends(current_member)):
    return await finance.set_budget(p, body.category, body.monthly_limit, body.currency)


@router.delete("/finance/budgets/{category}", status_code=204, tags=["household"])
async def finance_clear_budget(category: str, p: Principal = Depends(current_member)):
    await finance.clear_budget(p, category)


@router.get("/finance/warranties", tags=["household"], description="Purchases with a return window or a warranty still running.")
async def finance_warranties(p: Principal = Depends(current_member)):
    return await finance.warranties(p)


@router.post("/finance/warranties", status_code=201, tags=["household"], description="Note a purchase with how many days it can be returned and how many months it is under warranty.")
async def finance_add_warranty(body: WarrantyIn, p: Principal = Depends(current_member)):
    return await finance.add_warranty(p, title=body.title, merchant=body.merchant, purchased_on=body.purchased_on, return_days=body.return_days,
                                      warranty_months=body.warranty_months, artifact_id=body.artifact_id)


@router.delete("/finance/warranties/{warranty_id}", status_code=204, tags=["household"])
async def finance_close_warranty(warranty_id: uuid.UUID, p: Principal = Depends(current_member)):
    await finance.close_warranty(p, warranty_id)


@router.get("/finance/goals", tags=["household"], description="Savings goals with what has been put in.")
async def finance_goals(p: Principal = Depends(current_member)):
    return await finance.goals(p)


@router.post("/finance/goals", status_code=201, tags=["household"])
async def finance_add_goal(body: GoalIn, p: Principal = Depends(current_member)):
    return await finance.add_goal(p, body.title, body.target_amount, body.currency, body.by_date, body.owner_member_id)


@router.post("/finance/goals/{goal_id}/contribute", tags=["household"], description="Record money put toward a goal (a negative amount takes some out). Moves nothing.")
async def finance_contribute(goal_id: uuid.UUID, body: ContributeIn, p: Principal = Depends(current_member)):
    return await finance.contribute(p, goal_id, body.amount, body.note)


@router.get("/finance/splits", tags=["household"], description="Bills split between the adults and who still owes whom.")
async def finance_splits(p: Principal = Depends(current_member)):
    return await finance.splits(p)


@router.post("/finance/splits", status_code=201, tags=["household"], description="Split a bill between adults by percent or amount; records who owes whom and moves nothing.")
async def finance_split(body: SplitIn, p: Principal = Depends(current_member)):
    return await finance.split(p, body.title, body.amount, body.currency, body.paid_by, [s.model_dump() for s in body.shares])


@router.post("/finance/splits/{split_id}/settle/{member_id}", tags=["household"], description="Mark one person's share settled.")
async def finance_settle(split_id: uuid.UUID, member_id: uuid.UUID, p: Principal = Depends(current_member)):
    return await finance.settle(p, split_id, member_id)


@router.put("/members/{member_id}/payment-limit", tags=["household"],
            description="A guardian sets the most one person may ask to buy at once, inside the household's own limit. Null removes it.")
async def set_member_payment_limit(member_id: uuid.UUID, body: MemberLimitIn, p: Principal = Depends(current_member)):
    return await finance.set_member_limit(p, member_id, body.payment_limit)


@router.get("/school/tomorrow", tags=["household"],
            description="What each child needs tomorrow (or on `on`): what is dated that day for them, and what the same notices say to bring or wear. "
                        "Read from accepted or undecided dates the member may see; nothing is guessed.")
async def school_tomorrow(on: date | None = None, p: Principal = Depends(current_member)):
    return await schoolday.tomorrow(p, on)


@router.get("/school/forms", tags=["household"],
            description="Forms and slips still to come back, per child, with whether each is undecided, to return, or already returned.")
async def school_forms(p: Principal = Depends(current_member)):
    return await schoolday.forms(p)


@router.post("/school/absence-note", tags=["household"],
             description="A draft absence note from a fixed template for you to edit and send yourself. Nothing is sent.")
async def school_absence_note(body: AbsenceNoteIn, p: Principal = Depends(current_member)):
    return await schoolday.absence_note(p, body.child_id, body.on, body.reason, body.until)


@router.get("/activity", tags=["household"],
            description="The Family Activity Ledger: each action as a receipt (what was observed, what was inferred and from which words, "
                        "the rule or tap, who approved, what changed) with an undo where it can honestly be undone. A guardian sees the "
                        "household's; anyone else only their own.")
async def activity_ledger(limit: int = 50, before: int | None = None, p: Principal = Depends(current_member)):
    return await activity.ledger(p, limit=limit, before_id=before)


@router.post("/activity/{event_id}/undo", tags=["household"],
             description="Undo that action, if nothing has changed since. The same checks apply as when it was done, and the undo is recorded too.")
async def activity_undo(event_id: int, p: Principal = Depends(current_member)):
    return await activity.undo(p, event_id)


@router.get("/decisions", tags=["household"],
            description="Decisions waiting on you, and nothing else: a date to accept, a revision to confirm, a notice handed to you, "
                        "and for a guardian an errand or a purchase to approve. Each carries its source, a fixed recommendation, the cost "
                        "of waiting and its buttons (the existing endpoints, described so a client calls them).")
async def decisions_queue(p: Principal = Depends(current_member)):
    return await decisions.queue(p)


@router.put("/household/balance", tags=["household"], description="A guardian switches the gentle balance word on or off. Off by default.")
async def household_balance(body: BalanceIn, p: Principal = Depends(current_member)):
    return await balance.set_enabled(p, body.enabled)


@router.get("/me/balance", tags=["household"],
            description="If the household switched it on and you have closed most of one kind of thing lately: one private sentence and an offer to hand the next to someone. Never a score, never anyone else's count.")
async def my_balance(p: Principal = Depends(current_member)):
    return await balance.nudges(p)


@router.post("/me/balance/dismiss", tags=["household"], description="Wave one nudge away; that kind stays quiet for you for 30 days.")
async def my_balance_dismiss(body: BalanceDismissIn, p: Principal = Depends(current_member)):
    return await balance.dismiss(p, body.domain)


@router.post("/scenarios", tags=["household"],
             description="What if: a member away between two dates, a purchase of some amount, or school reopening on another date. "
                         "An impact map from the record; it changes nothing and proposes nothing.")
async def run_scenario(body: ScenarioIn, p: Principal = Depends(current_member)):
    if body.kind == "member_away" and body.member_id and body.start and body.end:
        return await scenarios.member_away(p, body.member_id, body.start, body.end)
    if body.kind == "spend" and body.amount:
        return await scenarios.spend(p, body.amount, body.currency, body.category)
    if body.kind == "school_reopens" and body.reopens_on:
        return await scenarios.school_reopens(p, body.reopens_on)
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "that scenario needs member_id, start and end; or amount; or reopens_on")


@router.post("/me/agents", status_code=201, tags=["household"],
             description="Connect your own assistant (Grok Bot, Claude, ChatGPT, any MCP client) with a key of its own, shown once. It sees what you see, can read and propose "
                         "for you to confirm, and can share with the family only if you allow it. Connect it at /mcp.")
async def connect_agent(body: AgentIn, p: Principal = Depends(current_member)):
    return await agents.issue(p, body.label, can_share=body.can_share, days=body.days)


@router.get("/me/agents", tags=["household"], description="Your connected assistants, whether each still works, what it may do, and how often it was used this week.")
async def my_agents(p: Principal = Depends(current_member)):
    return await agents.list_for(p)


@router.delete("/me/agents/{key_id}", status_code=204, tags=["household"], description="Disconnect an assistant at once.")
async def disconnect_agent(key_id: uuid.UUID, p: Principal = Depends(current_member)):
    await agents.revoke(p, key_id)


@router.post("/me/assistant-connections", status_code=201, tags=["household"],
             description="Add your own Claude or Grok API key so FamilyOS can send it instructions. The key is sealed and never shown again.")
async def add_assistant_connection(body: AssistantConnectionIn, p: Principal = Depends(current_member)):
    return await assistant_tasks.add_connection(p, body.provider, body.label, body.api_key, body.model, body.daily_cap)


@router.get("/me/assistant-connections", tags=["household"], description="Your assistant connections and how many tasks each has done today.")
async def my_assistant_connections(p: Principal = Depends(current_member)):
    return await assistant_tasks.list_connections(p)


@router.delete("/me/assistant-connections/{connection_id}", status_code=204, tags=["household"], description="Remove a connection and forget its key.")
async def remove_assistant_connection(connection_id: uuid.UUID, p: Principal = Depends(current_member)):
    await assistant_tasks.remove_connection(p, connection_id)


@router.post("/me/assistant-tasks", status_code=202, tags=["household"],
             description="Send an instruction to your assistant. It reads FamilyOS as you, can only propose, and hands back text; poll the task for the answer.")
async def send_assistant_task(body: AssistantTaskIn, p: Principal = Depends(current_member)):
    return await assistant_tasks.ask(p, body.connection_id, body.instruction)


@router.get("/me/assistant-tasks", tags=["household"], description="Your recent assistant tasks and their answers.")
async def my_assistant_tasks(p: Principal = Depends(current_member)):
    return await assistant_tasks.list_tasks(p)


@router.get("/me/assistant-tasks/{task_id}", tags=["household"], description="One task: queued, running, done with the answer, or failed with a reason.")
async def my_assistant_task(task_id: uuid.UUID, p: Principal = Depends(current_member)):
    return await assistant_tasks.get_task(p, task_id)


@router.post("/me/mcp-servers", status_code=201, tags=["household"],
             description="Register an outside MCP server (https, public addresses only). Its credential is sealed and never shown again. No tool can be called until you allow it.")
async def add_mcp_server(body: McpServerIn, p: Principal = Depends(current_member)):
    return await mcp_client.add(p, body.label, body.url, body.auth)


@router.get("/me/mcp-servers", tags=["household"], description="Your outside MCP servers and which of their tools you have allowed.")
async def my_mcp_servers(p: Principal = Depends(current_member)):
    return await mcp_client.list_servers(p)


@router.delete("/me/mcp-servers/{server_id}", status_code=204, tags=["household"], description="Remove an outside server and forget its credential.")
async def remove_mcp_server(server_id: uuid.UUID, p: Principal = Depends(current_member)):
    await mcp_client.remove(p, server_id)


@router.get("/me/mcp-servers/{server_id}/tools", tags=["household"], description="Ask the server what tools it offers, to choose which to allow. Text from a stranger.")
async def mcp_server_tools(server_id: uuid.UUID, p: Principal = Depends(current_member)):
    return await mcp_client.discover(p, server_id)


@router.put("/me/mcp-servers/{server_id}/allowed", tags=["household"], description="Set exactly which of the server's tools may be called.")
async def allow_mcp_tools(server_id: uuid.UUID, body: McpAllowIn, p: Principal = Depends(current_member)):
    return await mcp_client.allow(p, server_id, body.tools)


@router.post("/me/mcp-servers/{server_id}/call", tags=["household"], description="Call one allowed tool, as you. The answer is untrusted text and is not stored.")
async def call_mcp_tool(server_id: uuid.UUID, body: McpCallIn, p: Principal = Depends(current_member)):
    return await mcp_client.call(p, server_id, body.tool, body.arguments)


@router.post("/me/teach", status_code=201, tags=["household"],
             description="Start teaching FamilyOS a task by showing it, on a phone app (the phone driver connects to /v1/teach/{id}/phone) or a public web page. "
                         "Returns what the screen says and which words could be tapped.")
async def teach_start(body: TeachStartIn, p: Principal = Depends(current_member)):
    if body.kind == "web":
        driver, release = await taught.web_browser(body.target)
        return await taught.start(p, "web", body.target, driver=driver, release=release)      # start() owns the release from here
    return await taught.start(p, body.kind, body.target)


@router.get("/me/teach/{lesson_id}", tags=["household"], description="The lesson now: the screen's words, what could be tapped, and the steps so far.")
async def teach_show(lesson_id: uuid.UUID, p: Principal = Depends(current_member)):
    return await taught.show(p, lesson_id)


@router.post("/me/teach/{lesson_id}/step", tags=["household"],
             description="Do one thing for real and keep it as a step: open, tap (by the words on the thing), swipe, or read this screen. Labels that would pay, send, submit or delete are refused.")
async def teach_step(lesson_id: uuid.UUID, body: TeachStepIn, p: Principal = Depends(current_member)):
    return await taught.step(p, lesson_id, body.model_dump())


@router.post("/me/teach/{lesson_id}/undo", tags=["household"], description="Forget the last step. The screen is not rewound.")
async def teach_undo(lesson_id: uuid.UUID, p: Principal = Depends(current_member)):
    return await taught.undo(p, lesson_id)


@router.post("/me/teach/{lesson_id}/save", status_code=201, tags=["household"], description="Keep the steps as a skill.")
async def teach_save(lesson_id: uuid.UUID, body: TeachSaveIn, p: Principal = Depends(current_member)):
    return await taught.save(p, lesson_id, body.title)


@router.delete("/me/teach/{lesson_id}", status_code=204, tags=["household"], description="Drop the lesson and release its browser.")
async def teach_cancel(lesson_id: uuid.UUID, p: Principal = Depends(current_member)):
    await taught.cancel(p, lesson_id)


@router.post("/me/teach/{lesson_id}/phone-ticket", tags=["household"],
             description="A one-use ticket (ten minutes) for the lesson's phone socket, so the session token need not sit in its URL.")
async def teach_phone_ticket(lesson_id: uuid.UUID, p: Principal = Depends(current_member)):
    ratelimit.enforce([(f"ticket:member:{p.member_id}", settings.rate_tickets_per_member)])
    await taught.show(p, lesson_id)                       # the lesson must be this person's
    return {"path": f"/v1/teach/{lesson_id}/phone?ticket={await sessions.issue_subject_ticket(p, lesson_id)}"}


@router.post("/me/skills/{skill_id}/phone-ticket", tags=["household"],
             description="A one-use ticket (ten minutes) for a taught phone skill's socket, so the session token need not sit in its URL.")
async def skill_phone_ticket(skill_id: uuid.UUID, p: Principal = Depends(current_member)):
    ratelimit.enforce([(f"ticket:member:{p.member_id}", settings.rate_tickets_per_member)])
    await taught.get_skill(p, skill_id)
    return {"path": f"/v1/skills/{skill_id}/phone?ticket={await sessions.issue_subject_ticket(p, skill_id)}"}


@router.get("/me/skills", tags=["household"], description="What FamilyOS has been taught by showing it.")
async def my_skills(p: Principal = Depends(current_member)):
    return await taught.list_skills(p)


@router.delete("/me/skills/{skill_id}", status_code=204, tags=["household"], description="Forget a skill.")
async def forget_skill(skill_id: uuid.UUID, p: Principal = Depends(current_member)):
    await taught.forget(p, skill_id)


@router.post("/me/skills/{skill_id}/run", tags=["household"],
             description="Do a web skill now. A phone skill runs when the phone driver connects to /v1/skills/{id}/phone. What it reads is handed in as a private notice.")
async def run_skill(skill_id: uuid.UUID, p: Principal = Depends(current_member)):
    skill = await taught.get_skill(p, skill_id)
    if skill["kind"] != "web":
        raise HTTPException(status_code=409, detail="a phone skill runs when the phone driver connects to /v1/skills/{id}/phone")
    driver, release = await taught.web_browser(skill["target"])
    try:
        return await taught.replay(p, skill, driver)
    finally:
        await release()


@router.websocket("/teach/{lesson_id}/phone")
async def teach_phone_socket(websocket: WebSocket, lesson_id: uuid.UUID, token: str = "", ticket: str = ""):
    """The phone driver joins a lesson: the console then taps through it. Ends when the socket does. `ticket=` is the way; `token=` still works
    for a driver launched with an older address (redacted from the access log)."""
    from familyos.execution import phone
    p = await (sessions.redeem_phone_ticket(ticket, lesson_id) if ticket else identity.authenticate(token)) if (ticket or token) else None
    if p is None or p.kind == "device":      # a share-extension token drives nothing else
        await websocket.close(code=4401)
        return
    try:
        await taught.show(p, lesson_id)             # the lesson must be this person's
    except Exception:  # noqa: BLE001
        await websocket.close(code=4404)
        return
    await websocket.accept()
    driver = phone.attach(lesson_id, websocket.send_json, p.household_id)
    try:
        while True:
            driver.answer(await websocket.receive_json())
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.info("phone socket for lesson %s ended", lesson_id, exc_info=True)
    finally:
        phone.detach(lesson_id, driver)
        driver.disconnect()


@router.websocket("/skills/{skill_id}/phone")
async def skill_phone_socket(websocket: WebSocket, skill_id: uuid.UUID, token: str = "", ticket: str = ""):
    """The phone driver runs a taught phone skill, then the socket says how it went."""
    from familyos.execution import phone
    p = await (sessions.redeem_phone_ticket(ticket, skill_id) if ticket else identity.authenticate(token)) if (ticket or token) else None
    if p is None or p.kind == "device":      # a share-extension token drives nothing else
        await websocket.close(code=4401)
        return
    try:
        skill = await taught.get_skill(p, skill_id)
    except Exception:  # noqa: BLE001
        await websocket.close(code=4404)
        return
    await websocket.accept()
    driver = phone.attach(skill_id, websocket.send_json, p.household_id)
    run = asyncio.create_task(taught.replay(p, skill, driver))
    try:
        while not run.done():
            receive = asyncio.create_task(websocket.receive_json())
            done, _ = await asyncio.wait({run, receive}, return_when=asyncio.FIRST_COMPLETED)
            if receive in done:
                driver.answer(receive.result())
            else:
                receive.cancel()
        await websocket.send_json({"op": "ended", "outcome": run.result()})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.info("phone socket for skill %s ended", skill_id, exc_info=True)
    finally:
        phone.detach(skill_id, driver)
        driver.disconnect()
        if not run.done():
            try:
                await asyncio.wait_for(asyncio.shield(run), 15)
            except (TimeoutError, Exception):  # noqa: BLE001
                run.cancel()


@router.get("/household/models", tags=["household"],
            description="Where this household's words are read: the model profiles available (with their trust class and where they run), which one extraction and Ask use, and the floor.")
async def household_models(p: Principal = Depends(current_member)):
    return await modelroute.listing(p)


@router.put("/household/models", tags=["household"],
            description="Choose the model for extraction and for Ask, and the least private class (cloud, confidential, own) the household's words may reach. A choice below the floor is refused. Guardians only.")
async def household_models_set(body: ModelRoutingIn, p: Principal = Depends(current_member)):
    return await modelroute.set_routing(p, extraction=body.extraction, ask=body.ask, floor=body.floor)


@router.get("/household/onboarding", tags=["household"], description="The first-run checklist: sign in, name the home, add the family, make it private. `show` is true only for a guardian with something left.")
async def household_onboarding(p: Principal = Depends(current_member)):
    return await onboarding.status(p)


@router.post("/household/onboarding/{choice}", tags=["household"], description="Say the name looks right (named), that making it private can wait (skip_private), or dismiss the checklist (dismissed). Guardians only.")
async def household_onboarding_choose(choice: str, p: Principal = Depends(current_member)):
    return await onboarding.choose(p, choice)


@router.get("/household/family-key", tags=["household"], description="Whether the household's key is held by the family, and whether it is locked now.")
async def family_key_status(p: Principal = Depends(current_member)):
    return await familykey.status(p)


@router.post("/household/family-key/begin", tags=["household"],
             description="Start holding the household's key as Shamir shares (any t of n open it). Returns the shares once; nothing changes until they are confirmed. Guardians only.")
async def family_key_begin(body: FamilyKeyBeginIn, p: Principal = Depends(current_member)):
    return await familykey.begin(p, body.threshold, body.count)


@router.post("/household/family-key/confirm", tags=["household"], description="Prove the shares work (give t of them back) and switch. The server then forgets its own copy of the key.")
async def family_key_confirm(body: FamilyKeySharesIn, p: Principal = Depends(current_member)):
    return await familykey.confirm(p, body.shares)


@router.post("/household/family-key/unlock", tags=["household"], description="Unlock the household for a few hours with t shares. Any adult.")
async def family_key_unlock(body: FamilyKeySharesIn, p: Principal = Depends(current_member)):
    return await familykey.unlock(p, body.shares)


@router.post("/household/family-key/lock", tags=["household"], description="Lock the household now. Any adult.")
async def family_key_lock(p: Principal = Depends(current_member)):
    return await familykey.lock(p)


@router.post("/household/family-key/reshare", tags=["household"], description="Make new shares (someone left, or one was lost); the old ones stop working. Needs the current shares. Guardians only.")
async def family_key_reshare(body: FamilyKeyReshareIn, p: Principal = Depends(current_member)):
    return await familykey.reshare(p, body.shares, body.threshold, body.count)


@router.post("/household/family-key/disable", tags=["household"], description="Go back to the server holding the key. Needs the current shares. Guardians only.")
async def family_key_disable(body: FamilyKeySharesIn, p: Principal = Depends(current_member)):
    return await familykey.disable(p, body.shares)


@router.post("/household/family-key/simple", tags=["household"],
             description="Make it private in one tap: one recovery phrase (shown once, never stored) and this device's secret. Nothing changes until /simple/done. Guardians only.")
async def family_key_simple(body: FamilyKeySimpleIn, p: Principal = Depends(current_member)):
    return await familykey.simple_begin(p, body.label, body.prf.model_dump() if body.prf else None)


@router.post("/household/family-key/simple/done", tags=["household"],
             description="Switch on, once this device has proved it kept its secret. The server then forgets its own copy of the key. Guardians only.")
async def family_key_simple_done(body: FamilyKeyDoneIn, p: Principal = Depends(current_member)):
    return await familykey.simple_done(p, body.device_id, body.device_secret)


@router.post("/household/family-key/unlock-with-passkey", tags=["household"],
             description="Unlock on a trusted device: needs a passkey sign-in in the last few minutes and this device's secret. Any adult.")
async def family_key_unlock_device(body: FamilyKeyDoneIn, p: Principal = Depends(current_member)):
    return await familykey.unlock_device(p, body.device_id, body.device_secret)


@router.post("/household/family-key/recover", tags=["household"], description="Unlock with the recovery phrase when no trusted device is to hand. Any adult.")
async def family_key_recover(body: FamilyKeyRecoverIn, p: Principal = Depends(current_member)):
    return await familykey.recover(p, body.phrase)


@router.post("/household/family-key/devices", status_code=201, tags=["household"],
             description="Trust another device of yours. The household must be unlocked. Returns the device's secret once.")
async def family_key_add_device(body: FamilyKeyDeviceIn, p: Principal = Depends(current_member)):
    return await familykey.enroll_device(p, body.label, body.prf.model_dump() if body.prf else None)


@router.get("/household/family-key/devices", tags=["household"], description="Your trusted devices, by label.")
async def family_key_devices(p: Principal = Depends(current_member)):
    return await familykey.devices(p)


@router.delete("/household/family-key/devices/{device_id}", status_code=204, tags=["household"], description="Stop trusting a device (a lost phone).")
async def family_key_remove_device(device_id: uuid.UUID, p: Principal = Depends(current_member)):
    await familykey.revoke_device(p, device_id)


@router.get("/household/family-key/share-seals", tags=["household"],
            description="Who keeps a share sealed to a passkey (names only), and your own sealed share with what the browser needs to ask the passkey for the secret. Households that split the key into shares.")
async def family_key_share_seals(p: Principal = Depends(current_member)):
    return await familykey.share_seals(p)


@router.post("/household/family-key/share-seals", tags=["household"],
             description="Keep your share sealed to your passkey. The browser wraps it under a secret derived inside the passkey and sends only the ciphertext.")
async def family_key_seal_share(body: FamilyKeySealShareIn, p: Principal = Depends(current_member)):
    return await familykey.seal_share(p, body.credential_id, body.salt, body.wrapped)


@router.delete("/household/family-key/share-seals", tags=["household"], description="Stop keeping your share in your passkey. The share itself is not lost: you still hold the words.")
async def family_key_unseal_share(p: Principal = Depends(current_member)):
    return await familykey.revoke_share_seal(p)


@router.post("/household/family-key/contribute", tags=["household"],
             description="Give your share (opened with your passkey) toward unlocking. When enough different members have, the household opens. Needs a recent passkey sign-in.")
async def family_key_contribute(body: FamilyKeyContributeIn, p: Principal = Depends(current_member)):
    return await familykey.contribute(p, body.share)


@router.post("/household/family-key/new-phrase", tags=["household"], description="A fresh recovery phrase while the household is unlocked; the old one stops working. Guardians only.")
async def family_key_new_phrase(p: Principal = Depends(current_member)):
    return await familykey.new_phrase(p)


@router.get("/graph/find", tags=["household"], description="Find a person, shop, clinic, document, medicine or date in the household's graph by name, to start from.")
async def graph_find(q: str, limit: int = 8, p: Principal = Depends(current_member)):
    return await graph.find(p, q, limit)


@router.get("/graph/insights", tags=["household"],
            description="What the shape of the record shows that nobody asked about: a person with a pile of dated things coming, a prescription or document tied to no one, a warranty about to end.")
async def graph_insights(p: Principal = Depends(current_member)):
    return await graph.insights(p)


@router.get("/graph/touches", tags=["household"],
            description="What touches this thing (`ref` like person:<id> or org:croma), within one or two steps, as you may see it. Each link says how it connects and cites the notice it came from.")
async def graph_touches(ref: str, depth: int = 1, p: Principal = Depends(current_member)):
    return await graph.touches(p, ref, depth)


@router.get("/shop/status", tags=["household"], description="Whether product search is switched on for the household.")
async def shop_status(p: Principal = Depends(current_member)):
    return {"enabled": await shopsearch.enabled(p.household_id)}


@router.put("/household/shop-search", tags=["household"], description="A guardian switches live product search on or off. It sends only the words typed and the household's country to Shopify's catalogue.")
async def shop_search_switch(body: BalanceIn, p: Principal = Depends(current_member)):
    return await shopsearch.set_enabled(p, body.enabled)


@router.get("/shop/search", tags=["household"],
            description="Live product options for what you typed, or for a suggestion's kind (`suggestion`): the seller, price, rating, and the seller's own link as returned. Never stored. A query with a household member's name is refused.")
async def shop_search(q: str | None = None, suggestion: str | None = None, limit: int = 6, p: Principal = Depends(current_member)):
    words = q or (shopsearch.query_for(suggestion) if suggestion else None) or ""
    return await shopsearch.search(p, words, limit)


@router.get("/me/day", tags=["household"],
            description="My day: your own page. What needs you, what is suggested (ranked by what you accept), your routines, how FamilyOS "
                        "may reach you, what it has counted about you, and your Health line if you use it. Only the signed-in member's.")
async def my_day(p: Principal = Depends(current_member)):
    return await myday.build(p)


@router.get("/me/learned", tags=["household"],
            description="What FamilyOS has counted about which suggestions you accept or wave away, by kind, over the last 90 days. "
                        "Yours alone; it only orders and quiets suggestions.")
async def my_learned(p: Principal = Depends(current_member)):
    c = await feedback.counts(p)
    return [{"kind": k, "accepted": v["accepted"], "dismissed": v["dismissed"], "quiet": feedback.muted(v)} for k, v in sorted(c.items())]


@router.delete("/me/learned", status_code=200, tags=["household"], description="Forget those counts. Suggestions go back to the default order.")
async def forget_learned(p: Principal = Depends(current_member)):
    return {"cleared": await feedback.clear(p)}


@router.get("/payments", response_model=PaymentsStatus, tags=["household"],
            description="Whether FamilyOS may pay for the family: the guardian's switch, a connected provider, a saved card, the limits and the month so far.")
async def payments_status(p: Principal = Depends(current_member)):
    return PaymentsStatus(**await payments.status(p))


@router.post("/payments/session", response_model=PaymentsSession, tags=["household"],
             description="A guardian's short-lived login token and the provider's client-side key, for the provider's own card and verification screens.")
async def payments_session(p: Principal = Depends(current_member)):
    return PaymentsSession(**await payments.session(p))


@router.put("/payments/card", response_model=PaymentsStatus, tags=["household"],
            description="A guardian records the id of the card they saved in the provider's own form. Never a card number.")
async def payments_card(body: PaymentMethodIn, p: Principal = Depends(current_member)):
    return PaymentsStatus(**await payments.set_payment_method(p, body.payment_method_id))


@router.get("/purchases", response_model=list[Purchase], tags=["household"],
            description="Purchases asked for: a guardian sees all of them, anyone else their own.")
async def list_purchases(p: Principal = Depends(current_member)):
    return [Purchase(**x) for x in await payments.list_for(p)]


@router.post("/purchases", response_model=Purchase, status_code=201, tags=["household"],
             description="Ask for a purchase. Refused when payments are off or the amount is above a household limit. Nothing is bought: a guardian approves this one purchase first.")
async def request_purchase(body: PurchaseIn, p: Principal = Depends(current_member)):
    return Purchase(**await payments.request(p, title=body.title, merchant_name=body.merchant_name, merchant_url=body.merchant_url,
                                              amount=decimal.Decimal(str(body.amount)), currency=body.currency, obligation_id=body.obligation_id,
                                              merchant_country=body.merchant_country))


@router.post("/purchases/{purchase_id}/decision", response_model=Purchase, tags=["household"],
             description="A guardian approves or declines this one purchase.")
async def decide_purchase(purchase_id: uuid.UUID, body: PurchaseDecisionIn, p: Principal = Depends(current_member)):
    return Purchase(**await payments.decide(p, purchase_id, body.approve))


@router.post("/purchases/{purchase_id}/allowance", response_model=Purchase, tags=["household"],
             description="Try again to make the allowance for an approved purchase that was waiting, on your own saved card.")
async def purchase_allowance(purchase_id: uuid.UUID, p: Principal = Depends(current_member)):
    return Purchase(**await payments.make_allowance_now(p, purchase_id))


@router.post("/purchases/{purchase_id}/refresh", response_model=Purchase, tags=["household"],
             description="Ask the provider how this purchase's allowance stands now, for instance after the cardholder verified it.")
async def purchase_refresh(purchase_id: uuid.UUID, p: Principal = Depends(current_member)):
    return Purchase(**await payments.refresh(p, purchase_id))


@router.delete("/purchases/{purchase_id}", response_model=Purchase, tags=["household"],
               description="Cancel a purchase that is not done; its allowance is revoked with the provider.")
async def cancel_purchase(purchase_id: uuid.UUID, p: Principal = Depends(current_member)):
    return Purchase(**await payments.cancel(p, purchase_id))


@router.get("/routines", response_model=list[Routine], tags=["household"],
            description="Your own routines: an instruction and the time it runs. No one sees another member's.")
async def list_routines(p: Principal = Depends(current_member)):
    return [Routine(**x) for x in await routines.list_for(p)]


@router.post("/routines", response_model=Routine, status_code=201, tags=["household"],
             description="Set a routine, for example every Sunday at 6 pm: what is on for the school next week. It only reads and says; with nothing to say it stays silent.")
async def create_routine(body: RoutineIn, p: Principal = Depends(current_member)):
    return Routine(**await routines.create(p, body.instruction, body.weekday, body.hour, trigger=body.trigger, trigger_days=body.trigger_days, policy=body.policy))


@router.put("/routines/{routine_id}/pause", tags=["household"], description="Pause or resume a routine of yours without losing it.")
async def pause_routine(routine_id: uuid.UUID, body: RoutinePauseIn, p: Principal = Depends(current_member)):
    return await routines.pause(p, routine_id, body.paused)


@router.get("/routines/{routine_id}/history", tags=["household"], description="Every run of one of your routines: when, what fired it, and what it did.")
async def routine_history(routine_id: uuid.UUID, p: Principal = Depends(current_member)):
    return await routines.history(p, routine_id)


@router.delete("/routines/{routine_id}", status_code=204, tags=["household"])
async def stop_routine(routine_id: uuid.UUID, p: Principal = Depends(current_member)):
    await routines.stop(p, routine_id)


@router.get("/me/interruptions", response_model=InterruptionPrefsOut, tags=["household"],
            description="How much FamilyOS may say to you unprompted: quiet hours and a daily cap.")
async def get_interruptions(p: Principal = Depends(current_member)):
    return InterruptionPrefsOut(**await interruptions.prefs(p.member_id))


@router.put("/me/interruptions", response_model=InterruptionPrefsOut, tags=["household"])
async def set_interruptions(body: InterruptionPrefs, p: Principal = Depends(current_member)):
    return InterruptionPrefsOut(**await interruptions.set_prefs(p.member_id, quiet_from=body.quiet_from, quiet_to=body.quiet_to, daily_cap=body.daily_cap,
                                                              morning_hour=body.morning_hour, morning_off=body.morning_off))


@router.get("/chat/opening", response_model=ChatOpening, tags=["chat"],
            description="What needs you, as cards with the answer one tap away: dates waiting for a yes, ideas, what may be running low, "
                        "refills, what is late. Each action card's buttons confirm or cancel a staged action; nothing runs until one is pressed.")
async def chat_opening(p: Principal = Depends(current_member)):
    return ChatOpening(**await cards.opening(p))


@router.post("/chat/pending/{action_id}/confirm", tags=["chat"],
             description="Confirm something Ask suggested and you were shown. Only the member it was shown to, once, within half an hour.")
async def confirm_pending(action_id: uuid.UUID, p: Principal = Depends(current_member)):
    return await chat_actions.confirm(p, action_id)


@router.post("/chat/pending/{action_id}/cancel", status_code=204, tags=["chat"])
async def cancel_pending(action_id: uuid.UUID, p: Principal = Depends(current_member)):
    await chat_actions.cancel(p, action_id)


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
async def request_sign_in(body: SignInRequest, request: Request):
    ratelimit.enforce([(f"signin:ip:{ratelimit.client_ip(request)}", settings.rate_sign_in_per_ip),
                       (f"signin:email:{body.email.strip().lower()}", settings.rate_sign_in_per_email)])
    await identity.request_sign_in(body.email)
    return {"sent": "If that address can sign in, a link is on its way."}


@router.get("/sign-in/google", tags=["household"],
            description="Where to send someone who chose Continue with Google. Basic scopes only -- "
                        "signing in asks Google for nothing that needs review.")
async def google_sign_in(response: Response, native: bool = False):
    begun = await identity.google_sign_in_url(native=native)
    # Bind the flow to this browser: the callback must come back carrying the
    # cookie, or an attacker could start a flow of their own and hand the
    # victim the callback link (login CSRF). The phone app's own web session
    # does not share a cookie jar with the app's request, so a native flow
    # is not bound (KNOWN_ISSUES.md).
    if not native:
        response.set_cookie(identity.STATE_COOKIE, begun["state"], max_age=15 * 60, httponly=True, samesite="lax",
                            secure=settings.console_url.startswith("https://"), path="/v1/sign-in/google")
    return {"url": begun["url"]}


@router.get("/sign-in/google/callback", include_in_schema=False)
async def google_sign_in_callback(request: Request, state: str = "", code: str = "", error: str | None = None):
    # Back to where it began either way: the console, or the phone app
    # through its URL scheme. A browser that followed Google here should
    # land somewhere a person recognises, not on a JSON body.
    app = identity.began_in_app(state)
    home = f"{identity.APP_SCHEME}://signin" if app else "/app/"
    if error or not code:
        return RedirectResponse(f"{home}?signin=cancelled")
    if not app and not identity.state_matches_cookie(state, request.cookies.get(identity.STATE_COOKIE)):
        # Not the browser that began this: refused before the state is spent.
        return RedirectResponse(f"{home}?signin=failed")
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
    if app:
        # The phone app takes the token from the fragment: never sent to a server, and not kept in history.
        return RedirectResponse(f"{identity.APP_SCHEME}://signed-in#token={quote(token)}")
    # A console gets its session as an HttpOnly cookie on this very response: no token in the address bar at all.
    back = RedirectResponse("/app/")
    session_cookie.set_for(back, request, token)
    return back


@router.post("/sign-in/redeem", response_model=SignedIn, status_code=200, tags=["household"],
             description="Spend a one-time link and receive a session token. A link works once.")
async def redeem_sign_in(body: SignInRedeem, request: Request, response: Response):
    member, token = await identity.redeem(body.link)
    if session_cookie.wants_cookie(request):
        session_cookie.set_for(response, request, token)
        token = None
    return SignedIn(member=Member(**member), token=token)


@router.post("/sign-in/passkey/options", tags=["household"], description="Start a passkey sign-in: a one-use challenge for the device to sign. No username; the device offers the accounts it holds.")
async def passkey_login_options(request: Request):
    ratelimit.enforce([(f"passkey:ip:{ratelimit.client_ip(request)}", settings.rate_passkey_per_ip)])
    return await passkeys.login_options(request.headers.get("origin"))


@router.post("/sign-in/passkey", response_model=SignedIn, status_code=200, tags=["household"], description="Finish a passkey sign-in and receive a session token.")
async def passkey_login(body: PasskeyLoginIn, request: Request, response: Response):
    ratelimit.enforce([(f"passkey:ip:{ratelimit.client_ip(request)}", settings.rate_passkey_per_ip)])
    member, token = await passkeys.login_finish(request.headers.get("origin"), body.credential)
    if session_cookie.wants_cookie(request):
        session_cookie.set_for(response, request, token)
        token = None
    return SignedIn(member=Member(**member), token=token)


@router.get("/me/whatsapp", tags=["household"], description="The member's own WhatsApp reading: the chats they named, the link, the costs they must accept, the last pass.")
async def whatsapp_status(p: Principal = Depends(current_member)):
    return await whatsapp_watch.status(p)


@router.put("/me/whatsapp/chats", tags=["household"], description="Name the chats to read (up to eight). Nothing else is ever opened.")
async def whatsapp_chats(body: WhatsAppChats, p: Principal = Depends(current_member)):
    return await whatsapp_watch.set_chats(p, body.chats, body.tags)


@router.get("/members/{member_id}/profile", tags=["household"],
            description="One person's profile: how they are reached, where they work, and (for a guardian) the details the emergency card and school rules use. Themselves or a guardian only.")
async def member_profile(member_id: uuid.UUID, p: Principal = Depends(current_member)):
    try:
        return await profile.get(p, member_id)
    except identity.NotAllowed as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


@router.put("/members/{member_id}/work", tags=["household"],
            description="Set or clear a person's work place and usual start time, for their commute on Today. Themselves or a guardian only.")
async def member_work(member_id: uuid.UUID, body: WorkIn, p: Principal = Depends(current_member)):
    try:
        return await profile.set_work(p, member_id, label=body.label, lat=body.lat, lon=body.lon, starts=body.starts)
    except identity.NotAllowed as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


@router.put("/me/phone", tags=["household"], description="Set the signed-in adult's own phone number (with country code): the number their WhatsApp uses.")
async def set_my_phone(body: PhoneIn, p: Principal = Depends(current_member)):
    return await identity.set_my_phone(p, body.phone)


@router.post("/me/whatsapp/link", tags=["household"], description="Start linking WhatsApp Web: returns the code to type into WhatsApp on the phone.")
async def whatsapp_link(p: Principal = Depends(current_member)):
    return await whatsapp_watch.start_link(p)


@router.get("/me/whatsapp/link", tags=["household"], description="Whether the code has been entered yet.")
async def whatsapp_link_check(p: Principal = Depends(current_member)):
    return await whatsapp_watch.check_link(p)


@router.post("/me/whatsapp/enable", tags=["household"], description="Switch the half-hourly reading on, after the costs are accepted.")
async def whatsapp_enable(body: WhatsAppEnable, p: Principal = Depends(current_member)):
    return await whatsapp_watch.enable(p, understood=body.understood, cloud_ok=body.cloud_ok)


@router.post("/me/whatsapp/read-now", tags=["household"], description="Read the named chats now (at most once in five minutes).")
async def whatsapp_read_now(p: Principal = Depends(current_member)):
    return await whatsapp_watch.read_now(p)


@router.delete("/me/whatsapp", tags=["household"], description="Stop, delete the logged-in browser on this machine, and forget the chat list.")
async def whatsapp_forget(p: Principal = Depends(current_member)):
    return await whatsapp_watch.forget(p)


@router.post("/me/passkeys/options", tags=["household"], description="Start adding a passkey on this device. Signed in already.")
async def passkey_add_options(request: Request, p: Principal = Depends(current_member)):
    return await passkeys.register_options(p, request.headers.get("origin"))


@router.post("/me/passkeys", status_code=201, tags=["household"], description="Finish adding a passkey; only its public half is kept.")
async def passkey_add(body: PasskeyAddIn, request: Request, p: Principal = Depends(current_member)):
    return await passkeys.register_finish(p, request.headers.get("origin"), body.credential, body.label)


@router.get("/me/passkeys", tags=["household"], description="Your passkeys, by label, with when each was last used.")
async def my_passkeys(p: Principal = Depends(current_member)):
    return await passkeys.list_for(p)


@router.delete("/me/passkeys/{passkey_id}", status_code=204, tags=["household"], description="Remove a passkey (a lost device).")
async def remove_passkey(passkey_id: uuid.UUID, p: Principal = Depends(current_member)):
    await passkeys.revoke(p, passkey_id)


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


@router.post("/circle/presets/{key}", tags=["household"],
             description="Hand someone one of the named, narrow scopes (pickups only, medicine reminders, one child's school notices, while we travel, "
                         "the emergency card) for a short while. A guardian only; the reason is written from the scope.")
async def circle_preset(key: str, body: CirclePresetIn, p: Principal = Depends(current_member)):
    return await circle.grant_preset(p, key, body.member_id, subject_member_id=body.subject_member_id, days=body.days)


@router.get("/circle/presets", tags=["household"], description="The named scopes a guardian can hand out.")
async def circle_presets(p: Principal = Depends(current_member)):
    return circle.PRESETS


@router.put("/members/{member_id}/circle-role", response_model=Member, tags=["household"],
            description="Who this member is in the circle around a parent: parent, sibling, spouse, caregiver or other. A label, except "
                        "that a caregiver does not see what the household shares, only what is handed to them. Guardians only. Null clears.")
async def set_circle_role(member_id: uuid.UUID, body: CircleRoleIn, p: Principal = Depends(current_member)):
    try:
        return _member(await circle.set_role(p, member_id, body.circle_role))
    except identity.NotAllowed as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except identity.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except identity.Invalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("/household/constitution", response_model=Constitution, tags=["household"],
            description="The household's authority in sentences: what is fixed, the rules set, and for each person what they see and why, "
                        "derived from the rows that decide it. Readable by any member: a person is entitled to know who sees what.")
async def get_constitution(p: Principal = Depends(current_member)):
    return await circle.constitution(p)


@router.get("/members/{member_id}/care", response_model=CareView, tags=["household"],
            description="One person's documents (and what is expiring), bills, appointments, unusual charges and messages that looked like "
                        "scams, read through the caller's own visibility.")
async def care_view(member_id: uuid.UUID, p: Principal = Depends(current_member)):
    try:
        return await circle.care(p, member_id)
    except identity.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/scam/reports", response_model=ScamReading, status_code=201, tags=["household"],
             description="Something looked wrong: a call, a text, a message. It is filed as a shared notice, read at once for the shapes of a "
                         "scam, and answered with what to do whatever the reading says. A high reading tells the guardians. Adults only.")
async def report_scam(body: ScamReportIn, p: Principal = Depends(current_member)):
    try:
        return await circle.report_scam(p, body.text, caller=body.caller, about_member_id=body.about_member_id)
    except identity.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except identity.Invalid as exc:
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
             description="Send a member their way in. Guardians only; a child has nothing to sign in to. Returns a single-use link good for a week, to paste into a message; "
                         "it is also emailed when mail is set up.")
async def invite_member(member_id: uuid.UUID, body: InviteIn | None = None, p: Principal = Depends(current_member)):
    out = await identity.invite(p, member_id, send_email=(body.send_email if body else True))
    return {"invited": out["member_id"], **out}


@router.post("/signout", status_code=200, tags=["household"],
             description="End the token this request arrived on. Other devices stay signed in.")
async def sign_out(request: Request, response: Response, p: Principal = Depends(current_member)):
    ended = await identity.sign_out(p)
    session_cookie.clear(response, request)       # the console's cookie goes with the token it carried
    return {"ended": ended}


@router.post("/session", status_code=200, tags=["household"],
             description="Trade a session token for the console's HttpOnly session cookie (the token is then never held by script). "
                         "Used by a console that finds a token pasted by hand or kept by an earlier version. Needs the console's CSRF header.")
async def start_session(body: SessionIn, request: Request, response: Response):
    ratelimit.enforce([(f"session:ip:{ratelimit.client_ip(request)}", settings.rate_sign_in_per_ip)])
    if not session_cookie.wants_cookie(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this is for FamilyOS's own pages")
    token = (body.token or "").strip()
    principal = await identity.authenticate(token)
    if principal is None or principal.kind != "session":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or revoked token")
    session_cookie.set_for(response, request, token)
    return {"member_id": str(principal.member_id)}


def _errand(row: dict) -> Errand:
    """An errand as the household sees it. A stopped run keeps its browser's DevTools address and session id in `outcome.browser`; that is a
    live, signed-in session whose take-over is the asker's alone (a one-use ticket, `/live-ticket`), so neither goes out in any response."""
    outcome = dict(row.get("outcome") or {})
    if "browser" in outcome:
        outcome["browser"] = {"held": bool((outcome["browser"] or {}).get("ws_url"))}
    return Errand(**{**row, "outcome": outcome})


@router.post("/errands", response_model=Errand, status_code=201, tags=["errands"],
             description="Write a booking or purchase down in full -- what, when, the most it may cost, how it is "
                         "paid -- fingerprinted. Nothing runs until a guardian approves exactly this.")
async def propose_errand(body: ErrandIn, p: Principal = Depends(current_member)):
    return _errand(await errands.propose(p, service=body.service, kind=body.kind, title=body.title, spec=body.spec.model_dump()))


@router.get("/errands", response_model=list[Errand], tags=["errands"])
async def list_errands(p: Principal = Depends(current_member)):
    return [_errand(x) for x in await errands.list_for(p)]


@router.get("/errands/{errand_id}", response_model=Errand, tags=["errands"])
async def get_errand(errand_id: uuid.UUID, p: Principal = Depends(current_member)):
    return _errand(await errands.get(p, errand_id))


@router.post("/errands/{errand_id}/approve", response_model=Errand, tags=["errands"],
             description="A guardian approves exactly what was shown, by echoing back its fingerprint.")
async def approve_errand(errand_id: uuid.UUID, body: ErrandApproveIn, p: Principal = Depends(current_member)):
    return _errand(await errands.approve(p, errand_id, body.params_sha256, body.run_on))


@router.post("/errands/{errand_id}/finish", response_model=Errand, tags=["errands"],
             description="I finished it in the browser: the errand is done and the browser released.")
async def finish_errand(errand_id: uuid.UUID, p: Principal = Depends(current_member)):
    return _errand(await errands.finish(p, errand_id))


@router.post("/errands/{errand_id}/live-ticket", tags=["errands"])
async def errand_live_ticket(errand_id: uuid.UUID, p: Principal = Depends(current_member)):
    ratelimit.enforce([(f"ticket:member:{p.member_id}", settings.rate_tickets_per_member)])
    ticket = await sessions.issue_errand_live_ticket(p, errand_id)
    return {"path": f"/v1/errands/{errand_id}/live?ticket={ticket}"}


@router.websocket("/errands/{errand_id}/live")
async def errand_live_socket(websocket: WebSocket, errand_id: uuid.UUID, ticket: str = ""):
    from familyos.execution import livebridge
    ws_url = await sessions.redeem_errand_live_ticket(ticket, errand_id)
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


@router.post("/errands/{errand_id}/phone-ticket", tags=["errands"],
             description="A one-use ticket (ten minutes, to build and start the driver) for the phone socket, so the session token need not sit in its URL.")
async def errand_phone_ticket(errand_id: uuid.UUID, p: Principal = Depends(current_member)):
    ratelimit.enforce([(f"ticket:member:{p.member_id}", settings.rate_tickets_per_member)])
    ticket = await sessions.issue_phone_ticket(p, errand_id)
    return {"path": f"/v1/errands/{errand_id}/phone?ticket={ticket}"}


@router.websocket("/errands/{errand_id}/phone")
async def errand_phone_socket(websocket: WebSocket, errand_id: uuid.UUID, token: str = "", ticket: str = ""):
    """The app's web view as the errand's browser. The app connects with its
    session token, answers the runbook's questions (goto, text, buttons,
    press ...) by id, and the run ends when the socket does."""
    from familyos.execution import phone
    # `ticket=` is the way (the console's "copy driver address" and the Mac's launch script ask for one); `token=` still works for a driver
    # launched with an older address, and is redacted from the access log by familyos/logfilter.py.
    if ticket:
        p = await sessions.redeem_phone_ticket(ticket, errand_id)
    else:
        p = await identity.authenticate(token) if token else None
    if p is None or p.kind == "device":
        await websocket.close(code=4401)
        return
    # Whose errand it is is settled before anything is displaced: the household's own, and the person who asked for it.
    owner = await db.pool().fetchval("SELECT created_by FROM errands WHERE id = $1 AND household_id = $2", errand_id, p.household_id)
    if owner is None:
        await websocket.close(code=4404)
        return
    if owner != p.member_id:
        await websocket.close(code=4403)
        return
    await websocket.accept()
    driver = phone.attach(errand_id, websocket.send_json, p.household_id)
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
    return _errand(await errands.cancel(p, errand_id))


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
    ratelimit.enforce([(f"ticket:member:{p.member_id}", settings.rate_tickets_per_member)])
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


@router.get("/inbound/share/tags", response_class=PlainTextResponse, tags=["intake"],
            description="The names the share shortcut offers as a tag, one per line: the household's children, then Nobody. A caregiver is offered Nobody only.")
async def share_tags(p: Principal = Depends(current_member)):
    from familyos import circle
    names = [] if await circle.is_caregiver(p.member_id) else [
        r["display_name"] for r in await db.pool().fetch(
            "SELECT display_name FROM members WHERE household_id = $1 AND role = 'child' ORDER BY created_at", p.household_id)]
    return "\n".join([*names, "Nobody"])


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


@router.get("/shortcut", tags=["household"], include_in_schema=False,
            description="The Share with FamilyOS Shortcut, for someone who will not install the app. Where this server can sign one (a Mac), it is built for "
                        "the member with a phone token already inside, so nothing is pasted; otherwise the generic file, which asks for a token once.")
async def share_shortcut(request: Request, p: Principal = Depends(current_member)):
    from pathlib import Path

    from familyos import shortcut
    # A link on another site must not be able to mint a token by pointing the browser here.
    if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        raise HTTPException(403, "open the shortcut from the console itself")
    media = "application/octet-stream"
    name = 'attachment; filename="Share with FamilyOS.shortcut"'
    base = settings.console_url.split("/app")[0].rstrip("/")
    if shortcut.can_sign() and base.startswith("https://"):
        _, token = await identity.issue_device_token(p, "Shortcut")
        try:
            data = await shortcut.signed_for(base, token)
        except Exception:  # noqa: BLE001 - signing is a convenience; the generic file below still works
            logger.warning("could not sign a personal shortcut", exc_info=True)
        else:
            return Response(data, media_type=media, headers={"Content-Disposition": name})
    path = Path(settings.share_shortcut_file) if settings.share_shortcut_file else None
    if path is None or not path.is_file():
        raise HTTPException(404, "this server has no shortcut file yet")
    return FileResponse(path, media_type=media, filename="Share with FamilyOS.shortcut")


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
    return DigestSent(**await digest.send_to(p, clock.today(), force=True))


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
        return Assigned(**await inbox.assign(p, artifact_id, body.member_id, body.note, body.backup_member_id))
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
    from familyos.extraction import sandbox
    try:
        jpeg = await sandbox.jpeg(data, None if full else 1600)
    except Exception as exc:  # noqa: BLE001 - a picture that cannot be read is said so, not served raw
        raise HTTPException(status_code=422, detail=f"the picture could not be read: {type(exc).__name__}") from exc
    return Response(content=jpeg, media_type="image/jpeg", headers={
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


@router.get("/reminders/phone", response_model=list[PhoneReminder], tags=["extraction"],
            description="What this member's phone should tell them over the next fortnight, with the words of the day each "
                        "fires. The app schedules these on the phone itself; Done on a banner marks the notice done.")
async def phone_reminders(days: int = 14, p: Principal = Depends(current_member)):
    return [PhoneReminder(**r) for r in await reminders.for_phone(p, days=min(max(days, 1), 30))]


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

MAILBOX_STATE_COOKIE = "fos_mbx_state"


@router.get("/google/mailboxes", response_model=list[Mailbox], tags=["intake"])
async def list_mailboxes(p: Principal = Depends(current_member)):
    """The member's own connected mailboxes. Nobody sees anyone else's: a
    mailbox is more private than a notice out of it."""
    return [Mailbox(**m) for m in await mailbox.list_for(p)]


@router.post("/google/mailboxes/authorize", response_model=MailboxAuthorization, tags=["intake"],
             description="Start connecting a Gmail account. Send the member to `url`; Google returns them to the "
                         "callback, which finishes it.")
async def authorize_mailbox(response: Response, native: bool = False, p: Principal = Depends(current_member)):
    begun = await mailbox.begin(p, native=native)
    # Bind the consent to this browser (see google_callback). The console calls this itself, so its cookie jar is the one Google sends back.
    response.set_cookie(MAILBOX_STATE_COOKIE, begun["state"], max_age=15 * 60, httponly=True, samesite="lax",
                        secure=settings.console_url.startswith("https://"), path="/v1/google/callback")
    return MailboxAuthorization(**begun)


@router.get("/google/callback", include_in_schema=False)
async def google_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    """Where Google sends the member back.

    No FamilyOS token arrives on this request -- it is a browser redirect from
    Google -- so the single-use state row says whose consent this is, and the
    state cookie says the browser is the one that began it. Without the cookie
    anyone could begin a connection of their own and hand its Google link to a
    victim, whose mailbox would then be read into the attacker's account.
    """
    # Back to Home, not Household: the first thing a newly connected mailbox
    # should do is fill the screen, and Home is where that happens.
    if identity.began_in_app(state):
        # The phone app's own web session: no cookie to match, so nothing is connected here. The code is parked and the app is handed a
        # finish token through its URL scheme; only the member it began for can spend it (mailbox.finish).
        if error or not code:
            return RedirectResponse(f"{identity.APP_SCHEME}://mailbox?result=" + quote(error or "cancelled"))
        try:
            return RedirectResponse(f"{identity.APP_SCHEME}://mailbox?finish=" + quote(await mailbox.park(state, code)))
        except identity.Invalid:
            return RedirectResponse(f"{identity.APP_SCHEME}://mailbox?result=failed")
    if error or not code or not state:
        return RedirectResponse("/app/#/home?mailbox=" + quote(error or "cancelled"))
    if not identity.state_matches_cookie(state, request.cookies.get(MAILBOX_STATE_COOKIE)):
        logger.warning("a mailbox consent came back in a browser that did not begin it; refused before the state was spent")
        return RedirectResponse("/app/#/home?mailbox=failed")
    try:
        await mailbox.complete(state, code)
    except (identity.Invalid, mailbox.NotConfigured, google_adapter.GoogleError) as exc:
        logger.warning("could not finish connecting a mailbox: %s", exc)
        return RedirectResponse("/app/#/home?mailbox=failed")
    return RedirectResponse("/app/#/home?mailbox=connected")


@router.post("/google/mailboxes/finish", response_model=Mailbox, tags=["intake"],
             description="The phone app finishes a consent it began with `authorize?native=true`, with the token the callback handed it through its URL scheme. "
                         "Only the member the consent began for can spend it.")
async def finish_mailbox(body: MailboxFinishIn, p: Principal = Depends(current_member)):
    try:
        return Mailbox(**await mailbox.finish(p, body.finish))
    except (identity.Invalid, mailbox.NotConfigured, google_adapter.GoogleError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


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
    from familyos import paylinks
    return [Obligation(**r) for r in await paylinks.annotate(p.household_id, await extraction.list_obligations(p, status or None, limit))]


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
    if not settings.inbound_email_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "inbound email is switched off: set FAMILYOS_INBOUND_WEBHOOK_SECRET to a long random value "
                            "(it is empty or still 'change-me')")
    if not hmac.compare_digest(
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


async def _telegram_reply(chat_id: int, text: str, buttons: list | None = None) -> None:
    """Said back into the chat, which is the only place a parent binding an
    account is looking. Best effort: a failed courtesy must not fail the
    webhook, because Telegram would redeliver the update and the binding would
    be spent twice."""
    try:
        await telegram_adapter.send_message(
            chat_id, text, bot_token=settings.telegram_bot_token,
            api_base=settings.telegram_api_base, buttons=buttons)
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

    update = await request.json()
    pressed = telegram_adapter.parse_callback(update)
    if pressed is not None:
        return await _telegram_pressed(pressed)

    message = telegram_adapter.parse(update, bot_username=settings.telegram_bot_username)
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
    # A voice note in the member's own private chat is words like any others:
    # heard, said back, and answered if it is a question, filed as their own
    # private note if it is not. The audio is never kept.
    if (message.chat_type == "private" and not message.text and not message.forwarded and len(message.media) == 1
            and message.media[0].media_type.startswith("audio/") and settings.voice_engine != "off"):
        spoken = await _telegram_voice(message)
        if spoken is not None:
            return spoken
    command = (message.text or "").strip().lower().lstrip("/").split("@")[0].strip() if (message.chat_type == "private" and message.text and not message.media and not message.forwarded) else ""
    if command in ("today", "needs", "help", "setup", "whatsapp"):
        member = await identity.member_by_telegram(message.sender_id)
        if member is None:
            return {"received": 0, "refused": 1, "reason": "unknown_sender"}
        asker = Principal(member_id=member["id"], household_id=member["household_id"], role=member["role"], display_name=member["display_name"])
        await _telegram_command(message.chat_id, asker, command)
        return {"received": 0, "refused": 0, "command": command}
    if (message.chat_type == "private" and message.text and not message.media and not message.forwarded
            and chat.is_question(message.text)):
        member = await identity.member_by_telegram(message.sender_id)
        if member is None:
            return {"received": 0, "refused": 1, "reason": "unknown_sender"}
        asker = Principal(member_id=member["id"], household_id=member["household_id"],
                          role=member["role"], display_name=member["display_name"])
        shown = await _telegram_ask(message.chat_id, asker, message.text)
        return {"received": 0, "refused": 0, "answered": True, "cards": shown}

    if message.directed and message.chat_type in telegram_group.GROUP_CHATS and message.text and not message.media and not message.forwarded:
        handled = await _telegram_group(message)
        if handled is not None:
            return handled

    try:
        stored = await gateway.receive_telegram(message)
    except gateway.Rejected as exc:
        # Nothing is said back for either refusal. A group that is not read
        # should not be told it is being watched, and a stranger should learn
        # nothing but that the bot exists.
        return {"received": 0, "refused": 1, "reason": exc.reason}
    return {"received": len(stored), "refused": 0}


async def _telegram_group(message) -> dict | None:
    """A message that names the bot in a group. `family` / `leave` from a guardian make and unmake the family's own group; in that group
    `today` and `week` are answered from what the household shared with everyone (familyos/telegram_group.py). Anything else is left to
    the ordinary path, and nothing is said into a group that is not the family's."""
    member = await identity.member_by_telegram(message.sender_id)
    if member is None:
        return None                      # a stranger learns nothing: the ordinary path refuses it
    command = telegram_group.command_of(message.text)
    household_id = await telegram_group.household_of(message.chat_id)
    if command == "family":
        await _telegram_reply(message.chat_id, await telegram_group.register(message.chat_id, member))
        return {"received": 0, "refused": 0, "group": "registered"}
    if household_id is None or household_id != member["household_id"]:
        return None                      # not the family's group, or someone else's household: read as before
    if command == "leave":
        await _telegram_reply(message.chat_id, await telegram_group.leave(message.chat_id, member))
        return {"received": 0, "refused": 0, "group": "left"}
    if command in ("today", "week"):
        await _telegram_reply(message.chat_id, await telegram_group.answer(message.chat_id, household_id, command))
        return {"received": 0, "refused": 0, "group": "answered"}
    if chat.is_question(message.text) or command == "help":
        await _telegram_reply(message.chat_id, telegram_group.HELP)
        return {"received": 0, "refused": 0, "group": "help"}
    return None


_HELP = ("Forward a notice, a photo or a PDF and it is read.\n"
         "today: what the day needs from you.\n"
         "needs: dates, heads-ups, renewals and warranties waiting for you, each with its buttons.\n"
         "setup: the first-run checklist for a new home.\n"
         "whatsapp: the chats you named, when they were last read, and a code to link WhatsApp.\n"
         "Or ask a question ending with ?, and I answer from what you can see.")


async def _telegram_ask(chat_id: int, asker: Principal, text: str, *, heard: str | None = None) -> int:
    """A question, typed or spoken, answered in the chat, with what it would do offered as Confirm cards."""
    say, cards, clarify = await chat.answer_with_cards(asker, text)
    await _telegram_reply(chat_id, (f"I heard: “{heard}”\n\n" if heard else "") + say)
    if clarify:
        # Unsure, so it asks: each choice is a button that sends that text as the next message.
        rows = []
        for choice in clarify["choices"]:
            rows.append([(choice, f"pick:{await chat_actions.stage_choice(asker, choice)}")])
        await _telegram_reply(chat_id, "Which one?", buttons=rows)
        return 0
    shown = 0
    for proposal in cards[:3]:
        staged = await chat_actions.stage(asker, proposal)
        if staged:
            shown += 1
            await _telegram_reply(chat_id, staged["summary"][:300].capitalize() + "?", buttons=[[("Confirm", f"act:{staged['id']}:y"), ("Not now", f"act:{staged['id']}:n")]])
    return shown


async def _telegram_noticed(chat_id: int, asker: Principal, *, limit: int) -> int:
    """Heads-ups, renewals, warranties and school-app pointers, each with the buttons the console gives it."""
    shown = 0
    for c in [c for c in await decisions.queue(asker) if c["kind"] in cards.CHAT_KINDS][:limit]:
        buttons = await cards.decision_buttons(asker, c)
        if buttons:
            await _telegram_reply(chat_id, c["title"] + (f"\n{c['happened']}" if c.get("happened") else ""), buttons=[cards.telegram_buttons({"buttons": buttons})])
            shown += 1
    return shown


async def _telegram_command(chat_id: int, asker: Principal, command: str) -> None:
    """today, needs and help, in the member's own chat. Only what they may see; nothing is decided here
    except by a button they press."""
    if command == "help":
        await _telegram_reply(chat_id, _HELP)
        return
    if command == "whatsapp":
        st = await whatsapp_watch.status(asker)
        if not st["available"]:
            await _telegram_reply(chat_id, "Reading WhatsApp is not switched on here.")
            return
        when = st["last_ok_at"].strftime("%-d %b %H:%M") if st.get("last_ok_at") else "not yet"
        text = (f"WhatsApp: {'reading' if st['enabled'] else 'off'}, link {st['status'].replace('_', ' ')}.\n"
                f"Chats: {', '.join(st['chats']) or 'none named'}.\nLast read: {when}." + (f"\n{st['last_error']}" if st.get("last_error") else "")
                + "\nName chats and accept what it costs in the app or console; the link code can come here.")
        buttons = [[("Get a link code", "wa:link")] + ([("Read now", "wa:read")] if st["enabled"] else [])]
        await _telegram_reply(chat_id, text, buttons=buttons)
        return
    if command == "setup":
        from familyos import onboarding
        st = await onboarding.status(asker)
        if not asker.is_guardian:
            await _telegram_reply(chat_id, "A guardian sets up the home.")
            return
        lines = [("✅ " if s["done"] else "⬜ ") + s["title"] for s in st["steps"]]
        nxt = next((s for s in st["steps"] if not s["done"]), None)
        tail = {"named": "Does the name look right? " + (nxt or {}).get("detail", ""),
                "family": "Invite the adults from Settings → Family in the app: it makes a link good for a week.",
                "private": "The family key is made in the app, where the words are shown once; never send them in a chat."}.get(nxt["key"] if nxt else "", "")
        buttons = [[("Looks right", "setup:named")]] if nxt and nxt["key"] == "named" else ([[("Later", "setup:skip_private")]] if nxt and nxt["key"] == "private" else None)
        await _telegram_reply(chat_id, "\n".join(lines) + ("\n\n" + tail if tail else "\nThe home is set up."), buttons=buttons)
        return
    if command == "today":
        opening = await cards.opening(asker)
        texts = [c["text"] for c in opening["cards"] if c["type"] == "text"]
        await _telegram_reply(chat_id, "\n".join([opening["say"], *texts]))
        for c in opening["cards"]:
            if c["type"] != "action":
                continue
            await _telegram_reply(chat_id, c["title"] + (f"\n{c['sub']}" if c.get("sub") else ""), buttons=[cards.telegram_buttons(c)])
        await _telegram_noticed(chat_id, asker, limit=3)
        return
    today = await brief.today(asker)
    items = today.get("items") or []
    waiting = [i for i in items if i.get("status") == "proposed" and i.get("obligation_id")][:5]
    noticed = await _telegram_noticed(chat_id, asker, limit=4)
    if not waiting:
        if not noticed:
            await _telegram_reply(chat_id, "Nothing is waiting for your yes.")
        return
    for i in waiting:
        await _telegram_reply(chat_id, f"{i['title']}" + (f"\n{i['when']}" if i.get("when") else "") + (f"\n{i['why']}" if i.get("why") else ""),
                              buttons=[[("Accept", f"ob:{i['obligation_id']}:y"), ("Not this", f"ob:{i['obligation_id']}:n")]])


async def _telegram_pressed(pressed) -> dict:
    """A press on Done under a reminder: the notice is marked handled, as the member who pressed.
    Only a bound account can press, and only what that member can see is touched, by the same
    rule as every other way of saying done."""
    kwargs = dict(bot_token=settings.telegram_bot_token, api_base=settings.telegram_api_base)

    async def say(text: str, *, edit: str | None = None) -> None:
        try:
            await telegram_adapter.answer_callback(pressed.id, text, **kwargs)
            if edit:
                await telegram_adapter.edit_message(pressed.chat_id, pressed.message_id, edit, **kwargs)
        except Exception:  # noqa: BLE001 - a failed courtesy must not make Telegram redeliver the press
            logger.warning("could not answer a telegram button press", exc_info=True)

    kind, _, ref = pressed.data.partition(":")
    member = await identity.member_by_telegram(pressed.sender_id)
    if kind == "pick" and member is not None:
        who = Principal(member_id=member["id"], household_id=member["household_id"], role=member["role"], display_name=member["display_name"])
        try:
            choice = await chat_actions.take_choice(who, uuid.UUID(ref))
        except (identity.NotFound, ValueError):
            await say("That choice has expired. Ask again.")
            return {"received": 0, "refused": 1, "reason": "expired"}
        await say(f"Asking: {choice}"[:190], edit=f"You chose: {choice}"[:300])
        await _telegram_ask(pressed.chat_id, who, choice)
        return {"received": 0, "refused": 0, "picked": True}
    if kind == "act" and member is not None:
        who = Principal(member_id=member["id"], household_id=member["household_id"], role=member["role"], display_name=member["display_name"])
        aid, _, answer = ref.partition(":")
        try:
            if answer == "n":
                await chat_actions.cancel(who, uuid.UUID(aid))
                await say("Left as it was.", edit="Not now.")
                return {"received": 0, "refused": 0, "cancelled": True}
            done = await chat_actions.confirm(who, uuid.UUID(aid))
        except (identity.NotAllowed, identity.NotFound, identity.Invalid, ValueError) as exc:
            await say((str(exc) or "I could not do that.")[:190])
            return {"received": 0, "refused": 1, "reason": "not_allowed"}
        await say(done["said"][:190], edit=(done["said"] + " " + done["summary"])[:300])
        return {"received": 0, "refused": 0, "confirmed": done["kind"]}
    if kind == "wa" and member is not None and ref in ("link", "read"):
        who = Principal(member_id=member["id"], household_id=member["household_id"], role=member["role"], display_name=member["display_name"])
        try:
            if ref == "link":
                out = await whatsapp_watch.start_link(who)
                text = ("Already linked." if out.get("linked") else
                        f"Your WhatsApp link code: {out['code']}\nOn the phone: WhatsApp → Settings → Linked devices → Link a device → Link with phone number instead. It waits {out['expires_in'] // 60} minutes.")
            else:
                done = (await whatsapp_watch.read_now(who))["result"]
                text = "Read: " + (", ".join(f"{k} {v}" for k, v in done.items()) or "nothing new")
        except (identity.Invalid, identity.NotAllowed) as exc:
            await say(str(exc)[:190])
            return {"received": 0, "refused": 1, "reason": "not_allowed"}
        await say("Done.")
        await _telegram_reply(pressed.chat_id, text)
        return {"received": 0, "refused": 0, "whatsapp": ref}
    if kind == "setup" and member is not None and ref in ("named", "skip_private"):
        who = Principal(member_id=member["id"], household_id=member["household_id"], role=member["role"], display_name=member["display_name"])
        from familyos import onboarding
        try:
            await onboarding.choose(who, ref)
        except identity.NotAllowed as exc:
            await say(str(exc)[:190])
            return {"received": 0, "refused": 1, "reason": "not_allowed"}
        await say("Done.", edit="Done. Send setup to see what is next.")
        return {"received": 0, "refused": 0, "setup": ref}
    if kind == "ob" and member is not None:
        who = Principal(member_id=member["id"], household_id=member["household_id"], role=member["role"], display_name=member["display_name"])
        oid, _, answer = ref.partition(":")
        try:
            done = await extraction.decide(who, uuid.UUID(oid), "accepted" if answer == "y" else "dismissed")
        except (identity.NotAllowed, identity.NotFound, ValueError, Exception) as exc:  # noqa: BLE001 - said in a line, never a trace
            await say(("I could not do that: " + str(exc))[:190] if str(exc) else "I could not do that.")
            return {"received": 0, "refused": 1, "reason": "not_found"}
        await say("Accepted. It is on the calendar." if answer == "y" else "Set aside.", edit=(("Accepted: " if answer == "y" else "Set aside: ") + (done.get("title") or ""))[:300])
        return {"received": 0, "refused": 0, "decided": answer}
    if kind == "buy" and member is not None:
        # Approve or Decline one purchase, as the guardian who pressed it. The same rule as everywhere: only a guardian decides.
        who = Principal(member_id=member["id"], household_id=member["household_id"], role=member["role"], display_name=member["display_name"])
        pid, _, answer = ref.partition(":")
        try:
            done = await payments.decide(who, uuid.UUID(pid), answer == "y")
        except (identity.NotAllowed, identity.NotFound, ValueError) as exc:
            await say(str(exc) or "I could not do that.")
            return {"received": 0, "refused": 1, "reason": "not_allowed"}
        said = {"declined": "Declined. Nothing will be bought.", "ready": "Approved. The allowance is ready; nothing has been bought.",
                "approved": "Approved. It waits for a saved card, then the allowance; nothing has been bought.", "failed": "Approved, but the provider refused: " + (done.get("note") or "")}.get(done["status"], "Done.")
        await say(said[:190], edit=(("Approved: " if answer == "y" else "Declined: ") + done["title"])[:300])
        return {"received": 0, "refused": 0, "decided": done["status"]}
    if kind != "done" or member is None:
        await say("This Telegram account is not linked to a member." if member is None else "That button is no longer used.")
        return {"received": 0, "refused": 1, "reason": "unknown_sender" if member is None else "unknown_button"}
    try:
        obligation_id = uuid.UUID(ref)
    except ValueError:
        await say("That button is no longer used.")
        return {"received": 0, "refused": 1, "reason": "unknown_button"}
    artifact_id = await db.pool().fetchval("SELECT artifact_id FROM obligations WHERE id = $1 AND household_id = $2",
                                        obligation_id, member["household_id"])
    asker = Principal(member_id=member["id"], household_id=member["household_id"], role=member["role"], display_name=member["display_name"])
    try:
        if artifact_id is None:
            raise inbox.NotFound("artifact")
        await inbox.mark_handled(asker, artifact_id, "done from a reminder in Telegram")
    except (inbox.NotFound, identity.NotAllowed):
        await say("I could not mark that done.")
        return {"received": 0, "refused": 1, "reason": "not_found"}
    await say("Marked done.", edit="Done. Marked as handled from Telegram.")
    return {"received": 0, "refused": 0, "handled": True}


async def _telegram_voice(message) -> dict | None:
    member = await identity.member_by_telegram(message.sender_id)
    if member is None:
        return None            # an unknown sender goes down the ordinary refusal path
    p = Principal(member_id=member["id"], household_id=member["household_id"], role=member["role"], display_name=member["display_name"])
    media = message.media[0]
    try:
        audio = await telegram_adapter.download(media.file_id, bot_token=settings.telegram_bot_token, api_base=settings.telegram_api_base)
        heard = await voice.transcribe(p, audio, media.media_type, via="telegram")
    except (voice.VoiceUnavailable, identity.Invalid) as exc:
        await _telegram_reply(message.chat_id, f"I could not read that voice note: {exc}.")
        return {"received": 0, "refused": 0, "voice": "unreadable"}
    except Exception:  # noqa: BLE001 - a courtesy must not fail the webhook, or Telegram redelivers it
        logger.warning("could not fetch a Telegram voice note", exc_info=True)
        return {"received": 0, "refused": 0, "voice": "unreadable"}
    text = heard.text
    if not text:
        await _telegram_reply(message.chat_id, "I could not make out any words in that. Try again closer to the phone.")
        return {"received": 0, "refused": 0, "voice": "silent"}
    if chat.is_question(text):
        shown = await _telegram_ask(message.chat_id, p, text, heard=text)
        return {"received": 0, "refused": 0, "answered": True, "voice": "question", "cards": shown}
    await gateway.receive_share(p, text=text, note="a voice note", visibility="private")
    await _telegram_reply(message.chat_id, f"Noted, privately: “{text}”. Say it as a question if you wanted an answer.")
    return {"received": 1, "refused": 0, "voice": "noted"}


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
