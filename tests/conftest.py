from __future__ import annotations

from pathlib import Path

import pytest

from wayback_seance.evidence import Evidence, Facts, Relic
from wayback_seance.extract import extract
from wayback_seance.wayback import Capture

FIXTURES = Path(__file__).parent / "fixtures"

PAGES = {
    "19961022173245": """<html><head><title>Welcome to GeoCities Home Page</title></head><body>
        <h1>Free Home Pages &amp; Free Member Email</h1>
        <p>Is modern society getting you down? Come meet Grogg, the Internet's only Neanderthal advice columnist.</p>
        <p>Introducing GeoPlus! Use up to 10MB for your site.</p></body></html>""",
    "20040507000000": """<html><head><title>Yahoo! GeoCities - Your Home on the Web</title>
        <meta name="description" content="Get a free web site with easy-to-use site building tools."></head>
        <body><p>Everything you need to create a personal web site, including your own domain name.</p>
        <p>Find visitors who share your interests in the Member Pages Directory.</p></body></html>""",
    "20090801000000": """<html><head><title>GeoCities is closing</title></head><body>
        <p>GeoCities is closing on October 26, 2009.</p><p>Save your files before your site disappears.</p></body></html>""",
}


def make_evidence() -> Evidence:
    relics = []
    for i, (ts, html) in enumerate(PAGES.items(), 1):
        cap = Capture(ts, "http://www.geocities.com/", "200", "text/html", f"D{i}")
        relics.append(Relic(id=f"S{i}", capture=cap, page=extract(html)))
    facts = Facts(
        target="geocities.com",
        first_seen="1996-10-22",
        last_seen="2026-10-01",
        last_alive="2009-08-01",
        captures=42,
        activity={
            1996: {"alive": 2, "moved": 0, "gone": 0, "unchanged": 0},
            2009: {"alive": 3, "moved": 1, "gone": 0, "unchanged": 0},
            2020: {"alive": 0, "moved": 4, "gone": 1, "unchanged": 2},
        },
        busiest_year=2009,
        moved_since=2020,
        redirect_target="https://www.yahoo.com/",
    )
    return Evidence(target="geocities.com", relics=relics, facts=facts)


@pytest.fixture
def evidence() -> Evidence:
    return make_evidence()


import http.server  # noqa: E402
import json as _json  # noqa: E402
import threading  # noqa: E402


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body=b"", headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        routes = {
            "/ok": (200, b"fine", {}),
            "/moved": (302, b"", {"Location": "/ok"}),
            "/missing": (404, b"nope", {}),
            "/teapot": (418, b"", {}),
            "/flaky": (503, b"", {}),
            "/v1/models": (200, b'{"data":[]}', {}),
        }
        code, body, headers = routes.get(self.path, (404, b"", {}))
        self._send(code, body, headers)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        req = _json.loads(self.rfile.read(length))
        if self.path == "/broken/chat/completions":
            return self._send(500, b"model exploded")
        self.server.requests.append(req)
        events = [
            {"choices": [{"delta": {"role": "assistant"}}]},
            {"choices": [{"delta": {"content": "I was "}}]},
            "not json",
            {"choices": [{"delta": {"content": "born. [S1]"}}]},
            {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 5}},
        ]
        body = b": keep-alive\n\n"
        for ev in events:
            payload = ev if isinstance(ev, str) else _json.dumps(ev)
            body += f"data: {payload}\n\n".encode()
        body += b"data: [DONE]\n\n"
        self._send(200, body, {"Content-Type": "text/event-stream"})


@pytest.fixture
def http_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
