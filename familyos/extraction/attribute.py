"""Whom a notice is about, when nobody said.

A circular is addressed by class, not by name: "Dear Parents of Grade 4",
"Class IX students will", or -- most often, in a pasted WhatsApp text --
nothing at all beyond "Dear Parents". The extractor records what it was
addressed to in `applies_to`, and the household records which class each
child is in. This matches the two.

Two rules, tried in order, and only when no person has tagged the notice:

1. **Class.** A claim scoped to a class a child is in attaches that child.
   "Grade 4" finds the child whose class_label is "4"; "Class IX-B" finds
   the one in "IX-B". Generic words (class, grade, section, students) are
   ignored, so "Class 4" and "Grade 4" and "4" are the same key.

2. **Elimination.** No class matched, the notice reads as a school notice,
   and every consented child with a school recorded is at the *same* school:
   then it is that school's notice, and it is about all of them. Not because
   the message said so -- it did not -- but because there is nothing else it
   could be. Two schools and no class named is genuinely ambiguous, and a
   parent decides.

"Reads as a school notice" is the honest limit of this. Without it, every
household's children would be attached to the electricity bill. The test is
whether a claim's audience names children, students, parents or a class, in
English or by a class label; a notice in Tamil that says only "all" is not
attributed, and a parent tags it. That is a known gap, not a surprise.

Consent is the same gate it is everywhere: a child without active consent is
never attached, by any rule.
"""
from __future__ import annotations

import datetime as dt
import re
import uuid

import asyncpg

from familyos.consent import HOUSEHOLD_RECORDS

# Words that make "Class IX" and "Grade IX" and "IX" the same key.
_GENERIC = frozenset({
    "class", "classes", "grade", "grades", "std", "standard", "section", "sec",
    "students", "student", "pupils", "pupil", "of", "the", "and", "&", "for",
})

# A claim whose audience is any of these is a school's, not a biller's.
# "all" is not here on purpose: an electricity bill's claims are scoped to
# "all" too, and the first bill through the seeded household was handed to
# both children for it. "All" counts only beside a word that names them.
_SCHOOL_AUDIENCE = frozenset({
    "children", "child", "kids", "students", "student", "pupils", "pupil",
    "parents", "parent", "guardians", "school",
})

_ROMAN = re.compile(r"^(?=[ivx])m*(c[md]|d?c{0,3})(x[cl]|l?x{0,3})(i[xv]|v?i{0,3})$")


def _tokens(text: str | None) -> set[str]:
    words = re.split(r"[\s,/()\-]+", (text or "").casefold())
    return {w.strip(".:;") for w in words if w.strip(".:;")}


def class_key(label: str | None) -> set[str]:
    """The tokens that identify a class once the generic words are gone."""
    return _tokens(label) - _GENERIC


def class_matches(applies_to: str | None, class_label: str | None) -> bool:
    """Whether a claim's scope names this class. The class's own key must be
    wholly inside the claim's scope: "IX-B" is in "Class IX-B students", and
    "4" is in "Grades 4 and 5" -- but "4" is not in "Grade 14", because 14 is
    one token and 4 is another."""
    key = class_key(class_label)
    scope = class_key(applies_to)
    return bool(key) and key <= scope


def looks_like_class(applies_to: str | None) -> bool:
    """A scope that names a class even if no child is in it: a digit, or a
    roman numeral, among its tokens."""
    return any(t.isdigit() or _ROMAN.match(t) for t in class_key(applies_to))


def is_school_audience(applies_to: str | None) -> bool:
    toks = _tokens(applies_to)
    return bool(toks & _SCHOOL_AUDIENCE) or looks_like_class(applies_to)


def school_named(texts: list[str | None], school: str | None) -> bool:
    """Whether the notice's own words name this school. Every word of the
    school's name must appear, in order, as a phrase: "Aachi Global" is in
    "Aachi Global School, Circular 12" and not in "a global holiday"."""
    key = " ".join((school or "").split()).casefold()
    if not key:
        return False
    for t in texts:
        flat = " ".join((t or "").split()).casefold()
        if key in flat:
            return True
    return False


