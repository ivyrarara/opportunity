"""Netflix 자체 채용 API 어댑터 테스트 (fixture 기반)."""

from __future__ import annotations

import httpx

from opmon.adapters import netflix
from opmon.adapters.base import RunContext
from opmon.adapters.netflix import collect, run
from opmon.config import Adapter, Company, load_targets
from opmon.outcomes import Outcome

CFG = load_targets()
SCFG = {
    "host": "jobs.netflix.com",
    "search_texts": ["designer"],
    "location_contains": ["Korea", "Seoul", "Singapore", "Japan", "Tokyo", "APAC", "Asia", "Remote"],
    "max_pages": 1,
}


def _post(text, loc, pid, team="Consumer Products"):
    return {
        "external_id": pid,
        "text": text,
        "team": [team],
        "location": loc,
        "locations": [loc],
        "created_at": "2026-08-01",
    }


POSTINGS = [
    _post("Brand Designer, Consumer Products", "Seoul, South Korea", "n1"),
    _post("Graphic Designer", "Singapore", "n2"),
    _post("Sales Manager", "Seoul, South Korea", "n3"),          # 위치 OK, 디자인 아님
    _post("Product Designer", "Los Angeles, California", "n4"),  # 디자인, 위치 밖
]


def _body(posts):
    return {"records": {"postings": posts}, "info": {"postings": {"total": len(posts)}}}


def _client(data, status=200):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=data)))


def test_collect_ok():
    with _client(_body(POSTINGS)) as c:
        outcome, meta, raw = collect(SCFG, client=c)
    assert outcome == Outcome.OK_WITH_RESULTS
    assert meta["raw"] == 4 and meta["declared_max"] == 4


def test_collect_empty():
    with _client(_body([])) as c:
        outcome, meta, raw = collect(SCFG, client=c)
    assert outcome == Outcome.OK_EMPTY_TRUSTED


def test_collect_schema_error_when_unknown_shape():
    with _client({"oops": 1}) as c:
        outcome, meta, raw = collect(SCFG, client=c)
    assert outcome == Outcome.PARSE_ERROR


def test_collect_blocked_403():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403))) as c:
        outcome, meta, raw = collect(SCFG, client=c)
    assert outcome == Outcome.BLOCKED


def test_extract_postings_fallback_keys():
    assert netflix._extract_postings({"postings": [{"a": 1}]}) == [{"a": 1}]
    assert netflix._extract_postings({"positions": [{"a": 1}]}) == [{"a": 1}]
    assert netflix._extract_postings([{"a": 1}, "x"]) == [{"a": 1}]
    assert netflix._extract_postings({"nope": 1}) is None


def _company():
    return Company(id="netflix", name="Netflix", adapter=Adapter.NETFLIX)


def test_run_filters_location_and_design(monkeypatch):
    monkeypatch.setattr(netflix, "get_netflix_config", lambda cid: SCFG)
    with _client(_body(POSTINGS)) as c:
        res = run(_company(), CFG, RunContext(client=c))
    assert res.outcome == Outcome.OK_WITH_RESULTS
    assert res.meta["located"] == 3   # n1,n2,n3 위치 통과 (n4 LA 제외)
    assert res.meta["design"] == 2    # n1,n2 디자인 (n3 판매직 제외)
    titles = {m.posting.title for m in res.matches}
    assert titles == {"Brand Designer, Consumer Products", "Graphic Designer"}
    urls = {m.posting.url for m in res.matches}
    assert "https://jobs.netflix.com/jobs/n1" in urls


def test_run_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(netflix, "get_netflix_config", lambda cid: None)
    res = run(_company(), CFG, RunContext())
    assert res.skipped is True
