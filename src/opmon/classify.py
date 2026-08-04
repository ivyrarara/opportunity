"""정적/잡코리아 classifier (명세 §5-3).

단일 요청 (response, exception)을 Outcome 하나로 분류한다.

철칙 두 가지(§5-1):
  1) 0건은 "명시적 증거(empty 마커 / declared==0)"가 있을 때만 신뢰한다.
  2) 차단/봇 신호 검사를 파싱보다 먼저 한다 (봇페이지를 0건으로 오분류 금지).
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .extract import extract_with_fingerprint
from .outcomes import Outcome

_REDIRECT_CODES = (301, 302, 303, 307, 308)


def classify(
    resp: httpx.Response | None,
    exc: Exception | None,
    cfg: dict[str, Any],
    *,
    base: str = "",
) -> tuple[Outcome, dict[str, Any]]:
    """(resp, exc, fingerprint_cfg) → (Outcome, meta)."""
    if exc is not None:
        return Outcome.TRANSPORT_ERROR, {"error": repr(exc)[:200]}
    if resp is None:
        return Outcome.TRANSPORT_ERROR, {"error": "no_response"}

    st = resp.status_code
    body = resp.text or ""
    meta: dict[str, Any] = {"status": st, "bytes": len(body)}

    # 1) 상태코드 차단
    if st == 429:
        return Outcome.RATE_LIMITED, meta
    if st in (401, 403):
        return Outcome.BLOCKED, meta
    if st >= 500:
        return Outcome.TRANSPORT_ERROR, meta
    if st in _REDIRECT_CODES:
        loc = resp.headers.get("location", "")
        if any(h in loc for h in cfg.get("login_redirect_hosts", [])):
            return Outcome.BLOCKED, {**meta, "redirect": loc}

    # 2) 200으로 위장된 봇/캡차 페이지 (파싱보다 먼저)
    low = body.lower()
    if any(m.lower() in low for m in cfg.get("block_markers", [])):
        return Outcome.BLOCKED, {**meta, "reason": "block_marker_in_body"}

    # 3) 우리가 아는 그 페이지인가 (뼈대 확인) — 없으면 0건 취급 금지
    if meta["bytes"] < cfg.get("min_body_bytes", 0):
        return Outcome.SUSPICIOUS_EMPTY, {**meta, "reason": "body_too_small"}
    anchors = cfg.get("anchor_selectors", [])
    if anchors:
        soup = BeautifulSoup(body, "html.parser")
        if not any(soup.select(sel) for sel in anchors):
            return Outcome.SUSPICIOUS_EMPTY, {**meta, "reason": "no_page_anchor"}
    elif cfg.get("title_contains"):
        # CSS 앵커가 없는 사이트(React 등)는 <title> 텍스트로 "우리 페이지인가" 확인
        tm = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
        title_txt = tm.group(1) if tm else ""
        if not any(t in title_txt for t in cfg["title_contains"]):
            return Outcome.SUSPICIOUS_EMPTY, {**meta, "reason": "no_title_anchor"}

    # 4) declared count + items 추출 (다층 fallback)
    declared, items, ex = extract_with_fingerprint(body, cfg, base=base)
    parsed = len(items)
    meta.update(ex)
    meta["declared"] = declared
    meta["parsed"] = parsed

    if declared == 0:
        return Outcome.OK_EMPTY_TRUSTED, {**meta, "count": 0}

    if cfg.get("paginated"):
        # 페이지네이션 소스: declared는 전체(모든 페이지), parsed는 1페이지.
        # declared>parsed는 정상. "총 N건인데 하나도 못 뽑음"만 파손으로 본다.
        if parsed > 0:
            return Outcome.OK_WITH_RESULTS, {**meta, "count": parsed}
        if declared is not None and declared > 0:
            return Outcome.PARSE_ERROR, meta  # 위장: count는 있는데 파싱 0
    else:
        # 단일 페이지 소스: declared==parsed 여야 정상. 부족하면 부분 파싱 실패.
        if declared is not None and declared > parsed:
            return Outcome.PARSE_ERROR, meta
        if parsed > 0:
            return Outcome.OK_WITH_RESULTS, {**meta, "count": parsed}

    # parsed==0 공통 처리: 명시적 빈 마커가 있어야만 0건 신뢰 (§5-1)
    if any(m in body for m in cfg.get("empty_markers", [])):
        return Outcome.OK_EMPTY_TRUSTED, {**meta, "count": 0}
    return Outcome.SUSPICIOUS_EMPTY, {**meta, "reason": "empty_without_marker"}
