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


def _best_title(texts: list[str], job_id: str) -> str | None:
    """한 공고의 여러 앵커 텍스트 중 실제 제목을 고른다.

    Njoyn 행은 같은 Jobid로 링크가 여러 개(직무ID 셀·제목 셀 등)다. ID 형태·빈 텍스트를
    제외하고 가장 긴 것을 제목으로 본다. 남는 게 없으면(제목 셀 없음) None.
    """
    cands = [t for t in texts if t and t != job_id and not _IDLIKE_RE.match(t)]
    return max(cands, key=len) if cands else None


def parse_listing(body: str, base_url: str) -> list[Posting]:
    """목록 HTML → JobDetails 공고를 Posting으로(관련성 필터 이전).

    같은 Jobid의 앵커들을 묶어 그 중 실제 제목 텍스트를 선택한다(§ID 셀 링크 오인 방지).
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(body, "html.parser")
    groups: dict[str, dict] = {}  # job_id → {"url": 첫 href, "texts": [...]}
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "jobdetails" not in href.lower():
            continue
        m = _JOBID_RE.search(href)
        job_id = m.group(1) if m else href
        g = groups.setdefault(job_id, {"url": urljoin(base_url, href), "texts": []})
        text = a.get_text(strip=True)
        if text:
            g["texts"].append(text)

    out: list[Posting] = []
    for job_id, g in groups.items():
        title = _best_title(g["texts"], job_id)
        if not title:
            continue
        out.append(Posting(job_id=job_id, title=title, url=g["url"]))
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

    body = resp.text  # type: ignore[union-attr]
    outcome, meta, relevant = classify_and_parse(body, url)
    # --- 임시 진단 (실측용, 확인 후 제거) ---
    import os as _os
    if _os.getenv("OPMON_NJOYN_DEBUG"):
        all_posts = parse_listing(body, url)
        low = body.lower()
        print(f"[njoyn:{company.id}] status={resp.status_code} bytes={len(body)} "  # type: ignore[union-attr]
              f"raw_jobdetails={low.count('jobdetails')} raw_jobid={low.count('jobid=')} "
              f"iframe={'<iframe' in low} anchors={len(all_posts)} relevant={len(relevant)}")
        for p in all_posts[:8]:
            print(f"   · {p.title[:70]} | {p.job_id}")
    # --- /임시 진단 ---
    matches = []
    if outcome == Outcome.OK_WITH_RESULTS:
        for p in relevant:
            mr = evaluate_posting(p, cfg)
            if mr is not None:
                matches.append(mr)
    meta = {**meta, "matched": len(matches)}
    return AdapterResult(outcome=outcome, meta=meta, matches=matches)
