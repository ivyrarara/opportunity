"""현대차 NetFunnel 어댑터 (명세 §4, §11 — 맨 마지막·실패 허용).

현대차 채용은 NetFunnel 대기열(트래픽 제어) 뒤에 있어 가장 취약하다.
대기열/세션 토큰 처리가 필요하고, 실패해도 전체 파이프라인에 영향을 주면 안 된다.
config의 `failure_tolerant: true`가 그 격리를 담당한다(aggregate에서 fleet 제외 + 알림 억제).

현재는 NetFunnel 대기열 감지까지 구현. 실제 대기열 통과·상세 파싱은 네트워크 실측 후 확장한다.
URL이 확정되지 않으면(targets.json urls 비어있음) skip 한다.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import Company, TargetsConfig
from ..http_client import REAL_BROWSER_HEADERS, fetch
from ..outcomes import Outcome
from .base import AdapterResult, RunContext

# NetFunnel 대기열/트래픽 제어 페이지 마커 [검증필요]
NETFUNNEL_MARKERS = ["NetFunnel", "nf_service", "대기하고 계십니다", "접속 대기", "혼잡", "잠시만 기다"]


def classify_netfunnel(resp: httpx.Response | None, exc: Exception | None) -> tuple[Outcome, dict[str, Any]]:
    """NetFunnel 응답 분류. 대기열이면 CHALLENGE로 (봇 챌린지와 동일 취급)."""
    if exc is not None:
        return Outcome.TRANSPORT_ERROR, {"error": repr(exc)[:200]}
    if resp is None:
        return Outcome.TRANSPORT_ERROR, {"error": "no_response"}
    st = resp.status_code
    if st == 429:
        return Outcome.RATE_LIMITED, {"status": st}
    if st in (401, 403):
        return Outcome.BLOCKED, {"status": st}
    if st >= 500:
        return Outcome.TRANSPORT_ERROR, {"status": st}
    body = resp.text or ""
    if any(m in body for m in NETFUNNEL_MARKERS):
        return Outcome.CHALLENGE, {"reason": "netfunnel_queue"}
    # 대기열은 아니지만 상세 파싱 미구현 → 의심(실패 허용이라 조용히 로그만 됨)
    return Outcome.SUSPICIOUS_EMPTY, {"reason": "netfunnel_parsing_not_implemented"}


def run(company: Company, cfg: TargetsConfig, ctx: RunContext) -> AdapterResult:
    if not company.urls:
        return AdapterResult(
            Outcome.SUSPICIOUS_EMPTY, {"reason": "url_not_configured"},
            skipped=True, skip_reason="현대차 채용 URL 미확정",
        )
    if ctx.rate_limiter is not None:
        ctx.rate_limiter.wait()
    resp, exc = fetch(company.urls[0], headers=REAL_BROWSER_HEADERS, client=ctx.client)
    outcome, meta = classify_netfunnel(resp, exc)
    # 상세 공고 추출은 대기열 통과 로직 실측 후. 지금은 outcome 판정까지(실패 허용).
    return AdapterResult(outcome=outcome, meta=meta)
