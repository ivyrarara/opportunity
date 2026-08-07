"""Greenhouse 보드 어댑터 테스트 (Figma/Pinterest, fixture 기반)."""

from __future__ import annotations

import httpx

from opmon.adapters import greenhouse
from opmon.adapters.base import RunContext
from opmon.adapters.greenhouse import collect, run
from opmon.config import Adapter, Company, load_targets
from opmon.outcomes import Outcome

CFG = load_targets()
SCFG = {"token": "figma", "location_contains": ["Toronto", "Ontario", "Canada", "Remote"]}


def _job(title, loc, jid):
    return {
        "id": jid,
        "title": title,
        "absolute_url": f"https://boards.greenhouse.io/figma/jobs/{jid}",
        "location": {"name": loc},
        "updated_at": "2026-08-01T00:00:00Z",
    }


JOBS = [
    _job("Brand Designer", "Remote, US", 1),
    _job("Product Designer", "Toronto, Ontario, Canada", 2),
    _job("Account Executive", "Remote, US", 3),        # 위치 OK, 디자인 아님
    _job("Visual Designer", "San Francisco, CA", 4),   # 디자인, 위치 밖
]


def _body(jobs):
    return {"meta": {"total": len(jobs)}, "jobs": jobs}


def _client(data, status=200):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=data)))


def test_collect_ok():
    with _client(_body(JOBS)) as c:
        outcome, meta, jobs = collect(SCFG, client=c)
    assert outcome == Outcome.OK_WITH_RESULTS and meta["raw"] == 4 and meta["declared_max"] == 4


def test_collect_empty():
    with _client(_body([])) as c:
        outcome, meta, jobs = collect(SCFG, client=c)
    assert outcome == Outcome.OK_EMPTY_TRUSTED


def test_collect_schema_error():
    with _client({"oops": 1}) as c:
        outcome, meta, jobs = collect(SCFG, client=c)
    assert outcome == Outcome.PARSE_ERROR


def test_collect_blocked_404():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as c:
        outcome, meta, jobs = collect(SCFG, client=c)
    assert outcome == Outcome.BLOCKED


def _company():
    return Company(id="figma", name="Figma", adapter=Adapter.GREENHOUSE)


def test_run_filters_location_and_design(monkeypatch):
    monkeypatch.setattr(greenhouse, "get_greenhouse_config", lambda cid: SCFG)
    with _client(_body(JOBS)) as c:
        res = run(_company(), CFG, RunContext(client=c))
    assert res.outcome == Outcome.OK_WITH_RESULTS
    assert res.meta["located"] == 3   # 1,2,3 위치 통과 (4 SF 제외)
    assert res.meta["design"] == 2    # 1,2 디자인 (3 AE 제외)
    titles = {m.posting.title for m in res.matches}
    assert titles == {"Brand Designer", "Product Designer"}


def test_run_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(greenhouse, "get_greenhouse_config", lambda cid: None)
    res = run(_company(), CFG, RunContext())
    assert res.skipped is True
