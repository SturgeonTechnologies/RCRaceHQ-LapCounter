"""Download this club's events from RC Race HQ (docs/event-sync.md).

1. `request_events` publishes `{"requestId"}` to `<topicPrefix>/events/get` over
   AWS IoT's HTTPS endpoint (port 8443, the device certificate as client cert).
2. RC Race HQ writes one pack per event to `packs/<thing>/<eventId>.json` in the
   lap counter bucket, then `packs/<thing>/index.json` carrying our requestId.
3. `sync_events` polls the index until it carries our requestId, downloads the
   packs whose sha256 changed, checks each hash and stores them; events that
   are no longer in the index are removed.

S3 is read with short-lived keys from the IoT credentials provider
(cloud.fetch_credentials), signed with sigv4.py. Every network call is
injectable so tests never touch AWS.
"""

from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from . import cloud, db, sigv4
from .cloud import CloudError

SCHEMA = 1
LAST_SYNC_KEY = "events.last_sync"
POLL_INTERVAL_S = 1.5
POLL_TIMEOUT_S = 25.0
MAX_OBJECT_BYTES = 5 * 1024 * 1024
CREDS_REFRESH_S = 5 * 60
HTTP_TIMEOUT_S = 10.0
EVENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


# --- publish (HTTPS to AWS IoT with the device certificate) -------------------

Publish = Callable[[str, bytes, ssl.SSLContext], int]


def https_publish(url: str, body: bytes, context: ssl.SSLContext) -> int:
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S, context=context) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CloudError(f"Can't reach AWS IoT ({getattr(exc, 'reason', exc)}). "
                         "Check the Pi's internet.") from exc


def request_events(link: dict, paths: cloud.Paths, request_id: str,
                   publish: Publish = https_publish) -> None:
    if not (paths.key.exists() and paths.cert.exists()):
        raise CloudError("The key or certificate is missing on this Pi. Link it again.")
    context = ssl.create_default_context()
    context.load_cert_chain(certfile=str(paths.cert), keyfile=str(paths.key))
    topic = quote(f"{link['topicPrefix']}/events/get", safe="/")
    url = f"https://{link['iotEndpoint']}:8443/topics/{topic}?qos=1"
    status = publish(url, json.dumps({"requestId": request_id}).encode(), context)
    if status == 200:
        return
    if status in (401, 403):
        raise CloudError("AWS IoT refused the certificate. It was probably unlinked in "
                         "RC Race HQ; link this Pi again under Settings.")
    raise CloudError(f"AWS IoT answered HTTP {status} to the download request.")


# --- S3 (GET only, SigV4 with credentials-provider keys) ----------------------

HttpGet = Callable[[str, dict], tuple[int, bytes]]


