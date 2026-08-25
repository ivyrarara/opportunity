"""잡코리아 어댑터 파싱 + end-to-end 매칭(오프라인) 테스트."""

from __future__ import annotations

import random
from pathlib import Path

import httpx

from opmon.adapters import jobkorea
from opmon.config import load_targets
from opmon.http_client import RateLimiter, fetch
from opmon.matching import evaluate_posting

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CFG = load_targets()
NHN = CFG.get_company("nhn")


def test_build_search_url_uses_brand_filter():
    url = jobkorea.build_search_url(NHN)
    assert "www.jobkorea.co.kr" in url  # 데스크탑 www가 실제 검색됨(모바일 m은 검색어 무시)
    assert "stext=" in url
    # 엔에이치엔 URL 인코딩 포함
    assert "%" in url.split("stext=")[1]


def test_parse_search_fixture():
    body = (FIXTURES / "jobkorea_nhn_synthetic.html").read_text(encoding="utf-8")
    declared, postings, meta = jobkorea.parse_search(body, NHN)
    assert declared == 6
    assert len(postings) == 6
    assert meta["item_layer"] == "selector[0]"


def test_end_to_end_offline_match():
    """fixture → 파싱 → §3 매칭. 6건 중 대상은 A(UX/HMI)·D(패키지)·F(브랜딩) 3건."""
    body = (FIXTURES / "jobkorea_nhn_synthetic.html").read_text(encoding="utf-8")
    _, postings, _ = jobkorea.parse_search(body, NHN)
    matched = [m for p in postings if (m := evaluate_posting(p, CFG)) is not None]
    cats = sorted(m.category for m in matched)
    assert cats == ["UX/HMI", "브랜딩", "패키지/인쇄"]

    by_cat = {m.category: m for m in matched}
    # UX/HMI: 경력 확인됨
    assert by_cat["UX/HMI"].min_experience_ok is True
    # 패키지/인쇄: 경력 필드 없음 → 확인필요
    assert by_cat["패키지/인쇄"].min_experience_ok is None
    # 브랜딩: 영어가능 하이라이트
    assert "영어가능" in by_cat["브랜딩"].highlights


# --- http_client (네트워크 없이, fake transport) -------------------------


def _client_returning(status: int, text: str = "ok") -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=text)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_returns_response_on_200():
    with _client_returning(200, "hello") as client:
        resp, exc = fetch("https://x.test/", client=client)
    assert exc is None
    assert resp is not None and resp.status_code == 200


def test_fetch_no_retry_on_403():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403, text="denied")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resp, exc = fetch("https://x.test/", client=client, sleep=lambda _: None)
    assert resp is not None and resp.status_code == 403
    assert calls["n"] == 1  # 정책성 4xx는 재시도 안 함


def test_fetch_retries_on_500_then_gives_up():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    slept: list[float] = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resp, exc = fetch(
            "https://x.test/", client=client, max_retries=2,
            sleep=slept.append, rng=random.Random(0),
        )
    assert resp is not None and resp.status_code == 500
    assert calls["n"] == 3  # 최초 + 2회 재시도
    assert len(slept) == 2  # 재시도 사이 백오프 2회


def test_fetch_retries_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("reset")

    slept: list[float] = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resp, exc = fetch(
            "https://x.test/", client=client, max_retries=1,
            sleep=slept.append, rng=random.Random(0),
        )
    assert resp is None
    assert isinstance(exc, httpx.ConnectError)
    assert len(slept) == 1


def test_rate_limiter_waits_with_jitter():
    slept: list[float] = []
    rl = RateLimiter(min_interval=3.0, jitter=2.0, sleep=slept.append, rng=random.Random(0))
    delay = rl.wait()
    assert 3.0 <= delay <= 5.0
    assert slept == [delay]
