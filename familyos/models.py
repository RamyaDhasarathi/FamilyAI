"""API schemas."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl

Role = Literal["guardian", "adult", "child"]
Visibility = Literal["private", "shared"]


class MemberIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    role: Role
    email: EmailStr | None = None
    # The number they forward from on WhatsApp. Any shape a person types;
    # stored as digits.
    phone: str | None = Field(default=None, max_length=24)
    date_of_birth: date | None = None
    # Children only. The key a circular is addressed by: "Grade 4", "IX-B".
    school: str | None = Field(default=None, max_length=100)
    class_label: str | None = Field(default=None, max_length=40)


class MemberSchool(BaseModel):
    """Set or clear a child's school and class. Null clears. `since` is the
    day the new class began (today unless said), kept as history."""
    school: str | None = Field(default=None, max_length=100)
    class_label: str | None = Field(default=None, max_length=40)
    since: date | None = None


class MemberBirthday(BaseModel):
    """Set or clear a date of birth."""
    date_of_birth: date | None = None


class School(BaseModel):
    id: uuid.UUID
    name: str
    portal_url: str | None = None
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    # The school day, local time, for "leave by" and the morning's traffic alert.
    starts_at: time | None = None
    ends_at: time | None = None
    exam_sheet_url: str | None = None
    exam_sheet_read_at: datetime | None = None
    children: list[str] = []
    sources: list[str] = []
    created_at: datetime


class SchoolIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    portal_url: str | None = Field(default=None, max_length=300)
    exam_sheet_url: str | None = Field(default=None, max_length=300)
    address: str | None = Field(default=None, max_length=200)
    lat: float | None = None
    lon: float | None = None
    starts_at: time | None = None
    ends_at: time | None = None


class PlaceSuggestion(BaseModel):
    """A place the map search found, or a pasted link resolved to."""
    label: str
    lat: float
    lon: float


class PlaceIn(BaseModel):
    """A place picked for the household: home or the office. Null clears."""
    label: str | None = Field(default=None, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class ReplyDraftIn(BaseModel):
    """Draft a reply to the notice's sender. `stance` is yes, no or note."""
    stance: Literal["yes", "no", "note"] | None = None
    note: str | None = Field(default=None, max_length=300)


class ReplyDraft(BaseModel):
    artifact_id: uuid.UUID
    channel: Literal["email", "telegram"]
    to: str
    subject: str
    text: str


