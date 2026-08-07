"""HRSmart(ClearCompany) 채용포털 설정 — BC Public Service 등.

목록 페이지 HTML에서 공고 상세 링크(/hr/ats/Posting/view/{id})를 href 패턴으로 뽑는다.
company id로 키잉. 없으면 skip.
"""

from __future__ import annotations

from typing import Any

HRSMART_BOARDS: dict[str, dict[str, Any]] = {
    # BC Public Service — 주정부(GDX 등). HRSmart.
    #   bcpublicservice.hua.hrsmart.com/hr/ats/JobSearch/search
    "bc_public_service": {
        "host": "bcpublicservice.hua.hrsmart.com",
        "path": "/hr/ats/JobSearch/search",
    },
}


def get_hrsmart_config(company_id: str) -> dict[str, Any] | None:
    return HRSMART_BOARDS.get(company_id)
