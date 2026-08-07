"""Workday CXS 어댑터 (토론토 모니터링, 명세 §7 API 경로의 POST 변형).

Workday 공개 CXS API는 tenant/site만 알면 인증 없이 목록 JSON을 준다.
경로 A(§7-2)와 같은 "총 N건(total) vs 파싱 대조" 원칙을 그대로 적용하되,
요청이 POST+JSON(searchText)이라 SPA api 경로 대신 전용 어댑터로 둔다.

설정(workday_boards.py)이 없는 회사는 skip. 실패 Outcome은 캐시 오염 금지(§7-6, 오케스트레이터 처리).
"""

from __future__ import annotations

from typing import Any, Callable

import httpx

from ..config import Company, TargetsConfig
from ..extract import derive_job_id
from ..matching import evaluate_posting
from ..models import Posting
from ..outcomes import Outcome
from ..relevance import is_design_or_access
from ..workday_boards import get_workday_config
from .base import AdapterResult, RunContext

WD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Accept-Language": "en-CA,en;q=0.9",
}

_PAGE_SIZE = 20
_MAX_OFFSET = 200  # 안전 상한 (검색어당 최대 10페이지)

# 제목 가드: Workday searchText는 본문까지 훑어 판매직·분석직·법무를 끌어온다.
# 공용 relevance(정확 토큰)로 디자인/접근성 제목만 통과시킨다.
_is_design_title = is_design_or_access

FetchFn = Callable[..., tuple[httpx.Response | None, Exception | None]]


def _endpoint(scfg: dict[str, Any]) -> str:
    return f"https://{scfg['host']}/wday/cxs/{scfg['tenant']}/{scfg['site']}/jobs"


def _job_base(scfg: dict[str, Any]) -> str:
    return f"https://{scfg['host']}/{scfg.get('locale', 'en-US')}/{scfg['site']}"


def _classify_response(
    resp: httpx.Response | None, exc: Exception | None
) -> tuple[Outcome, dict] | None:
    """전송/상태 이상만 Outcome으로. 정상 응답이면 None(계속 진행)."""
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


def collect_workday(
    scfg: dict[str, Any],
    *,
    client: httpx.Client | None = None,
    fetch_fn: FetchFn | None = None,
    rate_wait: Callable[[], Any] | None = None,
) -> tuple[Outcome, dict, list[dict]]:
    """search_texts 전부를 offset 페이지네이션으로 순회, externalPath로 dedupe.

    반환 (outcome, meta, raw_items). raw_items는 위치 필터 이전 원본 jobPosting.
    """
    from ..http_client import fetch as _default_fetch

    fetch_fn = fetch_fn or _default_fetch
    endpoint = _endpoint(scfg)
    searches = scfg.get("search_texts") or [""]
    max_offset = int(scfg.get("max_offset", _MAX_OFFSET))  # 대형 테넌트(삼성 등) 과다 페이지네이션 방지

    union: dict[str, dict] = {}   # externalPath → item
    declared_max = 0
    pages = 0

    for q in searches:
        offset = 0
        while offset < max_offset:
            if rate_wait is not None:
                rate_wait()
            body = {"appliedFacets": {}, "limit": _PAGE_SIZE, "offset": offset, "searchText": q}
            resp, exc = fetch_fn(
                endpoint, method="POST", json_body=body, headers=WD_HEADERS, client=client
            )
            pages += 1
            bad = _classify_response(resp, exc)
            if bad is not None:
                return bad[0], bad[1], []
            try:
                data = resp.json()  # type: ignore[union-attr]
            except Exception:
                return Outcome.BLOCKED, {"reason": "expected_json_got_html"}, []
            if not isinstance(data, dict) or "jobPostings" not in data or "total" not in data:
                return Outcome.PARSE_ERROR, {"reason": "schema_changed"}, []
            total = data.get("total") or 0
            posts = data.get("jobPostings") or []
            declared_max = max(declared_max, int(total))
            for it in posts:
                key = it.get("externalPath") or it.get("title")
                if key and key not in union:
                    union[key] = it
            offset += _PAGE_SIZE
            if not posts or offset >= int(total):
                break

    raw = list(union.values())
    meta = {"declared_max": declared_max, "raw": len(raw), "pages": pages, "searches": len(searches)}

    # 검색은 됐는데(total>0) 배열 파싱이 0 → 스키마 드리프트.
    if declared_max > 0 and not raw:
        return Outcome.PARSE_ERROR, meta, []
    return Outcome.OK_WITH_RESULTS if raw else Outcome.OK_EMPTY_TRUSTED, meta, raw


def _location_ok(item: dict, wants: list[str]) -> bool:
    if not wants:
        return True
    loc = (item.get("locationsText") or "")
    return any(w.lower() in loc.lower() for w in wants)


def parse_workday_items(items: list[dict], scfg: dict[str, Any]) -> list[Posting]:
    base = _job_base(scfg)
    out: list[Posting] = []
    for it in items:
        title = it.get("title")
        path = it.get("externalPath")
        if not title or not path:
            continue
        url = base + path
        bullets = it.get("bulletFields") or []
        job_id = str(bullets[0]) if bullets else derive_job_id(url, {})
        out.append(Posting(
            job_id=job_id,
            title=str(title),
            url=url,
            posted_date=it.get("postedOn"),
        ))
    return out


def run(company: Company, cfg: TargetsConfig, ctx: RunContext) -> AdapterResult:
    scfg = get_workday_config(company.id)
    if scfg is None:
        return AdapterResult(
            Outcome.SUSPICIOUS_EMPTY, {"reason": "workday_not_configured"},
            skipped=True, skip_reason="Workday board 미설정",
        )
    rate_wait = ctx.rate_limiter.wait if ctx.rate_limiter is not None else None
    outcome, meta, raw = collect_workday(scfg, client=ctx.client, rate_wait=rate_wait)

    if outcome not in (Outcome.OK_WITH_RESULTS, Outcome.OK_EMPTY_TRUSTED):
        return AdapterResult(outcome=outcome, meta=meta)

    wants = scfg.get("location_contains") or []
    located = [it for it in raw if _location_ok(it, wants)]
    # 제목 가드: 판매직·분석직 등 비(非)디자인 제목을 매칭 전에 제거(오탐 차단).
    design = [it for it in located if _is_design_title(str(it.get("title") or ""))]
    matches = []
    for p in parse_workday_items(design, scfg):
        mr = evaluate_posting(p, cfg)
        if mr is not None:
            matches.append(mr)

    meta = {**meta, "located": len(located), "design": len(design), "matched": len(matches)}
    # 사이트는 정상 응답(raw>0)이나 토론토/디자인 필터로 0이면 "신뢰 가능한 빈 결과".
    final = Outcome.OK_WITH_RESULTS if design else Outcome.OK_EMPTY_TRUSTED
    return AdapterResult(outcome=final, meta=meta, matches=matches)
