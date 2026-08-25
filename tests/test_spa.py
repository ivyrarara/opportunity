"""8단계: SPA api/render 어댑터 테스트."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from opmon.adapters import spa
from opmon.adapters.base import RunContext
from opmon.adapters.spa import (
    RenderTimeout,
    classify_api,
    classify_render,
    collect_api,
    parse_api_items,
    pluck,
    run_api,
)
from opmon.config import load_targets
from opmon.outcomes import Outcome

CFG = load_targets()

API_SCFG = {
    "mode": "api",
    "api_url": "https://api.test/jobs",
    "items_path": ["result", "jobList"],
    "total_path": ["result", "total"],
    "paginate": {"param": "page", "size_param": "size", "size": 2, "start": 1},
    "item_fields": {
        "id": ["id"],
        "title": ["title"],
        "url_template": "https://api.test/jobs/{id}",
        "employment_type": ["employ"],
        "experience": ["career"],
    },
}


def _json_resp(payload, status=200):
    return httpx.Response(status, json=payload)


# --- pluck --------------------------------------------------------------


def test_pluck_nested():
    assert pluck({"a": {"b": [1, 2]}}, ["a", "b"]) == [1, 2]
    assert pluck({"a": 1}, None) == {"a": 1}


# --- classify_api (§7-2 단일 응답) --------------------------------------


def test_classify_api_ok():
    o, m = classify_api(_json_resp({"result": {"jobList": [1, 2], "total": 2}}), None, API_SCFG)
    assert o == Outcome.OK_WITH_RESULTS and m["count"] == 2


def test_classify_api_empty_trusted():
    o, m = classify_api(_json_resp({"result": {"jobList": [], "total": 0}}), None, API_SCFG)
    assert o == Outcome.OK_EMPTY_TRUSTED


def test_classify_api_parse_error_when_total_gt_parsed():
    o, m = classify_api(_json_resp({"result": {"jobList": [1], "total": 5}}), None, API_SCFG)
    assert o == Outcome.PARSE_ERROR


def test_classify_api_blocked_403():
    o, _ = classify_api(httpx.Response(403), None, API_SCFG)
    assert o == Outcome.BLOCKED


def test_classify_api_html_instead_of_json():
    o, m = classify_api(httpx.Response(200, text="<html>bot</html>"), None, API_SCFG)
    assert o == Outcome.BLOCKED and m["reason"] == "expected_json_got_html"


def test_classify_api_schema_changed():
    o, m = classify_api(_json_resp({"unexpected": {}}), None, API_SCFG)
    assert o == Outcome.PARSE_ERROR and m["reason"] == "schema_changed"


def test_classify_api_429():
    assert classify_api(httpx.Response(429), None, API_SCFG)[0] == Outcome.RATE_LIMITED


def test_classify_api_transport_exc():
    assert classify_api(None, httpx.ConnectError("x"), API_SCFG)[0] == Outcome.TRANSPORT_ERROR


def test_classify_api_empty_no_total_suspicious():
    scfg = {**API_SCFG, "total_path": ["result", "missing"]}
    # total 경로가 없으면 pluck에서 KeyError → schema_changed(PARSE_ERROR)
    o, _ = classify_api(_json_resp({"result": {"jobList": []}}), None, scfg)
    assert o == Outcome.PARSE_ERROR


# --- collect_api 페이지네이션 -------------------------------------------


def _paged_client():
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(dict(request.url.params).get("page", "1"))
        total = 3
        data = {1: [{"id": 11, "title": "A"}, {"id": 12, "title": "B"}],
                2: [{"id": 13, "title": "C"}]}.get(page, [])
        return httpx.Response(200, json={"result": {"jobList": data, "total": total}})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_collect_api_paginates_to_declared():
    with _paged_client() as client:
        outcome, meta, items = collect_api(API_SCFG, client=client)
    assert outcome == Outcome.OK_WITH_RESULTS
    assert meta["declared"] == 3 and meta["parsed"] == 3 and meta["pages"] == 2
    assert [i["id"] for i in items] == [11, 12, 13]


def test_collect_api_parse_error_if_short():
    def handler(request):
        page = int(dict(request.url.params).get("page", "1"))
        data = [{"id": 1, "title": "A"}] if page == 1 else []  # 이후 페이지 고갈
        return httpx.Response(200, json={"result": {"jobList": data, "total": 9}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        outcome, meta, _ = collect_api(API_SCFG, client=client)
    # 끝까지 순회했는데 declared(9) > parsed(1) → 부분 파싱 실패
    assert outcome == Outcome.PARSE_ERROR
    assert meta["declared"] == 9 and meta["parsed"] == 1


def test_collect_api_blocked():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403))) as client:
        outcome, _, _ = collect_api(API_SCFG, client=client)
    assert outcome == Outcome.BLOCKED


# --- parse_api_items ----------------------------------------------------


def test_parse_api_items_maps_fields():
    items = [{"id": 42, "title": "AI 기획자", "employ": "정규직", "career": "경력 5년"}]
    posts = parse_api_items(items, API_SCFG)
    assert len(posts) == 1
    p = posts[0]
    assert p.job_id == "42"
    assert p.url == "https://api.test/jobs/42"
    assert p.employment_type == "정규직"
    assert p.experience_text == "경력 5년"


def test_parse_api_items_skips_incomplete():
    items = [{"id": 1}]  # title 없음 → 스킵
    assert parse_api_items(items, API_SCFG) == []


# --- run_api end-to-end (매칭) ------------------------------------------


def test_run_api_end_to_end_matches():
    def handler(request):
        page = int(dict(request.url.params).get("page", "1"))
        data = {
            1: [{"id": 1, "title": "브랜딩 디자이너", "employ": "정규직", "career": "경력 5~10년"},
                {"id": 2, "title": "재무 담당자", "employ": "정규직", "career": "경력 7년"}],
        }.get(page, [])
        return httpx.Response(200, json={"result": {"jobList": data, "total": 2}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        res = run_api(CFG.get_company("toss"), CFG, RunContext(client=client), API_SCFG)
    assert res.outcome == Outcome.OK_WITH_RESULTS
    assert len(res.matches) == 1               # 브랜딩만 매칭, 재무는 카테고리 무매칭
    assert res.matches[0].category == "브랜딩"


# --- run 디스패치 / skip ------------------------------------------------


def test_run_skips_when_unconfigured():
    res = spa.run(CFG.get_company("kakao"), CFG, RunContext())
    assert res.skipped is True
    assert res.skip_reason and "미실측" in res.skip_reason


def test_run_dispatches_to_api(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"result": {"jobList": [{"id": 1, "title": "AI 기획"}], "total": 1}})

    monkeypatch.setattr(spa, "get_spa_config", lambda cid: API_SCFG)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        res = spa.run(CFG.get_company("toss"), CFG, RunContext(client=client))
    assert res.skipped is False
    assert res.outcome == Outcome.OK_WITH_RESULTS


# --- classify_render (§7-3, fake page) ----------------------------------


class FakePage:
    def __init__(self, *, html="<div id=root></div>", timeout=False, empty=False, item_count=0):
        self._html, self._timeout, self._empty, self._n = html, timeout, empty, item_count

    async def content(self):
        return self._html

    async def wait_for_selector(self, selector, timeout):
        if self._timeout:
            raise RenderTimeout("no anchor")
        return object()

    async def query_selector(self, selector):
        return object() if self._empty else None

    async def query_selector_all(self, selector):
        return [object()] * self._n


RENDER_SCFG = {
    "list_ready_selector": ".JobCard",
    "empty_state_selector": ".empty",
    "item_selector": ".JobCard",
    "render_timeout_ms": 100,
    "challenge_markers": ["Checking your browser", "DataDome"],
}


def _arun(coro):
    return asyncio.run(coro)


def test_render_challenge():
    page = FakePage(html="<html>DataDome check</html>")
    o, m = _arun(classify_render(page, RENDER_SCFG))
    assert o == Outcome.CHALLENGE


def test_render_timeout():
    o, m = _arun(classify_render(FakePage(timeout=True), RENDER_SCFG))
    assert o == Outcome.RENDER_TIMEOUT


def test_render_empty_state():
    o, m = _arun(classify_render(FakePage(empty=True), RENDER_SCFG))
    assert o == Outcome.RENDER_EMPTY_STATE and m["count"] == 0


def test_render_ok_with_items():
    o, m = _arun(classify_render(FakePage(item_count=3), RENDER_SCFG))
    assert o == Outcome.OK_WITH_RESULTS and m["count"] == 3


def test_render_suspicious_when_no_items_no_empty():
    o, m = _arun(classify_render(FakePage(item_count=0), RENDER_SCFG))
    assert o == Outcome.SUSPICIOUS_EMPTY


def test_render_parse_error_declared_gt_parsed():
    scfg = {**RENDER_SCFG, "_declared_for_test": 5}
    o, m = _arun(classify_render(FakePage(item_count=2), scfg))
    assert o == Outcome.PARSE_ERROR
