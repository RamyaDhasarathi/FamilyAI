"""The collecting layer's local cache: one SQLite file in `settings.collect_dir`, readable by this machine's owner only.

Not the shared database, on purpose (decided 30 Oct 2026): collected data stays here until it is decided where it goes.
Keyed by the Google account's address, which is how a FamilyOS member is found (members.email). The refresh token is
sealed with the master key (AES-GCM, the address as associated data), so the file alone does not open the mailbox;
the collected items themselves are kept as read, for the agent brain to take later.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from familyos import crypto
from familyos.settings import settings

KINDS = {"gmail": "gmail_messages", "calendar": "calendar_events", "tasks": "google_tasks"}
# What the Android app sends (device.py).
DEVICE = {"sms": "device_sms", "calls": "device_calls", "notifications": "device_notifications",
          "locations": "device_locations", "files": "device_files"}
TABLES = {**KINDS, **DEVICE}
_ORDER = {"gmail": "sent_at DESC", "calendar": "starts ASC", "tasks": "(status = 'completed'), due ASC",
          "sms": "sent_at DESC", "calls": "started_at DESC", "notifications": "posted_at DESC",
          "locations": "fixed_at DESC", "files": "added_at DESC"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS google_accounts (
  email TEXT PRIMARY KEY, refresh_sealed BLOB NOT NULL, scopes TEXT NOT NULL,
  connected_at TEXT NOT NULL, last_run_at TEXT, last_errors TEXT);
CREATE TABLE IF NOT EXISTS gmail_messages (
  email TEXT NOT NULL, id TEXT NOT NULL, thread_id TEXT, sender TEXT, recipients TEXT, subject TEXT, snippet TEXT,
  sent_at TEXT, labels TEXT, fetched_at TEXT NOT NULL, PRIMARY KEY (email, id));
CREATE TABLE IF NOT EXISTS calendar_events (
  email TEXT NOT NULL, id TEXT NOT NULL, summary TEXT, starts TEXT, ends TEXT, all_day INTEGER, location TEXT,
  status TEXT, updated TEXT, fetched_at TEXT NOT NULL, PRIMARY KEY (email, id));
CREATE TABLE IF NOT EXISTS google_tasks (
  email TEXT NOT NULL, id TEXT NOT NULL, list_title TEXT, title TEXT, notes TEXT, due TEXT, status TEXT,
  completed TEXT, updated TEXT, fetched_at TEXT NOT NULL, PRIMARY KEY (email, id));
CREATE TABLE IF NOT EXISTS device_sms (
  email TEXT NOT NULL, id TEXT NOT NULL, sender TEXT, body TEXT, sent_at TEXT, thread_id TEXT,
  fetched_at TEXT NOT NULL, PRIMARY KEY (email, id));
CREATE TABLE IF NOT EXISTS device_calls (
  email TEXT NOT NULL, id TEXT NOT NULL, number TEXT, kind TEXT, started_at TEXT, duration_s INTEGER,
  fetched_at TEXT NOT NULL, PRIMARY KEY (email, id));
CREATE TABLE IF NOT EXISTS device_notifications (
  email TEXT NOT NULL, id TEXT NOT NULL, package TEXT, app_label TEXT, title TEXT, text TEXT, posted_at TEXT,
  fetched_at TEXT NOT NULL, PRIMARY KEY (email, id));
CREATE TABLE IF NOT EXISTS device_locations (
  email TEXT NOT NULL, id TEXT NOT NULL, lat REAL, lon REAL, accuracy REAL, fixed_at TEXT,
  fetched_at TEXT NOT NULL, PRIMARY KEY (email, id));
CREATE TABLE IF NOT EXISTS device_files (
  email TEXT NOT NULL, id TEXT NOT NULL, name TEXT, size INTEGER, mime TEXT, added_at TEXT,
  fetched_at TEXT NOT NULL, PRIMARY KEY (email, id));
CREATE TABLE IF NOT EXISTS device_apps (
  email TEXT NOT NULL, package TEXT NOT NULL, label TEXT, collect INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
  PRIMARY KEY (email, package));
CREATE TABLE IF NOT EXISTS site_accounts (
  email TEXT NOT NULL, service TEXT NOT NULL, username TEXT NOT NULL, host TEXT, added_at TEXT NOT NULL, last_used_at TEXT,
  PRIMARY KEY (email, service));
CREATE TABLE IF NOT EXISTS site_items (
  email TEXT NOT NULL, service TEXT NOT NULL, id TEXT NOT NULL, title TEXT, amount TEXT, status TEXT, happened TEXT,
  fetched_at TEXT NOT NULL, PRIMARY KEY (email, service, id));
CREATE TABLE IF NOT EXISTS app_methods (
  email TEXT NOT NULL, package TEXT NOT NULL, category TEXT, status TEXT NOT NULL, methods TEXT, error TEXT, model TEXT,
  started_at TEXT, analyzed_at TEXT, PRIMARY KEY (email, package));
CREATE TABLE IF NOT EXISTS gmail_attachments (
  email TEXT NOT NULL, message_id TEXT NOT NULL, attachment_id TEXT NOT NULL, filename TEXT, mime TEXT, size INTEGER,
  path TEXT, fetched_at TEXT NOT NULL, PRIMARY KEY (email, message_id, attachment_id));
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL, source TEXT NOT NULL, started_at TEXT NOT NULL,
  finished_at TEXT, counts TEXT, errors TEXT);
"""


