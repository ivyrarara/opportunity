"""BambooHR 채용 설정 (예: NUDESTIX).

BambooHR 공개 채용 목록 API는 인증 없이 JSON을 준다(실측):
  GET https://{subdomain}.bamboohr.com/careers/list
  → {"result": [{id, jobOpeningName(제목), departmentLabel,
      location:{city,state,...} 또는 locationName, employmentStatusLabel, ...}]}

공고 상세 URL = https://{subdomain}.bamboohr.com/careers/{id}

company id로 키잉. 없으면(=미설정) 어댑터가 skip.
location_contains: 비우면 위치 무관(소규모 회사는 위치가 하나뿐이라 안 거는 게 안전).
"""

from __future__ import annotations

from typing import Any

BAMBOOHR_BOARDS: dict[str, dict[str, Any]] = {
    # NUDESTIX — Vaughan 뷰티 브랜드(패키지). BambooHR subdomain 'nudestix'.
    # 소규모라 위치 필터 없이 디자인/패키지 제목이면 다 잡는다(Ivy 최적핏).
    "nudestix": {
        "subdomain": "nudestix",
        "location_contains": [],
    },
}


def get_bamboohr_config(company_id: str) -> dict[str, Any] | None:
    return BAMBOOHR_BOARDS.get(company_id)
