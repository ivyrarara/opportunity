"""사이트별 fingerprint config (명세 §6-3).

fingerprint는 "이 페이지가 우리가 아는 그 검색결과 페이지인가"를 계층적으로 확인하고,
공고 리스트와 "총 N건"을 추출하기 위한 셀렉터/마커 모음이다.

안정성 순서(하나에 베팅 금지):
  L1 URL·"총 N건"·title 텍스트 → L2 JSON-LD → L3 시맨틱 속성/링크패턴 → L4 CSS 클래스(최후 그물)

주의: `[검증필요]`로 표시된 값은 접근이 뚫린 환경에서 NHN probe(§6-4) 1회로 실측 확정해야 한다.
현재 세션은 egress 정책상 m.jobkorea.co.kr 접근이 차단되어 실측 미완 → 아래는 명세 기준 잠정값이다.
"""

from __future__ import annotations

from typing import Any

# [검증필요] 실측 전 잠정값. probe로 확정 후 갱신.
JOBKOREA_M_FINGERPRINT: dict[str, Any] = {
    "url_ok_patterns": [r"m\.jobkorea\.co\.kr"],
    "title_contains": ["잡코리아", "채용", "검색"],  # [검증필요]
    "count_selectors": [  # "총 N건" — 위→아래 우선순위 [검증필요]
        {"type": "text_regex", "pattern": r"총\s*([\d,]+)\s*건"},
        {"type": "text_regex", "pattern": r"검색결과\s*([\d,]+)"},
        {"type": "text_regex", "pattern": r"채용중\s*([\d,]+)"},
    ],
    "jsonld_types": ["JobPosting", "ItemList"],
    "anchor_selectors": ["#content", "form.form-search"],  # [검증필요]
    "item_selectors": [  # 위→아래 fallback [검증필요]
        'a[href*="/Recruit/GI_Read/"]',  # L3 링크패턴 (잘 안 바뀜)
        'a[href*="/Recruit/Co_Read/"]',  # L3
        ".list-default .list-post",  # L4 클래스 (개편 시 1순위 파손)
        ".recruit-info .list-item",  # L4
    ],
    "empty_markers": [  # [검증필요]
        "검색결과가 없습니다",
        "검색된 공고가 없",
        "일치하는 채용정보가 없",
        "등록된 채용정보가 없",
        "결과가 없습니다",
    ],
    "block_markers": [
        "비정상적인 접근",
        "Access Denied",
        "cf-browser-verification",
        "잠시 후 다시 시도",
        "자동입력 방지문자",
        "로봇이 아닙니다",
        "captcha",
        "unusual traffic",
    ],
    "login_redirect_hosts": ["login.jobkorea.co.kr"],
    "min_body_bytes": 3000,
    # 공고 상세 링크로 job_id를 뽑을 URL 패턴 (사이트 고유 ID 우선; §2-2)
    "job_id_url_patterns": [
        r"/Recruit/GI_Read/(\d+)",
        r"/Recruit/Co_Read/(\d+)",
    ],
}


# fingerprint 이름 → 정의. targets.json의 company.fingerprint 문자열이 여기를 참조한다.
FINGERPRINTS: dict[str, dict[str, Any]] = {
    "JOBKOREA_M_FINGERPRINT": JOBKOREA_M_FINGERPRINT,
}


def get_fingerprint(name: str) -> dict[str, Any]:
    try:
        return FINGERPRINTS[name]
    except KeyError as exc:
        raise KeyError(f"알 수 없는 fingerprint: {name!r}") from exc
