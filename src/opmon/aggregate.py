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

from .outcomes import BAD_OUTCOMES, OK_OUTCOMES, Outcome
from .state import StateStore

SUSPICIOUS_ALERT_THRESHOLD = 2   # 연속 N회 의심이면 알림 (디바운스)
FLEET_BLOCK_RATIO = 0.5          # 이번 실행 절반 이상 이상 → 전체 차단 승격
FLEET_MIN_TOTAL = 4              # 전체회사 축은 최소 이만큼 돌았을 때만 적용
# 한 소스(jobkorea 등)의 일시 차단은 조용히 넘어가고(자동 재시도·중복제거로 공고 유실 없음),
# 연속 이만큼(≈하루, 3회/일 기준) 계속 막힐 때만 "지속 차단" 경고 1회. 간헐 차단 노이즈 억제.
FLEET_SINGLE_SOURCE_SUSTAINED = 3
FLEET_STREAK_KEY = "__fleet__"   # 소스별 연속 차단 스트릭 상태 키 접두어(합성)
# 전체 fleet(50%) 미만이어도 한 어댑터에서 즉시-알림 차단이 이만큼 동시 발생하면
# 하나로 묶는다(예: Workday 6곳이 러너 IP 차단으로 동시에 expected_json_got_html).
ADAPTER_BLOCK_GROUP_MIN = 3
# 즉시 알림(디바운스 없음) 대상 차단 Outcome — 어댑터 그룹핑도 이들만 대상으로.
_IMMEDIATE_BLOCK_OUTCOMES = frozenset({Outcome.BLOCKED, Outcome.RATE_LIMITED, Outcome.CHALLENGE})
BASELINE_WINDOW = 5              # baseline 중앙값 계산 창
INFO_BASELINE_MIN = 3            # 평소 공고가 이 이상이던 회사가 0건이면 info


