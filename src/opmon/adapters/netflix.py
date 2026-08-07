"""Netflix 자체 채용 API 어댑터 (Eightfold 기반).

Netflix 채용은 Eightfold 사이트(explore.jobs.netflix.net)로 운영된다. 공개 검색
API를 그대로 쓴다(실측 확인):

  GET https://{host}/api/apply/v2/jobs?domain={domain}&start={n}&num={k}&query={q}
  → {..., "count": N, "positions": [{id, name(제목), location, locations[], ...}]}

응답 스키마는 개편 여지가 있어 방어적으로 파싱한다(positions 우선, 대체 키 탐색).
"총 N건(count) vs 파싱 대조" 원칙(§7)으로 스키마 드리프트를 PARSE_ERROR로 잡는다.
설정(netflix_boards.py) 없으면 skip. OPMON_NETFLIX_DEBUG=1이면 원본 키/샘플 로깅.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.parse import quote

import httpx

from ..config import Company, TargetsConfig
from ..matching import evaluate_posting
from ..models import Posting
from ..netflix_boards import get_netflix_config
from ..outcomes import Outcome
from ..relevance import is_design_or_access
from .base import AdapterResult, RunContext

JSON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}

_NUM = 25
_MAX_PAGES = 4
_DEBUG = "OPMON_NETFLIX_DEBUG"

FetchFn = Callable[..., tuple[httpx.Response | None, Exception | None]]


def _dbg(msg: str) -> None:
    if os.getenv(_DEBUG):
        print(f"[netflix] {msg}")


def _search_url(host: str, domain: str, query: str, start: int, num: int) -> str:
    q = quote(query)
    return (f"https://{host}/api/apply/v2/jobs?domain={domain}"
            f"&start={start}&num={num}&query={q}")


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


def _extract_postings(data: Any) -> list[dict] | None:
    """방어적 파싱: positions 우선, 대체 키(jobs/records.postings), 배열 원형까지."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("positions", "jobs", "results"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
        rec = data.get("records")
        if isinstance(rec, dict) and isinstance(rec.get("postings"), list):
            return [x for x in rec["postings"] if isinstance(x, dict)]
    return None


def _declared_total(data: Any) -> int:
    if isinstance(data, dict):
        for key in ("count", "total"):
            if isinstance(data.get(key), int):
                return data[key]
        info = data.get("info")
        if isinstance(info, dict):
            posts = info.get("postings")
            if isinstance(posts, dict) and isinstance(posts.get("total"), int):
                return posts["total"]
    return 0


def _item_locations(it: dict) -> str:
    parts: list[str] = []
    loc = it.get("location")
    if isinstance(loc, str):
        parts.append(loc)
    locs = it.get("locations")
    if isinstance(locs, list):
        parts.extend(str(x) for x in locs if x)
    return " | ".join(parts)


def _loc_ok(loc: str, wants: list[str]) -> bool:
    if not wants:
        return True
    low = loc.lower()
    return any(w.lower() in low for w in wants)


def _to_posting(it: dict, host: str, domain: str) -> Posting | None:
    title = it.get("name") or it.get("posting_name") or it.get("text") or it.get("title")
    if not title:
        return None
    pid = it.get("id") or it.get("display_job_id") or it.get("ats_job_id")
    url = it.get("canonicalPositionUrl") or it.get("apply_url")
    if not url and pid is not None:
        url = f"https://{host}/careers?pid={pid}&domain={domain}&sort_by=relevance"
    if not url:
        return None
    dept = it.get("department") or it.get("business_unit")
    t = it.get("t_create") or it.get("t_update")
    return Posting(
        job_id=str(it.get("display_job_id") or pid or url),
        title=str(title),
        url=str(url),
        dept=str(dept) if dept else None,
        posted_date=str(t) if t else None,
    )


def collect(scfg: dict[str, Any], *, client: httpx.Client | None = None,
            fetch_fn: FetchFn | None = None,
            rate_wait: Callable[[], Any] | None = None) -> tuple[Outcome, dict, list[dict]]:
    """search_texts 전부를 start/num 페이지네이션, id 기준 dedupe."""
    from ..http_client import fetch as _default_fetch

    fetch_fn = fetch_fn or _default_fetch
    host = scfg["host"]
    domain = scfg.get("domain", "netflix.com")
    searches = scfg.get("search_texts") or [""]
    num = int(scfg.get("num", _NUM))
    max_pages = int(scfg.get("max_pages", _MAX_PAGES))

    union: dict[str, dict] = {}
    declared_max = 0
    pages = 0

    for q in searches:
        for page in range(max_pages):
            start = page * num
            if rate_wait is not None:
                rate_wait()
            url = _search_url(host, domain, q, start, num)
            resp, exc = fetch_fn(url, headers=JSON_HEADERS, client=client)
            pages += 1
            bad = _classify_status(resp, exc)
            if bad is not None:
                return bad[0], bad[1], []
            try:
                data = resp.json()  # type: ignore[union-attr]
            except Exception:
                return Outcome.BLOCKED, {"reason": "expected_json_got_html"}, []

            posts = _extract_postings(data)
            if posts is None:
                if pages == 1:
                    _dbg(f"schema keys={list(data)[:20] if isinstance(data, dict) else type(data)}")
                return Outcome.PARSE_ERROR, {"reason": "schema_changed"}, []
            if pages == 1:
                _dbg(f"q={q!r} p0 posts={len(posts)} sample={json.dumps(posts[0], ensure_ascii=False)[:400] if posts else 'none'}")

            total = _declared_total(data)
            declared_max = max(declared_max, total)
            for it in posts:
                key = str(it.get("id") or it.get("display_job_id") or it.get("name") or id(it))
                if key not in union:
                    union[key] = it
            if not posts or (total and start + num >= total):
                break

    raw = list(union.values())
    meta = {"declared_max": declared_max, "raw": len(raw), "pages": pages, "searches": len(searches)}
    if declared_max > 0 and not raw:
        return Outcome.PARSE_ERROR, meta, []
    return (Outcome.OK_WITH_RESULTS if raw else Outcome.OK_EMPTY_TRUSTED), meta, raw


def run(company: Company, cfg: TargetsConfig, ctx: RunContext) -> AdapterResult:
    scfg = get_netflix_config(company.id)
    if scfg is None:
        return AdapterResult(
            Outcome.SUSPICIOUS_EMPTY, {"reason": "netflix_not_configured"},
            skipped=True, skip_reason="Netflix board 미설정",
        )
    rate_wait = ctx.rate_limiter.wait if ctx.rate_limiter is not None else None
    outcome, meta, raw = collect(scfg, client=ctx.client, rate_wait=rate_wait)
    if outcome not in (Outcome.OK_WITH_RESULTS, Outcome.OK_EMPTY_TRUSTED):
        return AdapterResult(outcome=outcome, meta=meta)

    host = scfg["host"]
    domain = scfg.get("domain", "netflix.com")
    wants = scfg.get("location_contains") or []
    located = design = 0
    matches = []
    for it in raw:
        if not _loc_ok(_item_locations(it), wants):
            continue
        located += 1
        title = str(it.get("name") or it.get("posting_name") or it.get("title") or "")
        if not is_design_or_access(title):
            continue
        p = _to_posting(it, host, domain)
        if p is None:
            continue
        design += 1
        mr = evaluate_posting(p, cfg)
        if mr is not None:
            matches.append(mr)

    meta = {**meta, "located": located, "design": design, "matched": len(matches)}
    final = Outcome.OK_WITH_RESULTS if design else Outcome.OK_EMPTY_TRUSTED
    return AdapterResult(outcome=final, meta=meta, matches=matches)
