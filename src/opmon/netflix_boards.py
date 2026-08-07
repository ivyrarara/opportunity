"""Netflix 자체 채용 API 설정.

Netflix는 표준 ATS를 쓰지 않고 자체 채용사이트(jobs.netflix.com)를 운영한다.
그 SPA가 호출하는 공개 검색 API는 인증 없이 JSON을 준다:

  GET https://jobs.netflix.com/api/search?q={query}&page={n}
  → {"records": {"postings": [{external_id, text(제목), team[], location, locations[], ...}]},
     "info": {"postings": {"total": N}}}

공고 상세 URL = https://jobs.netflix.com/jobs/{external_id}

company id로 키잉. 없으면(=미설정) 어댑터가 skip.
search_texts: 각 검색어로 페이지 순회 후 external_id 기준 합집합(dedupe).
location_contains: locations/location에 하나라도 포함될 때만 채택.
  Ivy 타겟 = Consumer Products APAC(한국 복귀 예정) → 한국/APAC/리모트 한정.
  비우면 위치 무관(전 세계) → 미국 UX 공고 폭주하므로 반드시 지정.
"""

from __future__ import annotations

from typing import Any

NETFLIX_BOARDS: dict[str, dict[str, Any]] = {
    # Netflix — Consumer Products(굿즈/브랜드/패키지) APAC 중심. jobs.netflix.com
    "netflix": {
        "host": "jobs.netflix.com",
        "search_texts": ["consumer products", "brand designer", "packaging", "graphic designer"],
        "location_contains": [
            "Korea", "Seoul", "Singapore", "Japan", "Tokyo",
            "APAC", "Asia", "Remote",
        ],
        "max_pages": 5,
    },
}


def get_netflix_config(company_id: str) -> dict[str, Any] | None:
    return NETFLIX_BOARDS.get(company_id)
