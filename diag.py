# -*- coding: utf-8 -*-
"""잡코리아: 어떤 헤더 조합이 '데스크탑(공고 담긴) 페이지'를 주는지 시험.

httpx(파이프라인과 동일 transport)로 여러 헤더 조합 × 검색어를 시험해,
'search/mobile'(모바일 앱) 대신 'CardJob'/'GI_Read'(데스크탑 SSR)가 오는 조합을 찾는다.

실행:  python diag.py
결과 전체를 복사해서 전달하세요.
"""
import httpx

URL = "https://www.jobkorea.co.kr/Search/?stext={q}"

UA_DESKTOP = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

VARIANTS = {
    "A_minimal(UA만)": {"User-Agent": UA_DESKTOP},
    "B_probe식(UA+Accept+Lang+UIR)": {
        "User-Agent": UA_DESKTOP,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Upgrade-Insecure-Requests": "1",
    },
    "C_현재헤더(Sec-Fetch포함)": {
        "User-Agent": UA_DESKTOP,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
    },
}

QUERIES = [("NHN", "NHN"), ("한글(엔에이치엔)", "엔에이치엔")]


def probe(name, headers, qlabel, q):
    try:
        with httpx.Client(follow_redirects=True, timeout=20.0) as cli:
            r = cli.get(URL.format(q=q), headers=headers)
        body = r.text
        mobile = "search/mobile" in body
        card = "CardJob" in body
        gi = "GI_Read" in body
        chong = "총" in body and "건" in body
        verdict = "★데스크탑OK" if (card or gi) else ("모바일" if mobile else "??")
        print(f"[{name} | {qlabel}] status={r.status_code} len={len(body)} "
              f"mobile={mobile} CardJob={card} GI_Read={gi} 총건={chong} → {verdict}")
    except Exception as e:
        print(f"[{name} | {qlabel}] 실패: {type(e).__name__} {str(e)[:120]}")


print("=" * 60)
print("잡코리아 헤더 조합 시험 (httpx)")
for name, headers in VARIANTS.items():
    for qlabel, q in QUERIES:
        probe(name, headers, qlabel, q)
print("=" * 60)
print("진단 끝 — 위 전체를 복사해서 전달하세요. '★데스크탑OK'가 뜨는 줄이 정답 조합입니다.")
