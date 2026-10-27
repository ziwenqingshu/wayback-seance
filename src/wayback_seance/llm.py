"""Talk to a local open-weight model. No API keys, no cloud.

Backends:

* ``openai`` – any OpenAI-compatible server on your machine: llama.cpp's
  ``llama-server`` (default ``http://127.0.0.1:8080/v1``) or Ollama
  (``http://127.0.0.1:11434/v1``).
* ``llama-cpp`` – in-process ``llama-cpp-python`` with a GGUF file.
* ``fake`` – a deterministic stand-in used by the tests and ``--offline`` demos.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Protocol

Message = dict[str, str]

DEFAULT_SERVERS = ("http://127.0.0.1:8080/v1", "http://127.0.0.1:11434/v1")


class ModelError(RuntimeError):
    pass


@dataclass
class Stats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0

    def add(self, other: Stats) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.seconds += other.seconds


class Backend(Protocol):
    name: str
    stats: Stats

    def stream(self, messages: list[Message], *, max_tokens: int, temperature: float, seed: int) -> Iterator[str]: ...


def _local_opener() -> urllib.request.OpenerDirector:
    # Never route a local model call through a system proxy.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


@dataclass
class OpenAICompatible:
    base_url: str
    model: str = "gemma-3-4b-it"
    timeout: float = 600.0
    name: str = "openai"
    stats: Stats = field(default_factory=Stats)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        is_local = re.match(r"https?://(127\.0\.0\.1|localhost|\[::1\]|0\.0\.0\.0)(:|/|$)", self.base_url)
        self._opener = _local_opener() if is_local else urllib.request.build_opener()

    def available(self, timeout: float = 2.0) -> bool:
        try:
            with self._opener.open(f"{self.base_url}/models", timeout=timeout) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def stream(self, messages: list[Message], *, max_tokens: int, temperature: float, seed: int) -> Iterator[str]:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "seed": seed,
            "stream_options": {"include_usage": True},
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        )
        started = time.monotonic()
        try:
            resp = self._opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200]
            raise ModelError(f"model server answered HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ModelError(f"cannot reach the model server at {self.base_url}: {exc}") from exc
        pieces = 0
        usage: dict = {}
        with resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                usage = event.get("usage") or usage
                for choice in event.get("choices") or []:
                    text = (choice.get("delta") or {}).get("content") or ""
                    if text:
                        pieces += 1
                        yield text
        self.stats.add(
            Stats(
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", pieces)),
                seconds=time.monotonic() - started,
            )
        )


@dataclass
class LlamaCppInProcess:
    model_path: str
    n_ctx: int = 8192
    name: str = "llama-cpp"
    stats: Stats = field(default_factory=Stats)

    def __post_init__(self) -> None:
        try:
            from llama_cpp import Llama  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on the optional extra
            raise ModelError("llama-cpp-python is not installed: pip install 'wayback-seance[llama-cpp]'") from exc
        self._llm = Llama(model_path=self.model_path, n_ctx=self.n_ctx, verbose=False)  # pragma: no cover

    def stream(self, messages, *, max_tokens, temperature, seed):  # pragma: no cover - needs a real model
        started = time.monotonic()
        count = 0
        for chunk in self._llm.create_chat_completion(
            messages=messages, max_tokens=max_tokens, temperature=temperature, seed=seed, stream=True
        ):
            text = chunk["choices"][0].get("delta", {}).get("content") or ""
            if text:
                count += 1
                yield text
        self.stats.add(Stats(completion_tokens=count, seconds=time.monotonic() - started))


_RELIC_LINE = re.compile(r"^\[(S\d+)\] (\d{4})-\d\d-\d\d$", re.M)
_TITLE_LINE = re.compile(r'^title: "(.*)"$', re.M)


def _fake_reply(messages: list[Message]) -> str:
    """Speak only in titles, plus one deliberate lie, so tests can watch the medium catch it."""
    prompt = messages[-1]["content"]
    blocks = re.split(r"(?=^\[S\d+\] \d{4})", prompt, flags=re.M)
    chinese = "你是" in messages[0]["content"]
    out = []
    for block in blocks:
        m = _RELIC_LINE.search(block)
        if not m:
            continue
        title = _TITLE_LINE.search(block)
        name = title.group(1) if title else "a page with no name"
        if chinese:
            out.append(f"{m.group(2)} 年，我的标题是“{name}”。[{m.group(1)}]")
        else:
            out.append(f'In {m.group(2)} my title read "{name}". [{m.group(1)}]')
    first = _RELIC_LINE.search(prompt)
    if first:
        lie = (
            f"人们为我跳舞的婴儿 GIF 而疯狂。[{first.group(1)}]"
            if chinese
            else f"Millions of visitors adored my Dancing Baby animation. [{first.group(1)}]"
        )
        out.append(lie)
    return " ".join(out)


@dataclass
class FakeModel:
    reply: Callable[[list[Message]], str] = _fake_reply
    name: str = "fake"
    stats: Stats = field(default_factory=Stats)
    calls: list[list[Message]] = field(default_factory=list)

    def stream(self, messages, *, max_tokens, temperature, seed):
        self.calls.append(messages)
        text = self.reply(messages)
        yield from re.findall(r"\S+\s*", text)
        self.stats.add(Stats(completion_tokens=len(text.split())))


def choose_backend(
    kind: str = "auto",
    *,
    base_url: str | None = None,
    model: str | None = None,
    model_path: str | None = None,
) -> Backend:
    kind = kind.lower()
    model = model or os.environ.get("SEANCE_MODEL", "gemma-3-4b-it")
    base_url = base_url or os.environ.get("SEANCE_BASE_URL")
    model_path = model_path or os.environ.get("SEANCE_MODEL_PATH")
    if kind == "fake":
        return FakeModel()
    if kind == "llama-cpp":
        if not model_path:
            raise ModelError("--backend llama-cpp needs --model-path to a .gguf file")
        return LlamaCppInProcess(model_path)
    if kind == "openai":
        return OpenAICompatible(base_url or DEFAULT_SERVERS[0], model=model)
    if kind != "auto":
        raise ModelError(f"unknown backend {kind!r}")
    for url in [base_url] if base_url else DEFAULT_SERVERS:
        if url is None:  # pragma: no cover - defensive
            continue
        server = OpenAICompatible(
            url, model=model if "11434" not in url else os.environ.get("SEANCE_OLLAMA_MODEL", "gemma3:4b")
        )
        if server.available():
            return server
    if model_path:
        return LlamaCppInProcess(model_path)
    raise ModelError(
        "no local model found. Start one, for example:\n"
        "  llama-server -hf unsloth/gemma-3-4b-it-GGUF:Q4_0 --port 8080\n"
        "or  ollama run gemma3:4b\n"
        "or pass --model-path to a GGUF (needs the llama-cpp extra), or --backend fake to rehearse."
    )
