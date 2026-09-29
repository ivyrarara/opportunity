"""Greenhouse 채용 보드 설정 (예: Figma, Pinterest).

Greenhouse 공개 보드 API는 인증 없이 JSON을 준다:
  GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=false
  → {"meta": {"total": N}, "jobs": [{id, title, absolute_url, location:{name}, updated_at}, ...]}

company id로 키잉. 없으면(=미설정) 어댑터가 skip.
location_contains: location.name에 하나라도 포함될 때만 채택.
  Figma/Pinterest는 미국 중심 → 토론토/캐나다/Remote(북미)만 남긴다(원격 자리 위주).
"""

from __future__ import annotations

from typing import Any

_NA_REMOTE = ["Toronto", "Ontario", "Canada", "Remote"]
# 한국 복귀 대비 — 서울/한국 소재 자리만. Greenhouse location.name은 보통 "Seoul, South Korea".
_KR_SEOUL = ["Seoul", "Korea", "Remote"]

GREENHOUSE_BOARDS: dict[str, dict[str, Any]] = {
    # Figma — Greenhouse token "figma". 프로덕트/브랜드 디자인.
    "figma": {
        "token": "figma",
        "location_contains": _NA_REMOTE,
    },
    # Pinterest — Greenhouse token "pinterest". 프로덕트/브랜드/크리에이티브.
    "pinterest": {
        "token": "pinterest",
        "location_contains": _NA_REMOTE,
    },
    # Coupang — Greenhouse token "coupang". 서울/한국 비주얼·브랜드·디자인 자리
    # (예: Senior Visual & Multimedia Designer, Seoul). jobkorea IP 차단 대체 이전(2026-09).
    "coupang": {
        "token": "coupang",
        "location_contains": _KR_SEOUL,
    },
}


def get_greenhouse_config(company_id: str) -> dict[str, Any] | None:
    return GREENHOUSE_BOARDS.get(company_id)
