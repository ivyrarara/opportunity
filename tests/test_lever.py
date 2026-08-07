"""Arc'teryx Lever 어댑터 테스트 (fixture 기반)."""

from __future__ import annotations

import httpx

from opmon.adapters import lever
from opmon.adapters.base import RunContext
from opmon.adapters.lever import collect, run
from opmon.config import Adapter, Company, load_targets
from opmon.outcomes import Outcome

CFG = load_targets()
SCFG = {"slug": "arcteryx.com", "location_contains": ["Vancouver", "British Columbia", ", BC", "Canada", "Remote"]}


def _post(text, loc, pid, dept="Creative", commitment="Full-time"):
    return {
        "id": pid,
        "text": text,
        "hostedUrl": f"https://jobs.lever.co/arcteryx.com/{pid}",
        "categories": {"location": loc, "department": dept, "commitment": commitment},
    }


DATA = [
    _post("Senior Brand Designer", "North Vancouver, BC", "a1"),
    _post("Graphic Designer", "Vancouver, British Columbia, Canada", "a2"),
    _post("Retail Sales Associate", "Vancouver, BC", "a3"),        # 위치는 OK지만 디자인 아님
    _post("Product Designer", "New York, United States", "a4"),    # 디자인이지만 위치 밖
]


def _client(data, status=200):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=data)))


def test_collect_ok():
    with _client(DATA) as c:
        outcome, meta, data = collect(SCFG, client=c)
    assert outcome == Outcome.OK_WITH_RESULTS and meta["total"] == 4


def test_collect_empty():
    with _client([]) as c:
        outcome, meta, data = collect(SCFG, client=c)
    assert outcome == Outcome.OK_EMPTY_TRUSTED


def test_collect_schema_error_when_not_list():
    with _client({"oops": 1}) as c:
        outcome, meta, data = collect(SCFG, client=c)
    assert outcome == Outcome.PARSE_ERROR


def test_collect_blocked_403():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403))) as c:
        outcome, meta, data = collect(SCFG, client=c)
    assert outcome == Outcome.BLOCKED


def _company():
    return Company(id="arcteryx", name="Arc'teryx", adapter=Adapter.LEVER)


def test_run_filters_location_and_design(monkeypatch):
    monkeypatch.setattr(lever, "get_lever_config", lambda cid: SCFG)
    with _client(DATA) as c:
        res = run(_company(), CFG, RunContext(client=c))
    assert res.outcome == Outcome.OK_WITH_RESULTS
    assert res.meta["located"] == 3   # a1,a2,a3 위치 통과 (a4 뉴욕 제외)
    assert res.meta["design"] == 2    # a1,a2 디자인 (a3 판매직 제외)
    titles = {m.posting.title for m in res.matches}
    assert titles == {"Senior Brand Designer", "Graphic Designer"}


def test_run_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(lever, "get_lever_config", lambda cid: None)
    res = run(_company(), CFG, RunContext())
    assert res.skipped is True
