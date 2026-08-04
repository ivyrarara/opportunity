"""SPA/ATS 어댑터 (명세 §7).

경로 A(선호): 내부/ATS JSON API 직행 (§7-2) — total 명시로 "총 N건 vs 파싱" 대조가 공짜.
경로 B(fallback): Playwright 렌더 (§7-3) — 리스트/빈상태 셀렉터 동시 wait로 렌더실패 구분.

정적 classifier를 SPA에 그대로 쓰면 빈 껍데기(<div id=root>)를 전부 차단으로 오판하므로,
판정 지점을 "데이터가 실제로 오는 곳"으로 옮긴다.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from ..config import Company, TargetsConfig
from ..extract import derive_job_id
from ..matching import evaluate_posting
from ..models import Posting
from ..outcomes import Outcome
from ..spa_fingerprints import get_spa_config
from .base import AdapterResult, RunContext

JSON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
}

_MAX_PAGES = 100  # 안전 상한 (무한 페이지네이션 방지)


class RenderTimeout(Exception):
    """render에서 리스트·빈상태 앵커 둘 다 미출현 (§7-3)."""


def pluck(data: Any, path: list[str] | None) -> Any:
    """중첩 dict를 path로 탐색. path가 falsy면 data 그대로."""
    if not path:
        return data
    cur = data
    for key in path:
        cur = cur[key]  # KeyError/TypeError는 호출부에서 스키마 변경으로 처리
    return cur


# --- 경로 A: API (§7-2) --------------------------------------------------


def classify_api(resp: httpx.Response | None, exc: Exception | None, cfg: dict[str, Any]) -> tuple[Outcome, dict]:
    """단일 API 응답 분류 (§7-2). 페이지네이션 없는 경우/테스트용.

    페이지네이션이 있으면 collect_api가 전 페이지 순회 후 대조한다.
    """
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
    try:
        data = resp.json()
    except Exception:
        return Outcome.BLOCKED, {"reason": "expected_json_got_html", "status": st}
    try:
        items = pluck(data, cfg.get("items_path"))
        declared = pluck(data, cfg.get("total_path"))
    except (KeyError, TypeError):
        return Outcome.PARSE_ERROR, {"reason": "schema_changed"}
    parsed = len(items)
    if declared == 0:
        return Outcome.OK_EMPTY_TRUSTED, {"count": 0}
    if declared and declared > parsed:
        return Outcome.PARSE_ERROR, {"declared": declared, "parsed": parsed}
    if parsed > 0:
        return Outcome.OK_WITH_RESULTS, {"count": parsed}
    return Outcome.SUSPICIOUS_EMPTY, {"reason": "empty_array_no_total"}


def _page_url(cfg: dict[str, Any], page: int) -> str:
    params = dict(cfg.get("params") or {})
    pg = cfg.get("paginate") or {}
    if pg.get("param"):
        params[pg["param"]] = page
    if pg.get("size_param"):
        params[pg["size_param"]] = pg.get("size", 50)
    url = cfg["api_url"]
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urlencode(params)}"
    return url


def collect_api(cfg: dict[str, Any], *, client: httpx.Client | None = None) -> tuple[Outcome, dict, list[Any]]:
    """페이지네이션을 끝까지 순회한 뒤 declared와 대조 (§7-2 노트). (outcome, meta, items)."""
    from ..http_client import fetch

    pg = cfg.get("paginate") or {}
    start = pg.get("start", 1)
    paginated = bool(pg.get("param"))
    headers = {**JSON_HEADERS, **(cfg.get("headers") or {})}

    all_items: list[Any] = []
    declared: int | None = None
    page = start
    pages_fetched = 0
    while pages_fetched < _MAX_PAGES:
        resp, exc = fetch(_page_url(cfg, page), headers=headers, client=client)
        pages_fetched += 1
        # 전송/상태 이상은 즉시 반환
        if exc is not None:
            return Outcome.TRANSPORT_ERROR, {"error": repr(exc)[:200]}, []
        if resp is None:
            return Outcome.TRANSPORT_ERROR, {"error": "no_response"}, []
        st = resp.status_code
        if st == 429:
            return Outcome.RATE_LIMITED, {"status": st}, []
        if st in (401, 403):
            return Outcome.BLOCKED, {"status": st}, []
        if st >= 500:
            return Outcome.TRANSPORT_ERROR, {"status": st}, []
        try:
            data = resp.json()
        except Exception:
            return Outcome.BLOCKED, {"reason": "expected_json_got_html", "status": st}, []
        try:
            items = list(pluck(data, cfg.get("items_path")))
            total = pluck(data, cfg.get("total_path"))
        except (KeyError, TypeError):
            return Outcome.PARSE_ERROR, {"reason": "schema_changed"}, []

        all_items.extend(items)
        if total is not None:
            declared = total

        if not paginated:
            break
        if declared is not None:
            if len(all_items) >= declared or not items:
                break
        else:
            if not items:  # total 미제공 → 빈 페이지에서 종료
                break
        page += 1

    parsed = len(all_items)
    meta = {"declared": declared, "parsed": parsed, "pages": pages_fetched}
    if declared == 0:
        return Outcome.OK_EMPTY_TRUSTED, {**meta, "count": 0}, []
    if declared is not None and declared > parsed:
        return Outcome.PARSE_ERROR, meta, all_items
    if parsed > 0:
        return Outcome.OK_WITH_RESULTS, {**meta, "count": parsed}, all_items
    if declared is None:
        return Outcome.SUSPICIOUS_EMPTY, {**meta, "reason": "empty_array_no_total"}, []
    return Outcome.OK_EMPTY_TRUSTED, {**meta, "count": 0}, []


def parse_api_items(items: list[Any], cfg: dict[str, Any]) -> list[Posting]:
    fields = cfg.get("item_fields") or {}
    out: list[Posting] = []
    for it in items:
        try:
            jid = pluck(it, fields.get("id"))
        except (KeyError, TypeError):
            jid = None
        title = _safe(it, fields.get("title"))
        url = _item_url(it, fields, jid)
        if not title or not url:
            continue
        job_id = str(jid) if jid is not None else derive_job_id(url, {})
        out.append(Posting(
            job_id=job_id,
            title=str(title),
            url=url,
            posted_date=_safe(it, fields.get("date")),
            dept=_safe(it, fields.get("dept")),
            employment_type=_safe(it, fields.get("employment_type")),
            experience_text=_safe(it, fields.get("experience")),
        ))
    return out


def _safe(item: Any, path: list[str] | None) -> str | None:
    if not path:
        return None
    try:
        v = pluck(item, path)
    except (KeyError, TypeError):
        return None
    return None if v is None else str(v)


def _item_url(item: Any, fields: dict[str, Any], jid: Any) -> str | None:
    url = _safe(item, fields.get("url"))
    if url:
        return url
    tmpl = fields.get("url_template")
    if tmpl and jid is not None:
        return tmpl.format(id=jid)
    return None


def run_api(company: Company, cfg: TargetsConfig, ctx: RunContext, scfg: dict[str, Any]) -> AdapterResult:
    if ctx.rate_limiter is not None:
        ctx.rate_limiter.wait()
    outcome, meta, items = collect_api(scfg, client=ctx.client)
    matches: list = []
    if outcome == Outcome.OK_WITH_RESULTS:
        for p in parse_api_items(items, scfg):
            mr = evaluate_posting(p, cfg)
            if mr is not None:
                matches.append(mr)
    return AdapterResult(outcome=outcome, meta=meta, matches=matches)


# --- 경로 B: render (§7-3) ----------------------------------------------


async def classify_render(page: Any, scfg: dict[str, Any]) -> tuple[Outcome, dict]:
    """렌더된 page를 분류 (§7-3). page는 wait_for_selector/query_selector*/content 지원.

    리스트 준비 셀렉터와 빈 상태 셀렉터를 동시에 wait — 둘 다 안 뜨면 RENDER_TIMEOUT.
    """
    html = await page.content()
    if any(m in html for m in scfg.get("challenge_markers", [])):
        return Outcome.CHALLENGE, {"reason": "bot_challenge"}
    ready = scfg["list_ready_selector"]
    empty = scfg["empty_state_selector"]
    try:
        await page.wait_for_selector(f"{ready}, {empty}", timeout=scfg.get("render_timeout_ms", 15000))
    except RenderTimeout:
        return Outcome.RENDER_TIMEOUT, {"reason": "no_anchor_within_timeout"}
    if await page.query_selector(empty):
        return Outcome.RENDER_EMPTY_STATE, {"count": 0}
    items = await page.query_selector_all(scfg["item_selector"])
    parsed = len(items)
    declared = scfg.get("_declared_for_test")  # 실제 count 파싱은 run_render에서 read
    if declared and declared > parsed:
        return Outcome.PARSE_ERROR, {"declared": declared, "parsed": parsed}
    if parsed > 0:
        return Outcome.OK_WITH_RESULTS, {"count": parsed}
    return Outcome.SUSPICIOUS_EMPTY, {"count": 0}


def run_render(company: Company, cfg: TargetsConfig, ctx: RunContext, scfg: dict[str, Any]) -> AdapterResult:
    """Playwright 렌더 실행 (§7-3). 브라우저·네트워크 필요.

    실패 Outcome(RENDER_TIMEOUT/CHALLENGE 등)은 캐시에 반영 금지(§7-6).
    """
    try:
        import asyncio
    except ImportError:  # pragma: no cover
        return AdapterResult(Outcome.TRANSPORT_ERROR, {"error": "asyncio_unavailable"})
    try:
        return asyncio.run(_run_render_async(company, cfg, scfg))
    except RuntimeError as exc:  # Playwright 미설치 등
        return AdapterResult(Outcome.TRANSPORT_ERROR, {"error": repr(exc)[:200]})


async def _run_render_async(company: Company, cfg: TargetsConfig, scfg: dict[str, Any]) -> AdapterResult:
    try:
        from playwright.async_api import TimeoutError as PWTimeout  # type: ignore
        from playwright.async_api import async_playwright  # type: ignore
    except ImportError as exc:  # pragma: no cover - 환경 의존
        raise RuntimeError(
            "playwright 미설치. `pip install playwright` 후 브라우저를 준비하세요(render 경로)."
        ) from exc

    async with async_playwright() as p:  # pragma: no cover - 브라우저 필요
        browser = await p.chromium.launch()
        page = await browser.new_page(extra_http_headers={"Accept-Language": "ko-KR"})
        adapter = _PWPage(page, PWTimeout)
        try:
            await page.goto(scfg["page_url"], wait_until="domcontentloaded")
            outcome, meta = await classify_render(adapter, scfg)
        finally:
            await browser.close()
    # render 경로의 공고 상세 추출은 fingerprint 실측 후 확장(현재 outcome 판정까지)
    return AdapterResult(outcome=outcome, meta=meta)


class _PWPage:  # pragma: no cover - 실제 Playwright page 래퍼
    """Playwright TimeoutError를 RenderTimeout으로 번역하는 얇은 래퍼."""

    def __init__(self, page: Any, pw_timeout: type[BaseException]) -> None:
        self._page = page
        self._pw_timeout = pw_timeout

    async def content(self):
        return await self._page.content()

    async def wait_for_selector(self, selector: str, timeout: int):
        try:
            return await self._page.wait_for_selector(selector, timeout=timeout)
        except self._pw_timeout as exc:
            raise RenderTimeout(str(exc)) from exc

    async def query_selector(self, selector: str):
        return await self._page.query_selector(selector)

    async def query_selector_all(self, selector: str):
        return await self._page.query_selector_all(selector)


# --- 디스패치 (레지스트리 진입점) ----------------------------------------


def run(company: Company, cfg: TargetsConfig, ctx: RunContext) -> AdapterResult:
    scfg = get_spa_config(company.id)
    if scfg is None:
        return AdapterResult(Outcome.SUSPICIOUS_EMPTY, {"reason": "spa_not_configured"},
                             skipped=True, skip_reason="SPA fingerprint 미실측")
    mode = scfg.get("mode")
    if mode == "api":
        return run_api(company, cfg, ctx, scfg)
    if mode == "render":
        return run_render(company, cfg, ctx, scfg)
    return AdapterResult(Outcome.SUSPICIOUS_EMPTY, {"reason": f"unknown_mode:{mode}"},
                         skipped=True, skip_reason=f"unknown mode {mode}")
