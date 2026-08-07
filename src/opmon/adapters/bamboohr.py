"""BambooHR 채용 어댑터 (예: NUDESTIX).

BambooHR 공개 목록 API는 인증 없이 JSON을 준다(실측):
  GET https://{subdomain}.bamboohr.com/careers/list
  → {"result": [{id, jobOpeningName, departmentLabel, location{...}, ...}]}

제목이 디자인/접근성인 것만, (설정 시) 위치 필터 통과분만 매칭.
설정(bamboohr_boards.py) 없으면 skip. OPMON_BAMBOOHR_DEBUG=1이면 원본 샘플 로깅.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

import httpx

from ..bamboohr_boards import get_bamboohr_config
from ..config import Company, TargetsConfig
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

_DEBUG = "OPMON_BAMBOOHR_DEBUG"
FetchFn = Callable[..., tuple[httpx.Response | None, Exception | None]]


def _dbg(msg: str) -> None:
    if os.getenv(_DEBUG):
        print(f"[bamboohr] {msg}")


def api_url(scfg: dict[str, Any]) -> str:
    return f"https://{scfg['subdomain']}.bamboohr.com/careers/list"


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


def _extract(data: Any) -> list[dict] | None:
    if isinstance(data, dict):
        for key in ("result", "results", "jobs", "data"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return None


def _title(it: dict) -> str:
    return str(it.get("jobOpeningName") or it.get("title") or it.get("jobTitle") or "")


def _location(it: dict) -> str:
    loc = it.get("location")
    if isinstance(loc, dict):
        parts = [loc.get("city"), loc.get("state"), loc.get("country")]
        return ", ".join(str(p) for p in parts if p)
    if isinstance(loc, str):
        return loc
    return str(it.get("locationName") or it.get("atsLocation") or "")


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
    items = _extract(data)
    if items is None:
        _dbg(f"schema keys={list(data)[:12] if isinstance(data, dict) else type(data)}")
        return Outcome.PARSE_ERROR, {"reason": "schema_changed"}, []
    if items:
        _dbg(f"n={len(items)} sample={json.dumps(items[0], ensure_ascii=False)[:400]}")
    return (Outcome.OK_WITH_RESULTS if items else Outcome.OK_EMPTY_TRUSTED), {"raw": len(items)}, items


def _loc_ok(loc: str, wants: list[str]) -> bool:
    if not wants:
        return True
    low = loc.lower()
    return any(w.lower() in low for w in wants)


def run(company: Company, cfg: TargetsConfig, ctx: RunContext) -> AdapterResult:
    scfg = get_bamboohr_config(company.id)
    if scfg is None:
        return AdapterResult(
            Outcome.SUSPICIOUS_EMPTY, {"reason": "bamboohr_not_configured"},
            skipped=True, skip_reason="BambooHR board 미설정",
        )
    if ctx.rate_limiter is not None:
        ctx.rate_limiter.wait()
    outcome, meta, items = collect(scfg, client=ctx.client)
    if outcome not in (Outcome.OK_WITH_RESULTS, Outcome.OK_EMPTY_TRUSTED):
        return AdapterResult(outcome=outcome, meta=meta)

    sub = scfg["subdomain"]
    wants = scfg.get("location_contains") or []
    located = design = 0
    matches = []
    for it in items:
        if not _loc_ok(_location(it), wants):
            continue
        located += 1
        title = _title(it)
        jid = it.get("id") or it.get("jobId")
        if not title or jid is None or not is_design_or_access(title):
            continue
        design += 1
        p = Posting(
            job_id=str(jid),
            title=title,
            url=f"https://{sub}.bamboohr.com/careers/{jid}",
            dept=it.get("departmentLabel") or it.get("department"),
            employment_type=it.get("employmentStatusLabel"),
        )
        mr = evaluate_posting(p, cfg)
        if mr is not None:
            matches.append(mr)

    meta = {**meta, "located": located, "design": design, "matched": len(matches)}
    final = Outcome.OK_WITH_RESULTS if design else Outcome.OK_EMPTY_TRUSTED
    return AdapterResult(outcome=final, meta=meta, matches=matches)
