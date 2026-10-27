import pytest

from wayback_seance.llm import FakeModel, ModelError, OpenAICompatible, choose_backend


def test_openai_stream_parses_sse_and_usage(http_server):
    backend = OpenAICompatible(http_server + "/v1", model="gemma-3-4b-it")
    assert backend.available()
    text = "".join(backend.stream([{"role": "user", "content": "hi"}], max_tokens=10, temperature=0.1, seed=1))
    assert text == "I was born. [S1]"
    assert backend.stats.prompt_tokens == 12 and backend.stats.completion_tokens == 5


def test_openai_errors(http_server):
    with pytest.raises(ModelError, match="HTTP 500"):
        list(OpenAICompatible(http_server + "/broken").stream([], max_tokens=1, temperature=0, seed=0))
    dead = OpenAICompatible("http://127.0.0.1:9/v1")
    assert not dead.available(timeout=0.5)
    with pytest.raises(ModelError, match="cannot reach"):
        list(dead.stream([], max_tokens=1, temperature=0, seed=0))


def test_fake_model_tells_one_lie():
    messages = [
        {"role": "system", "content": "You are the ghost"},
        {"role": "user", "content": '[S1] 1996-10-22\ntitle: "Welcome"\ntext: hi\n\n[S2] 2004-01-01\ntext: x'},
    ]
    fake = FakeModel()
    out = "".join(fake.stream(messages, max_tokens=1, temperature=0, seed=0))
    assert 'In 1996 my title read "Welcome". [S1]' in out
    assert "a page with no name" in out and "Dancing Baby" in out
    zh = "".join(
        fake.stream([{"role": "system", "content": "你是幽灵"}, messages[1]], max_tokens=1, temperature=0, seed=0)
    )
    assert "“Welcome”" in zh and len(fake.calls) == 2


def test_choose_backend(http_server, monkeypatch):
    monkeypatch.delenv("SEANCE_BASE_URL", raising=False)
    monkeypatch.delenv("SEANCE_MODEL_PATH", raising=False)
    assert isinstance(choose_backend("fake"), FakeModel)
    b = choose_backend("auto", base_url=http_server + "/v1", model="m")
    assert isinstance(b, OpenAICompatible) and b.model == "m"
    assert isinstance(choose_backend("openai"), OpenAICompatible)
    with pytest.raises(ModelError):
        choose_backend("llama-cpp")
    with pytest.raises(ModelError):
        choose_backend("cloud")
    with pytest.raises(ModelError, match="no local model"):
        choose_backend("auto", base_url="http://127.0.0.1:9/v1")
