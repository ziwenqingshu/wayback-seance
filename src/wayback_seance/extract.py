"""Turn a raw archived HTML page into the words a visitor would actually have read."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

_SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "object"}
_BLOCK = {
    "p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "table", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "header", "footer", "nav", "blockquote", "center", "font", "dd", "dt", "form",
    "option", "hr", "title", "body",
}  # fmt: skip
_HEADINGS = {"h1", "h2", "h3"}


@dataclass
class Page:
    title: str = ""
    description: str = ""
    headings: list[str] = field(default_factory=list)
    text: str = ""
    lines: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        if len(self.text) < 30 and not self.title and not self.description:
            return True
        # compressed or binary bodies decode to a soup of control and Latin-1 symbols
        sample = self.title + self.text[:2000]
        noise = sum(
            1 for ch in sample if ch == "\ufffd" or 0x80 <= ord(ch) < 0x100 or not (ch.isprintable() or ch.isspace())
        )
        return noise > len(sample) * 0.12

    def excerpt(self, limit: int = 650) -> str:
        """The most sentence-like lines first, trimmed to ``limit`` characters."""
        prose = [ln for ln in self.lines if len(ln.split()) >= 4]
        picked: list[str] = []
        size = 0
        for line in prose or self.lines:
            if line in picked:
                continue
            if size + len(line) > limit:
                if not picked:
                    picked.append(line[:limit].rsplit(" ", 1)[0] + "…")
                break
            picked.append(line)
            size += len(line) + 1
        return " / ".join(picked)


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page = Page()
        self._skip_depth = 0
        self._in_title = False
        self._heading: list[str] | None = None
        self._buf: list[str] = []
        self._lines: list[str] = []
        self._title: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attr = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            name = (attr.get("name") or attr.get("property") or "").lower()
            if name in ("description", "og:description", "twitter:description") and not self.page.description:
                self.page.description = _clean(attr.get("content", ""))
            elif name == "og:title" and not self._title:
                self._title.append(attr.get("content", ""))
            return
        if tag == "title":
            self._in_title = True
            return
        if tag in _SKIP:
            self._skip_depth += 1
            return
        if tag == "img" and attr.get("alt") and not self._skip_depth:
            self._buf.append(f" {attr['alt']} ")
        if tag in _BLOCK:
            self._flush()
        if tag in _HEADINGS:
            self._heading = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
            return
        if tag in _SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag in _HEADINGS and self._heading is not None:
            heading = _clean("".join(self._heading))
            if heading:
                self.page.headings.append(heading)
            self._heading = None
        if tag in _BLOCK:
            self._flush()

    def handle_data(self, data):
        if self._in_title:
            self._title.append(data)
            return
        if self._skip_depth:
            return
        self._buf.append(data)
        if self._heading is not None:
            self._heading.append(data)

    def _flush(self):
        line = _clean("".join(self._buf))
        self._buf = []
        if line and re.search(r"\w", line):
            self._lines.append(line)

    def finish(self) -> Page:
        self._flush()
        self.page.title = _clean("".join(self._title))
        # old portals repeat their nav bars; keep the first occurrence only
        seen: set[str] = set()
        lines = []
        for ln in self._lines:
            key = ln.lower()
            if key not in seen:
                seen.add(key)
                lines.append(ln)
        self.page.lines = lines
        self.page.text = "\n".join(lines)
        return self.page


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip(" |-·•»\u00a0\t")


def decode_html(raw: bytes) -> str:
    """Decode bytes using the page's own declared charset, falling back to cp1252."""
    head = raw[:4096].decode("ascii", errors="ignore")
    match = re.search(r"""charset\s*=\s*["']?([A-Za-z0-9_.:-]+)""", head, re.I)
    candidates = [match.group(1)] if match else []
    candidates += ["utf-8", "cp1252"]
    for enc in candidates:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("latin-1")  # pragma: no cover - latin-1 never fails


def extract(raw: bytes | str) -> Page:
    markup = decode_html(raw) if isinstance(raw, bytes) else raw
    parser = _Extractor()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:  # pragma: no cover - html.parser is very forgiving
        pass
    return parser.finish()
