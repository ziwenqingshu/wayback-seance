"""Lay out the séance as a single self-contained HTML ofrenda (no external assets)."""

from __future__ import annotations

import datetime as _dt
from html import escape

from .grounding import FAINT, GROUNDED, UNVERIFIED, Sentence
from .seance import Testimony

ROMAN = ["I", "II", "III", "IV"]

UI = {
    "en": {
        "lang": "en",
        "in_memory": "In loving memory of",
        "kept_by": "as kept by the Internet Archive and spoken through {model}, a local open-weight model",
        "life": "A life in captures",
        "life_note": "Monthly captures per year. Marigold: a living page. Violet: a redirect. Ash: gone or erroring. Gold dust: unchanged.",
        "testimony": "The testimony",
        "testimony_note": "Every sentence was held up to the snapshot it cites before it was allowed onto the altar.",
        "faint": "faint: only partly supported by the snapshot",
        "silenced": "silenced by the medium",
        "silenced_title": "Words the medium could not verify",
        "silenced_note": "The ghost said these, but no snapshot backs them up. They are kept here, struck through, so you can see what a small model invents when it is not watched.",
        "relics": "The relics",
        "relics_note": "The real snapshots the ghost was allowed to remember.",
        "open": "Open this snapshot in the Wayback Machine",
        "verdict": "{g} grounded · {f} faint · {u} silenced",
        "how": "How this ofrenda was made",
        "how_body": "Wayback Séance listed every capture of {site} with the Wayback Machine's CDX API, read {n} snapshots as raw HTML, and asked {model} to speak one chapter at a time using only those snapshots. A deterministic checker then compared every sentence with the snapshot it cites: quotes, years, numbers and names must appear there, and enough of its words must too.",
        "thanks": "Snapshots courtesy of the Internet Archive. The Wayback Machine is how the web remembers; consider supporting it.",
        "made": "Made with wayback-seance on {date}.",
        "years": "{first} – {last}",
        "first_seen": "first seen",
        "last_page": "last living page",
        "last_seen": "last capture",
        "leads": "now leads to",
        "no_title": "(no title)",
    },
    "zh": {
        "lang": "zh-CN",
        "in_memory": "谨以此祭坛，纪念",
        "kept_by": "由互联网档案馆保存，经本地开源权重模型 {model} 转述",
        "life": "一生的快照",
        "life_note": "每年的月度快照数。金盏花色：仍在运行的页面；紫色：重定向；灰烬色：消失或报错；金粉色：内容未变。",
        "testimony": "幽灵的证词",
        "testimony_note": "每一句话在被摆上祭坛之前，都已与它所引用的快照核对过。",
        "faint": "微弱：快照只部分支持这句话",
        "silenced": "被灵媒噤声",
        "silenced_title": "灵媒无法核实的话",
        "silenced_note": "幽灵说了这些话，但没有任何快照能证明。我们把它们划掉后保留在这里，让你看到小模型在无人监督时会编造什么。",
        "relics": "遗物",
        "relics_note": "幽灵被允许记住的真实快照。",
        "open": "在 Wayback Machine 中打开这张快照",
        "verdict": "{g} 句有据 · {f} 句微弱 · {u} 句噤声",
        "how": "这座祭坛是如何搭建的",
        "how_body": "Wayback Séance 用 Wayback Machine 的 CDX API 列出 {site} 的全部快照，以原始 HTML 读取其中 {n} 张，然后请 {model} 只依据这些快照、一章一章地讲述。随后，一个确定性的检查器把每句话与它引用的快照逐一比对：引语、年份、数字和名字都必须出现在快照中，句中足够多的词也必须如此。",
        "thanks": "快照由互联网档案馆提供。Wayback Machine 是互联网的记忆，欢迎支持它。",
        "made": "由 wayback-seance 生成于 {date}。",
        "years": "{first} – {last}",
        "first_seen": "初次被记录",
        "last_page": "最后一张活着的页面",
        "last_seen": "最后一次快照",
        "leads": "如今通向",
        "no_title": "（无标题）",
    },
}

