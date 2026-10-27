import json

import pytest

from wayback_seance.evidence import Facts, _moved_since, gather
from wayback_seance.wayback import Response, Wayback, WaybackError

from .test_wayback import DictTransport


def rows(*items):
    return json.dumps([["timestamp", "original", "statuscode", "mimetype", "digest"], *items]).encode()


def site(years_alive, years_moved, empty=()):
    items = [[f"{y}0101000000", "http://ex.com/", "200", "text/html", f"D{y}"] for y in years_alive]
    items += [[f"{y}0101000000", "http://ex.com/", "301", "text/html", f"R{y}"] for y in years_moved]
    routes = {"cdx/search": rows(*items)}
    for y in years_alive:
        body = b"" if y in empty else f"<title>Ex {y}</title><p>Welcome to the {y} edition of Ex.</p>".encode()
        routes[f"{y}0101000000id_"] = body
    for y in years_moved:
        routes[f"{y}0101000000id_"] = Response(
            301, b"", {"Location": f"https://web.archive.org/web/{y}0101000001/https://new.ex/"}
        )
    return DictTransport(routes)


def test_gather_spreads_relics_and_computes_facts():
    t = site(range(2000, 2010), range(2010, 2015))
    events = {"fetch": 0, "relic": [], "skip": 0}
    ev = gather(
        "https://ex.com/",
        Wayback(t),
        count=4,
        on_fetch=lambda c: events.__setitem__("fetch", events["fetch"] + 1),
        on_relic=events["relic"].append,
        on_skip=lambda c, why: None,
    )
    assert [r.id for r in ev.relics] == ["S1", "S2", "S3", "S4"]
    assert [r.year for r in ev.relics] == [2000, 2003, 2006, 2009]
    assert events["fetch"] == 4 and len(events["relic"]) == 4
    f = ev.facts
    assert (f.first_seen, f.last_alive, f.last_seen) == ("2000-01-01", "2009-01-01", "2014-01-01")
    assert any("readable words" in line for line in f.lines())
    assert f.moved_since == 2010 and f.redirect_target == "https://new.ex/"
    assert any("redirects" in line for line in f.lines()) and 2010 in f.years
    assert ev.by_id()["S2"].prompt_block().startswith('[S2] 2003-01-01\ntitle: "Ex 2003"')


def test_gather_fills_gaps_when_snapshots_are_hollow():
    t = site(range(2000, 2016), [], empty={2015, 2014, 2013})
    skipped = []
    ev = gather("ex.com", Wayback(t), count=4, on_skip=lambda c, why: skipped.append(c.year))
    assert len(ev.relics) == 4
    assert 2015 in skipped
    assert all(r.year < 2013 for r in ev.relics)
    assert ev.skipped and ev.facts.redirect_target is None


def test_gather_survives_fetch_errors_and_reports_empty_archive():
    t = site([2001, 2002], [])
    t.routes["20020101000000id_"] = Response(503, b"")
    ev = gather("ex.com", Wayback(t), count=2)
    assert [r.year for r in ev.relics] == [2001]
    with pytest.raises(WaybackError, match="no memory"):
        gather("ex.com", Wayback(DictTransport({"cdx/search": rows()})))


def test_moved_since_and_facts_lines():
    alive = {"alive": 3, "moved": 0, "gone": 0, "unchanged": 0}
    dead = {"alive": 0, "moved": 2, "gone": 1, "unchanged": 0}
    assert _moved_since({2000: alive, 2001: dead, 2002: dead}) == 2001
    assert _moved_since({2000: dead, 2001: dead}) is None
    assert _moved_since({2000: alive}) is None
    f = Facts("ex.com", "2000-01-01", "2000-01-01", None, 1, {}, None)
    assert len(f.lines()) == 2 and f.years == {2000}