def http_get(url: str, headers: dict) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            return resp.status, resp.read(MAX_OBJECT_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CloudError(f"Can't reach S3 ({getattr(exc, 'reason', exc)}). "
                         "Check the Pi's internet.") from exc


Creds = Callable[[], dict]


class S3:
    """Reads objects from the lap counter bucket with cached short-lived keys."""

    def __init__(self, bucket: str, region: str, creds: Creds, get: HttpGet = http_get,
                 clock: Callable[[], float] = time.time):
        self.bucket, self.region = bucket, region
        self._creds, self._get, self._clock = creds, get, clock
        self._cached: dict | None = None
        self._expires = 0.0

    def _keys(self) -> dict:
        if self._cached is None or self._clock() >= self._expires - CREDS_REFRESH_S:
            creds = self._creds()
            self._cached, self._expires = creds, _epoch(creds.get("expiration"), self._clock())
        return self._cached

    def get(self, key: str) -> bytes | None:
        """Object bytes, or None if it doesn't exist (yet)."""
        keys = self._keys()
        host = f"{self.bucket}.s3.{self.region}.amazonaws.com"
        path = sigv4.canonical_path(key)
        headers = sigv4.sign(
            method="GET", host=host, path=path, region=self.region, service="s3",
            headers={"x-amz-security-token": keys["sessionToken"]},
            access_key=keys["accessKeyId"], secret_key=keys["secretAccessKey"],
            date=sigv4.amz_date(datetime.fromtimestamp(self._clock(), timezone.utc)),
        )
        headers.pop("host")
        status, body = self._get(f"https://{host}{path}", headers)
        if status == 200:
            if len(body) > MAX_OBJECT_BYTES:
                raise CloudError(f"{key} is larger than {MAX_OBJECT_BYTES // 1024} KB; refusing it.")
            return body
        if status == 404:
            return None
        if status == 403:
            self._cached = None  # keys may have expired early; fetch fresh ones next time
            raise CloudError(f"S3 refused {key} (403). Link the Pi again if this keeps happening.")
        raise CloudError(f"S3 answered HTTP {status} for {key}.")


def _epoch(iso: str | None, now: float) -> float:
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return now + 15 * 60


# --- validation --------------------------------------------------------------

def parse_index(raw: bytes, thing: str) -> dict:
    try:
        index = json.loads(raw)
    except ValueError as exc:
        raise CloudError("RC Race HQ's event index isn't valid JSON.") from exc
    if not isinstance(index, dict) or index.get("schema") != SCHEMA:
        raise CloudError(f"RC Race HQ sent event index schema {index.get('schema') if isinstance(index, dict) else '?'};"
                         f" this lap counter understands {SCHEMA}. Update the lap counter app.")
    for ev in index.get("events") or []:
        event_id = ev.get("eventId") if isinstance(ev, dict) else None
        if not isinstance(event_id, str) or not EVENT_ID.match(event_id):
            raise CloudError(f"RC Race HQ listed an event with a bad id: {event_id!r}.")
        if ev.get("packKey") != f"packs/{thing}/{event_id}.json":
            raise CloudError(f"Event {event_id} points outside this lap counter's folder.")
        if not re.fullmatch(r"[0-9a-f]{64}", str(ev.get("packSha256", ""))):
            raise CloudError(f"Event {event_id} has no valid packSha256.")
    return index


def parse_pack(raw: bytes, event_id: str) -> dict:
    try:
        pack = json.loads(raw)
    except ValueError as exc:
        raise CloudError(f"The pack for event {event_id} isn't valid JSON.") from exc
    if not isinstance(pack, dict) or pack.get("schema") != SCHEMA:
        raise CloudError(f"The pack for event {event_id} is schema "
                         f"{pack.get('schema') if isinstance(pack, dict) else '?'}; this lap counter "
                         f"understands {SCHEMA}. Update the lap counter app.")
    if pack.get("eventId") != event_id:
        raise CloudError(f"The pack for event {event_id} is for {pack.get('eventId')!r}.")
    for key in ("classes", "entries", "heats"):
        if not isinstance(pack.get(key, []), list):
            raise CloudError(f"The pack for event {event_id} has a bad {key} list.")
    for e in pack.get("entries", []):
        if not isinstance(e, dict) or not e.get("registrationId"):
            raise CloudError(f"The pack for event {event_id} has an entry with no registrationId.")
        if e.get("transponder") is not None:
            e["transponder"] = str(e["transponder"]).strip() or None
    return pack


# --- the whole download --------------------------------------------------------

@dataclass(frozen=True)
class Result:
    events: int
    updated: int
    removed: int
    lap_counter: dict

    def message(self) -> str:
        n = "event" if self.events == 1 else "events"
        out = f"Downloaded {self.events} {n} ({self.updated} new or changed"
        return out + (f", {self.removed} removed)." if self.removed else ").")


def sync_events(conn, link: dict, paths: cloud.Paths, *, s3: S3 | None = None,
                publish: Publish = https_publish, sleep: Callable[[float], None] = time.sleep,
                clock: Callable[[], float] = time.monotonic,
                request_id: str | None = None) -> Result:
    thing = link["thingName"]
    s3 = s3 or S3(link["bucket"], link["region"], lambda: cloud.fetch_credentials(link, paths))
    request_id = request_id or uuid.uuid4().hex
    request_events(link, paths, request_id, publish)

    index_key = f"packs/{thing}/index.json"
    deadline = clock() + POLL_TIMEOUT_S
    while True:
        raw = s3.get(index_key)
        if raw is not None:
            index = parse_index(raw, thing)
            if index.get("requestId") == request_id:
                break
        if clock() >= deadline:
            raise CloudError("RC Race HQ didn't answer the download request within "
                             f"{int(POLL_TIMEOUT_S)} s. Try again; if it keeps happening the "
                             "event download isn't deployed on RC Race HQ yet.")
        sleep(POLL_INTERVAL_S)

    if index.get("error"):
        raise CloudError(f"RC Race HQ: {index['error']}")

    have = db.event_hashes(conn)
    listed = index.get("events") or []
    updated = 0
    for ev in listed:
        event_id, want = ev["eventId"], ev["packSha256"]
        if have.get(event_id) == want:
            continue
        body = s3.get(ev["packKey"])
        if body is None:
            raise CloudError(f"The pack for {ev.get('title') or event_id} is missing in S3.")
        got = hashlib.sha256(body).hexdigest()
        if got != want:
            raise CloudError(f"The pack for {ev.get('title') or event_id} didn't match its "
                             "checksum (changed while downloading?). Try again.")
        pack = parse_pack(body, event_id)
        db.store_event_pack(conn, pack, got, body.decode())
        updated += 1
    removed = db.delete_events_except(conn, {ev["eventId"] for ev in listed})

    lap_counter = index.get("lapCounter") if isinstance(index.get("lapCounter"), dict) else {}
    db.set_setting(conn, LAST_SYNC_KEY, json.dumps({
        "at_ms": db.now_ms(), "events": len(listed), "lapCounter": lap_counter,
        "generatedAt": index.get("generatedAt"),
    }))
    return Result(len(listed), updated, removed, lap_counter)


def last_sync(conn) -> dict | None:
    raw = db.get_setting(conn, LAST_SYNC_KEY)
    return json.loads(raw) if raw else None


# --- transponders to learn ----------------------------------------------------

def known_transponders(conn, rc4_dir: str | Path) -> set[str]:
    """Numbers this Pi can time: recorded in the list, or with a learned .rc4 file."""
    from .learning import learned_numbers
    numbers = {t["number"] for t in db.list_transponders(conn)} | learned_numbers(rc4_dir)
    return {str(n) for n in numbers}


def to_learn(conn, rc4_dir: str | Path, event_id: str | None = None) -> list[dict]:
    """Entries whose transponder is missing or not recorded on this Pi.

    Each row gets `reason` ("none" | "not_recorded") and `learnable` (the
    number can be pre-filled into Learn).
    """
    known = known_transponders(conn, rc4_dir)
    out = []
    for e in db.list_event_entries(conn, event_id):
        number = e["transponder"]
        if number and number in known:
            continue
        e["reason"] = "none" if not number else "not_recorded"
        e["learnable"] = bool(number and number.isdigit())
        out.append(e)
    return out