CSS = """
:root{--night:#120a18;--ink:#f6ead2;--bone:#efe3c8;--muted:#b9a98f;--marigold:#f4a42a;--cempa:#ff7a1a;
--violet:#a98bd6;--rose:#e0607e;--ash:#6f6574;--card:#1c1224;--line:#3a2a44}
*{box-sizing:border-box}
html{background:var(--night)}
body{margin:0;color:var(--ink);font:17px/1.65 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Noto Serif SC","Songti SC",serif;
background:radial-gradient(1200px 600px at 50% -10%,#3a1d3f 0%,transparent 60%),radial-gradient(900px 500px at 50% 110%,#2b1206 0%,transparent 60%),var(--night)}
a{color:var(--marigold)}
.picado{display:flex;height:64px;overflow:hidden}
.picado span{flex:1;margin:0 3px;clip-path:polygon(0 0,100% 0,100% 78%,88% 100%,75% 78%,62% 100%,50% 78%,38% 100%,25% 78%,12% 100%,0 78%);
opacity:.92;background-image:radial-gradient(circle at 50% 34%,var(--night) 6px,transparent 7px),
radial-gradient(circle at 24% 52%,var(--night) 3px,transparent 4px),radial-gradient(circle at 76% 52%,var(--night) 3px,transparent 4px),
radial-gradient(circle at 50% 62%,var(--night) 2px,transparent 3px)}
.picado span:nth-child(5n+1){background-color:#e0457b}.picado span:nth-child(5n+2){background-color:#f4a42a}.picado span:nth-child(5n+3){background-color:#3fb8af}
.picado span:nth-child(5n+4){background-color:#8e5fd1}.picado span:nth-child(5n){background-color:#ff7a1a}
main{max-width:860px;margin:0 auto;padding:24px 22px 80px}
header{text-align:center;padding:30px 0 10px}
.small{font-variant:small-caps;letter-spacing:.18em;color:var(--muted);font-size:15px}
h1{font-size:clamp(38px,7vw,68px);line-height:1.05;margin:.2em 0 .1em;color:var(--bone);font-weight:600;letter-spacing:.01em;
text-shadow:0 0 28px rgba(244,164,42,.35)}
.dates{font-size:22px;color:var(--marigold);letter-spacing:.12em}
.kept{color:var(--muted);font-style:italic;margin:.4em auto 0;max-width:620px}
.altar{display:flex;justify-content:center;align-items:flex-end;gap:26px;margin:34px 0 8px;height:120px}
.candle{position:relative;width:22px;background:linear-gradient(90deg,#d9c7a3,#fff3d6 45%,#cdb68c);border-radius:4px 4px 2px 2px}
.candle:nth-child(1){height:60px}.candle:nth-child(2){height:84px}.candle:nth-child(3){height:100px}.candle:nth-child(4){height:76px}.candle:nth-child(5){height:56px}
.candle:before{content:"";position:absolute;left:50%;top:-30px;width:14px;height:26px;margin-left:-7px;border-radius:50% 50% 45% 45%/60% 60% 40% 40%;
background:radial-gradient(ellipse at 50% 70%,#fff8d8 0%,#ffd466 35%,#ff8a1f 70%,rgba(255,90,0,0) 72%);filter:blur(.3px);
animation:flicker 2.6s infinite ease-in-out;transform-origin:50% 100%}
.candle:after{content:"";position:absolute;left:50%;top:-60px;width:80px;height:80px;margin-left:-40px;border-radius:50%;
background:radial-gradient(circle,rgba(255,180,60,.28),transparent 65%);animation:glow 2.6s infinite ease-in-out}
.candle:nth-child(2):before,.candle:nth-child(2):after{animation-delay:-.7s}.candle:nth-child(4):before,.candle:nth-child(4):after{animation-delay:-1.3s}
@keyframes flicker{0%,100%{transform:scale(1,1) rotate(-1deg)}30%{transform:scale(.92,1.06) rotate(2deg)}60%{transform:scale(1.04,.95) rotate(-2deg)}}
@keyframes glow{0%,100%{opacity:.9}50%{opacity:.6}}
.garland{text-align:center;color:var(--marigold);letter-spacing:.35em;font-size:20px;margin:10px 0 0;opacity:.9}
.garland b{color:var(--cempa);font-weight:normal}
section{margin-top:56px}
h2{font-size:28px;color:var(--bone);margin:0 0 4px;font-weight:600}
h2:before{content:"✿ ";color:var(--marigold)}
.note{color:var(--muted);margin:0 0 18px;font-size:15px}
.chart svg{width:100%;height:auto;display:block}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:16px}
.fact{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.fact span{display:block;color:var(--muted);font-size:13px;font-variant:small-caps;letter-spacing:.1em}
.fact b{color:var(--bone);font-weight:600;word-break:break-word}
.chapter{margin:28px 0 0}
.chapter h3{color:var(--marigold);font-weight:normal;letter-spacing:.14em;font-variant:small-caps;font-size:19px;margin:0 0 8px;
border-bottom:1px solid var(--line);padding-bottom:6px}
.speech{font-size:19px;line-height:1.75;color:var(--bone)}
.s{margin-right:.25em}
.s.faint{color:#cfc2a8;font-style:italic;opacity:.8}
.s.unverified{color:var(--rose);text-decoration:line-through;text-decoration-thickness:1.5px;opacity:.75}
.cite{font:600 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--night);background:var(--marigold);border-radius:8px;padding:3px 6px;
margin-left:3px;text-decoration:none;vertical-align:3px;white-space:nowrap}
.faint .cite{background:#b9a98f}.unverified .cite{background:var(--ash);color:var(--ink)}
.cite:hover{background:var(--cempa)}
.verdict{margin-top:22px;color:var(--muted);font-size:15px}
details{margin-top:18px;background:rgba(224,96,126,.06);border:1px dashed rgba(224,96,126,.4);border-radius:10px;padding:10px 16px}
summary{cursor:pointer;color:var(--rose)}
details li{margin:8px 0}
details .why{display:block;color:var(--muted);font-size:14px;text-decoration:none;font-style:normal}
.timeline{position:relative;margin-left:10px;padding-left:28px;border-left:2px solid var(--line)}
.relic{position:relative;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin:0 0 18px}
.relic:before{content:"";position:absolute;left:-38px;top:18px;width:16px;height:16px;border-radius:50%;
background:radial-gradient(circle,#ffd77a,var(--marigold) 60%,var(--cempa));box-shadow:0 0 14px rgba(244,164,42,.7)}
.relic .meta{font:600 13px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--marigold);letter-spacing:.06em}
.relic h4{margin:6px 0 4px;font-size:19px;color:var(--bone);font-weight:600}
.relic p{margin:0 0 8px;color:var(--muted);font-size:15px}
.relic a{font-size:14px}
footer{margin-top:64px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted);font-size:14px}
footer h2{font-size:20px}
@media (prefers-reduced-motion:reduce){.candle:before,.candle:after{animation:none}}
"""


