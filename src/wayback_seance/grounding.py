"""The medium's post-check: hold every sentence the ghost speaks up to the snapshots.

A small model is a fluent liar. Asked to "speak as the ghost of GeoCities" with
no evidence, Gemma happily remembers dancing babies that no snapshot we fetched
ever mentions. So every sentence must carry a citation like ``[S3]`` and survive
these checks against the text of the snapshot it cites:

* the cited snapshot exists,
* every quoted phrase really appears in it,
* every year and number appears in it (or in the CDX facts),
* names it drops (capitalised words, or Latin words in Chinese mode) appear in it,
* and enough of its content words come from it.

Sentences end up ``grounded``, ``faint`` (partly supported) or ``unverified``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from .evidence import Evidence, Relic

GROUNDED, FAINT, UNVERIFIED = "grounded", "faint", "unverified"

_CITE = re.compile(r"[\[(（【]\s*(S\d+(?:\s*[,;，、/&]\s*S?\d+)*)\s*[\])）】]")
_TERMINATORS = ".!?。！？"
_CJK_TERMINATORS = "。！？"
_CLOSERS = "\"'”’」』)）*"
_QUOTE = re.compile(r"\"([^\"]{2,200})\"|“([^”]{2,200})”|「([^」]{2,200})」|『([^』]{2,200})』")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’&+.-]*[A-Za-z0-9+]|[A-Za-z0-9]")
_YEAR = re.compile(r"(?<!\d)(19[89]\d|20[0-3]\d)(?!\d)")
_NUMBER = re.compile(
    r"(?<![\w.])\d[\d,.]*\d(?:\s?(?:mb|gb|kb|k|m|%))?|(?<![\w.])\d+\s?(?:mb|gb|kb|%)|(?<![\w.])\d{2,}", re.I
)
_CJK = re.compile(r"[\u3400-\u9fff]")

STOPWORDS = set(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "than",
        "so",
        "to",
        "of",
        "in",
        "on",
        "at",
        "by",
        "for",
        "from",
        "with",
        "without",
        "into",
        "onto",
        "over",
        "under",
        "up",
        "down",
        "out",
        "off",
        "about",
        "as",
        "is",
        "am",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "done",
        "not",
        "no",
        "nor",
        "it",
        "its",
        "it's",
        "this",
        "that",
        "these",
        "those",
        "there",
        "here",
        "their",
        "them",
        "they",
        "he",
        "she",
        "his",
        "her",
        "we",
        "us",
        "our",
        "you",
        "your",
        "i",
        "me",
        "my",
        "mine",
        "myself",
        "who",
        "whom",
        "whose",
        "which",
        "what",
        "when",
        "where",
        "why",
        "how",
        "all",
        "any",
        "each",
        "every",
        "some",
        "such",
        "very",
        "just",
        "also",
        "only",
        "still",
        "even",
        "ever",
        "never",
        "more",
        "most",
        "much",
        "many",
        "few",
        "less",
        "least",
        "own",
        "same",
        "other",
        "can",
        "could",
        "would",
        "should",
        "will",
        "shall",
        "may",
        "might",
        "must",
        "one",
        "ones",
        "while",
        "until",
        "again",
        "once",
        "now",
        "then",
        "like",
        "yet",
        "too",
    ]
)
# words a ghost uses about itself; they prove nothing about the snapshot
GHOST_WORDS = set(
    [
        "ghost",
        "spirit",
        "séance",
        "seance",
        "haunt",
        "haunted",
        "haunting",
        "remember",
        "remembered",
        "remembering",
        "memory",
        "memories",
        "recall",
        "recalled",
        "whisper",
        "whispered",
        "whispers",
        "echo",
        "echoes",
        "linger",
        "lingered",
        "lingering",
        "fade",
        "faded",
        "fading",
        "dust",
        "dusty",
        "silent",
        "silence",
        "quiet",
        "forgotten",
        "forget",
        "forgot",
        "dead",
        "death",
        "die",
        "died",
        "dying",
        "life",
        "lived",
        "living",
        "alive",
        "born",
        "birth",
        "glory",
        "decline",
        "last",
        "words",
        "final",
        "farewell",
        "goodbye",
        "time",
        "times",
        "day",
        "days",
        "year",
        "years",
        "once",
        "long",
        "ago",
        "age",
        "era",
        "now",
        "then",
        "site",
        "website",
        "webpage",
        "web",
        "page",
        "pages",
        "internet",
        "online",
        "visitor",
        "visitors",
        "people",
        "users",
        "world",
        "everyone",
        "anyone",
        "someone",
        "something",
        "thing",
        "things",
        "place",
        "became",
        "become",
        "began",
        "begin",
        "felt",
        "feel",
        "tell",
        "told",
        "say",
        "said",
        "speak",
        "spoke",
        "voice",
        "heart",
        "soul",
        "shadow",
        "shadows",
        "light",
        "candle",
        "candles",
        "grave",
        "offered",
        "offer",
        "offering",
        "called",
        "name",
        "named",
        "promise",
        "promised",
        "still",
    ]
)


@dataclass
class Sentence:
    raw: str
    text: str
    cites: list[str]
    verdict: str = UNVERIFIED
    reasons: list[str] = field(default_factory=list)
    support: str = ""  # the snapshot line that backs it up best
    coverage: float = 0.0

    @property
    def ok(self) -> bool:
        return self.verdict == GROUNDED


def _stem(word: str) -> str:
    """A deliberately crude stemmer: "Themes", "theme" and "themed" all become "them"."""
    w = word.lower().replace("’", "'").strip("'.-&+")
    if w.endswith("'s"):
        w = w[:-2]
    if len(w) > 4 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    for suffix in ("ing", "ed", "ly"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            w = w[: -len(suffix)]
            break
    if len(w) > 4 and w.endswith("e"):
        w = w[:-1]
    return w


def _norm(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[^\w\u3400-\u9fff']+", " ", text).strip()


def parse_citations(text: str) -> tuple[str, list[str]]:
    """Return the sentence without its citation tags, and the cited ids (S1, S2…)."""
    cites: list[str] = []
    for group in _CITE.findall(text):
        for part in re.split(r"[,;，、/&]", group):
            part = part.strip().upper()
            if part and not part.startswith("S"):
                part = "S" + part
            if part and part not in cites:
                cites.append(part)
    clean = _CITE.sub("", text)
    clean = re.sub(r"\s+([,.;:!?。，！？])", r"\1", clean)
    clean = re.sub(r"\*\*|__|^[\s>*#-]+", "", clean)
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    clean = re.sub(r"([.!?。！？])[.。]$", r"\1", clean)
    return clean, cites


class Segmenter:
    """Cuts a streamed token flow into sentences, keeping trailing citations attached."""

    def __init__(self) -> None:
        self.buffer = ""

    def feed(self, delta: str) -> list[str]:
        self.buffer += delta
        out, self.buffer = _cut(self.buffer, final=False)
        return out

    def flush(self) -> list[str]:
        out, self.buffer = _cut(self.buffer, final=True)
        return out


def _cut(text: str, *, final: bool) -> tuple[list[str], str]:
    out: list[str] = []
    start = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            piece = text[start:i].strip()
            if piece and _CITE.search(piece):
                out.append(piece)
                start = i + 1
            elif piece and (
                not re.search(r"\w", piece) or piece.startswith("#") or (len(piece) < 40 and piece.endswith(":"))
            ):
                start = i + 1  # a rule or a chapter heading the model echoed back
            i += 1
            continue
        if ch not in _TERMINATORS:
            i += 1
            continue
        j = i + 1
        while j < n and text[j] in _TERMINATORS + _CLOSERS:
            j += 1
        # absorb citation tags (and a stray full stop) that follow the terminator
        absorbed = False
        while True:
            k = j
            while k < n and text[k] in " \t":
                k += 1
            if k >= n:
                break
            m = _CITE.match(text, k)
            if m:
                absorbed = True
                j = m.end()
                while j < n and text[j] in ".。":
                    j += 1
                continue
            if text[k] in "[(（【" and not re.search(r"[\])）】]", text[k:]):
                j = n  # a citation is still arriving
            break
        if j >= n or (not final and text[j:].strip() == ""):
            if final:
                break
            return out, text[start:]
        nxt = text[j]
        after = text[j:].lstrip()
        if not absorbed and (_open_quote(text[start:j]) or (after[:1].islower() and ch not in _CJK_TERMINATORS)):
            i = j  # still inside a quotation, or the sentence carries on in lower case
            continue
        if not absorbed and ch not in _CJK_TERMINATORS and _CJK.match(after[:1] or " "):
            i = j  # an English "?" or "!" quoted inside a Chinese sentence
            continue
        if ch in _CJK_TERMINATORS or nxt.isspace():
            piece = text[start:j].strip()
            if piece:
                out.append(piece)
            start = j
        i = j
    rest = text[start:]
    if final:
        piece = rest.strip()
        if piece and re.search(r"\w", piece):
            out.append(piece)
        return out, ""
    return out, rest


_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def _spelled_date(date: str) -> str:
    """Let the ghost say "October 22, 1996" for a capture dated 1996-10-22."""
    y, m, d = date.split("-")
    return f"{date} {_MONTHS[int(m) - 1]} {int(d)} {y}"


def _open_quote(piece: str) -> bool:
    """True while a quotation opened in ``piece`` has not been closed yet."""
    if piece.count("“") > piece.count("”") or piece.count("「") > piece.count("」"):
        return True
    return piece.count('"') % 2 == 1


def _num_key(num: str) -> str:
    """'1,300' and '1300' are the same number; '4.95' is not '495'."""
    return re.sub(r"[^\d.]", "", num).strip(".")


def _unwrap(text: str) -> str:
    """The ghost sometimes wraps its whole speech in quotation marks; that is voice, not a citation."""
    t = text.strip()
    for left, right in (("“", "”"), ('"', '"'), ("「", "」")):
        if not t.startswith(left):
            continue
        inner = t[len(left) :]
        body = inner.rstrip(".。!?！？ ")
        speech = body[:-1] if body.endswith(right) and body.index(right) == len(body) - 1 else None
        if right not in inner:
            speech = inner  # opened and never closed
        # only the ghost's own first-person voice gets unwrapped; a bare page quote stays a quote
        if speech is not None and re.search(r"\b(I|my|me|mine)\b|我", speech):
            return speech
    return t


def _loose_quote(q_stems: list[str], corpus: str, corpus_stems: set[str]) -> bool:
    """Forgive plurals and small slips: short quotes must sit on one line, long ones mostly match."""
    if not q_stems:
        return False
    if len(q_stems) >= 3:
        return sum(s in corpus_stems for s in q_stems) / len(q_stems) >= 0.8
    return any(all(s in {_stem(w) for w in _WORD.findall(line)} for s in q_stems) for line in corpus.splitlines())


def _content_stems(text: str) -> list[str]:
    stems = []
    for word in _WORD.findall(text):
        low = word.lower()
        if low in STOPWORDS or low in GHOST_WORDS or len(low) < 3 or _YEAR.fullmatch(low):
            continue
        stem = _stem(low)
        if stem in GHOST_WORDS:
            continue
        stems.append(stem)
    return stems


def _anchors(text: str, chinese: bool) -> list[str]:
    """Proper-noun-ish words a reader would take as facts."""
    out = []
    words = list(re.finditer(_WORD, text))
    for idx, m in enumerate(words):
        word = m.group(0)
        low = word.lower()
        if low in STOPWORDS or low in GHOST_WORDS or low.isdigit():
            continue
        if chinese:
            if len(low) >= 2:
                out.append(word)
            continue
        before = text[: m.start()].rstrip()
        sentence_start = idx == 0 or before.endswith(('"', "“", ":", "—", "–", "(", "-"))
        if word[0].isupper() and not sentence_start and low != "i":
            out.append(word)
    return out


def _best_line(relics: Iterable[Relic], stems: set[str]) -> tuple[str, str]:
    best, best_id, best_score = "", "", 0
    for relic in relics:
        for line in [relic.page.title, relic.page.description, *relic.page.lines]:
            if not line:
                continue
            score = len(stems & {_stem(w) for w in _WORD.findall(line)})
            if score > best_score:
                best, best_id, best_score = line, relic.id, score
    return best_id, best


def check(raw: str, evidence: Evidence, *, allowed: Iterable[str] | None = None, chinese: bool = False) -> Sentence:
    """Judge one sentence. ``allowed`` restricts which relic ids this chapter may cite."""
    text, cites = parse_citations(raw)
    sent = Sentence(raw=raw, text=text, cites=cites)
    relics_by_id = evidence.by_id()
    if not cites:
        sent.reasons.append("no citation")
        return sent
    unknown = [c for c in cites if c not in relics_by_id]
    if unknown:
        sent.reasons.append(f"cites {', '.join(unknown)}, which the medium never summoned")
        return sent
    if allowed is not None:
        allowed_set = set(allowed)
        if not any(c in allowed_set for c in cites):
            sent.reasons.append("cites a snapshot from another chapter of its life")
    cited = [relics_by_id[c] for c in cites]
    # the CDX facts are true by construction, so the ghost may repeat them too
    corpus = "\n".join(
        [*(r.searchable for r in cited), *(_spelled_date(r.date) for r in cited), *evidence.facts.lines()]
    )
    corpus_norm = " " + _norm(corpus) + " "
    corpus_stems = {_stem(w) for w in _WORD.findall(corpus)}
    corpus_lower = corpus.lower()

    hard_fail = False
    quotes = [next(g for g in m.groups() if g) for m in _QUOTE.finditer(_unwrap(text))]
    good_quotes = 0
    for q in quotes:
        qn = _norm(q)
        q_stems = [_stem(w) for w in _WORD.findall(q)]
        if not qn or _CJK.search(q):
            continue  # a translated gloss is not a verbatim quote; its Latin names are checked below
        if f" {qn} " in corpus_norm or _loose_quote(q_stems, corpus, corpus_stems):
            good_quotes += 1
        else:
            hard_fail = True
            sent.reasons.append(f'quote "{q}" is not in {"/".join(cites)}')

    allowed_years = {r.year for r in cited} | evidence.facts.years
    for y in _YEAR.findall(text):
        if int(y) not in allowed_years and y not in corpus:
            hard_fail = True
            sent.reasons.append(f"the year {y} does not appear in {'/'.join(cites)}")

    text_wo_years = _YEAR.sub(" ", text)
    corpus_numbers = {_num_key(n) for n in _NUMBER.findall(corpus)}
    for num in _NUMBER.findall(text_wo_years):
        if _num_key(num) not in corpus_numbers and num.lower().strip() not in corpus_lower:
            hard_fail = True
            sent.reasons.append(f"the number {num.strip()} does not appear in {'/'.join(cites)}")

    anchors = _anchors(text, chinese)
    missing = [a for a in anchors if _stem(a) not in corpus_stems and a.lower() not in corpus_lower]
    if missing:
        sent.reasons.append(f"{', '.join(missing[:3])} not found in {'/'.join(cites)}")

    stems = _content_stems(_QUOTE.sub(lambda m: m.group(0), text))
    found = [s for s in stems if s in corpus_stems]
    sent.coverage = len(found) / len(stems) if stems else 0.0
    sent.support = _best_line(cited, set(found))[1]

    if hard_fail:
        sent.verdict = UNVERIFIED
        return sent
    if chinese:
        checkable = good_quotes + len(anchors)
        if checkable == 0:
            sent.verdict = FAINT
            sent.reasons.append("nothing in it can be checked against the snapshot")
        elif len(missing) >= 2 or (missing and good_quotes == 0):
            sent.verdict = UNVERIFIED
        elif good_quotes or len(anchors) >= 2:
            sent.verdict = FAINT if missing else GROUNDED
        else:
            sent.verdict = FAINT
        return sent
    if len(missing) >= 2:
        sent.verdict = UNVERIFIED
    elif not stems:
        sent.verdict = GROUNDED if good_quotes else FAINT
        if not good_quotes:
            sent.reasons.append("says nothing the snapshot could confirm")
    elif (good_quotes and sent.coverage >= 0.3) or sent.coverage >= 0.5:
        sent.verdict = FAINT if missing else GROUNDED
    elif sent.coverage >= 0.25 or good_quotes:
        # a real quotation wrapped in invented embroidery is only partly supported
        sent.verdict = FAINT
        sent.reasons.append(f"only {round(sent.coverage * 100)}% of its words appear in {'/'.join(cites)}")
    else:
        sent.verdict = UNVERIFIED
        sent.reasons.append(f"only {round(sent.coverage * 100)}% of its words appear in {'/'.join(cites)}")
    if sent.verdict == GROUNDED and sent.reasons:
        # e.g. it cites a real snapshot, but one from another chapter of its life
        sent.verdict = FAINT
    return sent


def check_stream(
    chunks: Iterable[str], evidence: Evidence, *, allowed: Iterable[str] | None = None, chinese: bool = False
) -> Iterator[Sentence]:
    """Check sentences as soon as the model finishes each one."""
    seg = Segmenter()
    allowed_list = list(allowed) if allowed is not None else None
    for chunk in chunks:
        for raw in seg.feed(chunk):
            if _is_sentence(raw):
                yield check(raw, evidence, allowed=allowed_list, chinese=chinese)
    for raw in seg.flush():
        if _is_sentence(raw):
            yield check(raw, evidence, allowed=allowed_list, chinese=chinese)


def _is_sentence(raw: str) -> bool:
    text, _ = parse_citations(raw)
    if not re.search(r"\w", text):
        return False
    # chapter headings the model sometimes echoes back ("Birth:", "## Glory")
    return not (len(text) < 40 and text.rstrip().endswith(":"))
