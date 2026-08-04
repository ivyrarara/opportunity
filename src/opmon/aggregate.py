"""Aggregator — 이력·전체회사 교차검증 (명세 §5-4, §5-5).

단일 SUSPICIOUS_EMPTY는 애매하다. 두 축으로 승격/억제한다:
  - 이력 축: 회사별 baseline_count 대비 급락·연속 의심 → 디바운스 후 알림.
  - 전체회사 축: 한 실행에서 다수가 동시에 0/실패 → 사이트 전체 차단으로 승격, 개별 억제.

반환은 Action 목록(log/alert). 실제 기록(crawl_errors)·전송(텔레그램)은 상위 단계가 수행.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .outcomes import BAD_OUTCOMES, Outcome
from .state import StateStore

SUSPICIOUS_ALERT_THRESHOLD = 2   # 연속 N회 의심이면 알림 (디바운스)
FLEET_BLOCK_RATIO = 0.5          # 이번 실행 절반 이상 이상 → 전체 차단 승격
FLEET_MIN_TOTAL = 4              # 전체회사 축은 최소 이만큼 돌았을 때만 적용
BASELINE_WINDOW = 5              # baseline 중앙값 계산 창
INFO_BASELINE_MIN = 3            # 평소 공고가 이 이상이던 회사가 0건이면 info


@dataclass
class RunResult:
    """어댑터 1회 실행 결과 (classifier 산출)."""

    company_id: str
    outcome: Outcome
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Action:
    """aggregator 산출. kind='log'는 crawl_errors 기록, kind='alert'는 텔레그램 전송."""

    kind: str  # "log" | "alert"
    company_id: str | None
    outcome: Outcome | None = None
    meta: dict[str, Any] | None = None
    severity: str | None = None  # alert: "info" | "warn" | "critical"
    text: str | None = None      # alert 본문


def _log(company_id: str | None, outcome: Outcome | None, meta: dict[str, Any] | None) -> Action:
    return Action(kind="log", company_id=company_id, outcome=outcome, meta=meta)


def _alert(company_id: str | None, severity: str, text: str, outcome: Outcome | None = None) -> Action:
    return Action(kind="alert", company_id=company_id, severity=severity, text=text, outcome=outcome)


def roll_median(recent: list[int], new_count: int, window: int = BASELINE_WINDOW) -> tuple[int, list[int]]:
    """최근 성공 카운트 창에 new_count를 넣고 (중앙값, 갱신된 창)을 반환."""
    counts = (list(recent) + [new_count])[-window:]
    return int(statistics.median(counts)), counts


def aggregate(
    run_results: list[RunResult],
    state_store: StateStore,
    *,
    now: Callable[[], float] = time.time,
) -> list[Action]:
    """실행 결과 목록 → Action 목록. 상태를 갱신하며 디바운스를 적용한다."""
    actions: list[Action] = []
    total = len(run_results)
    bad = [r for r in run_results if r.outcome in BAD_OUTCOMES]

    # 전체회사 축: 다수 동시 실패/의심 → 사이트 전체 차단으로 승격, 개별 알림 억제.
    if total >= FLEET_MIN_TOTAL and len(bad) / total >= FLEET_BLOCK_RATIO:
        actions.append(_alert(
            None, "critical",
            f"⚠️ 전체 차단 의심: {len(bad)}/{total} 실패/의심 (개별 알림 억제)",
        ))
        actions += [_log(r.company_id, r.outcome, r.meta) for r in run_results]
        return actions

    for r in run_results:
        cid, outcome, meta = r.company_id, r.outcome, r.meta
        st = state_store.get(cid)

        if outcome == Outcome.OK_WITH_RESULTS:
            count = int(meta.get("count", meta.get("parsed", 0)))
            baseline, recent = roll_median(st.recent_counts, count)
            state_store.update(
                cid, baseline_count=baseline, recent_counts=recent,
                last_ok_ts=now(), consecutive_suspicious=0, consecutive_zero=0,
            )

        elif outcome in (Outcome.OK_EMPTY_TRUSTED, Outcome.RENDER_EMPTY_STATE):
            zero = st.consecutive_zero + 1
            if (st.baseline_count or 0) >= INFO_BASELINE_MIN and zero == 1:
                actions.append(_alert(
                    cid, "info",
                    f"ℹ️ {cid}: 평소 ~{st.baseline_count}건이던 공고가 0건(사이트 정상). 소진 가능성",
                    outcome,
                ))
            state_store.update(cid, consecutive_zero=zero, consecutive_suspicious=0, last_ok_ts=now())

        elif outcome == Outcome.SUSPICIOUS_EMPTY:
            n = st.consecutive_suspicious + 1
            state_store.update(cid, consecutive_suspicious=n)
            actions.append(_log(cid, outcome, meta))
            if n >= SUSPICIOUS_ALERT_THRESHOLD:
                actions.append(_alert(
                    cid, "warn",
                    f"⚠️ {cid}: {n}회 연속 정체불명 0건 ({meta.get('reason')}). 셀렉터/구조 확인 필요",
                    outcome,
                ))

        elif outcome in (Outcome.BLOCKED, Outcome.RATE_LIMITED, Outcome.CHALLENGE):
            # 즉시 알림 (디바운스 없음)
            actions.append(_log(cid, outcome, meta))
            actions.append(_alert(
                cid, "warn",
                f"⚠️ {cid} 차단({outcome.value}): {meta.get('status', '')} {meta.get('reason', '')}".strip(),
                outcome,
            ))

        else:  # TRANSPORT_ERROR, PARSE_ERROR, RENDER_TIMEOUT
            actions.append(_log(cid, outcome, meta))
            n = st.consecutive_suspicious + 1
            state_store.update(cid, consecutive_suspicious=n)
            # PARSE_ERROR는 즉시, 나머지는 연속 2회부터 (§5-5)
            if outcome == Outcome.PARSE_ERROR or n >= SUSPICIOUS_ALERT_THRESHOLD:
                detail = str(meta.get("error", meta.get("reason", "")))[:120]
                actions.append(_alert(cid, "warn", f"⚠️ {cid} {outcome.value}: {detail}", outcome))

    return actions