def _sentence_html(s: Sentence, dates: dict[str, str], links: dict[str, str], ui: dict[str, str]) -> str:
    chips = "".join(
        f'<a class="cite" href="{escape(links.get(c, "#"))}" title="{escape(s.support or c)}">{escape(c)} · {escape(dates.get(c, "?")[:4])}</a>'
        for c in s.cites
    )
    title = ""
    if s.verdict == FAINT:
        title = f' title="{escape(ui["faint"] + (": " + "; ".join(s.reasons) if s.reasons else ""))}"'
    elif s.verdict == UNVERIFIED:
        title = f' title="{escape(ui["silenced"] + ": " + "; ".join(s.reasons))}"'
    return f'<span class="s {s.verdict}"{title}>{escape(s.text)}{chips}</span>'


def _chart(activity: dict[int, dict[str, int]]) -> str:
    if not activity:
        return ""
    years = list(range(min(activity), max(activity) + 1))
    w, h, pad = 820, 170, 26
    bw = (w - 2 * pad) / len(years)
    peak = max(sum(v.values()) for v in activity.values()) or 1
    colors = {"alive": "#f4a42a", "moved": "#a98bd6", "gone": "#6f6574", "unchanged": "#8a6d2f"}
    parts = [f'<svg viewBox="0 0 {w} {h + 30}" role="img" aria-label="captures per year">']
    for i, year in enumerate(years):
        x = pad + i * bw
        y = h
        counts = activity.get(year, {})
        for key in ("alive", "unchanged", "moved", "gone"):
            n = counts.get(key, 0)
            if not n:
                continue
            bh = (h - 20) * n / peak
            y -= bh
            parts.append(
                f'<rect x="{x + 2:.1f}" y="{y:.1f}" width="{max(bw - 4, 2):.1f}" height="{bh:.1f}" rx="2" fill="{colors[key]}"><title>{year}: {n} {key}</title></rect>'
            )
        if len(years) <= 16 or i % 2 == 0 or year == years[-1]:
            parts.append(
                f'<text x="{x + bw / 2:.1f}" y="{h + 18}" fill="#b9a98f" font-size="11" text-anchor="middle" font-family="ui-monospace,monospace">{year}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def render(testimony: Testimony, *, strict: bool = False, generated: _dt.date | None = None) -> str:
    ev = testimony.evidence
    f = ev.facts
    ui = UI.get(testimony.lang, UI["en"])
    dates = {r.id: r.date for r in ev.relics}
    links = {r.id: r.link for r in ev.relics}
    first_year, last_year = f.first_seen[:4], (f.last_alive or f.last_seen)[:4]
    model = escape(testimony.model)

    chapters_html = []
    silenced = []
    for i, ct in enumerate(testimony.chapters):
        spoken = []
        for s in ct.sentences:
            if s.verdict == UNVERIFIED:
                silenced.append(s)
                if strict:
                    continue
            spoken.append(_sentence_html(s, dates, links, ui))
        chapters_html.append(
            f'<div class="chapter"><h3>{ROMAN[i % 4]} · {escape(ct.chapter.title(testimony.lang))}</h3>'
            f'<p class="speech">{" ".join(spoken)}</p></div>'
        )
    silenced_html = ""
    if silenced:
        items = "".join(
            f'<li><span class="s unverified">{escape(s.text)}</span><span class="why">{escape("; ".join(s.reasons))}</span></li>'
            for s in silenced
        )
        silenced_html = (
            f"<details><summary>{escape(ui['silenced_title'])} ({len(silenced)})</summary>"
            f'<p class="note">{escape(ui["silenced_note"])}</p><ul>{items}</ul></details>'
        )

    relic_html = "".join(
        f'<article class="relic" id="relic-{escape(r.id)}"><div class="meta">{escape(r.id)} · {escape(r.date)}</div>'
        f"<h4>{escape(r.page.title or ui['no_title'])}</h4><p>{escape(r.page.excerpt(320))}</p>"
        f'<a href="{escape(r.link)}">{escape(ui["open"])} ↗</a></article>'
        for r in ev.relics
    )

    facts = [(ui["first_seen"], f.first_seen), (ui["last_page"], f.last_alive or "—"), (ui["last_seen"], f.last_seen)]
    if f.redirect_target:
        facts.append((ui["leads"], f.redirect_target))
    facts_html = "".join(f'<div class="fact"><span>{escape(k)}</span><b>{escape(v)}</b></div>' for k, v in facts)

    verdict = ui["verdict"].format(g=testimony.count(GROUNDED), f=testimony.count(FAINT), u=testimony.count(UNVERIFIED))
    date = (generated or _dt.date.today()).isoformat()
    garland = " ".join("<b>✿</b>" if i % 2 else "✿" for i in range(11))
    return f"""<!doctype html>
<html lang="{ui["lang"]}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(ev.target)} · Wayback Séance</title>
<meta name="description" content="{escape(ui["in_memory"])} {escape(ev.target)}: a grounded ghost story told from Internet Archive snapshots.">
<style>{CSS}</style>
</head>
<body>
<div class="picado" aria-hidden="true">{"<span></span>" * 14}</div>
<main>
<header>
<div class="small">{escape(ui["in_memory"])}</div>
<h1>{escape(ev.target)}</h1>
<div class="dates">{escape(ui["years"].format(first=first_year, last=last_year))}</div>
<p class="kept">{escape(ui["kept_by"]).format(model=model)}</p>
<div class="altar" aria-hidden="true"><div class="candle"></div><div class="candle"></div><div class="candle"></div><div class="candle"></div><div class="candle"></div></div>
<div class="garland" aria-hidden="true">{garland}</div>
</header>

<section>
<h2>{escape(ui["life"])}</h2>
<p class="note">{escape(ui["life_note"])}</p>
<div class="chart">{_chart(f.activity)}</div>
<div class="facts">{facts_html}</div>
</section>

<section>
<h2>{escape(ui["testimony"])}</h2>
<p class="note">{escape(ui["testimony_note"])}</p>
{"".join(chapters_html)}
<p class="verdict">{escape(verdict)}</p>
{silenced_html}
</section>

<section>
<h2>{escape(ui["relics"])}</h2>
<p class="note">{escape(ui["relics_note"])}</p>
<div class="timeline">{relic_html}</div>
</section>

<footer>
<h2>{escape(ui["how"])}</h2>
<p>{escape(ui["how_body"].format(site=ev.target, n=len(ev.relics), model=testimony.model))}</p>
<p>{escape(ui["thanks"])} <a href="https://archive.org/donate">archive.org/donate</a></p>
<p>{escape(ui["made"].format(date=date))} <a href="https://github.com/ziwenqingshu/wayback-seance">github.com/ziwenqingshu/wayback-seance</a></p>
</footer>
</main>
</body>
</html>
"""
