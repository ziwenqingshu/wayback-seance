"""Gather the relics: the real snapshots (and plain facts) the ghost may speak from."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .extract import Page, extract
from .wayback import Capture, Wayback, WaybackError, normalize_target, pick_evenly, yearly_activity


@dataclass
class Relic:
    """One archived snapshot, numbered S1, S2, … in time order."""

    id: str
    capture: Capture
    page: Page

    @property
    def date(self) -> str:
        return self.capture.date

    @property
    def year(self) -> int:
        return self.capture.year

    @property
    def link(self) -> str:
        return self.capture.view_url

    @property
    def searchable(self) -> str:
        """Everything the post-check may match a sentence against."""
        p = self.page
        return "\n".join([p.title, p.description, *p.headings, p.text])

    def prompt_block(self, limit: int = 650) -> str:
        p = self.page
        parts = [f"[{self.id}] {self.date}"]
        if p.title:
            parts.append(f'title: "{p.title}"')
        if p.description:
            parts.append(f'description: "{p.description[:200]}"')
        excerpt = p.excerpt(limit)
        if excerpt:
            parts.append(f"text: {excerpt}")
        return "\n".join(parts)


@dataclass
class Facts:
    """Numbers computed from the CDX index. These are true by construction."""

    target: str
    first_seen: str
    last_seen: str
    last_alive: str | None
    captures: int
    activity: dict[int, dict[str, int]]
    busiest_year: int | None
    moved_since: int | None = None
    redirect_target: str | None = None

    def lines(self) -> list[str]:
        out = [
            f"The archive first saw {self.target} on {self.first_seen}.",
            f"The most recent capture is from {self.last_seen}.",
        ]
        if self.last_alive and self.last_alive != self.last_seen:
            out.append(f"The last snapshot with readable words is from {self.last_alive}.")
        if self.busiest_year:
            out.append(f"The archive visited most often in {self.busiest_year}.")
        if self.moved_since:
            out.append(f"From {self.moved_since} onward the address mostly answered with redirects.")
        if self.redirect_target:
            out.append(f"Its latest redirect pointed to {self.redirect_target}.")
        return out

    @property
    def years(self) -> set[int]:
        out = {int(self.first_seen[:4]), int(self.last_seen[:4])}
        if self.last_alive:
            out.add(int(self.last_alive[:4]))
        for value in (self.busiest_year, self.moved_since):
            if value:
                out.add(value)
        return out


@dataclass
class Evidence:
    target: str
    relics: list[Relic]
    facts: Facts
    skipped: list[str] = field(default_factory=list)

    def by_id(self) -> dict[str, Relic]:
        return {r.id: r for r in self.relics}


def _moved_since(activity: dict[int, dict[str, int]]) -> int | None:
    """First year after which redirects/errors outnumber live pages every year."""
    years = sorted(activity)
    for i, year in enumerate(years):
        tail = years[i:]
        if all(activity[y]["moved"] + activity[y]["gone"] > activity[y]["alive"] for y in tail):
            return year if i > 0 else None
    return None


def gather(
    url: str,
    wayback: Wayback,
    *,
    count: int = 7,
    on_relic: Callable[[Relic], None] | None = None,
    on_skip: Callable[[Capture, str], None] | None = None,
    on_fetch: Callable[[Capture], None] | None = None,
) -> Evidence:
    target = normalize_target(url)
    captures = wayback.captures(target)
    if not captures:
        raise WaybackError(f"the archive has no memory of {target}")
    pages = [c for c in captures if c.is_page]
    activity = yearly_activity(captures)
    busiest = max(activity, key=lambda y: sum(activity[y].values())) if activity else None
    moved = _moved_since(activity)

    redirect_target = None
    redirects = [c for c in captures if c.is_redirect]
    if redirects and (not pages or redirects[-1].timestamp > pages[-1].timestamp):
        redirect_target = wayback.redirect_target(redirects[-1])

    facts = Facts(
        target=target,
        first_seen=captures[0].date,
        last_seen=captures[-1].date,
        last_alive=pages[-1].date if pages else None,
        captures=len(captures),
        activity=activity,
        busiest_year=busiest,
        moved_since=moved,
        redirect_target=redirect_target,
    )

    relics: list[Relic] = []
    skipped: list[str] = []
    budget = max(count * 2, 4)  # never hammer the archive with more fetches than this
    tried: set[str] = set()
    hollow: list[int] = []  # captures that turned out empty; their neighbours usually are too

    def attempt(cap: Capture) -> bool:
        nonlocal budget
        tried.add(cap.timestamp)
        budget -= 1
        page = _summon(wayback, cap, skipped, on_skip, on_fetch)
        if page is None:
            hollow.append(_months(cap))
            return False
        relics.append(Relic(id="", capture=cap, page=page))
        return True

    for cap in pick_evenly(pages, count):
        if budget > 0:
            attempt(cap)
    # Some captures are empty shells (a bare redirect, a script-only page). Fill the
    # widest remaining gaps in the timeline with other captures until the budget runs out.
    while len(relics) < count and budget > 0:
        digests = {r.capture.digest for r in relics}
        spare = [
            c
            for c in pages
            if c.timestamp not in tried and c.digest not in digests and all(abs(_months(c) - h) > 12 for h in hollow)
        ]
        if not spare:
            break
        have = [_months(r.capture) for r in relics]
        pick = spare[len(spare) // 2] if not have else max(spare, key=lambda c: min(abs(_months(c) - h) for h in have))
        attempt(pick)
    relics.sort(key=lambda r: r.capture.timestamp)
    if relics:
        # the CDX calls an empty shell "200 OK" too; only a page we could read counts as alive
        facts.last_alive = relics[-1].date
    for i, relic in enumerate(relics, 1):
        relic.id = f"S{i}"
        if on_relic:
            on_relic(relic)
    return Evidence(target=target, relics=relics, facts=facts, skipped=skipped)


def _months(cap: Capture) -> int:
    return cap.year * 12 + int(cap.timestamp[4:6])


def _summon(wayback, cap, skipped, on_skip, on_fetch) -> Page | None:
    if on_fetch:
        on_fetch(cap)
    try:
        page = extract(wayback.fetch(cap))
    except WaybackError as exc:
        skipped.append(f"{cap.timestamp}: {exc}")
        if on_skip:
            on_skip(cap, str(exc))
        return None
    if page.is_empty:
        skipped.append(f"{cap.timestamp}: page had no readable text")
        if on_skip:
            on_skip(cap, "no readable text")
        return None
    return page
