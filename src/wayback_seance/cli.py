"""``seance <url>``: call a dead website back from the Internet Archive."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .evidence import gather
from .llm import ModelError, choose_backend
from .ofrenda import render
from .seance import hold_seance
from .terminal import Renderer
from .wayback import FixtureTransport, RecordingTransport, UrllibTransport, Wayback, WaybackError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="seance",
        description="Summon the ghost of a dead website. It may only speak from real Wayback Machine snapshots.",
    )
    p.add_argument("url", help="the website to call back, e.g. geocities.com")
    p.add_argument("-n", "--snapshots", type=int, default=7, help="how many snapshots to summon (default 7)")
    p.add_argument("--lang", choices=["en", "zh"], default="en", help="language the ghost speaks (default en)")
    p.add_argument("-o", "--out", default=None, help="write the HTML ofrenda here (default <site>.ofrenda.html)")
    p.add_argument("--no-html", action="store_true", help="do not write the HTML ofrenda")
    p.add_argument("--json", dest="json_path", default=None, help="also write the full testimony as JSON")
    p.add_argument("--strict", action="store_true", help="drop unverified sentences instead of striking them")
    p.add_argument(
        "--backend",
        choices=["auto", "openai", "llama-cpp", "fake"],
        default="auto",
        help="model backend (default auto)",
    )
    p.add_argument("--base-url", default=None, help="OpenAI-compatible server, e.g. http://127.0.0.1:8080/v1")
    p.add_argument("--model", default=None, help="model name sent to the server (default gemma-3-4b-it)")
    p.add_argument("--model-path", default=None, help="GGUF file for --backend llama-cpp")
    p.add_argument("--temperature", type=float, default=0.5)
    p.add_argument("--seed", type=int, default=1031)
    p.add_argument("--pace", type=float, default=None, help="seconds per character when the ghost speaks")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--cache-dir", default=None, help="cache snapshots here (default ~/.cache/wayback-seance)")
    p.add_argument("--fixtures", default=None, help="replay recorded archive responses from this directory (offline)")
    p.add_argument("--record", default=None, help="save archive responses to this directory for later --fixtures")
    p.add_argument("--version", action="version", version=f"wayback-seance {__version__}")
    return p


def _default_out(target: str, lang: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in target).strip("-")
    return f"{slug}{'.zh' if lang == 'zh' else ''}.ofrenda.html"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")  # marigolds must never crash a cp1252 console
    color = False if (args.no_color or os.environ.get("NO_COLOR")) else None
    pace = args.pace if args.pace is not None else (0.012 if sys.stdout.isatty() else 0.0)
    ui = Renderer(color=color, pace=pace, lang=args.lang, strict=args.strict)

    if args.fixtures:
        transport = FixtureTransport(Path(args.fixtures))
        cache = None
    else:
        transport = UrllibTransport()
        cache = Path(args.cache_dir or Path.home() / ".cache" / "wayback-seance")
    if args.record:
        transport = RecordingTransport(transport, Path(args.record))
        cache = None
    wayback = Wayback(transport, cache_dir=cache)

    try:
        backend = choose_backend(args.backend, base_url=args.base_url, model=args.model, model_path=args.model_path)
    except ModelError as exc:
        print(f"seance: {exc}", file=sys.stderr)
        return 2

    ui.opening(args.url)
    try:
        evidence = gather(
            args.url, wayback, count=args.snapshots, on_relic=ui.relic, on_skip=ui.skip, on_fetch=ui.fetching
        )
    except WaybackError as exc:
        print(f"\nseance: {exc}", file=sys.stderr)
        return 3
    if not evidence.relics:
        print("\nseance: no snapshot could be summoned; the ghost has nothing to remember.", file=sys.stderr)
        return 3
    ui.facts(evidence)

    model_name = getattr(backend, "model", None) or getattr(backend, "model_path", None) or backend.name
    try:
        testimony = hold_seance(
            evidence,
            backend,
            lang=args.lang,
            temperature=args.temperature,
            seed=args.seed,
            model_name=Path(str(model_name)).name,
            on_chapter=ui.chapter,
            on_sentence=ui.sentence,
        )
    except ModelError as exc:
        print(f"\nseance: {exc}", file=sys.stderr)
        return 4

    out = None
    if not args.no_html:
        out = args.out or _default_out(evidence.target, args.lang)
        Path(out).write_text(render(testimony, strict=args.strict), encoding="utf-8")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(testimony.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    ui.closing(testimony, out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
