"""End-to-end: recorded GeoCities archive responses + the fake model. No network."""

import json

import pytest

from wayback_seance import cli

from .conftest import FIXTURES

GEO = str(FIXTURES / "geocities")


def run(tmp_path, *extra):
    out = tmp_path / "o.html"
    js = tmp_path / "o.json"
    code = cli.main(
        [
            "geocities.com",
            "--fixtures",
            GEO,
            "--backend",
            "fake",
            "--no-color",
            "-o",
            str(out),
            "--json",
            str(js),
            *extra,
        ]
    )
    return code, out, js


def test_offline_seance_writes_ofrenda_and_json(tmp_path, capsys):
    code, out, js = run(tmp_path)
    assert code == 0
    text = capsys.readouterr().out
    assert "W A Y B A C K" in text and "Welcome to GeoCities" in text and "silences it" in text
    page = out.read_text(encoding="utf-8")
    assert "geocities.com" in page and "web.archive.org/web/1996" in page
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["target"] == "geocities.com" and len(data["relics"]) >= 5
    assert data["verdicts"]["unverified"] == 4
    assert data["facts"]["first_seen"] == "1996-10-22"


def test_chinese_and_strict(tmp_path, capsys):
    code, out, _ = run(tmp_path, "--lang", "zh", "--strict", "--pace", "0")
    assert code == 0
    assert "网 页 招 魂" in capsys.readouterr().out
    assert "谨以此祭坛" in out.read_text(encoding="utf-8")


def test_default_output_name_and_no_html(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["geocities.com", "--fixtures", GEO, "--backend", "fake", "--no-color"]) == 0
    assert (tmp_path / "geocities-com.ofrenda.html").exists()
    assert cli._default_out("del.icio.us", "zh") == "del-icio-us.zh.ofrenda.html"
    (tmp_path / "geocities-com.ofrenda.html").unlink()
    assert cli.main(["geocities.com", "--fixtures", GEO, "--backend", "fake", "--no-html", "--no-color"]) == 0
    assert not list(tmp_path.glob("*.html"))


def test_record_while_replaying(tmp_path):
    rec = tmp_path / "rec"
    code, _, _ = run(tmp_path, "--record", str(rec))
    assert code == 0 and len(list(rec.glob("*.json"))) >= 6


def test_errors(tmp_path, capsys, monkeypatch):
    assert cli.main(["nowhere.example", "--fixtures", GEO, "--backend", "fake"]) == 3
    assert "no recorded fixture" in capsys.readouterr().err
    assert cli.main(["geocities.com", "--backend", "llama-cpp"]) == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    from wayback_seance.wayback import RecordingTransport

    class Inner:
        def get(self, url, *, follow_redirects=True):
            from wayback_seance.wayback import Response

            if "cdx" in url:
                return Response(
                    200,
                    b'[["timestamp","original","statuscode","mimetype","digest"],["20000101000000","http://x/","200","text/html","A"]]',
                )
            return Response(200, b"")

    RecordingTransport(Inner(), empty).get(
        "https://web.archive.org/cdx/search/cdx?url=x.example&output=json&fl=timestamp%2Coriginal%2Cstatuscode%2Cmimetype%2Cdigest&collapse=timestamp%3A6"
    )
    RecordingTransport(Inner(), empty).get("https://web.archive.org/web/20000101000000id_/http://x/")
    assert cli.main(["x.example", "--fixtures", str(empty), "--backend", "fake"]) == 3
    assert "nothing to remember" in capsys.readouterr().err

    from wayback_seance import llm

    class Broken(llm.FakeModel):
        def stream(self, *a, **k):
            raise llm.ModelError("server went away")
            yield ""

    monkeypatch.setattr(cli, "choose_backend", lambda *a, **k: Broken())
    assert cli.main(["geocities.com", "--fixtures", GEO, "--no-html"]) == 4


def test_version(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert "wayback-seance" in capsys.readouterr().out
