"""Netflix 자체 채용 API 설정 (Eightfold 기반).

Netflix 채용은 Eightfold 탤런트 사이트(explore.jobs.netflix.net)로 운영된다.
공개 검색 API는 인증 없이 JSON을 준다(실측 확인):

  GET https://{host}/api/apply/v2/jobs?domain={domain}&start={n}&num={k}&query={q}
  → {..., "count": N, "positions": [{id, name(제목), location, locations[],
      department, display_job_id, t_create, ...}]}

공고 상세 URL = https://{host}/careers?pid={id}&domain={domain}&sort_by=relevance

company id로 키잉. 없으면(=미설정) 어댑터가 skip.
search_texts: 각 검색어로 start/num 페이지네이션 후 id 기준 합집합(dedupe).
location_contains: location/locations에 하나라도 포함될 때만 채택.
  Ivy 타겟 = APAC(한국 복귀) + 토론토 온사이트(현 거주) + 북미 리모트.
  비우면 위치 무관(전 세계) → 미국 온사이트 폭주하므로 반드시 지정.
"""

from __future__ import annotations

from typing import Any

NETFLIX_BOARDS: dict[str, dict[str, Any]] = {
    "netflix": {
        "host": "explore.jobs.netflix.net",
        "domain": "netflix.com",
        "search_texts": [
            "consumer products", "brand designer", "packaging designer",
            "graphic designer", "visual designer",
        ],
        "location_contains": [
            # APAC (한국 복귀 2026.02 대비)
            "Korea", "Seoul", "Singapore", "Japan", "Tokyo", "APAC", "Asia",
            # 토론토 온사이트 (현 거주) + 북미 리모트
            "Toronto", "Ontario", "Canada", "Remote",
        ],
        "num": 25,
        "max_pages": 4,
    },
}


def get_netflix_config(company_id: str) -> dict[str, Any] | None:
    return NETFLIX_BOARDS.get(company_id)
