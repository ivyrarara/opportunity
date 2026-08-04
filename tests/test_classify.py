"""classifier(§5-3) 테스트 — 각 Outcome 분기."""

from __future__ import annotations

from pathlib import Path

import httpx

from opmon.classify import classify
from opmon.fingerprints import JOBKOREA_M_FINGERPRINT
from opmon.outcomes import Outcome

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BASE = "https://www.jobkorea.co.kr"

# 파싱 경로를 격리하기 위해 min_body_bytes를 낮춘 cfg (합성 fixture는 3KB 미만).
CFG = {**JOBKOREA_M_FINGERPRINT, "min_body_bytes": 200}


def _resp(status: int, text: str = "", headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, text=text, headers=headers or {})


def _nhn_body() -> str:
    return (FIXTURES / "jobkorea_nhn_synthetic.html").read_text(encoding="utf-8")


def _empty_body() -> str:
    return (FIXTURES / "jobkorea_empty_synthetic.html").read_text(encoding="utf-8")


# --- 전송/상태코드 ------------------------------------------------------


def test_exception_is_transport_error():
    o, meta = classify(None, httpx.ConnectError("reset"), CFG)
    assert o == Outcome.TRANSPORT_ERROR
    assert "reset" in meta["error"]


def test_no_response_is_transport_error():
    o, _ = classify(None, None, CFG)
    assert o == Outcome.TRANSPORT_ERROR


def test_429_rate_limited():
    assert classify(_resp(429, "x"), None, CFG)[0] == Outcome.RATE_LIMITED


def test_403_blocked():
    assert classify(_resp(403, "x"), None, CFG)[0] == Outcome.BLOCKED


def test_500_transport_error():
    assert classify(_resp(500, "x"), None, CFG)[0] == Outcome.TRANSPORT_ERROR


def test_login_redirect_blocked():
    r = _resp(302, "", headers={"location": "https://login.jobkorea.co.kr/?ret=1"})
    o, meta = classify(r, None, CFG)
    assert o == Outcome.BLOCKED
    assert "login" in meta["redirect"]


# --- 200 위장 봇페이지 (파싱보다 먼저) ----------------------------------


def test_block_marker_in_200_body():
    body = "<html><body>비정상적인 접근이 감지되었습니다</body></html>" + "x" * 3000
    o, meta = classify(_resp(200, body), None, JOBKOREA_M_FINGERPRINT)
    assert o == Outcome.BLOCKED
    assert meta["reason"] == "block_marker_in_body"


# --- 뼈대 확인 ----------------------------------------------------------


def test_body_too_small_suspicious():
    o, meta = classify(_resp(200, "tiny"), None, JOBKOREA_M_FINGERPRINT)
    assert o == Outcome.SUSPICIOUS_EMPTY
    assert meta["reason"] == "body_too_small"


def test_no_title_anchor_suspicious():
    # <title>에 title_contains(잡코리아/채용/...) 중 아무것도 없으면 "우리 페이지 아님"
    body = "<html><head><title>Something Else</title></head><body>" + "x" * 5000 + "</body></html>"
    o, meta = classify(_resp(200, body), None, JOBKOREA_M_FINGERPRINT)
    assert o == Outcome.SUSPICIOUS_EMPTY
    assert meta["reason"] == "no_title_anchor"


# --- declared vs parsed 대조 --------------------------------------------


def test_ok_with_results():
    o, meta = classify(_resp(200, _nhn_body()), None, CFG, base=BASE)
    assert o == Outcome.OK_WITH_RESULTS
    assert meta["count"] == 6
    assert meta["declared"] == 6


def test_empty_trusted_declared_zero():
    o, meta = classify(_resp(200, _empty_body()), None, CFG, base=BASE)
    assert o == Outcome.OK_EMPTY_TRUSTED
    assert meta["count"] == 0


def test_parse_error_declared_but_zero_parsed():
    # 페이지네이션 소스: "총 12건"인데 공고 링크를 하나도 못 뽑음 → 위장(셀렉터 파손)
    body = (
        "<html><head><title>채용공고 | 총 12건의 검색결과</title></head><body>"
        + "x" * 5000 + "</body></html>"  # GI_Read 링크 없음, empty 마커도 없음
    )
    o, meta = classify(_resp(200, body), None, JOBKOREA_M_FINGERPRINT, base=BASE)
    assert o == Outcome.PARSE_ERROR
    assert meta["declared"] == 12
    assert meta["parsed"] == 0


def test_pagination_declared_gt_parsed_is_ok():
    # 실제 잡코리아 구조: "총 174건"인데 1페이지 2건만 파싱돼도 정상(페이지네이션)
    body = (
        "<html><head><title>'NHN' 관련 채용공고 | 총 174건의 검색결과</title></head><body>"
        + "x" * 5000
        + '<div data-sentry-component="CardJob">'
        + '<a href="https://www.jobkorea.co.kr/Recruit/GI_Read/111?x=1"><img alt="logo"/></a>'
        + '<a href="https://www.jobkorea.co.kr/Recruit/GI_Read/111?x=1">[NHN] AI 서비스 기획자</a>'
        + "</div>"
        + '<div data-sentry-component="CardJob">'
        + '<a href="https://www.jobkorea.co.kr/Recruit/GI_Read/222?y=2"><img alt="logo"/></a>'
        + '<a href="https://www.jobkorea.co.kr/Recruit/GI_Read/222?y=2">재무 담당자</a>'
        + "</div></body></html>"
    )
    o, meta = classify(_resp(200, body), None, JOBKOREA_M_FINGERPRINT, base=BASE)
    assert o == Outcome.OK_WITH_RESULTS
    assert meta["declared"] == 174
    assert meta["parsed"] == 2  # 로고 앵커 제외 + job_id 중복제거로 고유 2건


def test_empty_without_marker_suspicious():
    # 제목 앵커는 통과하는데 declared도 items도 empty마커도 없음 → 의심
    body = "<html><head><title>채용 검색</title></head><body>" + "x" * 5000 + "</body></html>"
    o, meta = classify(_resp(200, body), None, JOBKOREA_M_FINGERPRINT, base=BASE)
    assert o == Outcome.SUSPICIOUS_EMPTY
    assert meta["reason"] == "empty_without_marker"


def test_empty_marker_without_declared_trusted():
    body = (
        "<html><head><title>통합검색 | 잡코리아</title></head><body>"
        + "x" * 5000 + "<span>검색결과가 없습니다</span></body></html>"
    )
    o, meta = classify(_resp(200, body), None, JOBKOREA_M_FINGERPRINT, base=BASE)
    assert o == Outcome.OK_EMPTY_TRUSTED
    assert meta["count"] == 0
