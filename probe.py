# -*- coding: utf-8 -*-
"""잡코리아 접속 진단 v2 (standalone). 표준 라이브러리만 — pip 불필요.

실행:  python probe.py
결과(===== 부터 진단 끝 까지)를 통째로 복사해서 전달하세요.
"""
import gzip
import io
import json
import re
import ssl
import sys
import urllib.request
import urllib.error

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
}

# 데스크탑이 실제로 검색됨. 결과있음 / 결과없음(빈 상태) 둘 다 본다.
CASES = [
    ("결과 있음 (NHN)", "https://www.jobkorea.co.kr/Search/?stext=NHN"),
    ("결과 없음 추정", "https://www.jobkorea.co.kr/Search/?stext=존재하지않는회사명zzq123"),
]


def _decode(raw, resp):
    if "gzip" in (resp.headers.get("Content-Encoding") or "").lower():
        try:
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        except Exception:
            pass
    return raw.decode("utf-8", errors="replace")


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
        return resp.status, resp.geturl(), _decode(resp.read(), resp)


def analyze(label, url):
    print("\n" + "=" * 58)
    print("[", label, "]")
    print("URL:", url)
    try:
        status, final, body = fetch(url)
    except Exception as e:
        print("접속실패:", type(e).__name__, str(e)[:200])
        return
    print("상태코드:", status, "| 최종URL:", final, "| 길이:", len(body))

    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    print("제목:", m.group(1).strip()[:140] if m else "(없음)")

    # 총 N건
    counts = re.findall(r"총\s*<?[^>]*>?\s*([0-9,]+)\s*<?[^>]*>?\s*건", body)
    print("'총 N건' 후보:", counts[:6] if counts else "없음")

    # 공고 상세 링크 (GI_Read = 잡코리아 채용 상세)
    links = re.findall(r'href="([^"]*GI_Read/[0-9]+[^"]*)"', body)
    ids = re.findall(r"GI_Read/([0-9]+)", body)
    print("GI_Read 링크 수:", len(links), "| 고유 공고ID 수:", len(set(ids)))
    if links:
        print("링크 예시:", links[0][:120])

    # JSON-LD 블록
    lds = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', body, re.I | re.S)
    print("JSON-LD 블록 수:", len(lds))
    for i, ld in enumerate(lds[:3]):
        snippet = ld.strip()
        types = re.findall(r'"@type"\s*:\s*"([^"]+)"', snippet)
        print(f"  [LD{i}] @type들:", types[:12])
        print(f"  [LD{i}] 앞부분:", snippet[:600].replace("\n", " "))

    # 첫 공고 카드 주변 HTML (셀렉터 파악용)
    pos = body.find("GI_Read/")
    if pos != -1:
        start = max(0, pos - 700)
        chunk = body[start:pos + 400]
        chunk = re.sub(r"\s+", " ", chunk)
        print("공고카드 주변 HTML:\n", chunk[:1100])

    # 빈 상태 마커 후보
    empties = [w for w in ["검색결과가 없", "결과가 없", "0건", "일치하는", "검색 결과가 없", "다시 검색"]
               if w in body]
    print("빈상태 마커 후보:", empties if empties else "없음")


def main():
    print("=" * 58)
    print("잡코리아 진단 v2 시작 (파이썬", sys.version.split()[0], ")")
    for label, url in CASES:
        analyze(label, url)
    print("\n" + "=" * 58)
    print("진단 끝 — 위 ===== 부터 여기까지 전부 복사해서 전달하세요.")


if __name__ == "__main__":
    main()
