"""SPA/ATS fingerprint config (명세 §7-4).

회사별로 다르므로 company id로 키잉한다. 각 값은 DevTools(Network/Fetch·XHR)로
리스트 요청을 찾아 실측 확정해야 한다(§7-1) → 현재 전부 `[검증필요]` placeholder.

설정이 없는(=아직 실측 안 된) 회사는 어댑터가 skip한다. 하나씩 확정될 때마다 여기에 추가하면
오케스트레이터가 자동으로 실행에 포함한다.

스키마:
  mode: "api" | "render"
  # --- api 공통 ---
  api_url, method, headers?, params?(고정 쿼리),
  items_path (총목록 배열 경로), total_path (총개수 경로),
  paginate: {param, size_param?, size, start},
  item_fields: {id, title, url|url_template, date?, employment_type?, experience?, dept?}
  # --- render 공통 (§7-3) ---
  page_url, list_ready_selector, empty_state_selector, item_selector,
  count_selector?, render_timeout_ms, challenge_markers
"""

from __future__ import annotations

from typing import Any

# 실측 전 예시 골격 (§7-4). 실제 값 채워질 때까지 주석 처리로 두어 skip 되게 한다.
SPA_FINGERPRINT_EXAMPLE: dict[str, Any] = {
    "mode": "api",
    "api_url": "https://example.invalid/api/jobs",   # [검증필요]
    "method": "GET",
    "headers": {},
    "params": {},
    "items_path": ["result", "jobList"],             # [검증필요]
    "total_path": ["result", "totalCount"],          # [검증필요]
    "paginate": {"param": "page", "size_param": "size", "size": 50, "start": 1},
    "item_fields": {                                  # [검증필요]
        "id": ["id"],
        "title": ["title"],
        "url_template": "https://example.invalid/jobs/{id}",
        "date": ["postedAt"],
        "employment_type": ["employmentType"],
        "experience": ["career"],
        "dept": ["department"],
    },
    # render 예시
    "list_ready_selector": "[data-testid='job-card'], .JobCard",
    "empty_state_selector": "[data-testid='empty'], .empty-result",
    "count_selector": None,
    "item_selector": "[data-testid='job-card']",
    "render_timeout_ms": 15000,
    "challenge_markers": ["Checking your browser", "cf-chl", "DataDome", "잠시만 기다"],
}


# company id → SPA config. 실측 확정된 것만 넣는다.
# 지금은 비어 있음 → 모든 spa/greenhouse 회사는 어댑터가 skip (미구현이 아니라 "미설정").
SPA_FINGERPRINTS: dict[str, dict[str, Any]] = {
    # "toss": {... 실측 후 채움 ...},   # §7-5: SPA 공통 로직 검증 시작점
    # "coupang": {... greenhouse api ...},
}


def get_spa_config(company_id: str) -> dict[str, Any] | None:
    return SPA_FINGERPRINTS.get(company_id)
