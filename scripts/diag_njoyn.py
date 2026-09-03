"""임시 진단 — Vaughan njoyn 목록 페이지 실제 응답을 찍는다.
Actions(비차단 IP)에서 1회 실행 후 로그 분석하고 제거할 것.
"""
from __future__ import annotations

import re

import httpx

from opmon.http_client import REAL_BROWSER_HEADERS
from opmon.njoyn_boards import get_njoyn_config
from opmon.adapters.njoyn import listing_url, _EMPTY_MARKERS

scfg = get_njoyn_config("vaughan")
url = listing_url(scfg)
print("URL:", url)

try:
    r = httpx.get(url, headers=REAL_BROWSER_HEADERS, follow_redirects=True, timeout=30)
except Exception as e:
    print("EXC:", repr(e))
    raise SystemExit(0)

body = r.text
low = body.lower()
print("STATUS:", r.status_code)
print("FINAL_URL:", str(r.url))
print("BYTES:", len(body))
print("has 'jobdetails':", "jobdetails" in low)
print("count 'jobid=':", len(re.findall(r"[?&]jobid=", low)))
print("count <a href>:", low.count("<a "))
print("empty_marker_hit:", [mk for mk in _EMPTY_MARKERS if mk in low])

# href 샘플(앵커 URL 패턴이 바뀌었는지 확인)
from bs4 import BeautifulSoup
soup = BeautifulSoup(body, "html.parser")
hrefs = [a.get("href", "") for a in soup.select("a[href]")]
job_like = [h for h in hrefs if "job" in h.lower() or "detail" in h.lower()]
print("---- job-ish hrefs (up to 15) ----")
for h in job_like[:15]:
    print("  ", h[:160])

# 사람이 읽는 텍스트(빈결과 메시지 확인용) — 앞 2500자
text = soup.get_text(" ", strip=True)
print("---- visible text (2500 chars) ----")
print(text[:2500])