class ReplySendIn(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    subject: str | None = Field(default=None, max_length=200)


class ReplySent(BaseModel):
    artifact_id: uuid.UUID
    channel: str
    to: str
    sent: bool


class MemberClass(BaseModel):
    """One school and class a child was in, from when."""
    school: str | None = None
    class_label: str | None = None
    since: date


class SourceSchoolIn(BaseModel):
    """"This source is that school": a Telegram group, a sending domain."""
    source_key: str = Field(min_length=1, max_length=200)
    school: str = Field(min_length=1, max_length=100)


class SourceSchool(BaseModel):
    source_key: str
    school: str
    created_at: datetime


class GuardianIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    email: EmailStr


class HouseholdIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    guardian: GuardianIn
    # Where the household lives: the country picks a profile, the zone and
    # the currency follow from it unless said. India unless said.
    country: str = Field(default="IN", min_length=2, max_length=2)
    timezone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    # Proof the guardian holds that address: the ticket Google's callback or
    # the founding mail handed them. Without it nobody founds anything.
    founding: str = Field(min_length=8, max_length=200)


class Member(BaseModel):
    id: uuid.UUID
    household_id: uuid.UUID
    display_name: str
    role: Role
    email: str | None = None
    phone: str | None = None
    # Whether, not which: the console needs to know if the bot can reach this
    # member, and the account id is a handle nobody has any use for seeing.
    telegram_linked: bool = False
    date_of_birth: date | None = None
    school: str | None = None
    class_label: str | None = None
    created_at: datetime


class Household(BaseModel):
    id: uuid.UUID
    name: str
    inbound_address: str
    # Null until a business number is configured: the console only offers a way
    # in that actually works.
    whatsapp_number: str | None = None
    # The bot's @name, null until one is configured. Same rule as above: the
    # console offers a way in only when there is one.
    telegram_bot: str | None = None
    status: str
    created_at: datetime
    # The household's rule: a notice tagged with a child is shared with every
    # adult the moment it is tagged. On unless a guardian turns it off.
    childrens_notices_shared: bool = True
    weekly_digest: bool = True
    calendar_follows_decisions: bool = True
    local_models: bool = False
    members: list[Member] = []
    country: str = "IN"
    timezone: str = "Asia/Kolkata"
    currency: str = "INR"


class HouseholdLocaleIn(BaseModel):
    """Where the household lives. Guardians only."""
    country: str = Field(min_length=2, max_length=2)
    timezone: str = Field(min_length=1, max_length=64)
    currency: str = Field(min_length=3, max_length=3)


class HouseholdRulesIn(BaseModel):
    """Flip one or more switches; leave the rest alone."""
    childrens_notices_shared: bool | None = None
    weekly_digest: bool | None = None
    calendar_follows_decisions: bool | None = None
    local_models: bool | None = None
    holidays_accepted: bool | None = None
    receipts_close_bills: bool | None = None
    investments_quiet: bool | None = None
    pictures_by_model: bool | None = None
    bills_handed_to: uuid.UUID | None = None
    # Public context, read without any credential (publiccontext.py).
    weather_lines: bool | None = None
    travel_time: bool | None = None
    public_holidays: bool | None = None
    exam_dates: bool | None = None
    home_place: str | None = Field(default=None, max_length=200)
    work_place: str | None = Field(default=None, max_length=200)


class RuleOption(BaseModel):
    id: uuid.UUID
    name: str


class Rule(BaseModel):
    key: str
    title: str
    sentence: str
    on: bool
    fixed: bool
    why_fixed: str | None = None
    # A rule that names someone rather than switching: who, and who it could be.
    member_id: uuid.UUID | None = None
    options: list[RuleOption] | None = None
    # "switch" for a rule that is on or off; "text" for one a guardian types (where home is).
    kind: str = "switch"
    text: str | None = None


class LearnedRule(BaseModel):
    kind: str
    source_key: str
    label: str
    says: str
    created_at: datetime


class Rules(BaseModel):
    rules: list[Rule]
    learned: list[LearnedRule]


class Session(BaseModel):
    """A live sign-in. The token itself is never shown again."""
    id: uuid.UUID
    member_id: uuid.UUID
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    current: bool
    # "session" slides and ends; "device" is a phone's shortcut token, labelled, revoked on purpose.
    kind: Literal["session", "device"] = "session"
    label: str | None = None


class Credentials(BaseModel):
    """Returned once; only its hash is stored."""
    member: Member
    token: str


class HarvestIn(BaseModel):
    label: str
    allow_hosts: list[str]
    minutes: int = 90


class Harvest(BaseModel):
    id: uuid.UUID
    label: str
    # Where the member watches and drives, when a browser is configured.
    live_url: str | None = None
    allow_hosts: list[str]
    state: str
    expires_at: datetime
    started_at: datetime
    ended_at: datetime | None = None


class SignInIn(BaseModel):
    service: str


class SignInSitting(BaseModel):
    """A browser open on a site's sign-in page, for the member to use."""
    id: uuid.UUID
    service: str
    label: str
    how: str
    hosts: list[str]
    # The inspector, for a developer; and the browser's socket, which the
    # console turns into the page itself, to click and type into.
    live_url: str | None = None
    ws_url: str | None = None
    state: str
    expires_at: datetime
    created_at: datetime


class SignedInSite(BaseModel):
    """A site the member is signed in to, as far as FamilyOS keeps: the name,
    the dates, how often it was used. Nothing of what it holds."""
    id: uuid.UUID
    service: str
    label: str
    allow_hosts: list[str]
    expires_at: datetime
    last_used_at: datetime | None = None
    uses: int = 0
    created_at: datetime


class SiteOffer(BaseModel):
    service: str
    label: str
    hosts: list[str]
    how: str


class ErrandWhen(BaseModel):
    date: str | None = None
    # "15:30" when a time was said; else the part of the day.
    time: str | None = None
    part: Literal["morning", "afternoon", "evening", "any"] = "any"
    by: str | None = None


class ErrandSpecIn(BaseModel):
    what: str = Field(min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=600)
    when: ErrandWhen = ErrandWhen()
    # Required for a site (clean_spec says so); an app on the phone is a
    # read, so it has no limit.
    max_amount: float | None = None
    # An app on the phone: the school's own bundle id, when it is not the platform's.
    bundle: str | None = Field(default=None, max_length=160)
    currency: str = "INR"
    payment: Literal["pay_after_service", "upi_request"] = "pay_after_service"


class ErrandIn(BaseModel):
    service: str
    kind: Literal["booking", "purchase", "look"] = "booking"
    title: str = Field(min_length=1, max_length=160)
    spec: ErrandSpecIn


class ErrandApproveIn(BaseModel):
    params_sha256: str
    # "phone": run in the app's own web view while the asker holds it open,
    # with the family's own sign-ins and address; otherwise the server's browser.
    run_on: Literal["server", "phone"] | None = None


class Errand(BaseModel):
    id: uuid.UUID
    service: str
    kind: Literal["booking", "purchase", "look"]
    title: str
    spec: dict
    params_sha256: str
    status: Literal["proposed", "approved", "running", "needs_you", "done", "stopped", "failed", "cancelled"]
    created_by: uuid.UUID
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    outcome: dict = {}
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class HarvestCandidate(BaseModel):
    id: uuid.UUID
    url: str
    title: str
    text: str
    sha256: str
    bytes: int
    decision: str | None = None


class BillerIn(BaseModel):
    label: str
    provider: str
    identifier: str | None = None
    every_days: int = 30
    grace_days: int = 7
    visibility: str = "shared"


class Document(BaseModel):
    """A document the family holds, with its dates. Of its number, the last
    four characters only."""
    id: uuid.UUID
    artifact_id: uuid.UUID
    kind: str
    label: str
    title: str
    holder_member_id: uuid.UUID | None = None
    holder_name: str | None = None
    issuer: str | None = None
    identifier_tail: str | None = None
    valid_from: date | None = None
    expires_on: date | None = None
    status: str
    days_left: int | None = None


class DocumentCheck(BaseModel):
    kind: str
    title: str
    why: str
    document_id: uuid.UUID
    artifact_id: uuid.UUID
    holder_name: str | None = None
    expires_on: date | None = None
    plan_id: uuid.UUID | None = None
    plan_title: str | None = None
    needed_until: date | None = None


class Documents(BaseModel):
    documents: list[Document]
    checks: list[DocumentCheck]


class Biller(BaseModel):
    id: uuid.UUID
    label: str
    provider: str
    identifier_hint: str | None = None
    every_days: int
    grace_days: int
    visibility: str
    last_seen_at: datetime | None = None
    created_at: datetime


class AskIn(BaseModel):
    question: str


class Citation(BaseModel):
    ref: str
    kind: str
    text: str
    quote: str | None = None
    artifact_id: uuid.UUID | None = None
    obligation_id: uuid.UUID | None = None


class Answer(BaseModel):
    """An answer from the record, or a sentence saying the record has none."""
    answer: str
    grounded: bool
    citations: list[Citation]
    note: str | None = None


class LoadMember(BaseModel):
    member_id: uuid.UUID
    display_name: str
    carried: int
    share: int
    noticed: int
    decided: int
    acted: int


class Load(BaseModel):
    """How the work that arrived was divided. Counted, never self-reported."""
    days: int
    since: date
    total: int
    undecided: int
    missed: int
    members: list[LoadMember]
    note: str


class WatchIn(BaseModel):
    url: HttpUrl
    look_for: str
    label: str
    every_hours: int = 24
    days: int = 30
    allow_hosts: list[str] | None = None


class Watch(BaseModel):
    id: uuid.UUID
    url: str
    label: str
    look_for: str
    every_hours: int
    expires_at: datetime
    last_checked_at: datetime | None = None
    last_found: bool | None = None
    last_excerpt: str | None = None
    last_error: str | None = None
    notified_at: datetime | None = None
    paused_at: datetime | None = None


class HandleIn(BaseModel):
    handle: str


class GrantIn(BaseModel):
    grantee_member_id: uuid.UUID
    actions: list[str]
    reason: str
    subject_member_id: uuid.UUID | None = None
    days: int = 90


class Grant(BaseModel):
    id: uuid.UUID
    grantee_member_id: uuid.UUID
    grantee_name: str
    granted_by: uuid.UUID
    granted_by_name: str
    subject_member_id: uuid.UUID | None = None
    subject_name: str | None = None
    actions: list[str]
    reason: str
    expires_at: datetime
    created_at: datetime


class SignInRequest(BaseModel):
    email: EmailStr


class SignInRedeem(BaseModel):
    link: str


class SignedIn(BaseModel):
    member: Member
    token: str


class HouseholdCreated(BaseModel):
    household: Household
    credentials: Credentials


class Artifact(BaseModel):
    id: uuid.UUID
    household_id: uuid.UUID
    parent_id: uuid.UUID | None
    channel: str
    # What kind of sender this is (school, bills, food ...): the page uses it
    # to ask only the questions that fit. A receipt is not asked which school sent it.
    category: str | None = None
    submitted_by: uuid.UUID | None
    visibility: Visibility
    status: str
    quarantine_reason: str | None
    filename: str | None
    media_type: str
    size_bytes: int
    sha256: str
    source: dict
    note: str | None
    subject_member_ids: list[uuid.UUID] = []
    children: list[uuid.UUID] = []
    # Where it arrived from, as one string a household can attach a school
    # to (familyos.origin). Null for a paste, an upload or a private chat.
    source_key: str | None = None
    # Who is handling it, which is not whom it is about (subject_member_ids).
    assigned_to: uuid.UUID | None = None
    assigned_note: str | None = None
    assigned_by: uuid.UUID | None = None
    assigned_at: datetime | None = None
    handled_at: datetime | None = None
    handled_by: uuid.UUID | None = None
    handled_note: str | None = None
    received_at: datetime
    accepted_at: datetime | None


class AssignIn(BaseModel):
    """Hand a notice to a member with a note; null takes it back."""
    member_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class HandledIn(BaseModel):
    """Say a notice is dealt with, with a word back for whoever asked."""
    note: str | None = Field(default=None, max_length=500)


class Handled(BaseModel):
    id: uuid.UUID
    headline: str | None = None
    handled_at: datetime | None = None
    handled_by: uuid.UUID | None = None
    handled_note: str | None = None
    assigned_to: uuid.UUID | None = None
    assigned_by: uuid.UUID | None = None


class Assigned(BaseModel):
    id: uuid.UUID
    headline: str | None = None
    assigned_to: uuid.UUID | None = None
    assigned_note: str | None = None
    assigned_by: uuid.UUID | None = None
    assigned_at: datetime | None = None
    handled_at: datetime | None = None
    handled_by: uuid.UUID | None = None
    handled_note: str | None = None


class InboxRow(BaseModel):
    """A notice as the inbox shows it: a headline, who it came from, what it
    asks for, who is handling it, and whether anything is still open."""
    id: uuid.UUID
    channel: str
    visibility: Visibility
    submitted_by: uuid.UUID | None = None
    received_at: datetime
    filename: str | None = None
    media_type: str
    headline: str | None = None
    from_label: str
    subject_member_ids: list[uuid.UUID] = []
    assigned_to: uuid.UUID | None = None
    assigned_note: str | None = None
    assigned_by: uuid.UUID | None = None
    assigned_at: datetime | None = None
    handled_at: datetime | None = None
    handled_by: uuid.UUID | None = None
    handled_note: str | None = None
    dates: int = 0
    open: int = 0
    attachments: int = 0
    preview: list[str] = []
    next_date: date | None = None
    # Why the current read asked for nothing, when it did not: a locked PDF,
    # no text, nothing dated. Null when it did.
    reason: str | None = None
    state: Literal["todo", "done", "info"]
    # What kind of mail it is, from the sender and the subject (categories.py).
    # "unknown" when nothing said; never a guess.
    category: str = "unknown"


class IntakeResult(BaseModel):
    """`duplicate` is true when these exact bytes had already been sent by
    the same member (or the same email delivered twice): nothing new was
    stored and `artifact` is the one made the first time."""
    duplicate: bool
    artifact: Artifact


class VisibilityIn(BaseModel):
    visibility: Visibility


class QuarantineAcceptIn(BaseModel):
    # Who it belongs to. Left out, it belongs to the guardian vouching for it,
    # which is the right answer for a circular a school sent to the household
    # and a question nobody should have to answer about one.
    member_id: uuid.UUID | None = None
    visibility: Visibility = "shared"


class ConsentIn(BaseModel):
    subject_member_id: uuid.UUID
    purpose: str = Field(default="household_records", min_length=1, max_length=64)
    notice_version: str = Field(min_length=1, max_length=32)
    verification_method: str = Field(min_length=1, max_length=64,
                                     description="How the guardian was verified, e.g. 'account_holder' or 'digilocker'.")


class Consent(BaseModel):
    id: uuid.UUID
    household_id: uuid.UUID
    subject_member_id: uuid.UUID
    guardian_member_id: uuid.UUID | None
    purpose: str
    notice_version: str
    verification_method: str
    granted_at: datetime
    withdrawn_at: datetime | None
    withdrawn_by: uuid.UUID | None


class HouseholdEraseIn(BaseModel):
    confirm_name: str = Field(description="The household's name, typed to confirm.")


class Erasure(BaseModel):
    id: uuid.UUID
    scope: str
    status: str
    requested_at: datetime
    completed_at: datetime | None
    counts: dict


class AuditEvent(BaseModel):
    id: int
    actor_kind: str
    actor_member_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: uuid.UUID | None
    detail: dict
    at: datetime
    # The row in words, composed when read: who, what, to which record. The
    # headline of a notice appears only when the reader may see the notice.
    said: str = ""
    who: str | None = None
    about: str | None = None


# ----------------------------------------------------------------------------
# extraction
# ----------------------------------------------------------------------------

class SourceLocation(BaseModel):
    """Where a claim's quote sits in the original: the page, the character
    span in that page's extracted text, and one box per line (PDF points
    from the top left, or image pixels)."""
    page: int | None
    span_start: int | None
    span_end: int | None
    boxes: list[list[float]] | None
    match: str | None = Field(description="exact, normalized or fuzzy; null when the quote was not found")


class ClaimOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    date: date | None
    end_date: date | None
    date_text: str | None
    time_text: str | None
    place: str | None
    amount: float | None
    currency: str | None
    amount_text: str | None
    applies_to: str | None
    subject_name: str | None
    requires: list[str]
    optional: bool
    uncertain: bool
    amends: str | None
    change: str | None
    quote: str
    location: SourceLocation
    confidence: float


class ExtractionOut(BaseModel):
    id: uuid.UUID
    extractor: str
    model: str | None
    prompt_version: str
    parser_version: str
    reference_date: date | None
    actionable: bool
    non_actionable_reason: str | None
    page_count: int
    ocr_pages: int
    notes: list[str]
    created_at: datetime
    claims: list[ClaimOut]


class ArtifactExtraction(BaseModel):
    """`extraction` is null until the job has finished; `job_status` says where it is."""
    artifact_id: uuid.UUID
    extraction: ExtractionOut | None
    job_id: uuid.UUID | None
    job_status: str | None
    job_error: str | None


class Amendment(BaseModel):
    """A proposed link: this notice revises that earlier one. Proposed until a
    member confirms it, because a wrong link would stop a live reminder."""
    id: uuid.UUID
    artifact_id: uuid.UUID
    claim_id: uuid.UUID
    claim_title: str
    change: str | None
    amends_artifact_id: uuid.UUID
    amends_claim_id: uuid.UUID
    amends_title: str
    amends_date: date | None
    score: float
    matched_on: str
    status: Literal["proposed", "confirmed", "rejected"]
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime


class AmendmentDecisionIn(BaseModel):
    status: Literal["confirmed", "rejected"]


class Reminder(BaseModel):
    id: uuid.UUID
    obligation_id: uuid.UUID
    reason: Literal["due", "undecided"]
    lead_days: int
    send_after: datetime
    channel: str
    status: Literal["pending", "sent", "failed", "cancelled"]
    sent_at: datetime | None
    title: str
    action: str
    due_date: date | None
    subject_member_id: uuid.UUID | None


class Mailbox(BaseModel):
    """A connected Google mailbox. There is no field here for the token, and
    no endpoint that returns one."""
    id: uuid.UUID
    email: str
    scopes: list[str]
    connected_at: datetime
    last_polled_at: datetime | None = None
    needs_reconnect: bool = False
    last_error: str | None = None
    backfill_done: bool = False
    disconnected_at: datetime | None = None


class MailboxAuthorization(BaseModel):
    """Where to send the member, and the state that ties the callback back to
    this request."""
    url: str
    state: str


LivedWhere = Literal["email", "whatsapp_group", "whatsapp_direct", "school_portal", "school_app",
                     "other_app", "sms", "paper", "word_of_mouth", "unknown"]


class GapIn(BaseModel):
    """A member saying a notice never reached them here."""
    title: str = Field(min_length=1, max_length=300)
    lived_where: LivedWhere
    # Unknown is different from no: if it was also emailed, the gap is a
    # matching problem rather than a channel problem.
    also_emailed: bool | None = None
    had_date: bool = False
    noticed_on: date | None = None
    note: str | None = Field(default=None, max_length=2000)


class GapResolveIn(BaseModel):
    """The notice that eventually arrived, or nothing to unset it."""
    arrived_as: uuid.UUID | None = None


class Gap(BaseModel):
    id: uuid.UUID
    reported_by: uuid.UUID
    title: str
    lived_where: LivedWhere
    also_emailed: bool | None = None
    had_date: bool
    noticed_on: date | None = None
    arrived_as: uuid.UUID | None = None
    note: str | None = None
    created_at: datetime


class GapWhere(BaseModel):
    lived_where: LivedWhere
    count: int
    with_a_date: int
    also_emailed: int
    arrived_later: int
    # What this answer would mean doing, carried with the number so the
    # finding and its consequence are not separated.
    means: str


class CaptureSummary(BaseModel):
    since: date
    captured: int
    missed_reported: int
    # None, not 1.0, when nothing has arrived yet.
    capture_rate: float | None = None
    captured_by_channel: dict[str, int]
    missed_by_where: list[GapWhere]
    caveat: str


ActionKind = Literal["reply", "calendar"]


class ActionIn(BaseModel):
    """What to do about an obligation. There is no recipient field: the address
    is derived from the notice, which is what stops this being a way to send
    mail anywhere."""
    kind: ActionKind
    # Required for a reply, ignored for a calendar entry.
    body: str | None = Field(default=None, max_length=4000)


class ActionApproveIn(BaseModel):
    """The fingerprint of exactly what was shown. A mismatch means the stored
    action is not what the person read, so the approval does not apply."""
    params_sha256: str = Field(min_length=64, max_length=64)


class Action(BaseModel):
    id: uuid.UUID
    obligation_id: uuid.UUID
    artifact_id: uuid.UUID
    kind: ActionKind
    recipient: str
    subject: str
    body: str
    params_sha256: str
    status: Literal["proposed", "approved", "sending", "sent", "failed", "cancelled"]
    proposed_by: uuid.UUID
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    attempts: int
    error: str | None = None
    created_at: datetime


BriefReason = Literal["missed", "mailbox", "assigned", "handled", "unbilled", "overdue", "today", "undecided", "soon",
                      "amendment", "quarantine", "school_year", "birthday", "majority", "money", "prepare"]


class NextThing(BaseModel):
    """The first dated thing past the brief's horizon, said only when there is
    nothing else to say."""
    title: str
    due_date: date
    days_away: int
    when: str


class BriefItem(BaseModel):
    """One line of the brief. Which ids are set depends on the reason: a dated
    thing points at its obligation, a revision at the amendment to confirm, a
    quarantined item at the notice a guardian has to vouch for."""
    reason: BriefReason
    rank: int
    title: str
    why: str
    when: str | None = None
    due_date: date | None = None
    due_time: str | None = None
    action: str | None = None
    status: str | None = None
    optional: bool = False
    # Things already in a calendar this member can see that overlap this one.
    # A fact about the obligation, not another thing to do.
    clashes: list[str] | None = None
    # The account whose bill has not arrived, for the "unbilled" reason.
    biller_id: uuid.UUID | None = None
    # For an assignment: who handed it over, and what they said.
    assigned_by_name: str | None = None
    # For a bill: its own way to pay, one tap from here.
    pay_url: str | None = None
    handled_by_name: str | None = None
    note: str | None = None
    # Public context, when the household switched "leave by" on and the thing has a place.
    travel_minutes: int | None = None
    leave_by: str | None = None
    # A later notice may have changed this and nobody has confirmed it, so the
    # date shown might not be the date that holds.
    contested: bool = False
    subject_member_id: uuid.UUID | None = None
    subject_name: str | None = None
    obligation_id: uuid.UUID | None = None
    amendment_id: uuid.UUID | None = None
    artifact_id: uuid.UUID | None = None
    mailbox_id: uuid.UUID | None = None


class BriefContext(BaseModel):
    """Public context the household switched on: the weather for home, the
    holidays coming, read without any credential."""
    weather: str | None = None
    weather_days: list[dict] | None = None
    holidays: list[dict] | None = None
    # The school run from home, per school: minutes typical (public maps),
    # and in the two hours before school, minutes now and the delay (live
    # traffic, when a key is set), with a leave-by time from the school's start.
    school_runs: list[dict] | None = None


class Brief(BaseModel):
    date: date
    member_id: uuid.UUID
    display_name: str
    items: list[BriefItem]
    context: BriefContext | None = None
    # Everything found, by reason -- not everything shown, so "and 4 more" can
    # be said honestly.
    counts: dict[str, int]
    more: int
    next_thing: NextThing | None = None


class Obligation(BaseModel):
    id: uuid.UUID
    artifact_id: uuid.UUID
    claim_id: uuid.UUID
    subject_member_id: uuid.UUID | None
    kind: Literal["task", "calendar"]
    action: str
    title: str
    due_date: date | None
    end_date: date | None
    due_time: str | None
    optional: bool
    status: Literal["proposed", "accepted", "dismissed"]
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime
    # Set when a later notice replaced the claim this came from. The row stays,
    # so "what happened to that?" has an answer.
    superseded_at: datetime | None = None
    superseded_by_artifact_id: uuid.UUID | None = None
    # Set when the member's own Google Calendar carries this date.
    calendar_event_id: str | None = None
    # The bill's own way to pay, from the notice: the biller's page or a UPI
    # intent. FamilyOS opens it; the person pays there.
    pay_url: str | None = None


class ObligationDecisionIn(BaseModel):
    status: Literal["accepted", "dismissed"]


class MoneyCharge(BaseModel):
    """One charge, from one message: the claim a person would point at.
    `upcoming` when the mail announces it (a bill, a renewal) rather than
    confirms it; then `due` is the date and `date` is when the mail came."""
    message_id: uuid.UUID
    artifact_id: uuid.UUID
    merchant: str
    category: str
    amount: float
    currency: str
    date: date
    title: str
    headline: str
    says_recurring: bool = False
    period_end: date | None = None
    # A receipt that paid a bill the mail had announced: the bill's message and due date.
    settles_message_id: uuid.UUID | None = None
    settles_due: date | None = None
    upcoming: bool = False
    due: date | None = None


class MoneyRecurring(BaseModel):
    merchant: str
    category: str
    currency: str
    cadence: Literal["monthly", "yearly", "weekly", "stated"]
    manage_url: str | None = None
    last_amount: float | None = None
    last_date: date | None = None
    next_date: date
    next_amount: float
    times: int
    total: float
    artifact_id: uuid.UUID


class MoneyTotal(BaseModel):
    category: str | None = None
    merchant: str | None = None
    currency: str
    total: float
    times: int | None = None
    # The same window before this one, and what moved it.
    previous: float | None = None
    delta: float | None = None
    driver: str | None = None


class MoneySpend(BaseModel):
    days: int
    charges: int
    previous_charges: int = 0
    comparable: bool = False
    by_category: list[MoneyTotal]
    by_merchant: list[MoneyTotal]


class MoneyService(BaseModel):
    date: date
    merchant: str
    kind: str
    what: str
    amount: float
    currency: str
    artifact_id: uuid.UUID


class MoneyServices(BaseModel):
    timeline: list[MoneyService]
    last_done: list[MoneyService]


class RunningLow(BaseModel):
    """Something the household buys at a steady rhythm, due again."""
    item: str
    item_key: str
    merchant: str
    times: int
    every_days: int
    last_on: date
    expected_on: date
    status: Literal["overdue", "soon", "fine"]
    last_amount: float | None = None
    currency: str | None = None
    reorder_url: str | None = None
    artifact_id: uuid.UUID | None = None


class Usual(BaseModel):
    """Something the household orders again and again: a dish as much as a staple."""
    item: str
    item_key: str
    merchant: str
    times: int
    last_on: date
    kind: Literal["meal", "grocery"]
    last_amount: float | None = None
    currency: str | None = None
    reorder_url: str | None = None


class Money(BaseModel):
    """Money as far as mail can see it: derived from claims, never stored."""
    days: int
    charges: list[MoneyCharge]
    recurring: list[MoneyRecurring]
    month: MoneySpend
    services: MoneyServices
    running_low: list[RunningLow] = []
    usual: list[Usual] = []


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatMessage] = []


