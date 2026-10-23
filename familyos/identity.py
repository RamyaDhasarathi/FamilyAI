"""Households, members and sign-in tokens.

A household is the unit of tenancy, encryption and erasure. Members are
guardians (can consent for children and manage the household), adults
(sign in, see what is shared) and children (data subjects who do not sign
in in v1). Following Orbit's identity split, the person acting and the
household that owns the data are separate: every read and write names both.

Sign-in in v1 is a bearer token issued when a member is created. It stands
in for real authentication (phone OTP or email magic link), which replaces
`_issue_token` without changing anything that consumes a Principal.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
import secrets
import uuid
from dataclasses import dataclass

import asyncpg

from familyos import audit, crypto
from familyos.db import pool
from familyos.intake.whatsapp import normalise_phone
from familyos.models import HouseholdIn, MemberIn
from familyos.settings import settings

logger = logging.getLogger(__name__)


class NotAllowed(Exception):
    """The acting member may not do this."""


class NotFound(Exception):
    pass


class Invalid(ValueError):
    """The request is well-formed but not acceptable."""


@dataclass(frozen=True)
class Principal:
    member_id: uuid.UUID
    household_id: uuid.UUID
    role: str
    display_name: str
    # Which token this request arrived on, so signing out can end that one and
    # leave the member's other devices alone.
    token_id: uuid.UUID | None = None

    @property
    def is_guardian(self) -> bool:
        return self.role == "guardian"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


RESERVED_HANDLES = frozenset({
    "abuse", "admin", "administrator", "all", "billing", "contact", "familyos", "help", "hostmaster",
    "info", "mail", "mailer-daemon", "no-reply", "noreply", "postmaster", "root", "security",
    "support", "system", "webmaster", "www",
})
HANDLE_SHAPE = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")
TOKEN_SHAPE = re.compile(r"^h[0-9a-f]{20}$")


def inbound_address(inbound_token: str, handle: str | None = None) -> str:
    """What the family is shown. The handle when they have chosen one, and the
    generated token otherwise -- but both go on working forever, because an
    address written on a school form must not stop resolving."""
    return f"{handle or inbound_token}@{settings.inbound_domain}"


def clean_handle(raw: str) -> str:
    """The rules, said once, in the words a person will see if they break one."""
    handle = (raw or "").strip().lower()
    if not 3 <= len(handle) <= 32:
        raise Invalid("a family address is between 3 and 32 characters")
    if not HANDLE_SHAPE.match(handle):
        raise Invalid("use letters, numbers, dots and hyphens; start and end with a letter or number")
    if ".." in handle or "--" in handle or ".-" in handle or "-." in handle:
        raise Invalid("dots and hyphens cannot sit next to each other")
    if handle in RESERVED_HANDLES:
        raise Invalid("that address is reserved")
    if TOKEN_SHAPE.match(handle):
        raise Invalid("that looks like a generated address; choose something a person would say")
    return handle


async def handle_available(handle: str) -> bool:
    return not await pool().fetchval(
        "SELECT 1 FROM households WHERE lower(handle) = $1", clean_handle(handle))


async def set_handle(actor: Principal, raw: str) -> dict:
    """A guardian names the household. The generated token keeps working, so
    nothing already handed to a school breaks."""
    if not actor.is_guardian:
        raise NotAllowed("only a guardian can change the family address")
    handle = clean_handle(raw)
    async with pool().acquire() as conn, conn.transaction():
        taken = await conn.fetchval(
            "SELECT 1 FROM households WHERE lower(handle) = $1 AND id <> $2", handle, actor.household_id)
        if taken:
            raise Invalid("that address is taken")
        row = await conn.fetchrow(
            "UPDATE households SET handle = $2 WHERE id = $1 RETURNING *", actor.household_id, handle)
        await audit.record(actor.household_id, "household.handle_set", actor_member_id=actor.member_id,
                           target_type="household", target_id=actor.household_id, conn=conn)
    return dict(row)


async def _issue_token(conn: asyncpg.Connection, member_id: uuid.UUID) -> str:
    token = "fos_" + secrets.token_urlsafe(32)
    await conn.execute(
        "INSERT INTO member_tokens (id, member_id, token_hash, expires_at) "
        "VALUES ($1, $2, $3, NOW() + make_interval(days => $4))",
        uuid.uuid4(), member_id, _hash(token), settings.token_lifetime_days)
    return token


class LinkNotUsable(Invalid):
    """The link has expired, been used, or never existed. Said the same way for
    all three, so a stranger cannot learn which."""


class NoHouseholdYet(Invalid):
    """A Google-verified address that no household uses. Not a refusal: the
    person is who they say, and there is simply nothing for them to sign into
    yet. Carries the address so the console can offer to start one with it."""

    def __init__(self, email: str, ticket: str | None = None):
        super().__init__("no household uses that address yet")
        self.email = email
        # Proof the address was just verified: what founding a household takes.
        self.ticket = ticket


def _link_url(raw: str) -> str:
    base = settings.console_url
    return f"{base}{'&' if '?' in base else '?'}link={raw}"


def _founding_url(raw: str, email: str) -> str:
    """The ticket and the address ride in the fragment, as they do after
    Google: never sent to a server, taken out of the address bar at once."""
    from urllib.parse import quote
    base = settings.console_url
    return f"{base}{'&' if '?' in base else '?'}signin=new#found={quote(raw)}&email={quote(email)}"


async def _issue_link(conn: asyncpg.Connection, member_id: uuid.UUID, *, purpose: str,
                      issued_by: uuid.UUID | None = None) -> str:
    """One unused link per member at a time. Asking again replaces the last one,
    so a forwarded or screenshotted link stops working the moment a new one is
    asked for."""
    raw = "lnk_" + secrets.token_urlsafe(32)
    await conn.execute(
        "UPDATE sign_in_links SET used_at = NOW() WHERE member_id = $1 AND used_at IS NULL", member_id)
    await conn.execute(
        "INSERT INTO sign_in_links (id, member_id, token_hash, purpose, issued_by, expires_at) "
        "VALUES ($1, $2, $3, $4, $5, NOW() + make_interval(mins => $6))",
        uuid.uuid4(), member_id, _hash(raw), purpose, issued_by, settings.sign_in_link_minutes)
    return raw


async def request_sign_in(email: str) -> int:
    """Mail a sign-in link to every member row this address can sign in as.

    Returns how many were sent, for logs and tests. The route says the same
    thing either way: whether an address belongs to a family is not something
    an unauthenticated caller may discover.
    """
    from familyos import mail
    address = (email or "").strip().lower()
    if not address or "@" not in address:
        return 0
    sent = 0
    async with pool().acquire() as conn:
        members = await conn.fetch(
            "SELECT m.id, m.display_name, h.name AS household FROM members m "
            "JOIN households h ON h.id = m.household_id "
            "WHERE lower(m.email) = $1 AND m.role <> 'child'", address)
        anyone = await conn.fetchval("SELECT 1 FROM members WHERE lower(email) = $1 LIMIT 1", address)
        if not members and not anyone:
            # An address no family uses at all is offered one -- by mail, so
            # only the person holding the mailbox learns that, and the form's
            # answer stays the same for everyone. "At all" is deliberate: an
            # address on a row that cannot sign in is not a stranger's.
            async with conn.transaction():
                raw = await issue_founding(conn, address)
            try:
                await mail.send(
                    address, "Start a household on FamilyOS",
                    "Hello,\n\nNobody has signed up with this address yet. Open this link to start a household:\n\n"
                    f"{_founding_url(raw, address)}\n\n"
                    f"It works once and expires in {settings.sign_in_link_minutes} minutes. "
                    "If you did not ask for it, you can ignore this message.\n")
                return 1
            except Exception:  # noqa: BLE001 - never tell a caller whether the address exists
                logger.warning("could not send a founding link", exc_info=True)
                return 0
        for m in members:
            async with conn.transaction():
                raw = await _issue_link(conn, m["id"], purpose="sign_in")
            try:
                await mail.send(
                    address, f"Sign in to {m['household']}",
                    f"Hello {m['display_name']},\n\n"
                    f"Open this link to sign in to {m['household']}:\n\n{_link_url(raw)}\n\n"
                    f"It works once and expires in {settings.sign_in_link_minutes} minutes. "
                    "If you did not ask for it, you can ignore this message -- nobody can sign in without the link.\n")
            except Exception:  # noqa: BLE001 - never tell a caller whether the address exists
                # A mail failure must not be the difference between a known and
                # an unknown address. The link stands; they can ask again.
                logger.warning("could not send a sign-in link", exc_info=True)
                continue
            sent += 1
    return sent


async def invite(actor: Principal, member_id: uuid.UUID) -> str:
    """A guardian sends a member their way in. The same primitive as sign-in:
    an invitation is only a first link."""
    from familyos import mail
    if not actor.is_guardian:
        raise NotAllowed("only a guardian can invite a member")
    async with pool().acquire() as conn:
        member = await conn.fetchrow(
            "SELECT m.id, m.display_name, m.email, m.role, h.name AS household FROM members m "
            "JOIN households h ON h.id = m.household_id "
            "WHERE m.id = $1 AND m.household_id = $2", member_id, actor.household_id)
        if member is None:
            raise NotFound("member")
        if member["role"] == "child":
            raise Invalid("a child does not sign in, so there is nothing to invite them to")
        if not member["email"]:
            raise Invalid("this member has no email address to send an invitation to")
        async with conn.transaction():
            raw = await _issue_link(conn, member["id"], purpose="invite", issued_by=actor.member_id)
            await audit.record(actor.household_id, "member.invited", actor_member_id=actor.member_id,
                               target_type="member", target_id=member["id"], conn=conn)
    await mail.send(
        member["email"], f"{actor.display_name} added you to {member['household']}",
        f"Hello {member['display_name']},\n\n"
        f"{actor.display_name} added you to {member['household']} on FamilyOS.\n\n"
        f"Open this link to sign in:\n\n{_link_url(raw)}\n\n"
        f"It works once and expires in {settings.sign_in_link_minutes} minutes. "
        "You can ask for another from the sign-in page at any time.\n")
    return str(member["id"])


# ----------------------------------------------------------------------------
# signing in with Google
# ----------------------------------------------------------------------------

# A state the phone app began carries this mark, so the callback knows to
# hand the token back to the app and not to the console.
APP_STATE = "app-"
APP_SCHEME = "familyos"


async def google_sign_in_url(*, native: bool = False) -> dict:
    """Where to send someone who chose "Continue with Google".

    Only the basic scopes -- openid and email. Signing in costs nothing at
    Google's end: no verification, no CASA, none of what reading a mailbox
    needs. Connecting Gmail stays a separate, later decision.

    `native` is the phone app asking: the callback then returns to the app
    through its URL scheme instead of to the console.
    """
    from familyos.intake import google, mailbox
    client_id, _ = mailbox._require_client()
    state = (APP_STATE if native else "") + secrets.token_urlsafe(32)
    verifier, challenge = google.pkce()
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM google_sign_in_states WHERE created_at < NOW() - interval '15 minutes'")
        await conn.execute(
            "INSERT INTO google_sign_in_states (state, code_verifier) VALUES ($1, $2)", state, verifier)
    return {"state": state,
            "url": google.authorize_url(client_id=client_id, redirect_uri=settings.google_sign_in_redirect_uri,
                                        state=state, challenge=challenge, wanted=google.SIGN_IN_SCOPES)}


def began_in_app(state: str | None) -> bool:
    return bool(state) and state.startswith(APP_STATE)


async def complete_google_sign_in(state: str, code: str, *, transport=None) -> tuple[dict, str]:
    """Spend the callback and return (member, session token).

    The id_token is read rather than verified, which is sound here for the
    same reason it is sound anywhere: it arrived on our own TLS connection to
    Google's token endpoint, in answer to our own request carrying our own
    client secret. Nobody else's word is being taken.

    Two claims *are* checked, because this is authorisation and not labelling:
    the audience must be our client, and the address must be one Google says
    it verified -- an unverified address on a Workspace account is a name its
    administrator chose, not a mailbox anyone proved they hold.
    """
    from familyos.intake import google, mailbox
    client_id, client_secret = mailbox._require_client()
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "UPDATE google_sign_in_states SET used_at = NOW() WHERE state = $1 AND used_at IS NULL "
            "AND created_at > NOW() - interval '15 minutes' RETURNING code_verifier", state or "")
        if row is None:
            raise LinkNotUsable("that sign-in has expired or has already been used")

    token_in = await google.exchange_code(code, row["code_verifier"], client_id=client_id,
                                          client_secret=client_secret,
                                          redirect_uri=settings.google_sign_in_redirect_uri, transport=transport)
    if token_in.audience != client_id:
        raise LinkNotUsable("that sign-in was not meant for this deployment")
    if not token_in.email or not token_in.email_verified:
        raise LinkNotUsable("Google has not verified that address, so it cannot be used to sign in")

    address = token_in.email.strip().lower()
    async with pool().acquire() as conn, conn.transaction():
        member = await conn.fetchrow(
            "SELECT id, household_id, display_name, role, email, phone, date_of_birth, created_at "
            "FROM members WHERE lower(email) = $1 AND role <> 'child' ORDER BY created_at LIMIT 1", address)
        if member is None:
            # An address nobody here uses is told so, and offered a household.
            # That is safe where the magic-link form's silence is necessary:
            # there, anyone can type any address and learn which belong to
            # families. Here Google has just verified that this person holds
            # this mailbox, so the only address they can learn about is their
            # own. A brand-new parent who taps Google first -- the obvious
            # first tap -- must land somewhere, not at a dead end.
            #
            # No member row matched, so no household uses this address. That
            # holds because the schema forbids a child an email (members_check):
            # there is no "known address that still cannot sign in" to tell
            # apart from a stranger's. Age transition will change that, and
            # test_a_child_cannot_have_an_address_so_google_never_matches_one
            # is there to fail when it does.
            break_out = True
        else:
            break_out = False
            token = await _issue_token(conn, member["id"])
            await audit.record(member["household_id"], "member.signed_in", actor_member_id=member["id"],
                               target_type="member", target_id=member["id"],
                               detail={"via": "google"}, conn=conn)
    if break_out:
        # Its own transaction: raising inside the one above would roll the
        # ticket back with it.
        async with pool().acquire() as conn, conn.transaction():
            ticket = await issue_founding(conn, address)
        raise NoHouseholdYet(address, ticket)
    return dict(member), token


async def redeem(raw: str) -> tuple[dict, str]:
    """Spend a link and return (member, session token).

    The check and the spend are one statement: two tabs opening the same link
    cannot both come away with a session.
    """
    async with pool().acquire() as conn, conn.transaction():
        link = await conn.fetchrow(
            # purpose is checked, not just read: a Telegram binding token
            # travels through a chat and must never buy a console session.
            "UPDATE sign_in_links SET used_at = NOW() WHERE token_hash = $1 "
            "AND used_at IS NULL AND expires_at > NOW() AND purpose <> 'telegram' "
            "RETURNING member_id, purpose",
            _hash(raw or ""))
        if link is None:
            raise LinkNotUsable("that link has expired or has already been used")
        member = await conn.fetchrow(
            "SELECT id, household_id, display_name, role, email, phone, date_of_birth, created_at "
            "FROM members WHERE id = $1 AND role <> 'child'",
            link["member_id"])
        if member is None:
            raise LinkNotUsable("that link has expired or has already been used")
        token = await _issue_token(conn, member["id"])
        await audit.record(member["household_id"], "member.signed_in", actor_member_id=member["id"],
                           target_type="member", target_id=member["id"],
                           detail={"via": link["purpose"]}, conn=conn)
    return dict(member), token


async def issue_founding(conn: asyncpg.Connection, email: str) -> str:
    """A ticket to found a household, for an address somebody has just proved
    they hold. One live ticket per address: asking again replaces it."""
    address = (email or "").strip().lower()
    raw = "fnd_" + secrets.token_urlsafe(32)
    await conn.execute("UPDATE founding_tickets SET used_at = NOW() WHERE lower(email) = $1 AND used_at IS NULL", address)
    await conn.execute(
        "INSERT INTO founding_tickets (id, email, token_hash, expires_at) "
        "VALUES ($1, $2, $3, NOW() + make_interval(mins => $4))",
        uuid.uuid4(), address, _hash(raw), settings.sign_in_link_minutes)
    return raw


async def _spend_founding(conn: asyncpg.Connection, raw: str | None, email: str) -> None:
    """The ticket must be live and for this very address. Spending it is the
    same statement as checking it, so it cannot be used twice."""
    row = await conn.fetchrow(
        "UPDATE founding_tickets SET used_at = NOW() WHERE token_hash = $1 AND used_at IS NULL "
        "AND expires_at > NOW() AND lower(email) = $2 RETURNING id", _hash(raw or ""), email.strip().lower())
    if row is None:
        raise LinkNotUsable("founding a household takes a link sent to that address, or Google's word for it; "
                            "this one is missing, spent, expired, or for a different address")


async def create_household(data: HouseholdIn) -> tuple[dict, dict, str]:
    """A new household with its first guardian, founded on proof of the
    guardian's address. Returns (household, member, token)."""
    household_id, member_id = uuid.uuid4(), uuid.uuid4()
    async with pool().acquire() as conn, conn.transaction():
        await _spend_founding(conn, data.founding, str(data.guardian.email))
        from familyos import country as countries
        prof = countries.profile(data.country)
        c, tz, cur = countries.check(data.country, data.timezone or prof["timezone"], data.currency or prof["currency"])
        household = await conn.fetchrow(
            "INSERT INTO households (id, name, inbound_token, wrapped_key, country, timezone, currency) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
            household_id, data.name, "h" + secrets.token_hex(10), crypto.new_wrapped_key(household_id), c, tz, cur)
        member = await conn.fetchrow(
            "INSERT INTO members (id, household_id, display_name, role, email) VALUES ($1, $2, $3, 'guardian', $4) RETURNING *",
            member_id, household_id, data.guardian.display_name, str(data.guardian.email).lower())
        token = await _issue_token(conn, member_id)
        await audit.record(household_id, "household.created", actor_member_id=member_id,
                           target_type="household", target_id=household_id, conn=conn)
        await audit.record(household_id, "member.added", actor_member_id=member_id, target_type="member",
                           target_id=member_id, detail={"role": "guardian"}, conn=conn)
    return dict(household), dict(member), token


