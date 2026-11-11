"""Walk-up check-in on the hotspot (docs/checkin.md).

A racer at the track opens the Pi's page, types their phone number and is
marked as here for the event this Pi has checked out. They see only their
first name, their classes and a short to-do list (bring the car to the
learning table, staff's own note). Nothing else from the registration.

The Pi never holds phone numbers. RC Race HQ puts per-event tags in the pack
(lapCounterPacks.checkinPhoneTag): sha256("rchq-checkin:<eventId>:<E.164>"),
first 32 hex chars, for the racer's and the purchaser's account phones. The
typed number is normalized and hashed the same way here.

The hotspot is open, so anyone on it can type any number. Attempts are
throttled per client address and overall; a match shows a first name and
classes, nothing more.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import deque
from pathlib import Path

from . import db, eventsync, outbox

NOTE_KEY = "checkin.note"
MAX_NOTE = 300
TAG_LEN = 32


def normalize_phone(raw: str) -> str | None:
    """E.164 the way RC Race HQ stores it (backend lib/phone.ts normalizePhone).
    Bare 10 digits (or 1 + 10) are US/Canada; "+" means already international."""
    text = (raw or "").strip()
    if not text or re.search(r"[a-z]", text, re.I):
        return None
    digits = re.sub(r"\D", "", text)
    if text.startswith("+"):
        return f"+{digits}" if 8 <= len(digits) <= 15 else None
    national = digits[1:] if len(digits) == 11 and digits.startswith("1") else digits
    if len(national) != 10 or national[0] in "01":
        return None
    return f"+1{national}"


def phone_tag(event_id: str, e164: str) -> str:
    return hashlib.sha256(f"rchq-checkin:{event_id}:{e164}".encode()).hexdigest()[:TAG_LEN]


def open_events(conn) -> list[dict]:
    """Events checked out on this Pi (race day), soonest first."""
    rows = conn.execute(
        "SELECT p.event_id, p.title, p.date_iso FROM event_checkout c"
        " JOIN event_pack p ON p.event_id = c.event_id ORDER BY p.date_iso, p.title"
    ).fetchall()
    return [dict(r) for r in rows]


def find_entries(conn, event_id: str, e164: str) -> list[dict]:
    """Every registration in the event whose racer or purchaser has this phone."""
    tag = phone_tag(event_id, e164)
    rows = conn.execute(
        "SELECT * FROM event_entry WHERE event_id = ? AND phone_tags IS NOT NULL"
        " AND (' ' || phone_tags || ' ') LIKE ?",
        (event_id, f"% {tag} %"),
    ).fetchall()
    return [dict(r) for r in rows]


def check_in(conn, event_id: str, entries: list[dict], at_ms: int | None = None) -> int:
    """Mark entries as here and queue entry.checkin for RC Race HQ. Returns how
    many were new; checking in twice changes nothing."""
    at = at_ms or db.now_ms()
    new = 0
    for e in entries:
        cur = conn.execute(
            "INSERT OR IGNORE INTO entry_checkin (event_id, registration_id, checked_in_at_ms)"
            " VALUES (?, ?, ?)", (event_id, e["registration_id"], at))
        if cur.rowcount == 1:
            new += 1
            outbox.add(conn, "entry.checkin", event_id,
                       {"registrationId": e["registration_id"], "atMs": at},
                       f"checkin:{event_id}:{e['registration_id']}", at)
    return new


def checked_in(conn, event_id: str) -> dict[str, int]:
    """registration_id -> checked_in_at_ms for the event."""
    return {r["registration_id"]: r["checked_in_at_ms"] for r in conn.execute(
        "SELECT registration_id, checked_in_at_ms FROM entry_checkin WHERE event_id = ?", (event_id,))}


def note(conn) -> str:
    return db.get_setting(conn, NOTE_KEY) or ""


def set_note(conn, text: str) -> str:
    clean = " ".join((text or "").split())[:MAX_NOTE]
    db.set_setting(conn, NOTE_KEY, clean)
    return clean


def first_name(entries: list[dict]) -> str:
    for e in entries:
        name = (e.get("first_name") or "").strip() or (e.get("racer_name") or "").strip().split(" ")[0]
        if name:
            return name
    return ""


def todos(conn, rc4_dir: str | Path, entries: list[dict]) -> list[str]:
    """What this racer still needs to do, in plain words."""
    known = eventsync.known_transponders(conn, rc4_dir)
    out: list[str] = []
    for e in entries:
        number = (e.get("transponder") or "").strip()
        car = e.get("vehicle") or f"{e['racer_class']} car"
        if not number:
            out.append(f"Bring your {car} and its transponder to the learning table. "
                       "We don't have a transponder number for you yet.")
        elif number not in known:
            out.append(f"Bring your {car} (transponder {number}) to the learning table.")
    staff = note(conn)
    if staff:
        out.append(staff)
    return out


class Throttle:
    """Sliding-window limit per client and overall, in memory (one gunicorn
    worker on the Pi). Stops someone on the open hotspot walking through
    phone numbers."""

    def __init__(self, per_client: int = 6, overall: int = 60, window_s: float = 60.0,
                 clock=time.monotonic):
        self.per_client, self.overall, self.window_s, self.clock = per_client, overall, window_s, clock
        self._by_client: dict[str, deque] = {}
        self._all: deque = deque()
        self._lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = self.clock()
        with self._lock:
            cutoff = now - self.window_s
            for q in (self._all, *self._by_client.values()):
                while q and q[0] < cutoff:
                    q.popleft()
            self._by_client = {k: q for k, q in self._by_client.items() if q}
            mine = self._by_client.setdefault(client, deque())
            if len(mine) >= self.per_client or len(self._all) >= self.overall:
                return False
            mine.append(now)
            self._all.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._by_client.clear()
            self._all.clear()
