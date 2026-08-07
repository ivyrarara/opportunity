"""토론토 Workday CXS 어댑터 테스트 (fixture 기반, 네트워크 없음)."""

from __future__ import annotations

import json

import httpx

from opmon.adapters import workday
from opmon.adapters.base import RunContext
from opmon.adapters.workday import (
    collect_workday,
    parse_workday_items,
    run,
)
from opmon.config import Adapter, Company, load_targets
from opmon.outcomes import Outcome

CFG = load_targets()

SCFG = {
    "host": "test.wd3.myworkdayjobs.com",
    "tenant": "test",
    "site": "External",
    "locale": "en-US",
    "search_texts": ["designer"],
    "location_contains": ["Toronto", "Canada", "Remote"],
}


def _job(title, path, loc="Toronto, Ontario, Canada", bullets=None):
    return {
        "title": title,
        "externalPath": path,
        "locationsText": loc,
        "postedOn": "Posted 3 Days Ago",
        "bulletFields": bullets or [path.rsplit("_", 1)[-1]],
    }


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- collect_workday -----------------------------------------------------


def test_collect_single_page_ok():
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        assert req.method == "POST"
        assert body["searchText"] == "designer"
        return httpx.Response(200, json={
            "total": 2,
            "jobPostings": [_job("Brand Designer", "/job/T/Brand-Designer_1"),
                            _job("Graphic Designer", "/job/T/Graphic-Designer_2")],
        })

    with _client(handler) as c:
        outcome, meta, raw = collect_workday(SCFG, client=c)
    assert outcome == Outcome.OK_WITH_RESULTS
    assert meta["raw"] == 2 and meta["declared_max"] == 2


def test_collect_paginates_by_offset():
    def handler(req: httpx.Request) -> httpx.Response:
        offset = json.loads(req.content)["offset"]
        if offset == 0:
            posts = [_job(f"Designer {i}", f"/job/T/D_{i}") for i in range(20)]
        else:
            posts = [_job("Designer 20", "/job/T/D_20")]
        return httpx.Response(200, json={"total": 21, "jobPostings": posts})

    with _client(handler) as c:
        outcome, meta, raw = collect_workday(SCFG, client=c)
    assert outcome == Outcome.OK_WITH_RESULTS
    assert meta["raw"] == 21 and meta["pages"] == 2


def test_collect_dedupes_across_searches():
    scfg = {**SCFG, "search_texts": ["designer", "brand"]}

    def handler(req: httpx.Request) -> httpx.Response:
        q = json.loads(req.content)["searchText"]
        shared = _job("Brand Designer", "/job/T/Brand-Designer_1")
        if q == "designer":
            posts = [shared, _job("Graphic Designer", "/job/T/Graphic-Designer_2")]
        else:  # brand → 같은 공고 하나가 겹침
            posts = [shared, _job("Brand Manager", "/job/T/Brand-Manager_3")]
        return httpx.Response(200, json={"total": len(posts), "jobPostings": posts})

    with _client(handler) as c:
        outcome, meta, raw = collect_workday(scfg, client=c)
    # 4건이지만 shared 중복 제거 → 3건
    assert meta["raw"] == 3


def test_collect_empty_trusted():
    with _client(lambda r: httpx.Response(200, json={"total": 0, "jobPostings": []})) as c:
        outcome, meta, raw = collect_workday(SCFG, client=c)
    assert outcome == Outcome.OK_EMPTY_TRUSTED and raw == []


def test_collect_blocked_on_403():
    with _client(lambda r: httpx.Response(403)) as c:
        outcome, meta, raw = collect_workday(SCFG, client=c)
    assert outcome == Outcome.BLOCKED


def test_collect_schema_drift_missing_keys():
    with _client(lambda r: httpx.Response(200, json={"unexpected": 1})) as c:
        outcome, meta, raw = collect_workday(SCFG, client=c)
    assert outcome == Outcome.PARSE_ERROR


def test_collect_parse_error_declared_but_empty():
    # total>0 인데 배열이 빈 채로 옴 → 스키마 드리프트로 판정
    with _client(lambda r: httpx.Response(200, json={"total": 5, "jobPostings": []})) as c:
        outcome, meta, raw = collect_workday(SCFG, client=c)
    assert outcome == Outcome.PARSE_ERROR


# --- parse_workday_items -------------------------------------------------


def test_parse_builds_full_url_and_id():
    items = [_job("Brand Designer", "/job/T/Brand-Designer_R123", bullets=["R123"])]
    posts = parse_workday_items(items, SCFG)
    assert len(posts) == 1
    p = posts[0]
    assert p.url == "https://test.wd3.myworkdayjobs.com/en-US/External/job/T/Brand-Designer_R123"
    assert p.job_id == "R123"
    assert p.posted_date == "Posted 3 Days Ago"


def test_parse_skips_items_missing_title_or_path():
    items = [{"title": "No Path"}, {"externalPath": "/x"}]
    assert parse_workday_items(items, SCFG) == []


# --- run (디스패치 + 위치 필터 + 매칭) ----------------------------------


def _company():
    return Company(id="test", name="Test", adapter=Adapter.WORKDAY)


def test_run_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(workday, "get_workday_config", lambda cid: None)
    res = run(_company(), CFG, RunContext())
    assert res.skipped is True


def test_run_filters_by_location_and_matches(monkeypatch):
    monkeypatch.setattr(workday, "get_workday_config", lambda cid: SCFG)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "total": 2,
            "jobPostings": [
                _job("Senior Brand Designer", "/job/T/BD_1", loc="Toronto, Ontario, Canada"),
                _job("Brand Designer", "/job/NY/BD_2", loc="New York, United States"),
            ],
        })

    with _client(handler) as c:
        res = run(_company(), CFG, RunContext(client=c))
    # 토론토 1건만 위치 통과, 그리고 'Designer'/'Brand'로 매칭
    assert res.outcome == Outcome.OK_WITH_RESULTS
    assert res.meta["located"] == 1
    assert len(res.matches) == 1
    assert res.matches[0].posting.title == "Senior Brand Designer"


def test_run_drops_non_design_titles(monkeypatch):
    # 실측에서 나온 오탐: 'Analytics & BI'(BI 오탐), 'Brand Ambassador'(판매직).
    monkeypatch.setattr(workday, "get_workday_config", lambda cid: SCFG)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "total": 3,
            "jobPostings": [
                _job("Manager, Advanced Analytics & BI", "/job/T/AN_1"),
                _job("Brand Ambassador Experience", "/job/T/BA_2"),
                _job("Associate Graphic Designer", "/job/T/GD_3"),
            ],
        })

    with _client(handler) as c:
        res = run(_company(), CFG, RunContext(client=c))
    assert res.meta["located"] == 3        # 셋 다 토론토
    assert res.meta["design"] == 1         # 디자인 제목은 하나뿐
    assert len(res.matches) == 1
    assert res.matches[0].posting.title == "Associate Graphic Designer"


def test_run_empty_trusted_when_no_toronto(monkeypatch):
    monkeypatch.setattr(workday, "get_workday_config", lambda cid: SCFG)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "total": 1,
            "jobPostings": [_job("Brand Designer", "/job/NY/BD_2", loc="New York, US")],
        })

    with _client(handler) as c:
        res = run(_company(), CFG, RunContext(client=c))
    assert res.outcome == Outcome.OK_EMPTY_TRUSTED
    assert res.meta["located"] == 0 and res.matches == []