# Columns added after a table was first made (30 Oct -> 2 Nov 2026: every SMS field and its code, Qwen's category and
# summary, a place name for a location, a message's full text, every calendar). An existing cache gets them in place.
ADDED = {
    "device_sms": {"date_sent": "TEXT", "type": "INTEGER", "read": "INTEGER", "seen": "INTEGER", "subject": "TEXT",
                   "service_center": "TEXT", "person": "TEXT", "protocol": "INTEGER", "otp": "TEXT", "category": "TEXT",
                   "summary": "TEXT", "extracted": "TEXT", "categorize_tries": "INTEGER NOT NULL DEFAULT 0"},
    "device_notifications": {"category": "TEXT", "summary": "TEXT", "extracted": "TEXT", "otp": "TEXT",
                             "categorize_tries": "INTEGER NOT NULL DEFAULT 0"},
    "device_locations": {"place": "TEXT", "geocode_tries": "INTEGER NOT NULL DEFAULT 0"},
    "gmail_messages": {"cc": "TEXT", "body": "TEXT", "body_html": "TEXT", "attachments": "INTEGER", "otp": "TEXT",
                       "history_id": "TEXT", "size": "INTEGER"},
    "calendar_events": {"calendar_id": "TEXT", "calendar_name": "TEXT", "description": "TEXT", "organizer": "TEXT",
                        "attendees": "TEXT", "html_link": "TEXT", "recurring_event_id": "TEXT", "created": "TEXT"},
    "google_tasks": {"list_id": "TEXT", "parent": "TEXT", "position": "TEXT", "links": "TEXT"},
}


def _add_columns(con: sqlite3.Connection) -> None:
    for table, cols in ADDED.items():
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        for col, kind in cols.items():
            if col not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def path() -> Path:
    folder = Path(os.path.expanduser(settings.collect_dir))
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder / "collect.sqlite3"


def connect() -> sqlite3.Connection:
    p = path()
    con = sqlite3.connect(p)
    os.chmod(p, 0o600)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    _add_columns(con)
    return con


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    """One connection: committed when the block ends well, rolled back otherwise, and closed either way."""
    con = connect()
    try:
        with con:
            yield con
    finally:
        con.close()


def _aad(email: str) -> bytes:
    return b"collect|google|" + email.encode()


def _key(email: str) -> str:
    return (email or "").strip().lower()


# ── The Google account ──────────────────────────────────────────────────────

def keep_google(email: str, refresh_token: str, scopes) -> None:
    """Keep (or replace) the permission given at sign-in. The token is sealed; the scopes say what it may read."""
    email = _key(email)
    nonce = os.urandom(12)
    sealed = nonce + crypto._master().encrypt(nonce, refresh_token.encode(), _aad(email))
    with _db() as con:
        con.execute(
            "INSERT INTO google_accounts (email, refresh_sealed, scopes, connected_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (email) DO UPDATE SET refresh_sealed = excluded.refresh_sealed, scopes = excluded.scopes, "
            "connected_at = excluded.connected_at, last_errors = NULL",
            (email, sealed, json.dumps(list(scopes)), _now()))


def google_account(email: str) -> dict | None:
    with _db() as con:
        row = con.execute("SELECT email, scopes, connected_at, last_run_at, last_errors FROM google_accounts WHERE email = ?",
                          (_key(email),)).fetchone()
    if row is None:
        return None
    return {"email": row["email"], "scopes": json.loads(row["scopes"]), "connected_at": row["connected_at"],
            "last_run_at": row["last_run_at"], "last_errors": json.loads(row["last_errors"] or "{}")}


def google_refresh_token(email: str) -> str | None:
    with _db() as con:
        row = con.execute("SELECT refresh_sealed FROM google_accounts WHERE email = ?", (_key(email),)).fetchone()
    if row is None:
        return None
    sealed = bytes(row["refresh_sealed"])
    return crypto._master().decrypt(sealed[:12], sealed[12:], _aad(_key(email))).decode()