async def add_member(actor: Principal, data: MemberIn) -> tuple[dict, str | None]:
    """Guardians add members. Children get no token: they do not sign in."""
    if not actor.is_guardian:
        raise NotAllowed("only a guardian can add members")
    if data.role == "child" and data.email:
        raise Invalid("a child member has no email address in v1")
    if data.role != "child" and not data.email:
        raise Invalid("a guardian or adult member needs an email address")
    phone = normalise_phone(data.phone) if data.role != "child" else None
    if data.role == "child" and data.phone:
        raise Invalid("a child member has no phone number in v1")
    if data.role != "child" and (data.school or data.class_label):
        raise Invalid("school and class are recorded for children only")
    member_id = uuid.uuid4()
    async with pool().acquire() as conn, conn.transaction():
        try:
            member = await conn.fetchrow(
                "INSERT INTO members (id, household_id, display_name, role, email, phone, date_of_birth, "
                "school, class_label) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *",
                member_id, actor.household_id, data.display_name, data.role,
                str(data.email).lower() if data.email else None, phone, data.date_of_birth,
                _clean(data.school), _clean(data.class_label))
        except asyncpg.UniqueViolationError as exc:
            raise Invalid("a member with this email or phone number already exists in the household") from exc
        token = await _issue_token(conn, member_id) if data.role != "child" else None
        await audit.record(actor.household_id, "member.added", actor_member_id=actor.member_id, target_type="member",
                           target_id=member_id, detail={"role": data.role}, conn=conn)
    return dict(member), token


