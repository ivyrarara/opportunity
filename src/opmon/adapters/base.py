"""어댑터 공통 인터페이스 (명세 §4).

어댑터는 회사 1곳을 취득·분류·매칭해 AdapterResult를 돌려준다.
성공/실패를 어댑터가 스스로 Outcome으로 판정한다(§5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from ..config import Company, TargetsConfig
from ..http_client import RateLimiter
from ..models import MatchResult
from ..outcomes import Outcome


@dataclass
class RunContext:
    """어댑터 실행 공유 자원."""

    rate_limiter: RateLimiter | None = None
    client: httpx.Client | None = None


@dataclass
class AdapterResult:
    """어댑터 1회 실행 산출."""

    outcome: Outcome
    meta: dict[str, Any] = field(default_factory=dict)
    matches: list[MatchResult] = field(default_factory=list)  # §3 통과 공고만
    # 어댑터는 등록됐지만 이 회사가 아직 설정 미완(예: SPA api_url 미확정)이면 skip.
    # 오케스트레이터는 skip을 run_results에 넣지 않고 스킵 목록으로 처리한다.
    skipped: bool = False
    skip_reason: str | None = None


# 어댑터 러너 시그니처: (company, cfg, ctx) -> AdapterResult
AdapterRunner = Callable[[Company, TargetsConfig, RunContext], AdapterResult]
