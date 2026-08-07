"""6단계: 오케스트레이터 배선 테스트."""

from __future__ import annotations

from opmon.adapters.base import AdapterResult, RunContext
from opmon.config import load_targets
from opmon.models import MatchResult, Posting
from opmon.notify.memory import InMemoryNotifier
from opmon.outcomes import Outcome
from opmon.pipeline import run_once
from opmon.state import InMemoryStateStore
from opmon.storage.memory import InMemoryCrawlErrorStore, InMemoryPostingStore

CFG = load_targets()
CLOCK = lambda: 500.0  # noqa: E731


def _match(job_id="1", category="AI", title="AI 기획자", exp_ok=True):
    return MatchResult(
        posting=Posting(job_id=job_id, title=title, url=f"https://x/{job_id}"),
        category=category, matched_keywords=["AI"], highlights=[], min_experience_ok=exp_ok,
    )


def _stores():
    return dict(
        posting_store=InMemoryPostingStore(),
        state_store=InMemoryStateStore(),
        error_store=InMemoryCrawlErrorStore(),
        notifier=InMemoryNotifier(),
        ctx=RunContext(),
    )


def _run(adapters, *, only=None, seed=False, stores=None, now=CLOCK):
    s = stores or _stores()
    summary = run_once(CFG, adapters=adapters, only=only, seed=seed, now=now, **s)
    return summary, s


# --- 정상 매칭: 저장 + 알림 ---------------------------------------------


def test_ok_with_match_stores_and_alerts():
    adapters = {"jobkorea": lambda c, cfg, ctx: AdapterResult(Outcome.OK_WITH_RESULTS, {"count": 1}, [_match()])}
    summary, s = _run(adapters, only=["nhn"])
    assert summary.companies_run == ["nhn"]
    assert summary.new_postings == 1
    assert len(s["posting_store"]) == 1
    assert summary.dispatch.posting_messages_sent == 1
    # baseline 갱신됨
    assert s["state_store"].get("nhn").baseline_count == 1


def test_seed_suppresses_posting_alert_but_stores():
    adapters = {"jobkorea": lambda c, cfg, ctx: AdapterResult(Outcome.OK_WITH_RESULTS, {"count": 1}, [_match()])}
    summary, s = _run(adapters, only=["nhn"], seed=True)
    assert summary.new_postings == 1          # 저장은 됨
    assert len(s["posting_store"]) == 1
    assert summary.dispatch.posting_messages_sent == 0
    assert summary.dispatch.suppressed_by_seed == 1


def test_dedup_across_runs():
    store = _stores()
    adapters = {"jobkorea": lambda c, cfg, ctx: AdapterResult(Outcome.OK_WITH_RESULTS, {"count": 1}, [_match()])}
    _run(adapters, only=["nhn"], stores=store)
    summary2, _ = _run(adapters, only=["nhn"], stores=store)
    assert summary2.new_postings == 0          # 같은 job_id → 신규 아님
    assert summary2.dispatch.posting_messages_sent == 0


# --- 차단: alert + crawl_errors -----------------------------------------


def test_blocked_logs_and_alerts():
    adapters = {"jobkorea": lambda c, cfg, ctx: AdapterResult(Outcome.BLOCKED, {"status": 403})}
    summary, s = _run(adapters, only=["nhn"])
    assert summary.new_postings == 0
    assert summary.dispatch.alert_messages_sent == 1
    assert len(s["error_store"].entries) == 1
    assert s["error_store"].entries[0].outcome == "blocked"


# --- 미등록 어댑터 스킵 --------------------------------------------------


def test_unregistered_adapter_skipped():
    adapters = {"jobkorea": lambda c, cfg, ctx: AdapterResult(Outcome.OK_WITH_RESULTS, {"count": 0}, [])}
    summary, _ = _run(adapters, only=["skt"])  # skt=generic_list, 미등록
    assert summary.companies_run == []
    assert summary.companies_skipped == ["skt"]


# --- 어댑터 예외 → TRANSPORT_ERROR --------------------------------------


def test_adapter_exception_becomes_transport_error():
    def boom(c, cfg, ctx):
        raise RuntimeError("kaboom")

    summary, s = _run({"jobkorea": boom}, only=["nhn"])
    assert summary.run_results[0].outcome == Outcome.TRANSPORT_ERROR
    assert "kaboom" in summary.run_results[0].meta["error"]


# --- 전체 차단 승격 ------------------------------------------------------


def test_fleet_block_single_critical_alert():
    adapters = {"jobkorea": lambda c, cfg, ctx: AdapterResult(Outcome.BLOCKED, {"status": 403})}
    four = ["nhn", "tossbank", "loreal", "hybe"]  # 모두 jobkorea
    summary, s = _run(adapters, only=four)
    alerts = [a for a in summary.actions if a.kind == "alert"]
    assert len(alerts) == 1
    assert alerts[0].severity == "critical"
    assert s["notifier"].messages[0].startswith("⚠️ 전체 차단 의심")
    # 전 회사 로그는 남음
    assert len(s["error_store"].entries) == 4
