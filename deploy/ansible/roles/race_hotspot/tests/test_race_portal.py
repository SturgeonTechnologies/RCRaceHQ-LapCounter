"""Tests for files/race-portal.

Run from deploy/ansible:
    python3 -m pytest roles/race_hotspot/tests -q
"""

import importlib.machinery
import importlib.util
import pathlib
import subprocess
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "files" / "race-portal"


def _load():
    loader = importlib.machinery.SourceFileLoader("race_portal", str(SCRIPT))
    spec = importlib.util.spec_from_loader("race_portal", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["race_portal"] = module  # dataclasses look the module up
    loader.exec_module(module)
    return module


portal = _load()
CFG = portal.Config.from_env({})


# ── config ───────────────────────────────────────────────────────────────

def test_defaults():
    assert CFG.portal_url == "http://race/"
    assert CFG.hostnames == {"race", "race.lan", "10.77.0.1"}
    assert str(CFG.network) == "10.77.0.0/24"


def test_env_overrides():
    cfg = portal.Config.from_env({"PORTAL_GATEWAY": "10.9.0.1", "PORTAL_PREFIX": "16",
                                  "PORTAL_HOSTNAME": "Track", "PORTAL_DOMAIN": "club"})
    assert cfg.portal_url == "http://track/"
    assert "track.club" in cfg.hostnames
    assert str(cfg.network) == "10.9.0.0/16"


# ── host matching ────────────────────────────────────────────────────────

@pytest.mark.parametrize("header,expected", [
    ("race", "race"), ("RACE:80", "race"), ("race.lan.", "race.lan"),
    ("10.77.0.1:80", "10.77.0.1"), ("", ""), (None, ""),
])
def test_request_host(header, expected):
    assert portal.request_host(header) == expected


@pytest.mark.parametrize("header,expected", [
    ("race", "portal"), ("race.lan", "portal"), ("10.77.0.1", "portal"),
    ("captive.apple.com", "redirect"), ("connectivitycheck.gstatic.com", "redirect"),
    ("www.msftconnecttest.com", "redirect"), ("racetrack.com", "redirect"), (None, "redirect"),
])
def test_decide(header, expected):
    assert portal.decide(CFG, header) == expected


# ── who may be let through ───────────────────────────────────────────────

@pytest.mark.parametrize("client,ok", [
    ("10.77.0.50", True), ("10.77.0.254", True),
    ("10.77.0.1", False),       # the Pi itself
    ("10.77.0.0", False), ("10.77.0.255", False),
    ("192.168.0.20", False),    # uplink-side LAN
    ("::1", False), ("garbage", False),
])
def test_client_to_allow(client, ok):
    assert (portal.client_to_allow(CFG, client) is not None) == ok


def test_nft_command_is_an_argv_list():
    addr = portal.client_to_allow(CFG, "10.77.0.50")
    assert portal.nft_add_command(CFG, addr) == [
        "nft", "add", "element", "inet", "race_portal", "allowed",
        "{ 10.77.0.50 timeout 12h }"]


def test_grant_runs_nft():
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    assert portal.grant_access(CFG, "10.77.0.60", run=fake_run)
    assert calls[0][-1] == "{ 10.77.0.60 timeout 12h }"


def test_grant_refuses_outsiders_without_running_nft():
    def fail_run(*_a, **_k):
        raise AssertionError("nft must not run")

    assert not portal.grant_access(CFG, "192.168.0.20", run=fail_run)


def test_grant_reports_nft_failure():
    def bad_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, "", "No such file or directory")

    assert not portal.grant_access(CFG, "10.77.0.60", run=bad_run)


def test_landing_page_escapes_title():
    cfg = portal.Config.from_env({"PORTAL_TITLE": "<b>Club</b>"})
    body = portal.landing_page(cfg, online=True).decode()
    assert "&lt;b&gt;Club&lt;/b&gt;" in body and "<b>Club" not in body


# ── HTTP behaviour end to end (loopback, nft stubbed out) ────────────────

@pytest.fixture()
def server(monkeypatch):
    granted = []
    monkeypatch.setattr(portal, "grant_access", lambda cfg, client: granted.append(client) or True)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), portal.make_handler(CFG))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], granted
    srv.shutdown()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _get(port, host, method="GET"):
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(f"http://127.0.0.1:{port}/hotspot-detect.html",
                                 headers={"Host": host}, method=method)
    try:
        resp = opener.open(req, timeout=5)
    except urllib.error.HTTPError as err:
        resp = err
    return resp.status, resp.headers, resp.read()


def test_probe_is_redirected_to_portal(server):
    port, granted = server
    status, headers, _ = _get(port, "captive.apple.com")
    assert status == 302 and headers["Location"] == "http://race/"
    assert headers["Cache-Control"] == "no-store"
    assert granted == []


def test_visiting_race_grants_and_serves_page(server):
    port, granted = server
    status, headers, body = _get(port, "race")
    assert status == 200 and b"You're connected" in body
    assert headers["Content-Type"].startswith("text/html")
    assert granted == ["127.0.0.1"]


def test_head_has_no_body(server):
    port, _ = server
    status, _, body = _get(port, "race", method="HEAD")
    assert status == 200 and body == b""
