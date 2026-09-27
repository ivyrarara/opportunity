"""오케스트레이터 — 1회 실행 = 전 회사 순회 (명세 §10-2, §9).

흐름: config → (어댑터) 취득·classify·매칭 → 신규 저장(§8) → aggregate(§5)
      → crawl_errors 기록 → 알림(§9).

run_once는 저장소/알림/어댑터/컨텍스트를 인자로 받아 테스트 가능하게 하고,
main()은 env로 실제 Firestore/Telegram을 구성한다.
"""

from __future__ import annotations

import os
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


# 한 어댑터가 이 실행에서 연속으로 이만큼 transport_error를 내면 '전체 다운'으로 보고
# 같은 어댑터의 남은 타겟은 즉시 건너뛴다(회로 차단, §6). jobkorea IP 차단처럼 소스가
# 통째로 죽었을 때 24곳×타임아웃으로 실행이 30분+ 늘어지는 낭비를 막는다.
# 첫 N곳은 실제로 시도하므로 소스가 살아있으면 차단기는 열리지 않고, 다음 실행마다 리셋된다.
_CIRCUIT_OPEN_THRESHOLD = 3


@dataclass
class RunSummary:
    companies_run: list[str] = field(default_factory=list)
    companies_skipped: list[str] = field(default_factory=list)  # 미등록 어댑터
    companies_circuit_skipped: list[str] = field(default_factory=list)  # 회로 차단으로 건너뜀
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
    # 어댑터별 연속 transport_error 카운트 / 회로가 열린(전체 다운 판정) 어댑터.
    transport_streak: dict[str, int] = {}
    open_adapters: set[str] = set()

    for company in cfg.companies:
        if only is not None and company.id not in only:
            continue
        adapter_name = company.adapter.value
        runner = adapters.get(adapter_name)
        if runner is None:
            summary.companies_skipped.append(company.id)
            continue

        # 이 어댑터의 회로가 이미 열렸으면(앞선 타겟들이 연속 실패) 호출하지 않고
        # 즉시 같은 transport_error로 기록한다 — 타임아웃×재시도 낭비를 건너뛴다.
        if adapter_name in open_adapters:
            summary.companies_circuit_skipped.append(company.id)
            summary.run_results.append(RunResult(
                company.id, Outcome.TRANSPORT_ERROR, {"reason": "circuit_open"},
                failure_tolerant=company.failure_tolerant,
                adapter=adapter_name,
            ))
            continue

        try:
            result: AdapterResult = runner(company, cfg, ctx)  # type: ignore[operator]
        except Exception as exc:  # 어댑터가 던져도 파이프라인은 계속
            result = AdapterResult(Outcome.TRANSPORT_ERROR, {"error": repr(exc)[:200]})

        # 어댑터는 있지만 이 회사 설정이 미완이면 스킵 (§7 SPA 미확정 등)
        if result.skipped:
            summary.companies_skipped.append(company.id)
            continue

        # 회로 차단기: 연속 transport_error를 세다가 임계치에 닿으면 회로를 연다.
        # 그 외 outcome(성공·정책성 차단 등)이 하나라도 나오면 스트릭을 리셋한다.
        if result.outcome == Outcome.TRANSPORT_ERROR:
            transport_streak[adapter_name] = transport_streak.get(adapter_name, 0) + 1
            if transport_streak[adapter_name] >= _CIRCUIT_OPEN_THRESHOLD:
                open_adapters.add(adapter_name)
        else:
            transport_streak[adapter_name] = 0

        summary.companies_run.append(company.id)
        summary.run_results.append(RunResult(
            company.id, result.outcome, result.meta,
            failure_tolerant=company.failure_tolerant,
            adapter=adapter_name,
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


def _build_local(cfg: TargetsConfig, data_dir: str):
    """로컬 JSON 파일 저장소 + Telegram (Firebase 없이 개인용 실행)."""
    import httpx

    from .http_client import RateLimiter
    from .notify.telegram import TelegramNotifier
    from .storage.file import (
        JsonFileCrawlErrorStore,
        JsonFilePostingStore,
        JsonFileStateStore,
    )

    posting_store = JsonFilePostingStore(data_dir)
    state_store = JsonFileStateStore(data_dir)
    error_store = JsonFileCrawlErrorStore(data_dir)
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


def _make_stdout_utf8_safe() -> None:
    """윈도우 기본 콘솔(cp949)에서 이모지·—(em-dash) 등이 크래시하지 않도록 utf-8로."""
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    import argparse

    _make_stdout_utf8_safe()

    ap = argparse.ArgumentParser(description="기회 모니터링 1회 실행 (§10-2)")
    ap.add_argument("--seed", action="store_true", help="시드 모드: 공고 알림 억제, DB만 채움(§10-7)")
    ap.add_argument("--dry-run", action="store_true", help="인메모리(저장·전송 안 함)")
    ap.add_argument("--only", nargs="*", help="특정 company id만 실행")
    ap.add_argument(
        "--store", choices=["firestore", "file"],
        default=os.getenv("OPMON_STORE", "firestore"),
        help="중복제거 저장소. file=로컬 JSON(Firebase 불필요), firestore=배포용(기본)",
    )
    ap.add_argument(
        "--data-dir", default=os.getenv("OPMON_DATA_DIR", "./opmon_data"),
        help="--store file일 때 상태 파일 디렉터리 (기본 ./opmon_data)",
    )
    args = ap.parse_args(argv)

    cfg = load_targets()
    if args.dry_run:
        posting_store, state_store, error_store, notifier, ctx = _build_dry()
    elif args.store == "file":
        posting_store, state_store, error_store, notifier, ctx = _build_local(cfg, args.data_dir)
    else:
        posting_store, state_store, error_store, notifier, ctx = _build_real(cfg)

    summary = run_once(
        cfg, posting_store=posting_store, state_store=state_store,
        error_store=error_store, notifier=notifier, ctx=ctx,
        seed=args.seed, only=args.only,
    )

    print(f"[run] 실행 {len(summary.companies_run)}곳 / 스킵(미구현 어댑터) {len(summary.companies_skipped)}곳"
          + (f" / 회로차단 스킵 {len(summary.companies_circuit_skipped)}곳"
             if summary.companies_circuit_skipped else ""))
    print(f"[run] Outcome: {summary.outcome_counts()}")
    print(f"[run] 신규 공고 {summary.new_postings}건 / "
          f"공고알림 {summary.dispatch.posting_messages_sent} "
          f"(시드억제 {summary.dispatch.suppressed_by_seed}) / "
          f"운영알림 {summary.dispatch.alert_messages_sent}")

    # dry-run: 실제로 잡혀서 "보냈을" 메시지를 콘솔에 미리보기 (검증용, 전송·저장 안 함)
    if args.dry_run:
        msgs = getattr(notifier, "messages", [])
        if msgs:
            print(f"\n[dry-run] 보냈을 메시지 {len(msgs)}건 미리보기:")
            for i, m in enumerate(msgs, 1):
                print(f"\n--- 메시지 {i} ---\n{m}")
        else:
            print("\n[dry-run] 매칭된 신규 공고 없음 (알림 메시지 0건)")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
