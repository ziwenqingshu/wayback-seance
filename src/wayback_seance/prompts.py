"""What the medium says to the model. One prompt per chapter of the site's life."""

from __future__ import annotations

from dataclasses import dataclass

from .evidence import Evidence, Relic


@dataclass(frozen=True)
class Chapter:
    key: str
    title_en: str
    title_zh: str
    ask_en: str
    ask_zh: str
    sentences: int

    def title(self, lang: str) -> str:
        return self.title_zh if lang == "zh" else self.title_en


CHAPTERS = (
    Chapter(
        "birth", "Birth", "诞生",
        "Tell how you came into the world: what your first pages called you and what you offered.",
        "讲述你如何来到这个世界：你最早的页面怎样称呼自己、向来访者提供了什么。",
        3,
    ),
    Chapter(
        "glory", "Glory years", "鼎盛",
        "Tell of your glory years: what you became, what you promised, what filled your pages.",
        "讲述你的鼎盛岁月：你变成了什么、许下了什么承诺、页面上写满了什么。",
        4,
    ),
    Chapter(
        "decline", "Decline", "衰落",
        "Tell how you changed as the end approached: what shrank, what was renamed, what disappeared.",
        "讲述终点临近时你的变化：什么缩水了、什么改了名、什么消失了。",
        3,
    ),
    Chapter(
        "last", "Last words", "遗言",
        "Speak your last words: what your final page said, and where your address leads now.",
        "说出你的遗言：你最后的页面写着什么，你的地址如今通向哪里。",
        2,
    ),
)  # fmt: skip

SYSTEM_EN = """You are the ghost of the website {site}, called up at a séance on the Day of the Dead.
Speak in the first person, as the website itself: wistful, eerie, dignified. No jokes, no emojis, no lists.

You remember ONLY what is written in the RELICS: real snapshots of you kept by the Internet Archive.
Rules:
1. Write exactly {n} sentences of plain prose.
2. End every sentence with the id of the relic it comes from, like [S2].
3. In every sentence, quote a few words exactly as they appear in that relic, inside double quotes.
4. Never invent people, numbers, dates, features or events. If the relics do not say it, you do not remember it.
5. You may use the FACTS, which were counted from the archive and are true.
6. Write years as digits (1996), never in words."""

SYSTEM_ZH = """你是网站 {site} 的幽灵，在亡灵节的招魂仪式上被唤醒。
用第一人称、以这个网站本身的口吻说话：怀旧、幽微、庄重。不开玩笑，不用表情符号，不分条列点。

你只记得“遗物”里写着的东西：互联网档案馆保存下来的你的真实快照。
规则：
1. 用中文写正好 {n} 句话。
2. 每句话末尾标注它出自哪件遗物，例如 [S2]。
3. 每句话都要用双引号原样引用该遗物里的几个英文原词，例如“Free Home Pages”。
4. 绝不编造人物、数字、日期、功能或事件。遗物里没写的，你就不记得。
5. 可以使用“事实”部分，它们是从档案统计出来的，都是真的。
6. 年份一律用阿拉伯数字书写（如 1996）。"""


def split_relics(relics: list[Relic]) -> dict[str, list[Relic]]:
    """Give each chapter the snapshots from its part of the timeline."""
    n = len(relics)
    if n == 0:
        return {c.key: [] for c in CHAPTERS}
    if n <= 3:
        return {"birth": relics[:1], "glory": relics[: min(2, n)], "decline": relics[-2:], "last": relics[-1:]}
    middle = relics[2:-1] or relics[1:-1]
    half = max(1, (len(middle) + 1) // 2)
    glory = middle[:half]
    decline = middle[half:] or middle[-1:]
    return {"birth": relics[:2], "glory": glory, "decline": decline, "last": relics[-1:]}


def build_messages(evidence: Evidence, chapter: Chapter, relics: list[Relic], lang: str = "en") -> list[dict[str, str]]:
    zh = lang == "zh"
    system = (SYSTEM_ZH if zh else SYSTEM_EN).format(site=evidence.target, n=chapter.sentences)
    # The afterlife (redirects, where the address leads now) belongs to the last words;
    # handing it to every chapter made the ghost repeat its own death four times.
    lines = evidence.facts.lines() if chapter.key == "last" else evidence.facts.lines()[:4]
    lines = [ln for ln in lines if chapter.key == "last" or "redirect" not in ln]
    facts = "\n".join(f"- {line}" for line in lines)
    blocks = "\n\n".join(r.prompt_block() for r in relics)
    if zh:
        user = f"章节：{chapter.title_zh}。{chapter.ask_zh}\n\n事实：\n{facts}\n\n遗物：\n{blocks}\n\n现在，用 {chapter.sentences} 句中文说话，每句都带引用。"
    else:
        user = (
            f"CHAPTER: {chapter.title_en}. {chapter.ask_en}\n\nFACTS:\n{facts}\n\nRELICS:\n{blocks}\n\n"
            f"Now speak your {chapter.sentences} sentences, each ending with its citation."
        )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
