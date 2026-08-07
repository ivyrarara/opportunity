"""Greenhouse 채용 보드 어댑터 (예: Figma, Pinterest).

Greenhouse 공개 보드 API는 인증 없이 JSON을 준다:
  GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false
  → {"meta": {"total": N}, "jobs": [{id, title, absolute_url, location:{name}, ...}]}

위치(location.name)로 토론토/캐나다/Remote만 남기고, 제목이 디자인/접근성인 것만 매칭.
설정(greenhouse_boards.py) 없으면 skip. Lever와 동일한 "총 N vs 파싱 대조" 원칙(§7).
"""

from __future__ import annotations

from typing import Any, Callable

import httpx

from ..config import Company, TargetsConfig
from ..greenhouse_boards import get_greenhouse_config
from ..matching import evaluate_posting
from ..models import Posting
from ..outcomes import Outcome
from ..relevance import is_design_or_access
from .base import AdapterResult, RunContext

JSON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

FetchFn = Callable[..., tuple[httpx.Response | None, Exception | None]]


def api_url(scfg: dict[str, Any]) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{scfg['token']}/jobs?content=false"


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


def _loc_ok(loc: str | None, wants: list[str]) -> bool:
    if not wants:
        return True
    low = (loc or "").lower()
    return any(w.lower() in low for w in wants)


def collect(scfg: dict[str, Any], *, client: httpx.Client | None = None,
            fetch_fn: FetchFn | None = None) -> tuple[Outcome, dict, list[dict]]:
    from ..http_client import fetch as _default_fetch

    fetch_fn = fetch_fn or _default_fetch
    resp, exc = fetch_fn(api_url(scfg), headers=JSON_HEADERS, client=client)
    bad = _classify_status(resp, exc)
    if bad is not None:
        return bad[0], bad[1], []
    try:
        data = resp.json()  # type: ignore[union-attr]
    except Exception:
        return Outcome.BLOCKED, {"reason": "expected_json_got_html"}, []
    if not isinstance(data, dict) or "jobs" not in data:
        return Outcome.PARSE_ERROR, {"reason": "schema_changed"}, []
    jobs = data.get("jobs") or []
    declared = int((data.get("meta") or {}).get("total") or len(jobs))
    meta = {"declared_max": declared, "raw": len(jobs)}
    if declared > 0 and not jobs:
        return Outcome.PARSE_ERROR, meta, []
    return (Outcome.OK_WITH_RESULTS if jobs else Outcome.OK_EMPTY_TRUSTED), meta, jobs


def run(company: Company, cfg: TargetsConfig, ctx: RunContext) -> AdapterResult:
    scfg = get_greenhouse_config(company.id)
    if scfg is None:
        return AdapterResult(
            Outcome.SUSPICIOUS_EMPTY, {"reason": "greenhouse_not_configured"},
            skipped=True, skip_reason="Greenhouse board 미설정",
        )
    if ctx.rate_limiter is not None:
        ctx.rate_limiter.wait()
    outcome, meta, jobs = collect(scfg, client=ctx.client)
    if outcome not in (Outcome.OK_WITH_RESULTS, Outcome.OK_EMPTY_TRUSTED):
        return AdapterResult(outcome=outcome, meta=meta)

    wants = scfg.get("location_contains") or []
    located = design = 0
    matches = []
    for it in jobs:
        loc = (it.get("location") or {}).get("name")
        if not _loc_ok(loc, wants):
            continue
        located += 1
        title = it.get("title") or ""
        url = it.get("absolute_url")
        if not url or not is_design_or_access(title):
            continue
        design += 1
        p = Posting(
            job_id=str(it.get("id") or url),
            title=title,
            url=url,
            posted_date=it.get("updated_at"),
        )
        mr = evaluate_posting(p, cfg)
        if mr is not None:
            matches.append(mr)

    meta = {**meta, "located": located, "design": design, "matched": len(matches)}
    final = Outcome.OK_WITH_RESULTS if design else Outcome.OK_EMPTY_TRUSTED
    return AdapterResult(outcome=final, meta=meta, matches=matches)
