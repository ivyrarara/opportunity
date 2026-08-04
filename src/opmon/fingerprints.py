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

# 실측 완료 (2026-08, www.jobkorea NHN probe). 데스크탑 www가 실제 검색됨(모바일 m은 검색어 무시).
# 구조: React SSR(Next.js). 클래스명 불안정(Tailwind) → 안정 표식(GI_Read 링크, CardJob, 제목 총N건)에 베팅.
JOBKOREA_M_FINGERPRINT: dict[str, Any] = {
    "url_ok_patterns": [r"www\.jobkorea\.co\.kr", r"jobkorea\.co\.kr"],
    # 결과 제목엔 "채용", 빈 결과 제목엔 "잡코리아"/"통합검색" → ANY 매칭으로 페이지 확인
    "title_contains": ["잡코리아", "채용", "검색", "통합검색"],
    "count_selectors": [  # "총 N건" — 제목/본문에서 (제목 <title>이 본문 앞이라 먼저 매칭됨)
        {"type": "text_regex", "pattern": r"총\s*([\d,]+)\s*건"},
    ],
    "jsonld_types": ["JobPosting", "ItemList"],  # 잡코리아는 BreadcrumbList뿐이라 미사용 → 링크패턴 계층으로
    "anchor_selectors": [],  # CSS 앵커 대신 title_contains로 페이지 확인 (React라 안정 클래스 없음)
    "paginated": True,  # 페이지당 20건 / 총 N건. declared>parsed는 정상(파싱0일 때만 파손)
    "item_selectors": [  # L3 링크패턴에 베팅 (React 클래스 불안정)
        'a[href*="/Recruit/GI_Read/"]',  # 공고 상세 링크 — 카드마다 존재, 실측 확인
        'a[href*="/Recruit/Co_Read/"]',  # 회사 상세 (fallback)
    ],
    "empty_markers": [  # 실측: 빈 결과 페이지에 존재 확인
        "검색결과가 없",
        "결과가 없",
        "다시 검색",
        "일치하는",
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
    "min_body_bytes": 5000,  # 실측: 결과 344KB / 빈결과 211KB. 봇 차단 페이지는 보통 훨씬 작음
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
