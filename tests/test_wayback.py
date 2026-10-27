import json

import pytest

from wayback_seance.wayback import (
    Capture,
    FixtureTransport,
    RecordingTransport,
    Response,
    UrllibTransport,
    Wayback,
    WaybackError,
    normalize_target,
    parse_cdx,
    pick_evenly,
    yearly_activity,
)


class DictTransport:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, *, follow_redirects=True):
        self.calls.append((url, follow_redirects))
        for key, resp in self.routes.items():
            if key in url and (follow_redirects or isinstance(resp, Response)):
                return resp if isinstance(resp, Response) else Response(200, resp)
        return Response(404, b"")


CDX = json.dumps(
    [
        ["timestamp", "original", "statuscode", "mimetype", "digest"],
        ["20050101000000", "http://ex.com/", "200", "text/html", "B"],
        ["19990101000000", "http://ex.com/", "200", "text/html", "A"],
        ["20100101000000", "http://ex.com/", "301", "text/html", "C"],
        ["20110101000000", "http://ex.com/", "-", "warc/revisit", "C"],
        ["20120101000000", "http://ex.com/", "404", "text/html", "D"],
        ["garbage"],
    ]
)


def test_parse_cdx_sorts_and_skips_bad_rows():
    caps = parse_cdx(CDX)
    assert [c.year for c in caps] == [1999, 2005, 2010, 2011, 2012]
    assert caps[0].date == "1999-01-01"
    assert caps[0].is_page and caps[2].is_redirect and caps[3].is_revisit
    assert caps[0].raw_url == "https://web.archive.org/web/19990101000000id_/http://ex.com/"
    assert caps[0].view_url == "https://web.archive.org/web/19990101000000/http://ex.com/"
    assert parse_cdx(b"") == [] and parse_cdx("[]") == []
    with pytest.raises(WaybackError):
        parse_cdx("<html>busy</html>")


def test_normalize_target():
    assert normalize_target(" https://www.google.com/reader/ ") == "www.google.com/reader"
    assert normalize_target("del.icio.us") == "del.icio.us"
    with pytest.raises(WaybackError):
        normalize_target("  ")


def test_yearly_activity():
    act = yearly_activity(parse_cdx(CDX))
    assert act[1999]["alive"] == 1 and act[2010]["moved"] == 1
    assert act[2011]["unchanged"] == 1 and act[2012]["gone"] == 1


def cap(ts, digest):
    return Capture(ts, "http://ex.com/", "200", "text/html", digest)


def test_pick_evenly_keeps_ends_and_skips_duplicate_digests():
    caps = [cap(f"{y}0101000000", f"D{y}") for y in range(2000, 2011)]
    caps.insert(1, cap("20000201000000", "D2000"))  # same content as the first
    chosen = pick_evenly(caps, 3)
    assert [c.year for c in chosen] == [2000, 2005, 2010]
    assert pick_evenly(caps, 1) == [caps[0]]
    assert pick_evenly(caps, 0) == [] and pick_evenly([], 3) == []
    assert len(pick_evenly(caps[:3], 5)) == 2


def test_wayback_client_cdx_fetch_cache_and_redirect(tmp_path):
    transport = DictTransport(
        {
            "cdx/search": CDX.encode(),
            "19990101000000id_": b"<title>Hi</title>",
            "20100101000000id_": Response(
                302, b"", {"Location": "https://web.archive.org/web/20100101000001/http://new.example/"}
            ),
        }
    )
    wb = Wayback(transport, cache_dir=tmp_path)
    caps = wb.captures("http://ex.com/")
    assert "collapse=timestamp%3A6" in transport.calls[0][0]
    assert wb.fetch(caps[0]) == b"<title>Hi</title>"
    assert wb.fetch(caps[0]) == b"<title>Hi</title>"  # from cache
    assert sum("19990101000000id_" in u for u, _ in transport.calls) == 1
    assert wb.redirect_target(caps[2]) == "http://new.example/"
    with pytest.raises(WaybackError):
        wb.fetch(caps[1])  # 404 in the dict transport


def test_redirect_target_edge_cases():
    class Boom:
        def get(self, url, *, follow_redirects=True):
            raise WaybackError("down")

    c = cap("20100101000000", "X")
    assert Wayback(Boom()).redirect_target(c) is None
    assert Wayback(DictTransport({"id_": Response(200, b"")})).redirect_target(c) is None
    odd = DictTransport({"id_": Response(301, b"", {"location": "/somewhere"})})
    assert Wayback(odd).redirect_target(c) == "/somewhere"


def test_cdx_http_error():
    with pytest.raises(WaybackError):
        Wayback(DictTransport({})).captures("ex.com")


def test_record_then_replay(tmp_path):
    inner = DictTransport({"a": Response(200, "caf\xe9 ☃".encode(), {"Content-Type": "text/html", "X-Junk": "1"})})
    rec = RecordingTransport(inner, tmp_path / "rec")
    rec.get("https://x/a")
    replay = FixtureTransport(tmp_path / "rec")
    resp = replay.get("https://x/a")
    assert resp.body == "caf\xe9 ☃".encode() and resp.header("content-type") == "text/html"
    assert resp.header("x-junk") == ""
    with pytest.raises(WaybackError):
        replay.get("https://x/b")
    with pytest.raises(WaybackError):
        FixtureTransport(tmp_path / "missing")


def test_urllib_transport_against_local_server(http_server, monkeypatch):
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    t = UrllibTransport(timeout=5, retries=2, backoff=0)
    assert t.get(http_server + "/ok").body == b"fine"
    assert t.get(http_server + "/moved", follow_redirects=False).status == 302
    assert t.get(http_server + "/moved").body == b"fine"
    assert t.get(http_server + "/missing").status == 404
    with pytest.raises(WaybackError):
        t.get(http_server + "/teapot")
    with pytest.raises(WaybackError):
        t.get(http_server + "/flaky")
    with pytest.raises(WaybackError):
        UrllibTransport(timeout=1, retries=1, backoff=0).get("http://127.0.0.1:9/")


def test_fetch_decompresses_gzip_and_deflate():
    import gzip
    import zlib

    c = cap("19990101000000", "A")
    gz = DictTransport({"id_": Response(200, gzip.compress(b"<p>hello</p>"))})
    assert Wayback(gz).fetch(c) == b"<p>hello</p>"
    fl = DictTransport({"id_": Response(200, zlib.compress(b"<p>hi</p>"), {"Content-Encoding": "deflate"})})
    assert Wayback(fl).fetch(c) == b"<p>hi</p>"
    bad = DictTransport({"id_": Response(200, b"\x1f\x8bnot really", {})})
    assert Wayback(bad).fetch(c) == b"\x1f\x8bnot really"
    bad2 = DictTransport({"id_": Response(200, b"plain", {"Content-Encoding": "deflate"})})
    assert Wayback(bad2).fetch(c) == b"plain"


def test_fixture_plain_text_body(tmp_path):
    from wayback_seance.wayback import _fixture_name

    d = tmp_path / "fx"
    d.mkdir()
    (d / _fixture_name("u", True)).write_text(json.dumps({"status": 200, "body": "hi"}))
    assert FixtureTransport(d).get("u").body == b"hi"
