import io
import json

from wayback_seance.grounding import GROUNDED, UNVERIFIED
from wayback_seance.llm import FakeModel
from wayback_seance.ofrenda import render
from wayback_seance.prompts import CHAPTERS, build_messages, split_relics
from wayback_seance.seance import hold_seance
from wayback_seance.terminal import Renderer


def test_split_relics_shapes(evidence):
    relics = evidence.relics
    small = split_relics(relics)
    assert small["birth"] == relics[:1] and small["last"] == relics[-1:]
    many = relics * 3  # nine items
    groups = split_relics(many)
    assert groups["birth"] == many[:2] and groups["last"] == many[-1:]
    assert groups["glory"] and groups["decline"]
    assert split_relics([])["birth"] == []
    four = split_relics(relics + relics[:1])
    assert four["glory"] == four["decline"]


def test_prompts_carry_rules_facts_and_relics(evidence):
    msgs = build_messages(evidence, CHAPTERS[0], evidence.relics[:1])
    assert "[S2]" in msgs[0]["content"] and "geocities.com" in msgs[0]["content"]
    assert "[S1] 1996-10-22" in msgs[1]["content"] and "redirect" not in msgs[1]["content"]
    zh = build_messages(evidence, CHAPTERS[3], evidence.relics[-1:], "zh")
    assert "你是网站" in zh[0]["content"] and "遗言" in zh[1]["content"] and "yahoo" in zh[1]["content"]


def test_hold_seance_with_fake_model(evidence):
    seen = []
    t = hold_seance(evidence, FakeModel(), on_sentence=seen.append, on_chapter=lambda c: None)
    assert [c.chapter.key for c in t.chapters] == ["birth", "glory", "decline", "last"]
    assert seen == t.sentences
    assert t.count(GROUNDED) >= 4
    assert t.count(UNVERIFIED) == 4  # the fake's Dancing Baby lie, once per chapter
    d = t.to_dict()
    assert d["verdicts"]["unverified"] == 4 and d["relics"][0]["id"] == "S1"
    json.dumps(d)


def test_hold_seance_needs_relics(evidence):
    evidence.relics = []
    try:
        hold_seance(evidence, FakeModel())
    except ValueError as exc:
        assert "nothing to remember" in str(exc)
    else:  # pragma: no cover
        raise AssertionError


def test_ofrenda_html(evidence):
    t = hold_seance(evidence, FakeModel())
    t.evidence.relics[0].page.title = "<script>alert(1)</script>"
    page = render(t)
    assert page.startswith("<!doctype html>")
    assert "<script>alert" not in page and "&lt;script&gt;" in page
    assert 'class="s unverified"' in page and "Dancing Baby" in page
    assert "https://web.archive.org/web/19961022173245/" in page
    assert "<svg" in page and "now leads to" in page
    strict = render(t, strict=True)
    assert strict.count('class="s unverified"') == 4  # only in the "could not verify" list
    t.lang = "zh"
    assert "谨以此祭坛" in render(t)
    t.evidence.facts.activity = {}
    t.evidence.facts.redirect_target = None
    assert "<svg" not in render(t)


def test_terminal_renderer_plain_and_color(evidence):
    for color, strict, lang in [(False, False, "en"), (True, True, "zh"), (True, False, "en")]:
        buf = io.StringIO()
        ui = Renderer(buf, color=color, pace=0, lang=lang, strict=strict, width=70)
        ui.opening("geocities.com")
        for r in evidence.relics:
            ui.fetching(r.capture)
            ui.relic(r)
        ui.skip(evidence.relics[0].capture, "empty")
        ui.facts(evidence)
        t = hold_seance(evidence, FakeModel(), lang=lang, on_chapter=ui.chapter, on_sentence=ui.sentence)
        t.stats.seconds = 1.5
        ui.closing(t, "x.html")
        out = buf.getvalue()
        assert "geocities.com" in out and "x.html" in out
        if color:
            assert "\x1b[" in out
        else:
            assert "\x1b[" not in out and "✝ ~" in out
        if lang == "zh":
            assert "噤声" in out


def test_terminal_typing_pace(evidence, monkeypatch):
    import wayback_seance.terminal as term

    monkeypatch.setattr(term.time, "sleep", lambda s: None)
    buf = io.StringIO()
    ui = Renderer(buf, color=False, pace=0.01, width=60)
    ui.relic(evidence.relics[0])
    hold_seance(evidence, FakeModel(), on_sentence=ui.sentence)
    assert "S1·1996-10-22" in buf.getvalue()


def test_wide_wrap_keeps_english_words_whole():
    from wayback_seance.terminal import _wrap_wide

    lines = _wrap_wide("我曾承诺提供“Your free home page is waiting”，也曾尝试连接彼此。", 20, "  ")
    assert all(len(line) <= 24 for line in lines)
    assert (
        "".join(line.strip() for line in lines).replace(" ", "")
        == "我曾承诺提供“Yourfreehomepageiswaiting”，也曾尝试连接彼此。"
    )
    assert _wrap_wide("", 10, "> ") == ["> "]
