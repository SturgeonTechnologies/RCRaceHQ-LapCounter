import hashlib
import json

from lapcounter import cloud, db, eventsync
from lapcounter.config import Config
from lapcounter.web import create_app
from lapcounter.web.auth import reset_throttle

from .conftest import csrf_of, do_setup
from .test_cloud import PAIRED
from .test_eventsync import pack

LINK = {k: PAIRED.get(k) for k in cloud.LINK_FIELDS}


def make(tmp_path, *, linked=True, sync=None):
    reset_throttle()
    cfg = Config(db_path=str(tmp_path / "lc.db"), decoder_url="tcp://127.0.0.1:1",
                 rc4_dir=str(tmp_path / "rc4"), cloud_dir=str(tmp_path / "cloud"))
    app = create_app(cfg, testing=True)
    conn = db.open_db(cfg.db_path)
    if linked:
        db.set_setting(conn, cloud.LINK_KEY, json.dumps(LINK))
    conn.close()
    if sync is not None:
        app.extensions["event_sync"] = sync
    client = app.test_client()
    do_setup(client)
    client.cfg = cfg
    return client


def store(conn, p):
    body = json.dumps(p)
    db.store_event_pack(conn, p, hashlib.sha256(body.encode()).hexdigest(), body)


def fake_sync(conn, link):
    store(conn, pack())
    return eventsync.Result(1, 1, 0, {"clubName": "Riley's Radical RC Racing", "trackName": "Riley's Place"})


def test_needs_admin(tmp_path):
    client = make(tmp_path)
    client.post("/logout", data={"csrf": csrf_of(client)})
    for path in ("/events", "/events/ev1"):
        r = client.get(path)
        assert r.status_code == 302 and "/login" in r.headers["Location"], path


def test_not_linked(tmp_path):
    client = make(tmp_path, linked=False)
    page = client.get("/events").data.decode()
    assert "isn't linked" in page and "/settings" in page
    r = client.post("/events/download", data={"csrf": csrf_of(client)})
    assert "linked" in r.headers["Location"]


def test_download_and_show(tmp_path):
    client = make(tmp_path, sync=fake_sync)
    assert b"Download events from RC Race HQ" in client.get("/events").data
    r = client.post("/events/download", data={"csrf": csrf_of(client)}, follow_redirects=True)
    page = r.data.decode()
    assert "Downloaded 1 event (1 new or changed)." in page and "Test Race" in page
    assert "Transponders to learn" in page

    page = client.get("/events/ev1").data.decode()
    assert "Qualifier 1" in page and "Racers in this class: Kid, Riley, Sam" in page
    assert "not learned" in page and "B6 (2WD Buggy)" in page
    assert "label=8954097" in page and "racer_name=Riley" in page
    assert client.get("/events/nope").status_code == 404


def test_heat_shows_its_picked_racers_in_grid_order(tmp_path):
    def sync(conn, link):
        p = pack()
        p["heats"][0]["entries"] = [{"registrationId": "r3", "grid": 1}, {"registrationId": "r1", "grid": 2}]
        store(conn, p)
        return eventsync.Result(1, 1, 0, {})
    client = make(tmp_path, sync=sync)
    client.post("/events/download", data={"csrf": csrf_of(client)})
    page = client.get("/events/ev1").data.decode()
    assert "(2 on the grid)" in page and "Racers in this class" not in page
    heat = page[page.index('<ol class="grid">'):]
    heat = heat[:heat.index("</ol>")]
    assert heat.index("Sam") < heat.index("Riley") and "Kid" not in heat
    assert "7340166" in heat


def test_download_error_is_shown(tmp_path):
    def boom(conn, link):
        raise cloud.CloudError("RC Race HQ didn't answer the download request within 25 s.")
    client = make(tmp_path, sync=boom)
    r = client.post("/events/download", data={"csrf": csrf_of(client)}, follow_redirects=True)
    assert b"didn&#39;t answer" in r.data


def test_download_needs_csrf(tmp_path):
    client = make(tmp_path, sync=fake_sync)
    assert client.post("/events/download", data={}).status_code in (400, 403)


def test_transponders_page_lists_to_learn_and_prefills(tmp_path):
    client = make(tmp_path)
    conn = db.open_db(client.cfg.db_path)
    store(conn, pack())
    conn.close()
    page = client.get("/transponders").data.decode()
    assert "Transponders to learn" in page and "Kid" in page
    page = client.get("/transponders?label=8954097&racer_name=Riley").data.decode()
    assert 'value="8954097"' in page and 'value="Riley"' in page
