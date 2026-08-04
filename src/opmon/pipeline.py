"""오케스트레이터 — 1회 실행 = 전 회사 순회 (명세 §10-2, §9).

흐름: config → (어댑터) 취득·classify·매칭 → 신규 저장(§8) → aggregate(§5)
      → crawl_errors 기록 → 알림(§9).

run_once는 저장소/알림/어댑터/컨텍스트를 인자로 받아 테스트 가능하게 하고,
main()은 env로 실제 Firestore/Telegram을 구성한다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from .adapters.base import AdapterResult, RunContext
from .adapters.registry import REGISTRY
from .aggregate import Action, RunResult, aggregate
from .config import TargetsConfig, load_targets
from .dedup import persist_error_actions, store_new_postings
from .models import PostingRecord
from .notify.base import Notifier
from .notify.dispatch import DispatchResult, send_notifications
from .outcomes import Outcome
from .state import StateStore
from .storage.base import CrawlErrorStore, PostingStore


@dataclass
class RunSummary:
    companies_run: list[str] = field(default_factory=list)
    companies_skipped: list[str] = field(default_factory=list)  # 미등록 어댑터
    run_results: list[RunResult] = field(default_factory=list)
    new_postings: int = 0
    actions: list[Action] = field(default_factory=list)
    dispatch: DispatchResult = field(default_factory=DispatchResult)

    def outcome_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.run_results:
            counts[r.outcome.value] = counts.get(r.outcome.value, 0) + 1
        return counts


def run_once(
    cfg: TargetsConfig,
    *,
    posting_store: PostingStore,
    state_store: StateStore,
    error_store: CrawlErrorStore,
    notifier: Notifier,
    ctx: RunContext,
    adapters: dict[str, "object"] = REGISTRY,
    seed: bool = False,
    now: Callable[[], float] = time.time,
    only: list[str] | None = None,
) -> RunSummary:
    """전 회사 1회 실행. only가 주어지면 해당 company id만."""
    summary = RunSummary()
    all_records: list[PostingRecord] = []

    for company in cfg.companies:
        if only is not None and company.id not in only:
            continue
        runner = adapters.get(company.adapter.value)
        if runner is None:
            summary.companies_skipped.append(company.id)
            continue

        try:
            result: AdapterResult = runner(company, cfg, ctx)  # type: ignore[operator]
        except Exception as exc:  # 어댑터가 던져도 파이프라인은 계속
            result = AdapterResult(Outcome.TRANSPORT_ERROR, {"error": repr(exc)[:200]})

        # 어댑터는 있지만 이 회사 설정이 미완이면 스킵 (§7 SPA 미확정 등)
        if result.skipped:
            summary.companies_skipped.append(company.id)
            continue

        summary.companies_run.append(company.id)
        summary.run_results.append(RunResult(
            company.id, result.outcome, result.meta,
            failure_tolerant=company.failure_tolerant,
        ))
        all_records.extend(PostingRecord.from_match(m, company.id) for m in result.matches)

    # 신규 저장 (§8-1)
    new_records = store_new_postings(all_records, posting_store, now=now)
    summary.new_postings = len(new_records)

    # 이력·전체회사 교차검증 (§5-4) + 감사 로그 (§5-5)
    actions = aggregate(summary.run_results, state_store, now=now)
    summary.actions = actions
    persist_error_actions(actions, error_store, now=now)

    # 알림 (§9). 시드 모드면 공고 알림 억제.
    summary.dispatch = send_notifications(new_records, actions, cfg, notifier, seed=seed)
    return summary


# --- CLI / 실제 구성 -----------------------------------------------------


def _build_real(cfg: TargetsConfig):
    """env 기반 Firestore + Telegram 구성 (배포용)."""
    import httpx

    from .http_client import RateLimiter
    from .notify.telegram import TelegramNotifier
    from .storage.firestore import (
        FirestoreCrawlErrorStore,
        FirestorePostingStore,
        FirestoreStateStore,
        firestore_client,
    )

    client = firestore_client()
    posting_store = FirestorePostingStore(client)
    state_store = FirestoreStateStore(client)
    error_store = FirestoreCrawlErrorStore(client)
    notifier = TelegramNotifier.from_env()
    ctx = RunContext(rate_limiter=RateLimiter(), client=httpx.Client(follow_redirects=True, timeout=15.0))
    return posting_store, state_store, error_store, notifier, ctx


def _build_dry():
    """인메모리 구성 (드라이런). 알림·저장은 수집만."""
    from .http_client import RateLimiter
    from .notify.memory import InMemoryNotifier
    from .state import InMemoryStateStore
    from .storage.memory import InMemoryCrawlErrorStore, InMemoryPostingStore

    return (
        InMemoryPostingStore(),
        InMemoryStateStore(),
        InMemoryCrawlErrorStore(),
        InMemoryNotifier(),
        RunContext(rate_limiter=RateLimiter()),
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="기회 모니터링 1회 실행 (§10-2)")
    ap.add_argument("--seed", action="store_true", help="시드 모드: 공고 알림 억제, DB만 채움(§10-7)")
    ap.add_argument("--dry-run", action="store_true", help="인메모리(저장·전송 안 함)")
    ap.add_argument("--only", nargs="*", help="특정 company id만 실행")
    args = ap.parse_args(argv)

    cfg = load_targets()
    if args.dry_run:
        posting_store, state_store, error_store, notifier, ctx = _build_dry()
    else:
        posting_store, state_store, error_store, notifier, ctx = _build_real(cfg)

    summary = run_once(
        cfg, posting_store=posting_store, state_store=state_store,
        error_store=error_store, notifier=notifier, ctx=ctx,
        seed=args.seed, only=args.only,
    )

    print(f"[run] 실행 {len(summary.companies_run)}곳 / 스킵(미구현 어댑터) {len(summary.companies_skipped)}곳")
    print(f"[run] Outcome: {summary.outcome_counts()}")
    print(f"[run] 신규 공고 {summary.new_postings}건 / "
          f"공고알림 {summary.dispatch.posting_messages_sent} "
          f"(시드억제 {summary.dispatch.suppressed_by_seed}) / "
          f"운영알림 {summary.dispatch.alert_messages_sent}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
