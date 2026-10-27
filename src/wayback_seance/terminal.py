"""The séance as it happens in your terminal."""

from __future__ import annotations

import re
import shutil
import sys
import textwrap
import time
import unicodedata
from typing import TextIO

from .evidence import Evidence, Relic
from .grounding import FAINT, GROUNDED, UNVERIFIED, Sentence
from .prompts import CHAPTERS
from .seance import ChapterTestimony, Testimony
from .wayback import Capture

ROMAN = ["I", "II", "III", "IV", "V", "VI"]

TEXT = {
    "en": {
        "calling": "calling {site} back from the Internet Archive",
        "summon": "summoning",
        "relic": "relic",
        "lost": "lost to the dark",
        "remembers": "The archive remembers {site} from {first} to {last} ({n} monthly captures).",
        "busiest": "It was visited most in {year}.",
        "moved": "From {year} its address mostly answered with redirects{target}.",
        "medium": "Every sentence is checked against the snapshot it cites before you see it.",
        "silenced": "the medium silences it",
        "faint": "faint",
        "close": "The candles burn down. {g} of {t} sentences were grounded, {f} faint, {u} silenced.",
        "ofrenda": "Ofrenda laid at {path}",
    },
    "zh": {
        "calling": "正从互联网档案馆召回 {site}",
        "summon": "召唤",
        "relic": "遗物",
        "lost": "已散入黑暗",
        "remembers": "档案馆记得 {site}：从 {first} 到 {last}（共 {n} 个月份快照）。",
        "busiest": "它在 {year} 年被拜访得最勤。",
        "moved": "从 {year} 年起，这个地址大多只回应重定向{target}。",
        "medium": "灵媒会在你看到每句话之前，先把它与所引用的快照逐一核对。",
        "silenced": "灵媒让它噤声",
        "faint": "微弱",
        "close": "烛火燃尽。{t} 句证词中 {g} 句有据可查，{f} 句微弱，{u} 句被噤声。",
        "ofrenda": "祭坛已供奉于 {path}",
    },
}