# ── Collected items ─────────────────────────────────────────────────────────

def upsert(kind: str, email: str, rows: list[dict]) -> int:
    """Insert or refresh items by their Google id; returns how many were given."""
    if not rows:
        return 0
    table = TABLES[kind]
    email = _key(email)
    cols = ["email", *rows[0].keys(), "fetched_at"]
    marks = ", ".join("?" for _ in cols)
    update = ", ".join(f"{c} = excluded.{c}" for c in cols if c not in ("email", "id"))
    with _db() as con:
        con.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({marks}) ON CONFLICT (email, id) DO UPDATE SET {update}",
                        [(email, *r.values(), _now()) for r in rows])
    return len(rows)


def items(kind: str, email: str, limit: int = 100) -> list[dict]:
    with _db() as con:
        rows = con.execute(f"SELECT * FROM {TABLES[kind]} WHERE email = ? ORDER BY {_ORDER[kind]} LIMIT ?",
                           (_key(email), limit)).fetchall()
    return [{k: r[k] for k in r.keys() if k != "email"} for r in rows]


def record_run(email: str, source: str, started_at: str, counts: dict, errors: dict) -> None:
    email = _key(email)
    with _db() as con:
        con.execute("INSERT INTO runs (email, source, started_at, finished_at, counts, errors) VALUES (?, ?, ?, ?, ?, ?)",
                    (email, source, started_at, _now(), json.dumps(counts), json.dumps(errors)))
        con.execute("UPDATE google_accounts SET last_run_at = ?, last_errors = ? WHERE email = ?",
                    (_now(), json.dumps(errors), email))


def device_counts(email: str) -> dict[str, int]:
    with _db() as con:
        counts = {kind: con.execute(f"SELECT count(*) FROM {table} WHERE email = ?", (_key(email),)).fetchone()[0]
                  for kind, table in DEVICE.items()}
        counts["apps"] = con.execute("SELECT count(*) FROM device_apps WHERE email = ?", (_key(email),)).fetchone()[0]
        counts["apps_collecting"] = con.execute("SELECT count(*) FROM device_apps WHERE email = ? AND collect = 1", (_key(email),)).fetchone()[0]
    return counts


def set_apps(email: str, apps: list[dict]) -> None:
    """The phone's installed apps with their collect switch, replacing what was kept (an app removed from the phone goes)."""
    email = _key(email)
    with _db() as con:
        con.execute("DELETE FROM device_apps WHERE email = ?", (email,))
        con.executemany("INSERT INTO device_apps (email, package, label, collect, updated_at) VALUES (?, ?, ?, ?, ?)",
                        [(email, a["package"], a.get("label"), int(bool(a.get("collect"))), _now()) for a in apps])


def apps(email: str) -> list[dict]:
    with _db() as con:
        rows = con.execute("SELECT package, label, collect, updated_at FROM device_apps WHERE email = ? ORDER BY lower(label)",
                           (_key(email),)).fetchall()
    return [{"package": r["package"], "label": r["label"], "collect": bool(r["collect"]), "updated_at": r["updated_at"]} for r in rows]


# ── Connected services (vault.py): which site and username only; the password is in the Keychain ────

def set_site_account(email: str, service: str, username: str, host: str) -> None:
    with _db() as con:
        con.execute("INSERT INTO site_accounts (email, service, username, host, added_at) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT (email, service) DO UPDATE SET username = excluded.username, host = excluded.host, added_at = excluded.added_at",
                    (_key(email), service, username, host, _now()))


def site_account(email: str, service: str) -> dict | None:
    with _db() as con:
        r = con.execute("SELECT service, username, host, added_at, last_used_at FROM site_accounts WHERE email = ? AND service = ?",
                        (_key(email), service)).fetchone()
    return dict(r) if r else None


def site_accounts(email: str) -> list[dict]:
    with _db() as con:
        rows = con.execute("SELECT service, username, host, added_at, last_used_at FROM site_accounts WHERE email = ? ORDER BY service",
                           (_key(email),)).fetchall()
    return [dict(r) for r in rows]


def keep_site_items(email: str, service: str, rows: list[dict]) -> int:
    """What the browser agent read on a site (orders, bookings, bills), by the site's own id or a stand-in for it."""
    with _db() as con:
        con.executemany("INSERT INTO site_items (email, service, id, title, amount, status, happened, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT (email, service, id) DO UPDATE SET title = excluded.title, amount = excluded.amount, "
                        "status = excluded.status, happened = excluded.happened, fetched_at = excluded.fetched_at",
                        [(_key(email), service, r["id"], r.get("title"), r.get("amount"), r.get("status"), r.get("happened"), _now())
                         for r in rows])
        con.execute("UPDATE site_accounts SET last_used_at = ? WHERE email = ? AND service = ?", (_now(), _key(email), service))
    return len(rows)


