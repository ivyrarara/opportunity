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

# 주의: BambooHR라도 회사가 JS 렌더 채용페이지를 쓰면 /careers/list가 HTML만 준다
# (예: NUDESTIX — 실측 결과 JSON 미제공 + 현재 공고 0건이라 봇 대상에서 제외).
# JSON(/careers/list에 result[] 반환)을 주는 BambooHR 회사만 여기 등록한다.
BAMBOOHR_BOARDS: dict[str, dict[str, Any]] = {}


def get_bamboohr_config(company_id: str) -> dict[str, Any] | None:
    return BAMBOOHR_BOARDS.get(company_id)
