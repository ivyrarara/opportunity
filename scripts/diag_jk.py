"""잡코리아 접속 진단 — 러너 공인 IP + 잡코리아 직접 접속 성공/실패를 기록.

랜덤 차단인지(시간대 무관 IP 룰렛) vs 시간대 차단인지 vs 하드 차단인지 판정용.
GitHub Actions 러너는 직접 인터넷(프록시 없음)이라 실측이 그대로 프로덕션과 일치.
매 실행 한 줄 요약을 남겨 로그에서 grep 하기 쉽게 한다.
"""
import time
from datetime import datetime, timezone

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "text/html,*/*",
     "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"}

IP_ECHOS = ["https://checkip.amazonaws.com", "https://api.ipify.org",
            "https://ifconfig.me/ip"]
# 프로덕션 어댑터와 동일한 경로(잡코리아 통합검색) + 홈페이지 기준선
JK_URLS = [
    ("home", "https://www.jobkorea.co.kr/"),
    ("search", "https://www.jobkorea.co.kr/Search/?stext=%EB%84%A4%EC%9D%B4%EB%B2%84"),  # 네이버
]


def get_ip():
    for u in IP_ECHOS:
        try:
            r = httpx.get(u, timeout=8)
            if r.status_code == 200:
                return r.text.strip()
        except Exception:
            continue
    return "?"


def probe(url):
    t0 = time.monotonic()
    try:
        r = httpx.get(url, headers=H, timeout=20, follow_redirects=True)
        ms = int((time.monotonic() - t0) * 1000)
        return f"status={r.status_code} ms={ms} bytes={len(r.text)}"
    except Exception as e:
        ms = int((time.monotonic() - t0) * 1000)
        return f"status=ERR ms={ms} err={type(e).__name__}:{str(e)[:60]}"


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    ip = get_ip()
    print(f"JKDIAG| utc={now} ip={ip}")
    for name, url in JK_URLS:
        print(f"JKDIAG|   {name}: {probe(url)}")


if __name__ == "__main__":
    main()
