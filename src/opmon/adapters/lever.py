"""Lever 채용 API 어댑터 (예: Arc'teryx).

Lever 공개 API는 인증 없이 JSON 배열을 준다:
  GET https://api.lever.co/v0/postings/{slug}?mode=json

위치(categories.location)로 밴쿠버/BC/캐나다만 남기고, 제목이 디자인/접근성인 것만 매칭.
설정(lever_boards.py) 없으면 skip.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx

from ..config import Company, TargetsConfig
from ..lever_boards import get_lever_config
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
    return f"https://api.lever.co/v0/postings/{scfg['slug']}?mode=json"


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
    if not isinstance(data, list):
        return Outcome.PARSE_ERROR, {"reason": "schema_changed"}, []
    return (Outcome.OK_WITH_RESULTS if data else Outcome.OK_EMPTY_TRUSTED), {"total": len(data)}, data


def run(company: Company, cfg: TargetsConfig, ctx: RunContext) -> AdapterResult:
    scfg = get_lever_config(company.id)
    if scfg is None:
        return AdapterResult(
            Outcome.SUSPICIOUS_EMPTY, {"reason": "lever_not_configured"},
            skipped=True, skip_reason="Lever board 미설정",
        )
    if ctx.rate_limiter is not None:
        ctx.rate_limiter.wait()
    outcome, meta, data = collect(scfg, client=ctx.client)
    if outcome not in (Outcome.OK_WITH_RESULTS, Outcome.OK_EMPTY_TRUSTED):
        return AdapterResult(outcome=outcome, meta=meta)

    wants = scfg.get("location_contains") or []
    located = design = 0
    matches = []
    for it in data:
        cats = it.get("categories") or {}
        if not _loc_ok(cats.get("location"), wants):
            continue
        located += 1
        title = it.get("text") or ""
        url = it.get("hostedUrl")
        if not url or not is_design_or_access(title):
            continue
        design += 1
        p = Posting(
            job_id=str(it.get("id") or url),
            title=title,
            url=url,
            dept=cats.get("department") or cats.get("team"),
            employment_type=cats.get("commitment"),
        )
        mr = evaluate_posting(p, cfg)
        if mr is not None:
            matches.append(mr)

    meta = {**meta, "located": located, "design": design, "matched": len(matches)}
    final = Outcome.OK_WITH_RESULTS if design else Outcome.OK_EMPTY_TRUSTED
    return AdapterResult(outcome=final, meta=meta, matches=matches)
