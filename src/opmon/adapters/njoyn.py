"""Njoyn(CGI) 채용포털 어댑터 — 지자체(예: City of Vaughan).

목록 HTML을 받아 상세 링크(`Page=JobDetails&Jobid=...`) 앵커를 href 패턴으로 추출한다.
CSS 클래스에 의존하지 않아 포털 개편에 강하다.

지자체 포털은 전 직군(소방·행정 등)을 다 올리므로, 제목이 '디자인 또는 접근성' 토큰을
가진 공고만 남겨 노이즈를 차단한 뒤 §3 키워드 매칭을 적용한다.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

import httpx

from ..config import Company, TargetsConfig
from ..http_client import REAL_BROWSER_HEADERS, fetch
from ..matching import evaluate_posting
from ..models import Posting
from ..njoyn_boards import get_njoyn_config
from ..outcomes import Outcome
from .base import AdapterResult, RunContext

# 제목 관련성 가드: '디자인' 또는 '접근성' 직군만 통과(사용자 요청 = 디자이너 + accessibility).
_DESIGN_TOKENS = (
    "designer", "design", "graphic", "visual", "packaging",
    "art direction", "art director", "illustrat", "creative", "brand",
    "ux", "ui", "motion", "multimedia",
)
_ACCESS_TOKENS = ("accessib", "aoda", "wcag", "inclusive", "a11y")

_JOBID_RE = re.compile(r"[?&]jobid=([^&]+)", re.IGNORECASE)
# 직무ID 형태의 텍스트(예: J0726-0469) — 제목이 아니므로 제목 후보에서 제외.
_IDLIKE_RE = re.compile(r"^[A-Za-z]?\d{3,4}-\d+$")
# 링크 버튼 문구 — 제목이 아님.
_BUTTON_RE = re.compile(
    r"^(view\s*job\s*details|view\s*details|view|details|apply(\s*now)?|more\s*info)$",
    re.IGNORECASE,
)
_EMPTY_MARKERS = (
    "no job", "no current", "no opportunit", "no matching",
    "no positions", "there are currently no", "no results",
)
_MIN_BODY_BYTES = 1500


def _is_relevant(title: str) -> bool:
    t = title.lower()
    return any(tok in t for tok in _DESIGN_TOKENS) or any(tok in t for tok in _ACCESS_TOKENS)


def listing_url(scfg: dict) -> str:
    return (
        f"https://{scfg['host']}/cl4/xweb/xweb.asp"
        f"?page=joblisting&clid={scfg['clid']}&lang={scfg.get('lang', '1')}"
    )


def _classify_status(resp: httpx.Response | None, exc: Exception | None) -> tuple[Outcome, dict] | None:
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
    if st >= 400:
        return Outcome.BLOCKED, {"status": st}
    return None


def _is_title_text(t: str, job_id: str) -> bool:
    """제목 후보 판정: 비어있지 않고, 직무ID도 버튼 문구도 아닌 텍스트."""
    return bool(t) and t != job_id and not _IDLIKE_RE.match(t) and not _BUTTON_RE.match(t)


def _row_title(anchor, job_id: str) -> str | None:
    """앵커가 속한 행(tr/li)에서 제목 셀을 뽑는다.

    Njoyn 목록 행 구조: [직무ID, 제목, 부서, 고용형태, 게시일, 마감일].
    제목은 'ID 셀 바로 다음 셀'이다(길이 휴리스틱은 짧은 제목에서 오판하므로 위치 기반).
    ID 셀을 못 찾으면 첫 제목형 셀로 폴백.
    """
    row = anchor.find_parent("tr") or anchor.find_parent(["li", "article", "div"])
    if row is None:
        return None
    cells = row.find_all(["td", "th"]) or [row]
    texts = [c.get_text(" ", strip=True) for c in cells]
    # ID 셀(=job_id 또는 ID 형태) 바로 다음의 '제목형' 셀.
    for i, t in enumerate(texts):
        if t == job_id or _IDLIKE_RE.match(t):
            for nxt in texts[i + 1:]:
                if _is_title_text(nxt, job_id):
                    return nxt
            break
    # 폴백: 첫 제목형 셀.
    for t in texts:
        if _is_title_text(t, job_id):
            return t
    return None


def parse_listing(body: str, base_url: str) -> list[Posting]:
    """목록 HTML → JobDetails 공고를 Posting으로(관련성 필터 이전).

    같은 Jobid의 앵커들을 묶고, 제목은 앵커가 속한 행의 셀에서 추출한다.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(body, "html.parser")
    groups: dict[str, dict] = {}  # job_id → {"url", "title"}
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "jobdetails" not in href.lower():
            continue
        m = _JOBID_RE.search(href)
        job_id = m.group(1) if m else href
        g = groups.setdefault(job_id, {"url": urljoin(base_url, href), "title": None})
        title = _row_title(a, job_id)
        # 다른 포털(제목=앵커 텍스트) 대비 fallback.
        if not title:
            t = a.get_text(strip=True)
            title = t if _is_title_text(t, job_id) else None
        if title and (g["title"] is None or len(title) > len(g["title"])):
            g["title"] = title

    out: list[Posting] = []
    for job_id, g in groups.items():
        if g["title"]:
            out.append(Posting(job_id=job_id, title=g["title"], url=g["url"]))
    return out


def classify_and_parse(body: str, base_url: str) -> tuple[Outcome, dict, list[Posting]]:
    """200 응답 본문 → (outcome, meta, 관련 Posting)."""
    all_posts = parse_listing(body, base_url)
    relevant = [p for p in all_posts if _is_relevant(p.title)]
    meta = {"anchors": len(all_posts), "relevant": len(relevant)}
    if all_posts:
        outcome = Outcome.OK_WITH_RESULTS if relevant else Outcome.OK_EMPTY_TRUSTED
        return outcome, meta, relevant
    # 앵커가 하나도 없음 → 빈 마커 있으면 신뢰 가능한 빈 결과, 없으면 구조 변경 의심.
    low = body.lower()
    if any(mk in low for mk in _EMPTY_MARKERS):
        return Outcome.OK_EMPTY_TRUSTED, {**meta, "reason": "empty_marker"}, []
    if len(body) < _MIN_BODY_BYTES:
        return Outcome.BLOCKED, {**meta, "reason": "body_too_small", "bytes": len(body)}, []
    return Outcome.SUSPICIOUS_EMPTY, {**meta, "reason": "no_anchor_no_marker"}, []


def run(company: Company, cfg: TargetsConfig, ctx: RunContext) -> AdapterResult:
    scfg = get_njoyn_config(company.id)
    if scfg is None:
        return AdapterResult(
            Outcome.SUSPICIOUS_EMPTY, {"reason": "njoyn_not_configured"},
            skipped=True, skip_reason="Njoyn board 미설정",
        )
    if ctx.rate_limiter is not None:
        ctx.rate_limiter.wait()
    url = listing_url(scfg)
    resp, exc = fetch(url, headers=REAL_BROWSER_HEADERS, client=ctx.client)
    bad = _classify_status(resp, exc)
    if bad is not None:
        return AdapterResult(outcome=bad[0], meta=bad[1])

    outcome, meta, relevant = classify_and_parse(resp.text, url)  # type: ignore[union-attr]
    matches = []
    if outcome == Outcome.OK_WITH_RESULTS:
        for p in relevant:
            mr = evaluate_posting(p, cfg)
            if mr is not None:
                matches.append(mr)
    meta = {**meta, "matched": len(matches)}
    return AdapterResult(outcome=outcome, meta=meta, matches=matches)