def _clean(text: str | None) -> str | None:
    return " ".join((text or "").split()) or None


async def set_school(actor: Principal, member_id: uuid.UUID, school: str | None,
                     class_label: str | None, since: dt.date | None = None) -> dict:
    """Record which school and class a child is in. Guardians only, children
    only -- it is the key circulars are addressed by, and it changes once a
    year. Null clears. A change is kept with the date it began (`since`,
    today unless said), so a notice is matched to the class in force on
    its own date and last year's class is still known."""
    if not actor.is_guardian:
        raise NotAllowed("only a guardian can set a child's school")
    school, class_label = _clean(school), _clean(class_label)
    async with pool().acquire() as conn, conn.transaction():
        before = await conn.fetchrow("SELECT school, class_label FROM members WHERE id = $1 AND household_id = $2 AND role = 'child'",
                                     member_id, actor.household_id)
        if before is None:
            raise NotFound("child")
        from familyos import schools
        school_id = await schools.find_or_make(conn, actor.household_id, school)
        row = await conn.fetchrow(
            "UPDATE members SET school = $3, class_label = $4, school_id = $5 "
            "WHERE id = $1 AND household_id = $2 AND role = 'child' RETURNING *",
            member_id, actor.household_id, school, class_label, school_id)
        changed = (before["school"], before["class_label"]) != (school, class_label)
        if changed and (school or class_label):
            await conn.execute(
                "INSERT INTO member_classes (id, household_id, member_id, school, class_label, since, set_by) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                uuid.uuid4(), actor.household_id, member_id, school, class_label, since or dt.date.today(), actor.member_id)
        await audit.record(actor.household_id, "member.school_set", actor_member_id=actor.member_id,
                           target_type="member", target_id=member_id,
                           # Which school is a fact about the child; the audit
                           # records that it was set, not what to.
                           detail={"set": bool(row["school"] or row["class_label"]), "changed": changed}, conn=conn)
    return dict(row)


async def set_birthday(actor: Principal, member_id: uuid.UUID, date_of_birth: dt.date | None) -> dict:
    """A member's date of birth: a guardian sets anyone's, an adult their
    own. Null clears. It gives ages, birthdays on the brief, and the day a
    child's records become their own."""
    if not actor.is_guardian and actor.member_id != member_id:
        raise NotAllowed("only a guardian can set someone else's birthday")
    if date_of_birth and date_of_birth > dt.date.today():
        raise ValueError("a birthday cannot be in the future")
    async with pool().acquire() as conn, conn.transaction():
        row = await conn.fetchrow("UPDATE members SET date_of_birth = $3 WHERE id = $1 AND household_id = $2 RETURNING *",
                                  member_id, actor.household_id, date_of_birth)
        if row is None:
            raise NotFound("member")
        await audit.record(actor.household_id, "member.birthday_set", actor_member_id=actor.member_id, target_type="member",
                           target_id=member_id, detail={"set": date_of_birth is not None}, conn=conn)
    return dict(row)


async def class_history(p: Principal, member_id: uuid.UUID) -> list[dict]:
    """Every school and class a child has been recorded in, latest first."""
    rows = await pool().fetch(
        "SELECT c.school, c.class_label, c.since FROM member_classes c JOIN members m ON m.id = c.member_id "
        "WHERE m.household_id = $1 AND c.member_id = $2 ORDER BY c.since DESC, c.created_at DESC", p.household_id, member_id)
    if not rows:
        raise NotFound("child") if await pool().fetchval("SELECT 1 FROM members WHERE id = $1 AND household_id = $2", member_id, p.household_id) is None else None
    return [dict(r) for r in rows]


# The class a child was in on a date: the latest record that had begun by
# then, or the earliest record for a notice older than the history, or the
# members row when there is no history at all.
CLASS_AS_OF = """
SELECT m.id, m.display_name,
       COALESCE(c.school, e.school, m.school) AS school,
       COALESCE(c.class_label, e.class_label, m.class_label) AS class_label
FROM members m
LEFT JOIN LATERAL (SELECT school, class_label FROM member_classes WHERE member_id = m.id AND since <= $2
                   ORDER BY since DESC, created_at DESC LIMIT 1) c ON TRUE
LEFT JOIN LATERAL (SELECT school, class_label FROM member_classes WHERE member_id = m.id
                   ORDER BY since ASC, created_at ASC LIMIT 1) e ON TRUE
WHERE m.household_id = $1 AND m.role = 'child'
"""


async def authenticate(token: str, *, allow_erasing: bool = False) -> Principal | None:
    """A signed-in member. An erasing household signs nobody in; the one
    exception is reading the erasure's own progress (`allow_erasing`), which
    would otherwise be unreachable because erasure invalidates every token
    the moment it starts."""
    digest = _hash(token)
    row = await pool().fetchrow(
        "SELECT t.id AS token_id, m.id, m.household_id, m.role, m.display_name FROM member_tokens t "
        "JOIN members m ON m.id = t.member_id JOIN households h ON h.id = m.household_id "
        "WHERE t.token_hash = $1 AND t.revoked_at IS NULL AND m.role <> 'child' "
        "AND (t.expires_at IS NULL OR t.expires_at > NOW()) "
        "AND (h.status = 'active' OR ($2 AND h.status = 'erasing'))",
        digest, allow_erasing)
    if row is None:
        return None
    # Slide the expiry forward while the token is in use, at most once an hour
    # so a busy session is not a write per request. A token nobody uses ends.
    # A device token (a phone's shortcut) neither slides nor ends: it is
    # revoked, on purpose, from the Household page.
    await pool().execute(
        "UPDATE member_tokens SET last_used_at = NOW(), "
        "expires_at = CASE WHEN kind = 'device' THEN expires_at ELSE NOW() + make_interval(days => $2) END "
        "WHERE id = $1 AND (last_used_at IS NULL OR last_used_at < NOW() - INTERVAL '1 hour')",
        row["token_id"], settings.token_lifetime_days)
    return Principal(member_id=row["id"], household_id=row["household_id"], role=row["role"],
                     display_name=row["display_name"], token_id=row["token_id"])


async def sign_out(actor: Principal) -> int:
    """End the token this request arrived on, and nothing else: signing out on
    the shared laptop must not sign you out on your phone."""
    if actor.token_id is None:
        return 0
    async with pool().acquire() as conn, conn.transaction():
        done = await conn.execute(
            "UPDATE member_tokens SET revoked_at = NOW(), revoked_reason = 'signed_out' "
            "WHERE id = $1 AND revoked_at IS NULL", actor.token_id)
        ended = 0 if done == "UPDATE 0" else 1
        if ended:
            await audit.record(actor.household_id, "session.signed_out", actor_member_id=actor.member_id,
                               target_type="member", target_id=actor.member_id, conn=conn)
    return ended


async def revoke_all(actor: Principal, member_id: uuid.UUID) -> int:
    """Every token a member holds, ended at once. Yourself, or -- when a phone
    is lost and its owner cannot reach it -- anyone in the household, by a
    guardian. Children have no tokens to end."""
    if member_id != actor.member_id and not actor.is_guardian:
        raise NotAllowed("only a guardian can sign another member out")
    async with pool().acquire() as conn, conn.transaction():
        member = await conn.fetchrow("SELECT id FROM members WHERE id = $1 AND household_id = $2",
                                     member_id, actor.household_id)
        if member is None:
            raise NotFound("member")
        rows = await conn.fetch(
            "UPDATE member_tokens SET revoked_at = NOW(), revoked_reason = 'revoked' "
            "WHERE member_id = $1 AND revoked_at IS NULL RETURNING id", member_id)
        if rows:
            await audit.record(actor.household_id, "session.revoked", actor_member_id=actor.member_id,
                               target_type="member", target_id=member_id,
                               detail={"tokens_ended": len(rows)}, conn=conn)
    return len(rows)


async def sessions(actor: Principal, member_id: uuid.UUID | None = None) -> list[dict]:
    """The live tokens for a member: yours, or anyone's if you are a guardian.
    The token itself is never shown again -- only when it started, when it was
    last used, and when it ends."""
    member_id = member_id or actor.member_id
    if member_id != actor.member_id and not actor.is_guardian:
        raise NotAllowed("only a guardian can see another member's sessions")
    rows = await pool().fetch(
        "SELECT t.id, t.member_id, t.created_at, t.last_used_at, t.expires_at, t.kind, t.label "
        "FROM member_tokens t JOIN members m ON m.id = t.member_id "
        "WHERE t.member_id = $1 AND m.household_id = $2 AND t.revoked_at IS NULL "
        "AND (t.expires_at IS NULL OR t.expires_at > NOW()) ORDER BY t.created_at DESC",
        member_id, actor.household_id)
    return [{**dict(r), "current": r["id"] == actor.token_id} for r in rows]


async def get_household(household_id: uuid.UUID) -> dict:
    household = await pool().fetchrow("SELECT * FROM households WHERE id = $1", household_id)
    if household is None:
        raise NotFound("household")
    members = await pool().fetch("SELECT * FROM members WHERE household_id = $1 ORDER BY created_at", household_id)
    return {**dict(household), "members": [dict(m) for m in members]}


async def get_member(household_id: uuid.UUID, member_id: uuid.UUID) -> dict:
    row = await pool().fetchrow("SELECT * FROM members WHERE id = $1 AND household_id = $2", member_id, household_id)
    if row is None:
        raise NotFound("member")
    return dict(row)


async def household_by_inbound_token(inbound_token: str) -> dict | None:
    """Either address resolves to the same household: the generated token, and
    the handle the family chose. The two namespaces cannot collide -- a handle
    shaped like a token is refused when it is set."""
    row = await pool().fetchrow(
        "SELECT * FROM households WHERE (inbound_token = $1 OR lower(handle) = lower($1)) "
        "AND status = 'active'", inbound_token)
    return dict(row) if row else None


async def member_by_phone(number: str) -> dict | None:
    """The member a WhatsApp number belongs to, and so the household a
    forwarded message lands in. There is no per-household WhatsApp address the
    way there is for email -- every message arrives at one business number --
    so the sender is the only thing that can place it.

    A number in two households is ambiguous and places nothing: guessing which
    family a school notice belongs to is not a guess worth making."""
    from familyos.intake.whatsapp import phone_variants

    rows = await pool().fetch(
        "SELECT m.* FROM members m JOIN households h ON h.id = m.household_id "
        "WHERE m.phone = ANY($1::text[]) AND m.role <> 'child' AND h.status = 'active'",
        phone_variants(number))
    if len(rows) != 1:
        return None
    return dict(rows[0])


async def member_by_telegram(chat_id: int) -> dict | None:
    """The member a Telegram account belongs to.

    Simpler than `member_by_phone` because the binding was deliberate: nobody
    typed this id into a form, so there is no near-miss to reconcile and no
    second household it might also mean. A unique index makes two members
    sharing one Telegram account impossible rather than ambiguous.
    """
    row = await pool().fetchrow(
        "SELECT m.* FROM members m JOIN households h ON h.id = m.household_id "
        "WHERE m.telegram_chat_id = $1 AND m.role <> 'child' AND h.status = 'active'",
        int(chat_id))
    return dict(row) if row else None


class TelegramAlreadyLinked(Invalid):
    """That Telegram account is already bound to a different member."""


async def issue_telegram_link(p: Principal) -> str:
    """A one-time token for the member's own Telegram deep link.

    The member asks for it from the console, where they are already signed in,
    and opens it on the phone that has Telegram. That is the whole binding: no
    number to type, nothing to verify by SMS, and nothing a stranger can guess.
    """
    async with pool().acquire() as conn:
        return await _issue_link(conn, p.member_id, purpose="telegram")


async def bind_telegram(raw: str, chat_id: int) -> dict:
    """Spend a binding token and attach the Telegram account to its member.

    Single use, and single purpose: a token issued for binding cannot be
    redeemed for a session, and a sign-in link cannot bind an account. The
    spend and the check are one statement, as they are for sign-in, so the
    same link opened twice binds once.

    Re-binding is allowed and replaces: a parent who changes Telegram account
    asks for another link rather than for support.
    """
    async with pool().acquire() as conn, conn.transaction():
        link = await conn.fetchrow(
            "UPDATE sign_in_links SET used_at = NOW() WHERE token_hash = $1 "
            "AND used_at IS NULL AND expires_at > NOW() AND purpose = 'telegram' "
            "RETURNING member_id", _hash(raw or ""))
        if link is None:
            raise LinkNotUsable("that link has expired or has already been used")
        # Taken off whoever held it before, so the unique index cannot refuse
        # a parent who reinstalled Telegram and came back with a new id.
        await conn.execute(
            "UPDATE members SET telegram_chat_id = NULL WHERE telegram_chat_id = $1 AND id <> $2",
            int(chat_id), link["member_id"])
        member = await conn.fetchrow(
            "UPDATE members SET telegram_chat_id = $2 WHERE id = $1 AND role <> 'child' "
            "RETURNING id, household_id, display_name, role, email, phone, telegram_chat_id",
            link["member_id"], int(chat_id))
        if member is None:
            raise LinkNotUsable("that link has expired or has already been used")
        await audit.record(member["household_id"], "member.telegram_linked",
                           actor_member_id=member["id"], target_type="member",
                           target_id=member["id"], conn=conn)
    return dict(member)


async def unbind_telegram(p: Principal) -> bool:
    """Stop the bot reaching this member. Their own account, their own call."""
    async with pool().acquire() as conn, conn.transaction():
        done = await conn.fetchval(
            "UPDATE members SET telegram_chat_id = NULL "
            "WHERE id = $1 AND telegram_chat_id IS NOT NULL RETURNING TRUE", p.member_id)
        if done:
            await audit.record(p.household_id, "member.telegram_unlinked",
                               actor_member_id=p.member_id, target_type="member",
                               target_id=p.member_id, conn=conn)
    return bool(done)


async def member_by_email(household_id: uuid.UUID, email: str) -> dict | None:
    row = await pool().fetchrow(
        "SELECT * FROM members WHERE household_id = $1 AND lower(email) = lower($2) AND role <> 'child'", household_id, email)
    return dict(row) if row else None


# ----------------------------------------------------------------------------
# device tokens: what a phone's shortcut holds
# ----------------------------------------------------------------------------

DEVICE_LABEL_MAX = 80


async def issue_device_token(p: Principal, label: str) -> tuple[dict, str]:
    """A token for a shortcut or an automation on one device. Shown once;
    never slides, never expires; revoked from the Household page. It is the
    member's own token, so what the phone sends is theirs, private, audited."""
    label = " ".join((label or "").split())[:DEVICE_LABEL_MAX] or "A phone"
    token = "fosd_" + secrets.token_urlsafe(32)
    async with pool().acquire() as conn, conn.transaction():
        # A token issued under this label that was never used is a false start
        # (an app signing in again, a shortcut set up twice): it goes when the
        # next one comes, so the Devices card does not fill with "not used yet".
        await conn.execute(
            "UPDATE member_tokens SET revoked_at = NOW(), revoked_reason = 'replaced' "
            "WHERE member_id = $1 AND kind = 'device' AND label = $2 AND last_used_at IS NULL AND revoked_at IS NULL",
            p.member_id, label)
        row = await conn.fetchrow(
            "INSERT INTO member_tokens (id, member_id, token_hash, expires_at, kind, label) "
            "VALUES ($1, $2, $3, NULL, 'device', $4) RETURNING id, label, created_at, last_used_at",
            uuid.uuid4(), p.member_id, _hash(token), label)
        await audit.record(p.household_id, "device.added", actor_member_id=p.member_id, target_type="member",
                           target_id=p.member_id, detail={"token_id": str(row["id"]), "label": label}, conn=conn)
    return dict(row), token


async def list_devices(p: Principal) -> list[dict]:
    rows = await pool().fetch(
        "SELECT id, label, created_at, last_used_at FROM member_tokens WHERE member_id = $1 AND kind = 'device' "
        "AND revoked_at IS NULL ORDER BY created_at DESC", p.member_id)
    return [dict(r) for r in rows]


async def revoke_device(p: Principal, token_id: uuid.UUID) -> None:
    async with pool().acquire() as conn, conn.transaction():
        done = await conn.execute(
            "UPDATE member_tokens SET revoked_at = NOW(), revoked_reason = 'revoked' "
            "WHERE id = $1 AND member_id = $2 AND kind = 'device' AND revoked_at IS NULL", token_id, p.member_id)
        if done == "UPDATE 0":
            raise NotFound("device")
        await audit.record(p.household_id, "device.revoked", actor_member_id=p.member_id, target_type="member",
                           target_id=p.member_id, detail={"token_id": str(token_id)}, conn=conn)