class ChatCitation(BaseModel):
    ref: str
    kind: str
    text: str
    artifact_id: uuid.UUID | None = None
    obligation_id: uuid.UUID | None = None
    quote: str | None = None


class ChatProposal(BaseModel):
    """Something the model suggests doing. Nothing happens until a person
    confirms it, and then the ordinary endpoint does it."""
    kind: Literal["assign", "todo", "decide", "handled", "plan", "errand"]
    ok: bool
    why: str | None = None
    artifact_id: uuid.UUID | None = None
    headline: str | None = None
    obligation_id: uuid.UUID | None = None
    member_id: uuid.UUID | None = None
    member_name: str | None = None
    title: str | None = None
    due_date: date | None = None
    due_time: time | None = None
    note: str | None = None
    status: Literal["accepted", "dismissed"] | None = None
    brief: str | None = None
    shape: Literal["trip", "meals", "other"] | None = None
    # An errand: the site, what, and the most it may cost.
    service: str | None = None
    label: str | None = None
    what: str | None = None
    details: str | None = None
    part: Literal["morning", "afternoon", "evening", "any"] | None = None
    max_amount: float | None = None
    currency: str | None = None
    # True when the person only asked what is available: a look, not a booking.
    look: bool | None = None


class ChatTurn(BaseModel):
    say: str
    grounded: bool
    citations: list[ChatCitation]
    proposals: list[ChatProposal]
    model: str
    # Set when a reference in the answer does not seem to carry what the
    # answer attributes to it. The person is told to check before relying on it.
    note: str | None = None


class TodoIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: date | None = None
    # "11:00". Kept only with a date; alone it means nothing.
    due_time: time | None = None
    assigned_to: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class TodoDoneIn(BaseModel):
    done: bool


class Todo(BaseModel):
    id: uuid.UUID
    title: str
    note: str | None = None
    due_date: date | None = None
    due_time: time | None = None
    # Set once the to-do is on the member's Google Calendar.
    calendar_event_id: str | None = None
    assigned_to: uuid.UUID | None = None
    created_by: uuid.UUID | None = None
    done_at: datetime | None = None
    done_by: uuid.UUID | None = None
    created_at: datetime
    source_key: str | None = None


class DigestPreview(BaseModel):
    subject: str
    body: str
    sends_on: str


class DigestSent(BaseModel):
    sent: bool
    channel: str | None = None
    subject: str | None = None
    why: str | None = None


class PlanIn(BaseModel):
    brief: str = Field(min_length=1, max_length=2000)
    shape: Literal["trip", "meals", "other"] = "trip"


class PlanDay(BaseModel):
    day: int
    date: str | None = None
    title: str
    notes: str | None = None


class PlanPage(BaseModel):
    found: bool | None = None
    excerpt: str | None = None
    checked_at: datetime | None = None
    error: str | None = None


class PlanEvidence(BaseModel):
    """A real page, with what it said and when: shown with its source, never a fact."""
    url: str
    title: str | None = None
    excerpt: str | None = None
    read_at: str | None = None
    via: str | None = None


