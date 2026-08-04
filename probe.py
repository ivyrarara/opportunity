# -*- coding: utf-8 -*-
"""잡코리아 접속 진단 (standalone). 파이썬 표준 라이브러리만 사용 — pip 설치 불필요.

실행:  python probe.py
결과(===== 로 감싼 부분)를 통째로 복사해서 전달하세요.
"""
import gzip
import io
import re
import ssl
import sys
import urllib.request
import urllib.error

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}

# 검색어(회사명)로 시도할 후보 URL들
CANDIDATES = [
    "https://m.jobkorea.co.kr/Search/?stext=NHN",
    "https://www.jobkorea.co.kr/Search/?stext=NHN",
]

BLOCK_MARKERS = ["비정상적인 접근", "잠시 후 다시", "captcha", "cf-chl", "DataDome",
                 "Access Denied", "차단", "로봇", "Are you a human", "보안문자"]
LIST_MARKERS = ["채용", "공고", "모집", "지원하기", "경력", "신입"]


def _decode(raw, resp):
    enc = (resp.headers.get("Content-Encoding") or "").lower()
    if "gzip" in enc:
        try:
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        except Exception:
            pass
    return raw.decode("utf-8", errors="replace")


def probe(url):
    print("\n" + "-" * 60)
    print("URL:", url)
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            raw = resp.read()
            body = _decode(raw, resp)
            status = resp.status
            final = resp.geturl()
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = _decode(e.read(), e)
        except Exception:
            pass
        print("상태코드:", e.code, "(HTTPError)")
        print("본문길이:", len(body))
        _analyze(body)
        return
    except Exception as e:
        print("접속실패:", type(e).__name__, str(e)[:200])
        return

    print("상태코드:", status)
    print("최종URL :", final)
    print("본문길이:", len(body))
    _analyze(body)


def _analyze(body):
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    print("페이지제목:", (m.group(1).strip()[:120] if m else "(없음)"))
    print("JSON-LD 있음:", "application/ld+json" in body)
    blocks = [w for w in BLOCK_MARKERS if w.lower() in body.lower()]
    print("차단/봇 의심 단어:", blocks if blocks else "없음")
    lists = [w for w in LIST_MARKERS if w in body]
    print("채용목록 관련 단어:", lists if lists else "없음")
    # 숫자+건 패턴 (총 N건 후보)
    counts = re.findall(r"([0-9][0-9,]{0,6})\s*건", body)
    print("'N건' 후보:", counts[:8] if counts else "없음")
    # 본문 앞부분 텍스트 살짝
    text = re.sub(r"<script.*?</script>", " ", body, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    print("본문미리보기:", text[:300])


def main():
    print("=" * 60)
    print("잡코리아 접속 진단 시작 (파이썬", sys.version.split()[0], ")")
    for url in CANDIDATES:
        probe(url)
    print("\n" + "=" * 60)
    print("진단 끝 — 위 ===== 부터 여기까지 전부 복사해서 전달하세요.")


if __name__ == "__main__":
    main()
