# -*- coding: utf-8 -*-
"""잡코리아 접속 진단 v3 (standalone). 표준 라이브러리만 — pip 불필요.

실행:  python probe.py
결과(===== 부터 진단 끝 까지)를 통째로 복사해서 전달하세요.
"""
import gzip
import io
import re
import ssl
import sys
import urllib.parse
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

BASE = "https://www.jobkorea.co.kr/Search/"
CASES = [
    ("결과 있음 (NHN)", "NHN"),
    ("결과 없음 (없는검색어)", "zzqxqzNoSuchCompany12345"),  # ASCII만 (인코딩 에러 회피)
]


def _decode(raw, resp):
    if "gzip" in (resp.headers.get("Content-Encoding") or "").lower():
        try:
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        except Exception:
            pass
    return raw.decode("utf-8", errors="replace")


def fetch(query):
    url = BASE + "?" + urllib.parse.urlencode({"stext": query})
    req = urllib.request.Request(url, headers=HEADERS)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
        return url, resp.status, _decode(resp.read(), resp)


def _text(html):
    t = re.sub(r"<script.*?</script>", " ", html, flags=re.I | re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.I | re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    import html as _h
    t = _h.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def analyze(label, query):
    print("\n" + "=" * 58)
    print("[", label, "]  검색어:", query)
    try:
        url, status, body = fetch(query)
    except Exception as e:
        print("접속실패:", type(e).__name__, str(e)[:200])
        return
    print("URL:", url)
    print("상태코드:", status, "| 길이:", len(body))

    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    title = m.group(1).strip() if m else ""
    print("제목:", title[:140])
    # 제목에서 총 N건
    tc = re.search(r"총\s*([0-9,]+)\s*건", title)
    print("제목의 총건수:", tc.group(1) if tc else "(제목에 없음)")

    ids = re.findall(r"GI_Read/([0-9]+)", body)
    uniq = list(dict.fromkeys(ids))
    print("고유 공고ID 수:", len(uniq), "| 예:", uniq[:5])

    # 카드 단위 텍스트 (data-sentry-component="CardJob" 기준 분할)
    cards = body.split('data-sentry-component="CardJob"')
    print("CardJob 조각 수:", len(cards) - 1)
    for i, seg in enumerate(cards[1:4], 1):
        seg = seg[:2500]
        cid = re.search(r"GI_Read/([0-9]+)", seg)
        print(f"\n  --- 카드{i} (id={cid.group(1) if cid else '?'}) 텍스트 ---")
        print("  ", _text(seg)[:280])

    # 첫 카드 원본 HTML (셀렉터 확인용)
    if len(cards) > 1:
        raw = re.sub(r"\s+", " ", cards[1][:1800])
        print("\n  --- 카드1 원본 HTML 앞부분 ---")
        print("  ", raw)

    empties = [w for w in ["검색결과가 없", "결과가 없", "일치하는", "0건", "다시 검색", "과 일치하는"]
               if w in body]
    print("\n빈상태 마커 후보:", empties if empties else "없음")


def main():
    print("=" * 58)
    print("잡코리아 진단 v3 시작 (파이썬", sys.version.split()[0], ")")
    for label, q in CASES:
        analyze(label, q)
    print("\n" + "=" * 58)
    print("진단 끝 — 위 ===== 부터 여기까지 전부 복사해서 전달하세요.")


if __name__ == "__main__":
    main()
