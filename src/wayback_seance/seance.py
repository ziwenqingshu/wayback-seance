"""Run the séance: one chapter at a time, every sentence checked as it arrives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .evidence import Evidence
from .grounding import FAINT, GROUNDED, UNVERIFIED, Sentence, check_stream
from .llm import Backend, Stats
from .prompts import CHAPTERS, Chapter, build_messages, split_relics


@dataclass
class ChapterTestimony:
    chapter: Chapter
    relic_ids: list[str]
    sentences: list[Sentence] = field(default_factory=list)


@dataclass
class Testimony:
    evidence: Evidence
    lang: str
    model: str
    chapters: list[ChapterTestimony] = field(default_factory=list)
    stats: Stats = field(default_factory=Stats)

    @property
    def sentences(self) -> list[Sentence]:
        return [s for ch in self.chapters for s in ch.sentences]

    def count(self, verdict: str) -> int:
        return sum(1 for s in self.sentences if s.verdict == verdict)

    def to_dict(self) -> dict:
        ev = self.evidence
        return {
            "target": ev.target,
            "lang": self.lang,
            "model": self.model,
            "facts": {
                "first_seen": ev.facts.first_seen,
                "last_seen": ev.facts.last_seen,
                "last_alive": ev.facts.last_alive,
                "captures": ev.facts.captures,
                "busiest_year": ev.facts.busiest_year,
                "moved_since": ev.facts.moved_since,
                "redirect_target": ev.facts.redirect_target,
                "activity": {str(k): v for k, v in ev.facts.activity.items()},
            },
            "relics": [
                {"id": r.id, "date": r.date, "url": r.link, "title": r.page.title, "excerpt": r.page.excerpt(300)}
                for r in ev.relics
            ],
            "chapters": [
                {
                    "key": ch.chapter.key,
                    "relics": ch.relic_ids,
                    "sentences": [
                        {
                            "text": s.text,
                            "cites": s.cites,
                            "verdict": s.verdict,
                            "reasons": s.reasons,
                            "support": s.support,
                        }
                        for s in ch.sentences
                    ],
                }
                for ch in self.chapters
            ],
            "verdicts": {v: self.count(v) for v in (GROUNDED, FAINT, UNVERIFIED)},
            "stats": vars(self.stats),
        }


def hold_seance(
    evidence: Evidence,
    backend: Backend,
    *,
    lang: str = "en",
    temperature: float = 0.5,
    seed: int = 1031,
    model_name: str | None = None,
    on_chapter: Callable[[ChapterTestimony], None] | None = None,
    on_sentence: Callable[[Sentence], None] | None = None,
) -> Testimony:
    if not evidence.relics:
        raise ValueError("no snapshots could be summoned, so the ghost has nothing to remember")
    testimony = Testimony(evidence=evidence, lang=lang, model=model_name or getattr(backend, "model", backend.name))
    groups = split_relics(evidence.relics)
    for i, chapter in enumerate(CHAPTERS):
        relics = groups[chapter.key]
        ct = ChapterTestimony(chapter=chapter, relic_ids=[r.id for r in relics])
        testimony.chapters.append(ct)
        if on_chapter:
            on_chapter(ct)
        messages = build_messages(evidence, chapter, relics, lang)
        chunks = backend.stream(
            messages, max_tokens=90 * chapter.sentences + 60, temperature=temperature, seed=seed + i
        )
        for sentence in check_stream(chunks, evidence, allowed=ct.relic_ids, chinese=lang == "zh"):
            ct.sentences.append(sentence)
            if on_sentence:
                on_sentence(sentence)
    testimony.stats = backend.stats
    return testimony
