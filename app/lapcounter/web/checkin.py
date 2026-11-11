"""Walk-up check-in page (lapcounter/checkin.py). Open to anyone on the
hotspot once the Pi is set up; the event note is admin only."""

from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template, request, url_for

from .. import checkin
from .auth import check_csrf, login_required

bp = Blueprint("checkin", __name__)
THROTTLE = checkin.Throttle()


def reset_checkin_throttle() -> None:
    THROTTLE.reset()


def _form(events, *, error=None, phone="", status=200):
    return render_template("checkin.html", events=events, error=error, phone=phone), status


@bp.get("/checkin")
def form():
    from . import get_db
    return _form(checkin.open_events(get_db()))


@bp.post("/checkin")
def submit():
    from . import get_db
    check_csrf()
    conn = get_db()
    events = checkin.open_events(conn)
    if not events:
        return _form(events)
    raw = request.form.get("phone", "")[:40]
    if not THROTTLE.allow(request.remote_addr or "?"):
        return _form(events, phone=raw, status=429,
                     error="Too many tries. Wait a minute, or see the race desk.")
    e164 = checkin.normalize_phone(raw)
    if e164 is None:
        return _form(events, phone=raw, status=400,
                     error="That doesn't look like a phone number. Use the one on your RC Race HQ account.")
    ids = {e["event_id"] for e in events}
    event_id = request.form.get("event_id") or events[0]["event_id"]
    if event_id not in ids:
        event_id = events[0]["event_id"]
    entries = checkin.find_entries(conn, event_id, e164)
    if not entries:
        return _form(events, phone=raw, status=404,
                     error="We couldn't find a registration with that number. "
                           "Check it's the phone on your RC Race HQ account, or see the race desk.")
    checkin.check_in(conn, event_id, entries)
    cfg = current_app.config["LAPCOUNTER"]
    return render_template(
        "checkin_done.html",
        name=checkin.first_name(entries),
        classes=sorted({e["racer_class"] for e in entries}),
        todos=checkin.todos(conn, cfg.rc4_dir, entries),
    )


@bp.post("/checkin/note")
@login_required
def save_note():
    from . import get_db
    check_csrf()
    checkin.set_note(get_db(), request.form.get("note", ""))
    back = request.form.get("event_id")
    return redirect(url_for("events.show", event_id=back) + "#checkin" if back else url_for("checkin.form"))
