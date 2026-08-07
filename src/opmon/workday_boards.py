"""Workday CXS 채용 API 설정 (토론토 모니터링).

토론토·북미 회사 다수가 Workday를 쓴다. 공개 CXS(Candidate Experience Service)
JSON API는 tenant/site만 알면 인증 없이 목록을 준다:

  POST https://{host}/wday/cxs/{tenant}/{site}/jobs
  body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "designer"}
  resp: {"total": N, "jobPostings": [{title, externalPath, locationsText, postedOn, bulletFields}]}

공고 상세 URL = https://{host}/{locale}/{site}{externalPath}

company id로 키잉한다. host/site는 회사 채용 페이지 URL에서 확정한다.
search_texts: 각 검색어로 조회 후 externalPath 기준으로 합집합(dedupe).
location_contains: 있으면 locationsText에 하나라도 포함될 때만 채택(토론토·캐나다·리모트 한정).
비어 있으면(=미설정) 어댑터가 skip 한다.
"""

from __future__ import annotations

from typing import Any

WORKDAY_BOARDS: dict[str, dict[str, Any]] = {
    # Canada Goose — 토론토 HQ(100 Queens Quay East). 채용 URL:
    #   canadagoose.wd3.myworkdayjobs.com/en-US/CanadaGooseCareers
    "canada_goose": {
        "host": "canadagoose.wd3.myworkdayjobs.com",
        "tenant": "canadagoose",
        "site": "CanadaGooseCareers",
        "locale": "en-US",
        "search_texts": ["designer", "packaging"],
        "location_contains": ["Toronto", "Ontario", "Canada", "Remote"],
    },
    # Aritzia — 밴쿠버 본사이나 토론토 디자인/리테일 다수. 채용 URL:
    #   aritzia.wd3.myworkdayjobs.com/en-US/External
    "aritzia": {
        "host": "aritzia.wd3.myworkdayjobs.com",
        "tenant": "aritzia",
        "site": "External",
        "locale": "en-US",
        "search_texts": ["designer", "graphic", "packaging"],
        "location_contains": ["Toronto", "Ontario", "Canada", "Remote"],
    },
}


def get_workday_config(company_id: str) -> dict[str, Any] | None:
    return WORKDAY_BOARDS.get(company_id)