def _cols(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _wrap_wide(text: str, width: int, indent: str) -> list[str]:
    """Wrap mixed Chinese/English by display columns, without splitting English words."""
    lines: list[str] = []
    line, used = "", 0
    for token in re.findall(r"[A-Za-z0-9'’.,:;!?&@/+_-]+|\s+|.", text):
        size = sum(_cols(c) for c in token)
        if token.isspace():
            if line:
                line, used = line + " ", used + 1
            continue
        if used + size > width and line:
            lines.append(indent + line.rstrip())
            line, used = "", 0
        line, used = line + token, used + size
    if line or not lines:
        lines.append(indent + line.rstrip())
    return lines


class Renderer:
    def __init__(
        self,
        out: TextIO | None = None,
        *,
        color: bool | None = None,
        pace: float = 0.0,
        lang: str = "en",
        strict: bool = False,
        width: int | None = None,
    ) -> None:
        self.out = out or sys.stdout
        self.color = self.out.isatty() if color is None else color
        self.pace = pace
        self.lang = lang if lang in TEXT else "en"
        self.t = TEXT[self.lang]
        self.strict = strict
        self.width = min(width or shutil.get_terminal_size((88, 24)).columns, 96)
        self._dates: dict[str, str] = {}

    # -- helpers -------------------------------------------------------
    def _c(self, code: str, text: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if self.color else text

    def marigold(self, s: str) -> str:
        return self._c("38;5;214", s)

    def bone(self, s: str) -> str:
        return self._c("38;5;230", s)

    def dim(self, s: str) -> str:
        return self._c("2", s)

    def violet(self, s: str) -> str:
        return self._c("38;5;141", s)

    def blood(self, s: str) -> str:
        return self._c("38;5;167", s)

    def write(self, s: str = "") -> None:
        self.out.write(s + "\n")
        self.out.flush()

    def type_out(self, s: str, style) -> None:
        if self.pace <= 0:
            self.out.write(style(s))
            return
        for ch in s:
            self.out.write(style(ch))
            self.out.flush()
            time.sleep(self.pace)

    def wrap(self, s: str, indent: str = "   ") -> list[str]:
        if self.lang == "zh":
            return _wrap_wide(s, self.width - len(indent) - 2, indent)
        return textwrap.wrap(s, self.width - len(indent), initial_indent=indent, subsequent_indent=indent) or [indent]

    # -- the ritual ----------------------------------------------------
    def opening(self, site: str) -> None:
        title = "W A Y B A C K   S É A N C E" if self.lang == "en" else "网 页 招 魂"
        flames = self.marigold("  ı  ı  ı ")
        self.write()
        self.write(flames + self.bone(f"  {title}  ") + flames)
        self.write(self.dim("   " + self.t["calling"].format(site=site) + " …"))
        self.write()

    def fetching(self, capture: Capture) -> None:
        if self.color:
            self.out.write(self.dim(f"\r   {self.t['summon']} {capture.date} …") + "\x1b[K")
            self.out.flush()

    def relic(self, relic: Relic) -> None:
        self._dates[relic.id] = relic.date
        title = relic.page.title or relic.page.excerpt(60) or "(untitled)"
        if len(title) > self.width - 30:
            title = title[: self.width - 31] + "…"
        prefix = "\r" if self.color else ""
        line = f"{prefix}   {self.marigold('✿')} {self.dim(relic.date)}  {self.bone(title)}"
        self.write(line + (self._c("0", "\x1b[K") if self.color else "") + "  " + self.violet(relic.id))

    def skip(self, capture: Capture, why: str) -> None:
        prefix = "\r" if self.color else ""
        self.write(
            prefix + self.dim(f"   ✝ {capture.date}  {self.t['lost']} ({why})") + ("\x1b[K" if self.color else "")
        )

    def facts(self, evidence: Evidence) -> None:
        f = evidence.facts
        self.write()
        self.write(
            "   "
            + self.dim(self.t["remembers"].format(site=f.target, first=f.first_seen, last=f.last_seen, n=f.captures))
        )
        if f.busiest_year:
            self.write("   " + self.dim(self.t["busiest"].format(year=f.busiest_year)))
        if f.moved_since:
            target = f" → {f.redirect_target}" if f.redirect_target else ""
            self.write("   " + self.dim(self.t["moved"].format(year=f.moved_since, target=target)))
        self.write("   " + self.dim(self.t["medium"]))

    def chapter(self, ct: ChapterTestimony) -> None:
        number = ROMAN[[c.key for c in CHAPTERS].index(ct.chapter.key)]
        label = f" {number} · {ct.chapter.title(self.lang)} "
        rule = "─" * max(4, self.width - len(label) - 8)
        self.write()
        self.write("   " + self.marigold("──" + label + rule))

    def sentence(self, s: Sentence) -> None:
        cite = " ".join(f"{c}·{self._dates.get(c, '?')}" for c in s.cites)
        if s.verdict == GROUNDED:
            self._spoken(s.text, self.bone, cite)
        elif s.verdict == FAINT:
            self._spoken(s.text, lambda x: self._c("3;38;5;250", x), cite, note=self.t["faint"])
        else:
            if self.strict:
                self.write(self.blood(f"   ✝ … {self.t['silenced']}: {'; '.join(s.reasons) or '?'}"))
                return
            lines = self.wrap(s.text, "   ✝ ")
            for line in lines:
                self.write(self._c("9;38;5;167", line) if self.color else line.replace("   ✝ ", "   ✝ ~", 1))
            self.write(self.blood(f"       {self.t['silenced']}: {'; '.join(s.reasons) or '?'}"))

    def _spoken(self, text: str, style, cite: str, note: str | None = None) -> None:
        lines = self.wrap(text)
        for i, line in enumerate(lines):
            self.type_out(line, style)
            if i == len(lines) - 1:
                tag = f"  [{cite}]" + (f" ({note})" if note else "")
                self.out.write(self.violet(tag))
            self.out.write("\n")
            self.out.flush()

    def closing(self, testimony: Testimony, ofrenda_path: str | None = None) -> None:
        self.write()
        msg = self.t["close"].format(
            g=testimony.count(GROUNDED),
            t=len(testimony.sentences),
            f=testimony.count(FAINT),
            u=testimony.count(UNVERIFIED),
        )
        self.write("   " + self.marigold("ı ") + self.bone(msg))
        st = testimony.stats
        if st.completion_tokens and st.seconds:
            self.write(self.dim(f"   {testimony.model}: {st.completion_tokens} tokens in {st.seconds:.1f}s"))
        if ofrenda_path:
            self.write("   " + self.dim(self.t["ofrenda"].format(path=ofrenda_path)))
        self.write()
