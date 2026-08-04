"""aggregator(§5-4) · 디바운스(§5-5) · state(§8-2) 테스트."""

from __future__ import annotations

from opmon.aggregate import (
    FLEET_BLOCK_RATIO,
    RunResult,
    aggregate,
    roll_median,
)
from opmon.outcomes import Outcome
from opmon.state import CrawlState, InMemoryStateStore

CLOCK = lambda: 1000.0  # noqa: E731  결정적 시각


def _alerts(actions):
    return [a for a in actions if a.kind == "alert"]


def _logs(actions):
    return [a for a in actions if a.kind == "log"]


def _run(store, *results):
    return aggregate(list(results), store, now=CLOCK)


# --- roll_median --------------------------------------------------------


def test_roll_median_windowed():
    baseline, recent = roll_median([], 10)
    assert baseline == 10 and recent == [10]
    baseline, recent = roll_median([10, 20], 30)
    assert baseline == 20 and recent == [10, 20, 30]


def test_roll_median_caps_window():
    _, recent = roll_median([1, 2, 3, 4, 5], 6, window=5)
    assert recent == [2, 3, 4, 5, 6]


# --- OK_WITH_RESULTS: baseline 갱신, 무알림 -----------------------------


def test_ok_with_results_updates_baseline_no_alert():
    store = InMemoryStateStore()
    actions = _run(store, RunResult("nhn", Outcome.OK_WITH_RESULTS, {"count": 6}))
    assert _alerts(actions) == []
    st = store.get("nhn")
    assert st.baseline_count == 6
    assert st.last_ok_ts == 1000.0
    assert st.consecutive_suspicious == 0


# --- SUSPICIOUS_EMPTY 디바운스 (2회부터) --------------------------------


def test_suspicious_debounce_first_no_alert_second_alerts():
    store = InMemoryStateStore()
    a1 = _run(store, RunResult("nhn", Outcome.SUSPICIOUS_EMPTY, {"reason": "no_page_anchor"}))
    assert _logs(a1) and _alerts(a1) == []        # 1회: 로그만
    assert store.get("nhn").consecutive_suspicious == 1

    a2 = _run(store, RunResult("nhn", Outcome.SUSPICIOUS_EMPTY, {"reason": "no_page_anchor"}))
    assert len(_alerts(a2)) == 1                    # 2회: 알림
    assert _alerts(a2)[0].severity == "warn"
    assert store.get("nhn").consecutive_suspicious == 2


# --- 즉시 알림: BLOCKED / PARSE_ERROR -----------------------------------


def test_blocked_immediate_alert():
    store = InMemoryStateStore()
    actions = _run(store, RunResult("nhn", Outcome.BLOCKED, {"status": 403}))
    assert len(_alerts(actions)) == 1
    assert len(_logs(actions)) == 1


def test_parse_error_immediate_alert():
    store = InMemoryStateStore()
    actions = _run(store, RunResult("nhn", Outcome.PARSE_ERROR, {"declared": 12, "parsed": 3}))
    assert len(_alerts(actions)) == 1  # n=1이어도 PARSE_ERROR는 즉시


def test_transport_error_debounced():
    store = InMemoryStateStore()
    a1 = _run(store, RunResult("nhn", Outcome.TRANSPORT_ERROR, {"error": "timeout"}))
    assert _alerts(a1) == []            # 1회: 무알림
    a2 = _run(store, RunResult("nhn", Outcome.TRANSPORT_ERROR, {"error": "timeout"}))
    assert len(_alerts(a2)) == 1        # 2회: 알림


# --- 회복 시 카운터 리셋 -------------------------------------------------


def test_recovery_resets_suspicious_counter():
    store = InMemoryStateStore()
    _run(store, RunResult("nhn", Outcome.SUSPICIOUS_EMPTY, {"reason": "x"}))
    assert store.get("nhn").consecutive_suspicious == 1
    _run(store, RunResult("nhn", Outcome.OK_WITH_RESULTS, {"count": 5}))
    assert store.get("nhn").consecutive_suspicious == 0


# --- OK_EMPTY_TRUSTED info 알림 (평소 공고 많던 회사가 0건) --------------


def test_empty_trusted_info_alert_when_baseline_high():
    store = InMemoryStateStore()
    store.update("nhn", baseline_count=5)
    actions = _run(store, RunResult("nhn", Outcome.OK_EMPTY_TRUSTED, {"count": 0}))
    alerts = _alerts(actions)
    assert len(alerts) == 1 and alerts[0].severity == "info"
    assert store.get("nhn").consecutive_zero == 1


def test_empty_trusted_no_info_when_low_baseline():
    store = InMemoryStateStore()
    store.update("nhn", baseline_count=1)
    actions = _run(store, RunResult("nhn", Outcome.OK_EMPTY_TRUSTED, {"count": 0}))
    assert _alerts(actions) == []


def test_empty_trusted_info_only_first_zero():
    store = InMemoryStateStore()
    store.update("nhn", baseline_count=5, consecutive_zero=1)  # 이미 한 번 0건
    actions = _run(store, RunResult("nhn", Outcome.OK_EMPTY_TRUSTED, {"count": 0}))
    assert _alerts(actions) == []  # 두 번째 0건은 조용히


# --- 전체회사 축: 전체 차단 승격 ----------------------------------------


def test_fleet_block_suppresses_individual_alerts():
    store = InMemoryStateStore()
    results = [
        RunResult("a", Outcome.BLOCKED, {"status": 403}),
        RunResult("b", Outcome.SUSPICIOUS_EMPTY, {"reason": "x"}),
        RunResult("c", Outcome.TRANSPORT_ERROR, {"error": "t"}),
        RunResult("d", Outcome.OK_WITH_RESULTS, {"count": 3}),
    ]
    actions = _run(store, *results)
    alerts = _alerts(actions)
    assert len(alerts) == 1
    assert alerts[0].severity == "critical"
    assert "전체 차단" in alerts[0].text
    # 개별 알림은 억제, 전 회사 로그는 남음
    assert len(_logs(actions)) == 4


def test_no_fleet_when_below_ratio():
    store = InMemoryStateStore()
    results = [
        RunResult("a", Outcome.BLOCKED, {"status": 403}),
        RunResult("b", Outcome.OK_WITH_RESULTS, {"count": 3}),
        RunResult("c", Outcome.OK_WITH_RESULTS, {"count": 4}),
        RunResult("d", Outcome.OK_WITH_RESULTS, {"count": 5}),
    ]
    actions = _run(store, *results)
    # bad ratio 1/4 < 0.5 → 개별 처리 (blocked 즉시 알림 1건)
    assert len(_alerts(actions)) == 1
    assert _alerts(actions)[0].company_id == "a"


def test_fleet_ratio_constant_is_half():
    assert FLEET_BLOCK_RATIO == 0.5


# --- state store --------------------------------------------------------


def test_state_store_default_and_merge():
    store = InMemoryStateStore()
    assert store.get("x") == CrawlState()
    store.update("x", baseline_count=7)
    store.update("x", consecutive_zero=2)
    st = store.get("x")
    assert st.baseline_count == 7 and st.consecutive_zero == 2  # 병합 유지
