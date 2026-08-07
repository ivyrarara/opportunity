"""BambooHR 어댑터 테스트 (NUDESTIX, fixture 기반)."""

from __future__ import annotations

import httpx

from opmon.adapters import bamboohr
from opmon.adapters.bamboohr import collect, run
from opmon.adapters.base import RunContext
from opmon.config import Adapter, Company, load_targets
from opmon.outcomes import Outcome

CFG = load_targets()
SCFG = {"subdomain": "nudestix", "location_contains": []}


def _job(name, jid, city="Vaughan", dept="Creative"):
    return {
        "id": jid,
        "jobOpeningName": name,
        "departmentLabel": dept,
        "location": {"city": city, "state": "ON", "country": "Canada"},
        "employmentStatusLabel": "Full-Time",
    }


JOBS = [
    _job("Packaging Designer", 101),
    _job("Graphic Designer", 102),
    _job("Sales Associate", 103),   # 디자인 아님
]


def _client(data, status=200):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=data)))


def test_collect_ok():
    with _client({"result": JOBS}) as c:
        outcome, meta, items = collect(SCFG, client=c)
    assert outcome == Outcome.OK_WITH_RESULTS and meta["raw"] == 3


def test_collect_empty():
    with _client({"result": []}) as c:
        outcome, meta, items = collect(SCFG, client=c)
    assert outcome == Outcome.OK_EMPTY_TRUSTED


def test_collect_list_root():
    with _client(JOBS) as c:
        outcome, meta, items = collect(SCFG, client=c)
    assert outcome == Outcome.OK_WITH_RESULTS and meta["raw"] == 3


def test_collect_schema_error():
    with _client({"nope": 1}) as c:
        outcome, meta, items = collect(SCFG, client=c)
    assert outcome == Outcome.PARSE_ERROR


def test_collect_blocked_403():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403))) as c:
        outcome, meta, items = collect(SCFG, client=c)
    assert outcome == Outcome.BLOCKED


def _company():
    return Company(id="nudestix", name="NUDESTIX", adapter=Adapter.BAMBOOHR)


def test_run_filters_design(monkeypatch):
    monkeypatch.setattr(bamboohr, "get_bamboohr_config", lambda cid: SCFG)
    with _client({"result": JOBS}) as c:
        res = run(_company(), CFG, RunContext(client=c))
    assert res.outcome == Outcome.OK_WITH_RESULTS
    assert res.meta["design"] == 2   # Packaging/Graphic (Sales 제외)
    titles = {m.posting.title for m in res.matches}
    assert titles == {"Packaging Designer", "Graphic Designer"}
    urls = {m.posting.url for m in res.matches}
    assert "https://nudestix.bamboohr.com/careers/101" in urls


def test_run_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(bamboohr, "get_bamboohr_config", lambda cid: None)
    res = run(_company(), CFG, RunContext())
    assert res.skipped is True
