# -*- coding: utf-8 -*-
"""파이프라인과 동일 경로(opmon fetch→classify→extract) 전체 진단.

실행:  python diag.py > out.txt 2>&1
그다음:  notepad out.txt   → 전체 복사해서 전달.
"""
import re

from bs4 import BeautifulSoup

from opmon.adapters.jobkorea import DEFAULT_BASE, build_search_url
from opmon.classify import classify
from opmon.config import load_targets
from opmon.extract import extract_with_fingerprint, parse_item
from opmon.fingerprints import get_fingerprint
from opmon.http_client import REAL_BROWSER_HEADERS, fetch

print("=" * 60)
cfg = load_targets()
c = cfg.get_company("nhn")
url = build_search_url(c)
fp = get_fingerprint(c.fingerprint or "JOBKOREA_M_FINGERPRINT")
print("회사:", c.id, "| 검색어:", c.brand_filter or c.name)
print("URL:", url)

resp, exc = fetch(url, headers=REAL_BROWSER_HEADERS)
print("예외:", repr(exc)[:200] if exc else "없음")
if resp is None:
    raise SystemExit("resp 없음")

body = resp.text
print("상태:", resp.status_code, "| 길이:", len(body),
      "| Content-Encoding:", resp.headers.get("content-encoding"))
print("CardJob:", "CardJob" in body, "| GI_Read:", "GI_Read" in body,
      "| 'search/mobile':", "search/mobile" in body)
m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
print("제목:", (m.group(1).strip()[:130] if m else "(없음)"))

# 원시 셀렉터가 몇 개 잡는지 + parse_item 성공 수
soup = BeautifulSoup(body, "html.parser")
gi_anchors = soup.select('a[href*="/Recruit/GI_Read/"]')
print("GI_Read 앵커 수(셀렉터):", len(gi_anchors))
parsed_ok = 0
sample_titles = []
for a in gi_anchors[:40]:
    p = parse_item(a, DEFAULT_BASE, fp)
    if p is not None:
        parsed_ok += 1
        if len(sample_titles) < 6:
            sample_titles.append((p.job_id, p.title[:50]))
print("parse_item 성공 수(앞40개 중):", parsed_ok)
for jid, t in sample_titles:
    print("   -", jid, "|", t)

o, meta = classify(resp, exc, fp, base=DEFAULT_BASE)
print("\n>>> OUTCOME:", o)
print(">>> META:", dict(meta))

declared, items, ex = extract_with_fingerprint(body, fp, base=DEFAULT_BASE)
print(">>> declared:", declared, "| parsed(dedup):", len(items))

print("\n본문 앞 300자:", repr(body[:300]))
print("=" * 60)
print("진단 끝 — out.txt 전체를 복사해서 전달하세요.")