class PlanOption(BaseModel):
    id: str
    kind: str
    label: str
    provider: str
    url: str
    estimate: float | None = None
    currency: str | None = None
    note: str | None = None
    look_for: str | None = None
    watch_id: str | None = None
    chosen: bool = False
    booked_at: str | None = None
    page: PlanPage | None = None
    evidence: PlanEvidence | None = None


class PlanTodo(BaseModel):
    id: uuid.UUID
    title: str
    note: str | None = None
    due_date: date | None = None
    assigned_to: uuid.UUID | None = None
    done_at: datetime | None = None


class Plan(BaseModel):
    """A plan: written with the household in view, booked by the household."""
    id: uuid.UUID
    title: str
    brief: str
    status: Literal["writing", "draft", "active", "done", "dropped", "failed"]
    shape: Literal["trip", "meals", "other"] = "trip"
    # Why the writing failed, when it did; the page offers to try again.
    error: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    budget_amount: float | None = None
    budget_currency: str | None = None
    summary: str | None = None
    itinerary: list[PlanDay] = []
    options: list[PlanOption] = []
    todos: list[PlanTodo] = []
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class PlanChooseIn(BaseModel):
    option_id: str
    booked: bool = False


class PlanStatusIn(BaseModel):
    status: Literal["draft", "active", "done", "dropped"]


class DeviceIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)


class Device(BaseModel):
    id: uuid.UUID
    label: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None


class DeviceIssued(BaseModel):
    """The token is shown once, here, and never again."""
    device: Device
    token: str
    share_url: str


class ShareResult(BaseModel):
    """What a phone's share became: a notice, a duplicate of one, or a tag
    for the notice shared just before. `message` is the one line a shortcut
    can show on the phone."""
    artifact: Artifact | None = None
    duplicate: bool = False
    tagged: list[str] | None = None
    message: str = ""


class Suggestion(BaseModel):
    """A to-do an event implies. Suggested, never added on its own."""
    key: str
    title: str
    due_date: date
    why: str
    event: str
    event_on: date
    link: str | None = None


class SuggestionAcceptIn(BaseModel):
    assigned_to: uuid.UUID | None = None


class Offer(BaseModel):
    """Something FamilyOS could start doing, or will do, said in the family's
    names. Accept turns it on or opens Ask; Not now is remembered."""
    key: str
    kind: Literal["rule", "fyi", "ask"]
    title: str
    body: str
    limit: str
    fyi: bool
    accept_label: str | None = None
    ask: str | None = None


class OfferDone(BaseModel):
    key: str
    done: str
    ask: str | None = None
