"""잡코리아 모바일 어댑터 (명세 §4, §6).

회사명(brand_filter)으로 m.jobkorea.co.kr을 검색해 공고 리스트를 파싱한다.
정적 HTML이지만 접근 문턱이 가장 높다(§6) — 실제 취득은 network 되는 환경에서
probe로 fingerprint를 실측 확정한 뒤 유효하다.

이 모듈은 fetch(취득) / parse(추출) 를 분리해, fixture만으로도 파싱·매칭을
오프라인 검증할 수 있게 한다. Outcome 분류(§5)는 이후 단계에서 이 위에 얹는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from ..classify import classify
from ..config import Company, TargetsConfig
from ..extract import extract_with_fingerprint
from ..fingerprints import get_fingerprint
from ..http_client import REAL_BROWSER_HEADERS, fetch
from ..matching import evaluate_posting
from ..models import Posting
from ..outcomes import Outcome
from .base import AdapterResult, RunContext

DEFAULT_BASE = "https://m.jobkorea.co.kr"


@dataclass
class FetchOutcome:
    """fetch 결과 원자료 (classifier 입력용, §5). Outcome 분류는 아직 하지 않는다."""

    response: httpx.Response | None
    exception: Exception | None
    url: str


def build_search_url(company: Company, base: str | None = None) -> str:
    """회사명 검색 URL. [검증필요] 실제 엔드포인트는 probe로 확정.

    brand_filter가 없으면 회사명으로 검색한다.
    """
    base = base or (company.urls[0] if company.urls else DEFAULT_BASE)
    query = company.brand_filter or company.name
    # 잡코리아 모바일 통합검색 추정 경로 [검증필요]
    return f"{base.rstrip('/')}/Search/?stext={quote(query)}"


def fetch_search(
    company: Company,
    *,
    client: httpx.Client | None = None,
    **fetch_kwargs: Any,
) -> FetchOutcome:
    """검색 결과 페이지를 취득 (network 필요)."""
    url = build_search_url(company)
    resp, exc = fetch(url, headers=REAL_BROWSER_HEADERS, client=client, **fetch_kwargs)
    return FetchOutcome(response=resp, exception=exc, url=url)


def parse_search(body: str, company: Company, base: str | None = None) -> tuple[int | None, list[Posting], dict[str, Any]]:
    """검색 결과 HTML → (declared, postings, meta). fixture로 오프라인 검증 가능."""
    fp = get_fingerprint(company.fingerprint or "JOBKOREA_M_FINGERPRINT")
    base = base or (company.urls[0] if company.urls else DEFAULT_BASE)
    return extract_with_fingerprint(body, fp, base=base)


def run(company: Company, cfg: TargetsConfig, ctx: RunContext) -> AdapterResult:
    """어댑터 러너: 취득 → classify(§5) → 매칭(§3). 오케스트레이터가 호출한다."""
    if ctx.rate_limiter is not None:
        ctx.rate_limiter.wait()
    out = fetch_search(company, client=ctx.client)

    fp = get_fingerprint(company.fingerprint or "JOBKOREA_M_FINGERPRINT")
    base = company.urls[0] if company.urls else DEFAULT_BASE
    outcome, meta = classify(out.response, out.exception, fp, base=base)

    matches: list = []
    if outcome == Outcome.OK_WITH_RESULTS and out.response is not None:
        _, postings, _ = parse_search(out.response.text, company, base=base)
        for p in postings:
            mr = evaluate_posting(p, cfg)
            if mr is not None:
                matches.append(mr)
    return AdapterResult(outcome=outcome, meta=meta, matches=matches)


# --- probe / 콘솔 데모 (§6-4 겸용) ---------------------------------------


def _probe_report(body: str, company: Company, status: int | None) -> None:
    """§6-4 probe 진단 출력: title/JSON-LD/count후보/read-link/empty마커 실측."""
    import re

    from bs4 import BeautifulSoup

    fp = get_fingerprint(company.fingerprint or "JOBKOREA_M_FINGERPRINT")
    soup = BeautifulSoup(body, "html.parser")
    print(f"status: {status}  bytes: {len(body)}")
    print("title:", soup.title.string if soup.title else None)
    for s in soup.select('script[type="application/ld+json"]'):
        print("JSON-LD:", (s.string or "")[:200])
    for m in re.finditer(r"(총|검색결과|채용중)\s*[\d,]+\s*건?", body):
        print("count-candidate:", m.group(0))
    hrefs = {a["href"].split("?")[0] for a in soup.select("a[href]") if "Read" in a.get("href", "")}
    print("read-link patterns:", list(hrefs)[:10])
    hits = [m for m in fp["empty_markers"] if m in body]
    print("empty markers present:", hits)
    blk = [m for m in fp["block_markers"] if m.lower() in body.lower()]
    print("block markers present:", blk)


def _demo(body: str, company: Company) -> None:
    """fixture 파싱 → §3 매칭 → §9 알림 포맷으로 콘솔 출력 (오프라인 세로 검증)."""
    from ..config import load_targets
    from ..matching import evaluate_posting

    cfg = load_targets()
    declared, postings, meta = parse_search(body, company)
    print(f"[parse] declared={declared} parsed={meta.get('parsed')} "
          f"item_layer={meta.get('item_layer')} fragile={meta.get('fragile', False)}")
    matched = [m for p in postings if (m := evaluate_posting(p, cfg)) is not None]
    print(f"[match] {len(postings)}건 중 {len(matched)}건 대상\n")
    for m in matched:
        eng = " 🌐영어가능" if "영어가능" in m.highlights else ""
        exp = "" if m.min_experience_ok else "  ⚠️경력확인필요"
        print(f"🆕 [{m.category}] {company.name}{eng}")
        print(f"   {m.posting.title}{exp}")
        print(f"   매칭 키워드: {', '.join(m.matched_keywords)}")
        print(f"   {m.posting.url}\n")


def _main(argv: list[str]) -> int:
    import argparse

    from ..config import load_targets

    ap = argparse.ArgumentParser(description="잡코리아 어댑터 probe/parse (§6-4)")
    ap.add_argument("--company", default="nhn", help="targets.json의 company id")
    ap.add_argument("--fixture", help="HTML 파일 경로 (오프라인). 없으면 라이브 fetch")
    ap.add_argument("--probe", action="store_true", help="파싱 대신 §6-4 진단 출력")
    args = ap.parse_args(argv)

    company = load_targets().get_company(args.company)

    if args.fixture:
        with open(args.fixture, encoding="utf-8") as f:
            body = f.read()
        status: int | None = None
    else:
        out = fetch_search(company)
        if out.exception is not None or out.response is None:
            print(f"[FETCH FAIL] {out.url}\n  {out.exception!r}")
            print("  (이 세션은 egress 정책상 외부 접근 차단일 수 있음 — §6 참조)")
            return 2
        status, body = out.response.status_code, out.response.text

    if args.probe:
        _probe_report(body, company, status)
    else:
        _demo(body, company)
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
