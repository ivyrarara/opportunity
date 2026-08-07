"""Netflix Eightfold 채용 API 어댑터 테스트 (fixture 기반)."""

from __future__ import annotations

import httpx

from opmon.adapters import netflix
from opmon.adapters.base import RunContext
from opmon.adapters.netflix import collect, run
from opmon.config import Adapter, Company, load_targets
from opmon.outcomes import Outcome

CFG = load_targets()
SCFG = {
    "host": "explore.jobs.netflix.net",
    "domain": "netflix.com",
    "search_texts": ["designer"],
    "location_contains": [
        "Korea", "Seoul", "Singapore", "Japan", "Tokyo", "APAC", "Asia",
        "Toronto", "Ontario", "Canada", "Remote",
    ],
    "num": 25,
    "max_pages": 1,
}


def _pos(name, locs, pid, dept="Consumer Products"):
    return {
        "id": pid,
        "name": name,
        "posting_name": name,
        "location": locs[0],
        "locations": locs,
        "department": dept,
        "display_job_id": f"JR{pid}",
        "t_create": 1784764800,
        "type": "ATS",
    }


POSITIONS = [
    _pos("Brand Designer, Consumer Products", ["Seoul,South Korea"], 1),
    _pos("Character Designer", ["Los Angeles,California,United States of America",
                               "Vancouver,British Columbia,Canada"], 2),  # 미국+캐나다 → 캐나다로 통과
    _pos("Sales Manager", ["Seoul,South Korea"], 3),                       # 위치 OK, 디자인 아님
    _pos("Product Designer", ["Los Angeles,California,United States of America"], 4),  # 미국 온사이트 → 제외
    _pos("Visual Designer", ["USA - Remote"], 5),                          # 북미 리모트
]


def _body(positions):
    return {"domain": "netflix.com", "count": len(positions), "positions": positions}


def _client(data, status=200):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=data)))


def test_collect_ok():
    with _client(_body(POSITIONS)) as c:
        outcome, meta, raw = collect(SCFG, client=c)
    assert outcome == Outcome.OK_WITH_RESULTS
    assert meta["raw"] == 5 and meta["declared_max"] == 5


def test_collect_empty():
    with _client(_body([])) as c:
        outcome, meta, raw = collect(SCFG, client=c)
    assert outcome == Outcome.OK_EMPTY_TRUSTED


def test_collect_schema_error_when_unknown_shape():
    with _client({"oops": 1}) as c:
        outcome, meta, raw = collect(SCFG, client=c)
    assert outcome == Outcome.PARSE_ERROR


def test_collect_blocked_404():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as c:
        outcome, meta, raw = collect(SCFG, client=c)
    assert outcome == Outcome.BLOCKED


def test_extract_postings_fallback_keys():
    assert netflix._extract_postings({"positions": [{"a": 1}]}) == [{"a": 1}]
    assert netflix._extract_postings({"jobs": [{"a": 1}]}) == [{"a": 1}]
    assert netflix._extract_postings([{"a": 1}, "x"]) == [{"a": 1}]
    assert netflix._extract_postings({"nope": 1}) is None


def _company():
    return Company(id="netflix", name="Netflix", adapter=Adapter.NETFLIX)


def test_run_filters_location_and_design(monkeypatch):
    monkeypatch.setattr(netflix, "get_netflix_config", lambda cid: SCFG)
    with _client(_body(POSITIONS)) as c:
        res = run(_company(), CFG, RunContext(client=c))
    assert res.outcome == Outcome.OK_WITH_RESULTS
    assert res.meta["located"] == 4   # 1,2,3,5 위치 통과 (4 미국 온사이트 제외)
    assert res.meta["design"] == 3    # 1,2,5 디자인 (3 판매직 제외)
    titles = {m.posting.title for m in res.matches}
    assert titles == {"Brand Designer, Consumer Products", "Character Designer", "Visual Designer"}
    urls = {m.posting.url for m in res.matches}
    assert "https://explore.jobs.netflix.net/careers?pid=2&domain=netflix.com&sort_by=relevance" in urls


def test_run_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(netflix, "get_netflix_config", lambda cid: None)
    res = run(_company(), CFG, RunContext())
    assert res.skipped is True