@dataclass
class RunResult:
    """어댑터 1회 실행 결과 (classifier 산출)."""

    company_id: str
    outcome: Outcome
    meta: dict[str, Any] = field(default_factory=dict)
    # 실패 허용 회사(§4 현대차 등): 실패가 전체차단 비율 계산에서 제외되고 알림도 억제된다.
    failure_tolerant: bool = False
    adapter: str = ""  # 실패가 한 소스(호스트)에 몰렸는지 판정용 (전체차단 vs 단일소스 일시실패)


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
    # 실패 허용 회사는 전체차단 비율 계산에서 제외 (기대된 실패가 fleet 판정을 오염시키지 않도록).
    scored = [r for r in run_results if not r.failure_tolerant]
    total = len(scored)
    bad = [r for r in scored if r.outcome in BAD_OUTCOMES]

    # 소스 회복 감지: 이번 실행에서 OK가 하나라도 난 어댑터는 연속 차단 스트릭을 0으로 리셋.
    for ad in {r.adapter for r in scored if r.outcome in OK_OUTCOMES and r.adapter}:
        fk = FLEET_STREAK_KEY + ad
        if state_store.get(fk).consecutive_suspicious:
            state_store.update(fk, consecutive_suspicious=0)

    # 전체회사 축: 다수 동시 실패/의심 → 승격, 개별 알림 억제.
    # 단, 실패가 한 소스(어댑터/호스트)에 몰렸으면 "사이트 전체 차단"이 아니라
    # "그 소스 일시 실패"다 (예: jobkorea가 클라우드 IP를 간헐 차단하면 다수가
    # 동시 실패하지만 나머지 소스는 멀쩡). 이 경우는 조용히 로그만 남기고,
    # 연속 FLEET_SINGLE_SOURCE_SUSTAINED회(≈하루) 지속될 때만 경고 1회.
    if total >= FLEET_MIN_TOTAL and len(bad) / total >= FLEET_BLOCK_RATIO:
        # 실패가 한 소스(어댑터)에 '지배적으로' 몰렸으면 사이트 전체 차단이 아니라
        # 그 소스 일시 차단이다. 지배 소스 하나가 fleet 임계를 홀로 넘으면
        # (그 어댑터만으로 ratio 초과) 단일소스로 처리한다 — jobkorea(24곳)가 IP
        # 차단당한 실행에 다른 어댑터의 산발 실패 1~2건이 섞였다고 critical 전체차단으로
        # 오탐하지 않는다. 실패가 여러 어댑터에 고르게 퍼졌을 때만 전체차단으로 승격.
        bad_by_adapter: dict[str, int] = {}
        for r in bad:
            if r.adapter:
                bad_by_adapter[r.adapter] = bad_by_adapter.get(r.adapter, 0) + 1
        dom_adapter, dom_count = (
            max(bad_by_adapter.items(), key=lambda kv: kv[1]) if bad_by_adapter else (None, 0)
        )
        if dom_adapter is not None and dom_count / total >= FLEET_BLOCK_RATIO:
            fk = FLEET_STREAK_KEY + dom_adapter
            streak = state_store.get(fk).consecutive_suspicious + 1
            state_store.update(fk, consecutive_suspicious=streak)
            # 간헐 차단(streak < 임계)은 무음. 지속 차단으로 넘어가는 순간에만 1회 경고.
            if streak == FLEET_SINGLE_SOURCE_SUSTAINED:
                actions.append(_alert(
                    None, "warn",
                    f"⚠️ '{dom_adapter}' 소스 {streak}회 연속 차단(≈하루 지속): {dom_count}/{total}곳 "
                    f"동시 실패. 간헐 차단이 아니라 지속 차단 의심 — 소스 상태 확인 필요",
                ))
        else:
            actions.append(_alert(
                None, "critical",
                f"⚠️ 전체 차단 의심: {len(bad)}/{total} 실패/의심 "
                f"({len(bad_by_adapter) or '?'}개 소스 · 개별 알림 억제)",
            ))
        actions += [_log(r.company_id, r.outcome, r.meta) for r in run_results]
        return actions

    # 어댑터 단위 차단 클러스터(전체 fleet 미만): 한 어댑터에서 즉시-알림 차단이
    # ADAPTER_BLOCK_GROUP_MIN곳 이상 동시 발생하면(예: Workday 6곳이 러너 IP 차단으로
    # 동시에 expected_json_got_html) 하나로 묶는다. jobkorea와 동일하게 간헐은 무음,
    # 연속 지속(≈하루)일 때만 1회 경고 → 개별 차단 알림 폭탄 방지.
    grouped_ids: set[str] = set()
    block_by_adapter: dict[str, list[RunResult]] = {}
    for r in scored:
        if r.adapter and r.outcome in _IMMEDIATE_BLOCK_OUTCOMES:
            block_by_adapter.setdefault(r.adapter, []).append(r)
    for adapter, rs in block_by_adapter.items():
        if len(rs) < ADAPTER_BLOCK_GROUP_MIN:
            continue  # 1~2곳 산발 차단은 개별 처리(스팸 아님)
        fk = FLEET_STREAK_KEY + adapter
        streak = state_store.get(fk).consecutive_suspicious + 1
        state_store.update(fk, consecutive_suspicious=streak)
        for r in rs:
            actions.append(_log(r.company_id, r.outcome, r.meta))
            grouped_ids.add(r.company_id)
        if streak == FLEET_SINGLE_SOURCE_SUSTAINED:
            reason = rs[0].meta.get("reason") or rs[0].outcome.value
            actions.append(_alert(
                None, "warn",
                f"⚠️ '{adapter}' 소스 {streak}회 연속 차단(≈하루 지속): {len(rs)}곳 "
                f"동시 차단({reason}). 간헐 차단이 아니라 지속 차단 의심 — 소스 상태 확인 필요",
            ))

    for r in run_results:
        cid, outcome, meta = r.company_id, r.outcome, r.meta
        if cid in grouped_ids:
            continue  # 어댑터 그룹핑에서 이미 로그·처리됨(개별 알림 억제)
        st = state_store.get(cid)

        # 실패 허용 회사: 실패 Outcome은 감사 로그만 남기고 알림·카운터 조작 없음 (조용히 허용).
        if r.failure_tolerant and outcome not in OK_OUTCOMES:
            actions.append(_log(cid, outcome, meta))
            continue

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
