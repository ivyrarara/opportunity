"""9단계: 현대차 NetFunnel 어댑터 + 실패 허용 격리 테스트."""

from __future__ import annotations

import httpx

from opmon.adapters.base import RunContext
from opmon.adapters.hyundai import classify_netfunnel, run
from opmon.aggregate import RunResult, aggregate
from opmon.config import load_targets
from opmon.outcomes import Outcome
from opmon.state import InMemoryStateStore

CFG = load_targets()
CLOCK = lambda: 1.0  # noqa: E731


def _alerts(actions):
    return [a for a in actions if a.kind == "alert"]


# --- config: hyundai는 실패 허용 -----------------------------------------


def test_hyundai_is_failure_tolerant():
    assert CFG.get_company("hyundai").failure_tolerant is True


# --- classify_netfunnel -------------------------------------------------


def test_netfunnel_queue_is_challenge():
    resp = httpx.Response(200, text="<html>NetFunnel 접속 대기 중입니다</html>")
    o, m = classify_netfunnel(resp, None)
    assert o == Outcome.CHALLENGE and m["reason"] == "netfunnel_queue"


def test_netfunnel_403_blocked():
    assert classify_netfunnel(httpx.Response(403), None)[0] == Outcome.BLOCKED


def test_netfunnel_transport_exc():
    assert classify_netfunnel(None, httpx.ConnectError("x"))[0] == Outcome.TRANSPORT_ERROR


def test_netfunnel_non_queue_suspicious():
    o, m = classify_netfunnel(httpx.Response(200, text="<html>normal</html>"), None)
    assert o == Outcome.SUSPICIOUS_EMPTY


# --- run: URL 없으면 skip ------------------------------------------------


def test_run_skips_without_url():
    res = run(CFG.get_company("hyundai"), CFG, RunContext())
    assert res.skipped is True
    assert "URL 미확정" in res.skip_reason


# --- 실패 허용 격리 (aggregate) -----------------------------------------


def test_tolerant_failure_logs_only_no_alert():
    store = InMemoryStateStore()
    results = [RunResult("hyundai", Outcome.CHALLENGE, {"reason": "netfunnel_queue"}, failure_tolerant=True)]
    actions = aggregate(results, store, now=CLOCK)
    assert _alerts(actions) == []                       # 알림 억제
    assert [a.kind for a in actions] == ["log"]          # 감사 로그만
    # 카운터도 건드리지 않음
    assert store.get("hyundai").consecutive_suspicious == 0


def test_tolerant_excluded_from_fleet_ratio():
    store = InMemoryStateStore()
    # 정상 회사 3곳 OK + 현대차 1곳 실패 → tolerant 제외하면 bad 0/3 → 전체차단 아님
    results = [
        RunResult("a", Outcome.OK_WITH_RESULTS, {"count": 1}),
        RunResult("b", Outcome.OK_WITH_RESULTS, {"count": 1}),
        RunResult("c", Outcome.OK_WITH_RESULTS, {"count": 1}),
        RunResult("hyundai", Outcome.BLOCKED, {"status": 403}, failure_tolerant=True),
    ]
    actions = aggregate(results, store, now=CLOCK)
    crit = [a for a in actions if a.kind == "alert" and a.severity == "critical"]
    assert crit == []                                    # 전체차단 승격 안 됨
    # 현대차는 로그만
    hy_logs = [a for a in actions if a.company_id == "hyundai" and a.kind == "log"]
    assert len(hy_logs) == 1


def test_tolerant_does_not_mask_real_fleet_block():
    store = InMemoryStateStore()
    # 정상 회사 4곳 모두 차단 + 현대차 실패 → scored 4곳 전부 bad → 전체차단 승격
    results = [
        RunResult("a", Outcome.BLOCKED, {"status": 403}),
        RunResult("b", Outcome.BLOCKED, {"status": 403}),
        RunResult("c", Outcome.TRANSPORT_ERROR, {"error": "t"}),
        RunResult("d", Outcome.SUSPICIOUS_EMPTY, {"reason": "x"}),
        RunResult("hyundai", Outcome.CHALLENGE, {}, failure_tolerant=True),
    ]
    actions = aggregate(results, store, now=CLOCK)
    crit = [a for a in actions if a.kind == "alert" and a.severity == "critical"]
    assert len(crit) == 1                                # 진짜 전체차단은 여전히 감지
    assert "4/4" in crit[0].text                          # 현대차 제외한 4곳 기준
