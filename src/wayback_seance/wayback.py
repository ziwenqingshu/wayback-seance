"""A small, polite client for the Internet Archive's Wayback Machine.

Only two endpoints are used:

* the CDX API, which lists every capture of a URL, and
* ``/web/<timestamp>id_/<url>``, which returns a capture's raw bytes exactly as
  the crawler saw them (no Wayback toolbar, no rewritten links).

All network access goes through a :class:`Transport`, so tests can swap in
recorded fixtures and never touch the network.
"""

from __future__ import annotations

import base64
import calendar
import gzip
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from . import __version__

CDX_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
WEB_PREFIX = "https://web.archive.org/web/"
USER_AGENT = f"wayback-seance/{__version__} (+https://github.com/ziwenqingshu/wayback-seance)"
CDX_FIELDS = ("timestamp", "original", "statuscode", "mimetype", "digest")


class WaybackError(RuntimeError):
    """Raised when the archive cannot be reached or returns something unusable."""


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    def header(self, name: str) -> str:
        for key, value in self.headers.items():
            if key.lower() == name.lower():
                return value
        return ""


class Transport(Protocol):
    def get(self, url: str, *, follow_redirects: bool = True) -> Response: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibTransport:
    """Stdlib HTTP with retries and a friendly User-Agent."""

    def __init__(self, *, timeout: float = 45.0, retries: int = 3, backoff: float = 2.0) -> None:
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self._follow = urllib.request.build_opener()
        self._nofollow = urllib.request.build_opener(_NoRedirect)

    def get(self, url: str, *, follow_redirects: bool = True) -> Response:
        opener = self._follow if follow_redirects else self._nofollow
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                with opener.open(request, timeout=self.timeout) as resp:
                    return Response(resp.status, resp.read(), dict(resp.headers.items()))
            except urllib.error.HTTPError as exc:
                if exc.code in (301, 302, 303, 307, 308) or exc.code == 404:
                    return Response(exc.code, exc.read() or b"", dict(exc.headers.items()))
                last_error = exc
                if exc.code not in (429, 500, 502, 503, 504):
                    break
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last_error = exc
            time.sleep(self.backoff * (attempt + 1))
        raise WaybackError(f"could not fetch {url}: {last_error}")


def _fixture_name(url: str, follow_redirects: bool) -> str:
    digest = hashlib.sha1(f"{follow_redirects}:{url}".encode()).hexdigest()[:16]
    return f"{digest}.json"


class RecordingTransport:
    """Wraps another transport and saves every response as a JSON fixture."""

    def __init__(self, inner: Transport, directory: Path) -> None:
        self.inner = inner
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def get(self, url: str, *, follow_redirects: bool = True) -> Response:
        resp = self.inner.get(url, follow_redirects=follow_redirects)
        payload = {
            "url": url,
            "follow_redirects": follow_redirects,
            "status": resp.status,
            "base64": True,
            "headers": {
                k: v for k, v in resp.headers.items() if k.lower() in ("location", "content-type", "content-encoding")
            },
            "body": base64.b64encode(resp.body).decode("ascii"),
        }
        path = self.directory / _fixture_name(url, follow_redirects)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return resp


