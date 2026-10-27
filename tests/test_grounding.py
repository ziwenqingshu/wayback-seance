from wayback_seance.grounding import (
    FAINT,
    GROUNDED,
    UNVERIFIED,
    Segmenter,
    check,
    check_stream,
    parse_citations,
)


def feed_all(text: str, step: int = 1) -> list[str]:
    seg = Segmenter()
    out: list[str] = []
    for i in range(0, len(text), step):
        out += seg.feed(text[i : i + step])
    return out + seg.flush()


def test_parse_citations_variants():
    assert parse_citations("I was born. [S1]") == ("I was born.", ["S1"])
    assert parse_citations("Both [S1, S3] and (S2).")[1] == ["S1", "S3", "S2"]
    assert parse_citations("Joined [S1、2]")[1] == ["S1", "S2"]
    assert parse_citations("**Bold** start [S1]..")[0] == "Bold start."


def test_segmenter_keeps_trailing_citations_char_by_char():
    text = 'I was born offering "Free Home Pages". [S1] Then I grew. [S2, S3]\nI fell silent [S3].'
    assert feed_all(text) == [
        'I was born offering "Free Home Pages". [S1]',
        "Then I grew. [S2, S3]",
        "I fell silent [S3].",
    ]


def test_segmenter_does_not_split_inside_quotes_or_before_lowercase():
    text = "The promise of “multimedia Things!” beckoned. [S1] I said “Yahoo! GeoCities” twice. [S2] e.g. this. [S1]"
    out = feed_all(text, step=3)
    assert out[0].endswith("beckoned. [S1]")
    assert out[1] == "I said “Yahoo! GeoCities” twice. [S2]"


def test_segmenter_chinese():
    assert feed_all("我出生了[S1]。然后我沉默了。[S2]") == ["我出生了[S1]。", "然后我沉默了。[S2]"]


def test_segmenter_waits_for_a_citation_still_arriving():
    seg = Segmenter()
    assert seg.feed("I was born. [S") == []
    assert seg.feed("1] And") == ["I was born. [S1]"]
    assert seg.flush() == ["And"]


def test_segmenter_newline_without_terminator_and_headings():
    seg = Segmenter()
    out = seg.feed("## Birth\n---\nI offered free pages [S1]\nmore")
    assert out == ["I offered free pages [S1]"]


def test_grounded_quote(evidence):
    s = check('I was born offering "Free Home Pages & Free Member Email" to all. [S1]', evidence)
    assert s.verdict == GROUNDED, s.reasons
    assert s.support.startswith("Free Home Pages")


def test_hallucinated_names_are_silenced(evidence):
    s = check("Millions adored my Dancing Baby animation and Hampster Dance. [S1]", evidence)
    assert s.verdict == UNVERIFIED
    assert any("Dancing" in r for r in s.reasons)


def test_missing_and_phantom_citations(evidence):
    assert check("I was a home for everyone.", evidence).reasons == ["no citation"]
    s = check("I offered Free Home Pages. [S9]", evidence)
    assert s.verdict == UNVERIFIED and "never summoned" in s.reasons[0]


def test_fake_quote_and_wrong_year_and_number(evidence):
    assert check('I promised "unlimited storage forever". [S1]', evidence).verdict == UNVERIFIED
    s = check("In 2003 I welcomed Grogg the advice columnist. [S1]", evidence)
    assert s.verdict == UNVERIFIED and "2003" in s.reasons[0]
    s = check("GeoPlus gave you up to 50MB for your site. [S1]", evidence)
    assert s.verdict == UNVERIFIED and "50MB" in s.reasons[0]
    assert check("GeoPlus gave you up to 10MB for your site. [S1]", evidence).verdict == GROUNDED


def test_facts_may_be_repeated(evidence):
    s = check('Now my address leads only to "https://www.yahoo.com/", a redirect to Yahoo. [S3]', evidence)
    assert s.verdict != UNVERIFIED, s.reasons


def test_faint_and_low_coverage(evidence):
    s = check("Grogg kept me company through long and lonely nights of wandering. [S1]", evidence)
    assert s.verdict in (FAINT, UNVERIFIED)
    s = check("I wandered through endless corridors of moonlit sorrow. [S1]", evidence)
    assert s.verdict == UNVERIFIED


def test_only_ghost_words_is_faint(evidence):
    s = check("I remember, I remember. [S1]", evidence)
    assert s.verdict == FAINT


def test_other_chapter_citation_is_faint(evidence):
    s = check('I offered "Free Home Pages & Free Member Email". [S1]', evidence, allowed=["S3"])
    assert s.verdict == FAINT
    assert "another chapter" in s.reasons[0]


def test_chinese_mode(evidence):
    ok = check("我诞生时，承诺“Free Home Pages & Free Member Email”。[S1]", evidence, chinese=True)
    assert ok.verdict == GROUNDED
    lie = check("我因“Dancing Baby”而闻名。[S1]", evidence, chinese=True)
    assert lie.verdict == UNVERIFIED
    vague = check("我曾经很热闹。[S1]", evidence, chinese=True)
    assert vague.verdict == FAINT
    names = check("Yahoo 和 GeoCities 曾属于我。[S2]", evidence, chinese=True)
    assert names.verdict == GROUNDED
    one_name = check("我记得 GeoCities。[S2]", evidence, chinese=True)
    assert one_name.verdict == FAINT
    bad = check("我记得 Geoplanet 和 Tripod。[S2]", evidence, chinese=True)
    assert bad.verdict == UNVERIFIED


def test_check_stream(evidence):
    chunks = ['I offered "Free Home', ' Pages". [S1] ', "Dancing Baby GIFs made Netscape famous. [S1]", " ## End:"]
    out = list(check_stream(chunks, evidence, allowed=["S1"]))
    assert [s.verdict for s in out] == [GROUNDED, UNVERIFIED]


def test_short_quotes_forgive_plurals_but_need_one_line(evidence):
    s = check('I offered "Free Member Emails" to all who came. [S1]', evidence)
    assert s.verdict == GROUNDED, s.reasons
    s = check('I offered "Grogg Email" to all who came. [S1]', evidence)  # words from two different lines
    assert s.verdict == UNVERIFIED


def test_translated_quote_is_not_held_to_verbatim(evidence):
    s = check("我记得自己最初叫做“欢迎来到GeoCities主页”。[S1]", evidence, chinese=True)
    assert s.verdict != UNVERIFIED, s.reasons
    s = check("我记得“欢迎来到Tripod主页”。[S1]", evidence, chinese=True)
    assert s.verdict == UNVERIFIED
