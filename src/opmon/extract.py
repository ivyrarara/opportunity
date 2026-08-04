"""다층 추출기 (명세 §6-5).

body(HTML) + fingerprint cfg → (declared_count, postings, meta).
어느 계층에서 성공했는지 meta["item_layer"]에 기록해 파손 조짐을 관측한다.

계층: JSON-LD(L2) → item_selectors(L3 링크패턴 → L4 CSS 클래스).
"총 N건"(declared)은 count_selectors 정규식으로 추출.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .models import Posting

# job_id를 못 뽑을 때 URL 정규화(쿼리스트링/프래그먼트 제거) 후 해시로 대체 (§2-2).


def normalize_url(url: str, base: str | None = None) -> str:
    if base:
        url = urljoin(base, url)
    parts = urlparse(url)
    # 세션토큰/추적 파라미터 폭발 방지: scheme+host+path만 남긴다.
    return f"{parts.scheme}://{parts.netloc}{parts.path}".rstrip("/")


def derive_job_id(url: str, cfg: dict[str, Any], base: str | None = None) -> str:
    """사이트 고유 ID 우선, 없으면 정규화 URL의 해시 (§2-2)."""
    abs_url = urljoin(base, url) if base else url
    for pat in cfg.get("job_id_url_patterns", []):
        m = re.search(pat, abs_url)
        if m:
            return m.group(1)
    norm = normalize_url(abs_url)
    return "u_" + hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def _text(el: Tag | None) -> str | None:
    if el is None:
        return None
    t = el.get_text(" ", strip=True)
    return t or None


def parse_declared(body: str, cfg: dict[str, Any]) -> int | None:
    """count_selectors로 '총 N건' 추출 (없으면 None)."""
    for c in cfg.get("count_selectors", []):
        if c.get("type") == "text_regex":
            m = re.search(c["pattern"], body)
            if m:
                return int(m.group(1).replace(",", ""))
    return None


def from_jsonld(soup: BeautifulSoup, wanted_types: list[str], base: str, cfg: dict[str, Any]) -> list[Posting]:
    """JSON-LD(JobPosting / ItemList)에서 공고 추출 (L2)."""
    postings: list[Posting] = []
    for tag in soup.select('script[type="application/ld+json"]'):
        raw = tag.string or tag.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        for node in _iter_jsonld_nodes(data):
            ntype = node.get("@type")
            types = ntype if isinstance(ntype, list) else [ntype]
            if "JobPosting" in types:
                p = _jobposting_to_posting(node, base, cfg)
                if p:
                    postings.append(p)
            elif "ItemList" in types and "ItemList" in wanted_types:
                for item in node.get("itemListElement", []) or []:
                    inner = item.get("item") if isinstance(item, dict) else None
                    if isinstance(inner, dict) and "JobPosting" in (
                        inner.get("@type") if isinstance(inner.get("@type"), list) else [inner.get("@type")]
                    ):
                        p = _jobposting_to_posting(inner, base, cfg)
                        if p:
                            postings.append(p)
    return postings


def _iter_jsonld_nodes(data: Any):
    """JSON-LD 최상위가 dict / list / @graph 인 경우를 평탄화."""
    if isinstance(data, list):
        for d in data:
            yield from _iter_jsonld_nodes(d)
    elif isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            for d in data["@graph"]:
                yield from _iter_jsonld_nodes(d)
        else:
            yield data


def _jobposting_to_posting(node: dict[str, Any], base: str, cfg: dict[str, Any]) -> Posting | None:
    title = node.get("title") or node.get("name")
    url = node.get("url") or node.get("@id")
    if not title or not url:
        return None
    url = urljoin(base, url)
    return Posting(
        job_id=derive_job_id(url, cfg),
        title=str(title).strip(),
        url=url,
        posted_date=node.get("datePosted"),
        dept=node.get("occupationalCategory"),
        employment_type=node.get("employmentType"),
        experience_text=_jsonld_experience(node),
    )


def _jsonld_experience(node: dict[str, Any]) -> str | None:
    req = node.get("experienceRequirements")
    if isinstance(req, dict):
        mo = req.get("monthsOfExperience")
        if mo is not None:
            return f"{int(mo) // 12}년"
        return req.get("description")
    if isinstance(req, str):
        return req
    return None


def parse_item(el: Tag, base: str, cfg: dict[str, Any]) -> Posting | None:
    """선택자로 잡은 요소 하나를 Posting으로 (L3/L4).

    합성 fixture 구조 기준. [검증필요] — 실제 잡코리아 DOM 확정 시 셀렉터 보강.
    앵커면 자기 href, 아니면 내부 첫 링크에서 URL을 얻는다.
    """
    href = None
    if el.name == "a" and el.get("href"):
        href = el.get("href")
    else:
        a = el.select_one("a[href]")
        if a:
            href = a.get("href")
    if not href:
        return None
    url = urljoin(base, href)

    def pick(*selectors: str) -> str | None:
        for sel in selectors:
            found = el.select_one(sel)
            if found is not None:
                return _text(found)
        return None

    title = pick(".title", ".post-title", "strong", "h2", "h3") or _text(el)
    if not title:
        return None
    return Posting(
        job_id=derive_job_id(url, cfg),
        title=title,
        url=url,
        posted_date=pick(".date", ".post-date", "time"),
        dept=pick(".dept", ".corp", ".company"),
        employment_type=pick(".employ", ".employ-type", ".emp-type"),
        experience_text=pick(".exp", ".experience", ".career"),
    )


def extract_with_fingerprint(
    body: str, cfg: dict[str, Any], base: str = ""
) -> tuple[int | None, list[Posting], dict[str, Any]]:
    """§6-5 다층 추출기. (declared, postings, meta) 반환."""
    soup = BeautifulSoup(body, "html.parser")
    meta: dict[str, Any] = {}

    declared = parse_declared(body, cfg)
    meta["declared"] = declared

    items = from_jsonld(soup, cfg.get("jsonld_types", []), base, cfg)
    if items:
        meta["item_layer"] = "jsonld"
    else:
        for i, sel in enumerate(cfg.get("item_selectors", [])):
            found = soup.select(sel)
            if found:
                items = [p for el in found if (p := parse_item(el, base, cfg)) is not None]
                if items:
                    meta["item_layer"] = f"selector[{i}]"
                    if i >= 2:  # L4 CSS 클래스로 떨어짐 → 곧 깨질 신호 (info 알림 대상)
                        meta["fragile"] = True
                    break

    # 중복 job_id 제거 (같은 공고가 여러 셀렉터/링크로 잡히는 경우)
    deduped: list[Posting] = []
    seen: set[str] = set()
    for p in items:
        if p.job_id in seen:
            continue
        seen.add(p.job_id)
        deduped.append(p)

    meta["parsed"] = len(deduped)
    return declared, deduped, meta