class FixtureTransport:
    """Replays responses saved by :class:`RecordingTransport`. Never touches the network."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        if not self.directory.is_dir():
            raise WaybackError(f"fixture directory not found: {directory}")

    def get(self, url: str, *, follow_redirects: bool = True) -> Response:
        path = self.directory / _fixture_name(url, follow_redirects)
        if not path.exists():
            raise WaybackError(f"no recorded fixture for {url}")
        data = json.loads(path.read_text(encoding="utf-8"))
        body = base64.b64decode(data["body"]) if data.get("base64") else data["body"].encode("utf-8")
        return Response(int(data["status"]), body, dict(data.get("headers", {})))


@dataclass(frozen=True)
class Capture:
    """One row of the CDX index."""

    timestamp: str
    original: str
    status: str
    mimetype: str
    digest: str

    @property
    def year(self) -> int:
        return int(self.timestamp[:4])

    @property
    def date(self) -> str:
        t = self.timestamp
        return f"{t[:4]}-{t[4:6]}-{t[6:8]}"

    @property
    def is_page(self) -> bool:
        return self.status == "200" and self.mimetype.startswith("text/html")

    @property
    def is_redirect(self) -> bool:
        return self.status.startswith("3")

    @property
    def is_revisit(self) -> bool:
        return self.mimetype == "warc/revisit"

    @property
    def raw_url(self) -> str:
        return f"{WEB_PREFIX}{self.timestamp}id_/{self.original}"

    @property
    def view_url(self) -> str:
        """Human-friendly archive link (with the Wayback toolbar) used for citations."""
        return f"{WEB_PREFIX}{self.timestamp}/{self.original}"


def normalize_target(url: str) -> str:
    """Strip the scheme so CDX matches http and https captures alike."""
    url = url.strip()
    if not url:
        raise WaybackError("empty URL")
    url = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", url)
    return url.rstrip("/") or url


def parse_cdx(payload: bytes | str) -> list[Capture]:
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    text = text.strip()
    if not text:
        return []
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WaybackError(f"CDX answered with something that is not JSON: {text[:80]!r}") from exc
    if not rows:
        return []
    header, *body = rows
    index = {name: header.index(name) for name in CDX_FIELDS if name in header}
    captures = []
    for row in body:
        values = {name: (row[i] if i < len(row) else "") for name, i in index.items()}
        if not re.fullmatch(r"\d{14}", values.get("timestamp", "")):
            continue
        captures.append(
            Capture(
                timestamp=values["timestamp"],
                original=values.get("original", ""),
                status=values.get("statuscode", "-"),
                mimetype=values.get("mimetype", ""),
                digest=values.get("digest", ""),
            )
        )
    captures.sort(key=lambda c: c.timestamp)
    return captures


class Wayback:
    def __init__(self, transport: Transport | None = None, cache_dir: Path | None = None) -> None:
        self.transport = transport or UrllibTransport()
        self.cache_dir = Path(cache_dir) if cache_dir else None

    def captures(self, url: str, *, collapse: str = "timestamp:6") -> list[Capture]:
        """List captures, at most one per month by default (``collapse=timestamp:6``)."""
        query = urllib.parse.urlencode(
            {
                "url": normalize_target(url),
                "output": "json",
                "fl": ",".join(CDX_FIELDS),
                "collapse": collapse,
            }
        )
        resp = self.transport.get(f"{CDX_ENDPOINT}?{query}")
        if resp.status != 200:
            raise WaybackError(f"CDX API returned HTTP {resp.status}")
        return parse_cdx(resp.body)

    def fetch(self, capture: Capture) -> bytes:
        cached = self._cache_path(capture.raw_url)
        if cached and cached.exists():
            return cached.read_bytes()
        resp = self.transport.get(capture.raw_url)
        if resp.status != 200:
            raise WaybackError(f"snapshot {capture.timestamp} returned HTTP {resp.status}")
        body = _decompress(resp.body, resp.header("content-encoding"))
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(body)
        return body

    def redirect_target(self, capture: Capture) -> str | None:
        """Where a redirect capture pointed, as recorded by the archive."""
        try:
            resp = self.transport.get(capture.raw_url, follow_redirects=False)
        except WaybackError:
            return None
        location = resp.header("location")
        if not location:
            return None
        match = re.search(r"/web/\d{14}[a-z_]*/(.+)$", location)
        return match.group(1) if match else location

    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".html")


def _decompress(body: bytes, encoding: str) -> bytes:
    """``id_`` captures are byte-exact, so some still wear their original gzip."""
    if body[:2] == b"\x1f\x8b" or "gzip" in encoding.lower():
        try:
            return gzip.decompress(body)
        except (OSError, EOFError):
            return body
    if "deflate" in encoding.lower():
        try:
            return zlib.decompress(body)
        except zlib.error:
            return body
    return body


def pick_evenly(candidates: list[Capture], count: int) -> list[Capture]:
    """Choose ``count`` captures spread across time, always keeping the first and last.

    Captures whose content digest was already chosen are skipped, so we do not
    summon the same unchanged page twice.
    """
    unique: list[Capture] = []
    seen: set[str] = set()
    for cap in candidates:
        if cap.digest and cap.digest in seen:
            continue
        seen.add(cap.digest)
        unique.append(cap)
    if count <= 0 or not unique:
        return []
    if len(unique) <= count:
        return unique
    if count == 1:
        return [unique[0]]
    start = _seconds(unique[0])
    span = _seconds(unique[-1]) - start or 1
    chosen: list[Capture] = []
    for i in range(count):
        goal = start + span * i / (count - 1)
        best = min((c for c in unique if c not in chosen), key=lambda c: abs(_seconds(c) - goal))
        chosen.append(best)
    return sorted(chosen, key=lambda c: c.timestamp)


def _seconds(capture: Capture) -> float:
    t = capture.timestamp
    return calendar.timegm(
        (int(t[:4]), int(t[4:6]) or 1, int(t[6:8]) or 1, int(t[8:10]), int(t[10:12]), int(t[12:14]), 0, 0, 0)
    )


def yearly_activity(captures: Iterable[Capture]) -> dict[int, dict[str, int]]:
    """Count monthly captures per year, split into alive / moved / gone / unchanged."""
    out: dict[int, dict[str, int]] = {}
    for cap in captures:
        bucket = out.setdefault(cap.year, {"alive": 0, "moved": 0, "gone": 0, "unchanged": 0})
        if cap.is_revisit:
            bucket["unchanged"] += 1
        elif cap.status == "200":
            bucket["alive"] += 1
        elif cap.is_redirect:
            bucket["moved"] += 1
        else:
            bucket["gone"] += 1
    return dict(sorted(out.items()))