def attribute(scopes: list[str | None], children: list[dict],
              texts: list[str | None] | None = None, source_school: str | None = None) -> list[uuid.UUID]:
    """Pure: which children the scopes point at. `children` rows carry id,
    school and class_label, and are already consent-filtered. `texts` is what
    the notice said, as far as the claims quote it. `source_school` is what
    the household has said about where this notice arrived from.

    Four rules, in order: a class named; a school named in the text; the
    school the source belongs to; one school to eliminate to. Each is more
    certain than the next. The source rule is the one that carries a pasted
    "Dear Parents" with nothing else in it: the group it was pasted from was
    the Grade 4 group, and that is the whole answer.
    """
    by_class = [c["id"] for c in children
                if c.get("class_label") and any(class_matches(s, c["class_label"]) for s in scopes)]
    if by_class:
        return list(dict.fromkeys(by_class))
    # A notice addressed to a class nobody is in is somebody else's: a Grade
    # 5 circular when the only child is in Grade 4 does not fall through to
    # the school rules. (Last year's Grade 4 circular, read against last
    # year's class, still matches above.)
    if any(looks_like_class(s) for s in scopes) and any(c.get("class_label") for c in children):
        return []
    if not any(is_school_audience(s) for s in scopes):
        return []
    named = {_school_key(c) for c in children if c.get("school") and school_named(texts or [], c["school"])}
    if len(named) == 1:
        return _at_school(children, next(iter(named)))
    if named:
        # Two schools both named -- a joint notice, or a forwarded chain.
        # Not ours to pick.
        return []
    if source_school:
        at = _at_school(children, " ".join(source_school.split()).casefold())
        if at:
            return at
    schools = {_school_key(c) for c in children if c.get("school")}
    if len(schools) != 1:
        return []
    return _at_school(children, next(iter(schools)))


def _at_school(children: list[dict], school: str) -> list[uuid.UUID]:
    return [c["id"] for c in children if c.get("school") and _school_key(c) == school]


def named_by_word(word: str | None, children: list[dict]) -> list[uuid.UUID] | None:
    """A parent's one word after a forward: a child's name, or a school's.

    "varali" is Varali; "first cry" is everyone at First Cry. None when the
    word names nobody -- then it was not a tag but a message. A word has to
    be short to be a tag at all: a forwarded circular that happens to start
    with a child's name is still a circular.

    `children` rows carry id, display_name and school.
    """
    from familyos.consent import names_match
    text = " ".join((word or "").split())
    if not text or len(text) > 40 or len(text.split()) > 4:
        return None
    by_name = [c["id"] for c in children if names_match(text, c.get("display_name"))]
    if by_name:
        return by_name
    by_school = _at_school(children, text.casefold())
    return by_school or None


def _school_key(child: dict) -> str:
    """"DPS Bangalore" and " dps  bangalore " are one school."""
    return " ".join((child.get("school") or "").split()).casefold()


async def infer(conn: asyncpg.Connection, household_id: uuid.UUID, artifact_id: uuid.UUID,
                scopes: list[str | None], texts: list[str | None] = (),
                channel: str | None = None, source: dict | None = None,
                on: dt.date | None = None) -> list[uuid.UUID]:
    """Work out the subjects, record them as inferred, and return them.

    Replaces only what an earlier read inferred. Called only when no person
    has tagged the notice, so there is never a human row to collide with --
    but the DELETE is scoped to inferred rows regardless, because the caller's
    promise is not the schema's."""
    from familyos import identity, origin
    # Consent as it stands; the class as it stood on the notice's date, so a
    # circular from last term is matched to last term's class.
    consented = {r["id"] for r in await conn.fetch(
        "SELECT m.id FROM members m JOIN consent_records c ON c.subject_member_id = m.id "
        "WHERE m.household_id = $1 AND m.role = 'child' AND c.purpose = $2 AND c.withdrawn_at IS NULL "
        "FOR SHARE OF c", household_id, HOUSEHOLD_RECORDS)}
    children = [r for r in await conn.fetch(identity.CLASS_AS_OF, household_id, on or dt.date.today()) if r["id"] in consented]
    source_school = await origin.school_for(conn, household_id, origin.source_key(channel, source))
    found = attribute(scopes, [dict(r) for r in children], list(texts), source_school)
    await conn.execute("DELETE FROM artifact_subjects WHERE artifact_id = $1 AND inferred", artifact_id)
    if found:
        await conn.executemany(
            "INSERT INTO artifact_subjects (artifact_id, member_id, inferred) VALUES ($1, $2, TRUE)",
            [(artifact_id, m) for m in found])
        from familyos import artifacts
        await artifacts.share_for_children(conn, household_id, artifact_id, via="inferred")
    return found
