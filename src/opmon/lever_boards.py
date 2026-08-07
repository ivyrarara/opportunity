"""Lever 채용 API 설정 (예: Arc'teryx).

Lever 공개 API는 인증 없이 JSON 배열을 준다:
  GET https://api.lever.co/v0/postings/{slug}?mode=json
  → [{id, text(제목), hostedUrl, categories:{location,department,commitment,team}, createdAt}, ...]

company id로 키잉. 없으면 skip.
location_contains: categories.location에 하나라도 포함될 때만 채택(밴쿠버/BC/캐나다 한정).
"""

from __future__ import annotations

from typing import Any

LEVER_BOARDS: dict[str, dict[str, Any]] = {
    # Arc'teryx — 노스밴쿠버 본사. jobs.lever.co/arcteryx.com
    "arcteryx": {
        "slug": "arcteryx.com",
        "location_contains": ["Vancouver", "British Columbia", ", BC", "Canada", "Remote"],
    },
    # Wealthsimple — 토론토 본사 핀테크. jobs.lever.co/wealthsimple
    "wealthsimple": {
        "slug": "wealthsimple",
        "location_contains": ["Toronto", "Ontario", "Vancouver", "Canada", "Remote"],
    },
}


def get_lever_config(company_id: str) -> dict[str, Any] | None:
    return LEVER_BOARDS.get(company_id)
