"""HRSmart(ClearCompany) 어댑터 — BC Public Service 등 공공 포털.

목록 HTML에서 상세 링크(/hr/ats/Posting/view/{id})를 href 패턴으로 뽑는다.
제목은 앵커 텍스트를 기본으로 하되, 버튼 문구면 부모 행 셀에서 보완한다.
전 직군이 올라오므로 제목이 디자인/접근성인 공고만 매칭.

구조 미확정 → OPMON_HRSMART_DEBUG 로 실측 진단 후 확정.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urljoin

import httpx

from ..config import Company, TargetsConfig
from ..http_client import REAL_BROWSER_HEADERS, fetch
from ..matching import evaluate_posting
from ..models import Posting
from ..hrsmart_boards import get_hrsmart_config
from ..outcomes import Outcome
from ..relevance import is_design_or_access
from .base import AdapterResult, RunContext

_VIEW_RE = re.compile(r"/Posting/view/(\d+)", re.IGNORECASE)
_BUTTON_RE = re.compile(
    r"^(view(\s*job)?(\s*details)?|details|apply(\s*now)?|more\s*info|read\s*more)$",
    re.IGNORECASE,
)
_EMPTY_MARKERS = (
    "no job", "no current", "no opportunit", "no matching",
    "no positions", "there are currently no", "no results found",
)
_MIN_BODY_BYTES = 1500


def listing_url(scfg: dict) -> str:
    return f"https://{scfg['host']}{scfg['path']}"


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


def _is_title_text(t: str) -> bool:
    return bool(t) and not _BUTTON_RE.match(t) and len(t) >= 3


def _title_for(anchor) -> str | None:
    """앵커 텍스트가 제목이면 그대로, 버튼이면 부모 행 셀에서 가장 긴 제목형 텍스트."""
    t = anchor.get_text(" ", strip=True)
    if _is_title_text(t):
        return t
    row = anchor.find_parent("tr") or anchor.find_parent(["li", "article", "div"])
    if row is None:
        return None
    cands = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
    cands = [c for c in cands if _is_title_text(c)]
    return max(cands, key=len) if cands else None


def parse_listing(body: str, base_url: str) -> list[Posting]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(body, "html.parser")
    groups: dict[str, dict] = {}
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        m = _VIEW_RE.search(href)
        if not m:
            continue
        job_id = m.group(1)
        g = groups.setdefault(job_id, {"url": urljoin(base_url, href), "title": None})
        title = _title_for(a)
        if title and (g["title"] is None or len(title) > len(g["title"])):
            g["title"] = title
    return [Posting(job_id=k, title=g["title"], url=g["url"])
            for k, g in groups.items() if g["title"]]


def classify_and_parse(body: str, base_url: str) -> tuple[Outcome, dict, list[Posting]]:
    posts = parse_listing(body, base_url)
    relevant = [p for p in posts if is_design_or_access(p.title)]
    meta = {"anchors": len(posts), "relevant": len(relevant)}
    if posts:
        return (Outcome.OK_WITH_RESULTS if relevant else Outcome.OK_EMPTY_TRUSTED), meta, relevant
    low = body.lower()
    if any(mk in low for mk in _EMPTY_MARKERS):
        return Outcome.OK_EMPTY_TRUSTED, {**meta, "reason": "empty_marker"}, []
    if len(body) < _MIN_BODY_BYTES:
        return Outcome.BLOCKED, {**meta, "reason": "body_too_small", "bytes": len(body)}, []
    return Outcome.SUSPICIOUS_EMPTY, {**meta, "reason": "no_anchor_no_marker"}, []


def run(company: Company, cfg: TargetsConfig, ctx: RunContext) -> AdapterResult:
    scfg = get_hrsmart_config(company.id)
    if scfg is None:
        return AdapterResult(
            Outcome.SUSPICIOUS_EMPTY, {"reason": "hrsmart_not_configured"},
            skipped=True, skip_reason="HRSmart board 미설정",
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
    if os.getenv("OPMON_HRSMART_DEBUG"):
        low = body.lower()
        print(f"[hrsmart:{company.id}] status={resp.status_code} bytes={len(body)} "  # type: ignore[union-attr]
              f"raw_view={low.count('/posting/view/')} anchors={meta.get('anchors')} "
              f"relevant={meta.get('relevant')}")
        for p in parse_listing(body, url)[:12]:
            print(f"   title· {p.title[:75]} | {p.job_id}")

    matches = []
    if outcome == Outcome.OK_WITH_RESULTS:
        for p in relevant:
            mr = evaluate_posting(p, cfg)
            if mr is not None:
                matches.append(mr)
    meta = {**meta, "matched": len(matches)}
    return AdapterResult(outcome=outcome, meta=meta, matches=matches)