def site_items(email: str, service: str, limit: int = 100) -> list[dict]:
    with _db() as con:
        rows = con.execute("SELECT id, title, amount, status, happened, fetched_at FROM site_items WHERE email = ? AND service = ? "
                           "ORDER BY fetched_at DESC, rowid LIMIT ?", (_key(email), service, limit)).fetchall()
    return [dict(r) for r in rows]


def site_item_count(email: str, service: str) -> int:
    with _db() as con:
        return con.execute("SELECT count(*) FROM site_items WHERE email = ? AND service = ?", (_key(email), service)).fetchone()[0]


def record_site_run(email: str, source: str, started_at: str, counts: dict, errors: dict) -> None:
    """A run that is not Google's (the browser agent): in `runs` only."""
    with _db() as con:
        con.execute("INSERT INTO runs (email, source, started_at, finished_at, counts, errors) VALUES (?, ?, ?, ?, ?, ?)",
                    (_key(email), source, started_at, _now(), json.dumps(counts), json.dumps(errors)))


def last_run(email: str, source: str) -> dict | None:
    with _db() as con:
        r = con.execute("SELECT started_at, finished_at, counts, errors FROM runs WHERE email = ? AND source = ? ORDER BY id DESC LIMIT 1",
                        (_key(email), source)).fetchone()
    return {"started_at": r["started_at"], "finished_at": r["finished_at"], "counts": json.loads(r["counts"] or "{}"),
            "errors": json.loads(r["errors"] or "{}")} if r else None


def remove_site_account(email: str, service: str) -> None:
    with _db() as con:
        con.execute("DELETE FROM site_accounts WHERE email = ? AND service = ?", (_key(email), service))


# ── The decision layer (decide.py): which methods may collect from each app ────────────────

def set_analysis(email: str, package: str, *, category: str, status: str, methods: list | None = None,
                 error: str | None = None, model: str | None = None) -> None:
    pending = status == "pending"
    with _db() as con:
        con.execute("INSERT INTO app_methods (email, package, category, status, methods, error, model, started_at, analyzed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (email, package) DO UPDATE SET category = excluded.category, "
                    "status = excluded.status, methods = excluded.methods, error = excluded.error, model = excluded.model, "
                    "started_at = coalesce(excluded.started_at, app_methods.started_at), "
                    "analyzed_at = coalesce(excluded.analyzed_at, app_methods.analyzed_at)",
                    (_key(email), package, category, status, json.dumps(methods or []), error, model,
                     _now() if pending else None, None if pending else _now()))


def analyses(email: str) -> dict[str, dict]:
    with _db() as con:
        rows = con.execute("SELECT * FROM app_methods WHERE email = ?", (_key(email),)).fetchall()
    return {r["package"]: {"package": r["package"], "category": r["category"], "status": r["status"],
                           "methods": json.loads(r["methods"] or "[]"), "error": r["error"], "model": r["model"],
                           "started_at": r["started_at"], "analyzed_at": r["analyzed_at"]} for r in rows}


def notification_counts(email: str, package: str) -> tuple[int, int]:
    """(from this app, from any app) -- what the phone has actually sent."""
    with _db() as con:
        own = con.execute("SELECT count(*) FROM device_notifications WHERE email = ? AND package = ?", (_key(email), package)).fetchone()[0]
        anyn = con.execute("SELECT count(*) FROM device_notifications WHERE email = ?", (_key(email),)).fetchone()[0]
    return own, anyn


def gmail_senders(email: str) -> list[str]:
    with _db() as con:
        return [r[0] for r in con.execute("SELECT sender FROM gmail_messages WHERE email = ? AND sender IS NOT NULL", (_key(email),))]


# ── Background work on what was kept: Qwen's categories (categorize.py), place names (geocode.py) ───────────

def uncategorized(email: str, kind: str, limit: int, max_tries: int) -> list[dict]:
    table = DEVICE[kind]
    with _db() as con:
        rows = con.execute(f"SELECT * FROM {table} WHERE email = ? AND category IS NULL AND categorize_tries < ? "
                           f"ORDER BY {_ORDER[kind]} LIMIT ?", (_key(email), max_tries, limit)).fetchall()
    return [dict(r) for r in rows]


