# -*- coding: utf-8 -*-
"""설치된 opmon으로 잡코리아 1개 회사를 실제 취득→분류→추출 진단.

실행:  python diag.py
결과 전체를 복사해서 전달하세요.
"""
import re

from opmon.adapters.jobkorea import DEFAULT_BASE, build_search_url
from opmon.classify import classify
from opmon.config import load_targets
from opmon.extract import extract_with_fingerprint
from opmon.fingerprints import get_fingerprint
from opmon.http_client import REAL_BROWSER_HEADERS, fetch

print("=" * 58)
cfg = load_targets()
c = cfg.get_company("nhn")
url = build_search_url(c)
print("회사:", c.id, "| 검색어:", c.brand_filter or c.name)
print("URL:", url)

resp, exc = fetch(url, headers=REAL_BROWSER_HEADERS)
print("예외:", repr(exc)[:200] if exc else "없음")
if resp is not None:
    body = resp.text
    print("상태코드:", resp.status_code)
    print("Content-Encoding:", resp.headers.get("content-encoding"))
    print("Content-Type:", resp.headers.get("content-type"))
    print("본문 길이:", len(body))
    print("'총' 포함:", "총" in body, "| 'GI_Read' 포함:", "GI_Read" in body,
          "| 'CardJob' 포함:", "CardJob" in body)
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    print("제목:", (m.group(1).strip()[:120] if m else "(없음)"))

    fp = get_fingerprint(c.fingerprint or "JOBKOREA_M_FINGERPRINT")
    o, meta = classify(resp, exc, fp, base=DEFAULT_BASE)
    print("\n>>> OUTCOME:", o)
    print(">>> META:", {k: meta[k] for k in meta if k not in ()})

    declared, items, ex = extract_with_fingerprint(body, fp, base=DEFAULT_BASE)
    print(">>> declared:", declared, "| parsed:", len(items))
    for p in items[:6]:
        print("   -", p.job_id, "|", p.title[:60])

    print("\n본문 앞 400자(원본):")
    print(repr(body[:400]))
print("=" * 58)
print("진단 끝 — 위 전체를 복사해서 전달하세요.")
