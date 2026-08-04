"""Outcome 정의 (명세 §5-1).

"성공/실패" 이분법이 위장을 만든다. 단일 요청 하나로는 "진짜 0건"과 "위장된 0건"을
구분할 수 없으므로, 요청 1건을 아래 값 중 하나로 분류한다(classifier §5-3),
그 뒤 이력·전체회사 맥락으로 승격/억제한다(aggregator §5-4).
"""

from __future__ import annotations

from enum import Enum


class Outcome(str, Enum):
    OK_WITH_RESULTS = "ok_with_results"      # 정상 페이지 + 공고 N>0
    OK_EMPTY_TRUSTED = "ok_empty_trusted"    # 정상 페이지 + "결과없음" 명시 확인 → 진짜 0건
    SUSPICIOUS_EMPTY = "suspicious_empty"    # 200인데 리스트도 empty마커도 없음 → 못 믿을 0건
    BLOCKED = "blocked"                      # 403/401/캡차/봇페이지/로그인 리다이렉트
    RATE_LIMITED = "rate_limited"            # 429
    TRANSPORT_ERROR = "transport_error"      # 타임아웃/DNS/커넥션리셋/5xx
    PARSE_ERROR = "parse_error"              # 구조 깨짐 (declared > parsed 포함)
    # SPA render 전용 (8단계에서 사용)
    RENDER_TIMEOUT = "render_timeout"        # 리스트·empty 앵커 둘 다 미출현
    CHALLENGE = "challenge"                  # Cloudflare/DataDome 봇 챌린지
    RENDER_EMPTY_STATE = "render_empty_state"  # 렌더됨 + "공고 없음" UI 명시


# 정상(성공)으로 보는 Outcome 집합.
OK_OUTCOMES = frozenset({Outcome.OK_WITH_RESULTS, Outcome.OK_EMPTY_TRUSTED, Outcome.RENDER_EMPTY_STATE})

# 전체회사 축 판정에서 "나쁨"으로 카운트하는 Outcome (§5-4).
BAD_OUTCOMES = frozenset({
    Outcome.BLOCKED, Outcome.RATE_LIMITED, Outcome.SUSPICIOUS_EMPTY,
    Outcome.TRANSPORT_ERROR, Outcome.RENDER_TIMEOUT, Outcome.CHALLENGE,
})

# 즉시 알림(디바운스 없음) 대상 (§5-5).
IMMEDIATE_ALERT_OUTCOMES = frozenset({
    Outcome.BLOCKED, Outcome.RATE_LIMITED, Outcome.CHALLENGE, Outcome.PARSE_ERROR,
})