def set_category(email: str, kind: str, item_id: str, category: str, summary: str | None, extracted: dict | None) -> None:
    with _db() as con:
        con.execute(f"UPDATE {DEVICE[kind]} SET category = ?, summary = ?, extracted = ? WHERE email = ? AND id = ?",
                    (category, summary, json.dumps(extracted) if extracted else None, _key(email), item_id))


def count_try(email: str, kind: str, ids: list[str]) -> None:
    with _db() as con:
        con.executemany(f"UPDATE {DEVICE[kind]} SET categorize_tries = categorize_tries + 1 WHERE email = ? AND id = ?",
                        [(_key(email), i) for i in ids])


def unplaced(email: str, limit: int, max_tries: int) -> list[dict]:
    with _db() as con:
        rows = con.execute("SELECT id, lat, lon FROM device_locations WHERE email = ? AND place IS NULL AND geocode_tries < ? "
                           "AND lat IS NOT NULL ORDER BY fixed_at DESC LIMIT ?", (_key(email), max_tries, limit)).fetchall()
    return [dict(r) for r in rows]


def set_place(email: str, item_id: str, place: str | None) -> None:
    with _db() as con:
        if place:
            con.execute("UPDATE device_locations SET place = ? WHERE email = ? AND id = ?", (place, _key(email), item_id))
        else:
            con.execute("UPDATE device_locations SET geocode_tries = geocode_tries + 1 WHERE email = ? AND id = ?", (_key(email), item_id))


def latest_otp(email: str, since: str) -> dict | None:
    """The newest one-time code that arrived since `since` (ISO), by SMS, notification or mail -- for the browser agent."""
    found = []
    with _db() as con:
        for table, when in (("device_sms", "sent_at"), ("device_notifications", "posted_at"), ("gmail_messages", "sent_at")):
            r = con.execute(f"SELECT otp, {when} AS at FROM {table} WHERE email = ? AND otp IS NOT NULL AND {when} >= ? "
                            f"ORDER BY {when} DESC LIMIT 1", (_key(email), since)).fetchone()
            if r:
                found.append({"otp": r["otp"], "at": r["at"], "source": table})
    return max(found, key=lambda f: f["at"]) if found else None


def gmail_known(email: str, ids: list[str]) -> set[str]:
    """Messages already kept with their full text (not read again)."""
    if not ids:
        return set()
    with _db() as con:
        marks = ",".join("?" for _ in ids)
        return {r[0] for r in con.execute(f"SELECT id FROM gmail_messages WHERE email = ? AND body IS NOT NULL AND id IN ({marks})",
                                          (_key(email), *ids))}


def keep_attachment(email: str, message_id: str, attachment_id: str, filename: str, mime: str, size: int, path: str | None) -> None:
    with _db() as con:
        con.execute("INSERT INTO gmail_attachments (email, message_id, attachment_id, filename, mime, size, path, fetched_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (email, message_id, attachment_id) DO UPDATE SET "
                    "filename = excluded.filename, mime = excluded.mime, size = excluded.size, path = excluded.path",
                    (_key(email), message_id, attachment_id, filename, mime, size, path, _now()))


def attachments(email: str, message_id: str | None = None, limit: int = 200) -> list[dict]:
    with _db() as con:
        if message_id:
            rows = con.execute("SELECT message_id, attachment_id, filename, mime, size, path IS NOT NULL AS saved FROM gmail_attachments "
                               "WHERE email = ? AND message_id = ? LIMIT ?", (_key(email), message_id, limit)).fetchall()
        else:
            rows = con.execute("SELECT message_id, attachment_id, filename, mime, size, path IS NOT NULL AS saved FROM gmail_attachments "
                               "WHERE email = ? ORDER BY fetched_at DESC LIMIT ?", (_key(email), limit)).fetchall()
    return [dict(r) for r in rows]


def attachment_path(email: str, message_id: str, attachment_id: str) -> str | None:
    with _db() as con:
        r = con.execute("SELECT path FROM gmail_attachments WHERE email = ? AND message_id = ? AND attachment_id = ?",
                        (_key(email), message_id, attachment_id)).fetchone()
    return r["path"] if r else None


def status(email: str) -> dict:
    account = google_account(email)
    with _db() as con:
        counts = {kind: con.execute(f"SELECT count(*) FROM {table} WHERE email = ?", (_key(email),)).fetchone()[0]
                  for kind, table in KINDS.items()}
    return {"connected": account is not None, "email": account["email"] if account else None,
            "scopes": account["scopes"] if account else [], "connected_at": account["connected_at"] if account else None,
            "last_run_at": account["last_run_at"] if account else None, "last_errors": account["last_errors"] if account else {},
            "counts": counts}
