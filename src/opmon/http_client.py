"""HTTP 취득 공통 (명세 §2-4, §6-2).

착수 결정: 어댑터 공통에 처음부터 레이트리밋 + 실제 브라우저 헤더 + 실패 시 백오프.
용도는 개인 구직 알림 한정.

sleep/rng/client를 주입 가능하게 해 테스트에서 실제 대기·네트워크 없이 검증한다.
"""

from __future__ import annotations

import random
import time
from typing import Callable

import httpx

# 실제 모바일 브라우저 헤더 세트 (§6-2). 빈약한 지문이 봇으로 오인되는 것을 완화.
REAL_BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}


class RateLimiter:
    """요청 사이 간격 + 지터 (§6-2). 15곳 연타 방지."""

    def __init__(
        self,
        min_interval: float = 3.0,
        jitter: float = 2.0,
        *,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self.min_interval = min_interval
        self.jitter = jitter
        self._sleep = sleep
        self._rng = rng or random.Random()

    def wait(self) -> float:
        delay = self.min_interval + self._rng.random() * self.jitter
        self._sleep(delay)
        return delay


def fetch(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    client: httpx.Client | None = None,
    timeout: float = 15.0,
    max_retries: int = 3,
    backoff_base: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> tuple[httpx.Response | None, Exception | None]:
    """URL을 받아 (response, exception)을 반환.

    - 전송오류/5xx/429 → 지수 백오프(2s,4s,8s...+지터)로 재시도.
    - 4xx(403/401 등 정책성) → 재시도 없이 즉시 반환 (하머링 금지).
    반환된 (resp, exc)는 상위 classifier(§5)가 Outcome으로 분류한다.
    """
    rng = rng or random.Random()
    own_client = client is None
    if own_client:
        client = httpx.Client(follow_redirects=True, timeout=timeout)
    try:
        resp: httpx.Response | None = None
        exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                resp = client.get(url, headers=headers or REAL_BROWSER_HEADERS)
                exc = None
            except httpx.HTTPError as e:
                resp, exc = None, e
            else:
                # 재시도 대상이 아니면 즉시 반환.
                if resp.status_code < 500 and resp.status_code != 429:
                    return resp, None
            if attempt < max_retries:
                delay = backoff_base * (2**attempt) + rng.random()
                sleep(delay)
        return resp, exc
    finally:
        if own_client:
            client.close()
