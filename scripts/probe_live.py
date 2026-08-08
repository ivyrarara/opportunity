"""일회용 LEGO Workday tenant/site 추출 + BX 자리 (GitHub Actions 전용).

LEGO careers 가 wd103.myworkdayjobs.com(Workday) 사용 확인됨. careers 페이지에서
정확한 tenant/site를 뽑아 CXS로 디자인/브랜드/패키지 자리를 조회한다. 검증 후 삭제.
"""

from __future__ import annotations

import re

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
ch = httpx.Client(follow_redirects=True, timeout=25.0,
                  headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8"})
cj = httpx.Client(follow_redirects=True, timeout=25.0,
                  headers={"User-Agent": UA, "Accept": "application/json"})
BX = re.compile(r"design|brand|packag|graphic|visual|creative|experience|art director|illustrat|merchand", re.I)


def line(*a):
    print(*a, flush=True)


HOST = "wd103.myworkdayjobs.com"
# careers 페이지에서 site/tenant 단서 수집
sites, tenants = set(), set()
for url in ("https://www.lego.com/en-us/careers", "https://www.lego.com/en-us/careers/job-openings"):
    try:
        t = ch.get(url).text
    except Exception:
        continue
    for m in re.findall(r'wd103\.myworkdayjobs\.com/(?:wday/cxs/)?([A-Za-z0-9_]+)(?:/([A-Za-z0-9_]+))?', t):
        if m[0]:
            tenants.add(m[0]); sites.add(m[0])
        if m[1]:
            sites.add(m[1])
    for m in re.findall(r'/en-US/([A-Za-z0-9_]+)', t):
        sites.add(m)
line(f"추출 tenants={sorted(tenants)[:10]} sites={sorted(sites)[:15]}")

# 후보 조합으로 CXS 시도
tenant_cands = list(tenants) + ["lego", "legogroup", "thelegogroup", "LEGO"]
site_cands = list(sites) + ["External", "LEGO_External_Career_Site", "LEGO_Careers", "lego", "Careers"]

found = None
for tn in dict.fromkeys(tenant_cands):
    for st in dict.fromkeys(site_cands):
        url = f"https://{HOST}/wday/cxs/{tn}/{st}/jobs"
        try:
            r = cj.post(url, json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "designer"},
                        headers={"Content-Type": "application/json"})
        except Exception:
            continue
        if r.status_code == 200:
            try:
                d = r.json()
            except Exception:
                continue
            if isinstance(d, dict) and "jobPostings" in d:
                found = (tn, st, int(d.get("total") or 0))
                line(f"✅ HIT tenant='{tn}' site='{st}' total≈{found[2]}")
                break
    if found:
        break

if not found:
    line("❌ CXS 조합 못 찾음")
else:
    tn, st, _ = found
    base = f"https://{HOST}/wday/cxs/{tn}/{st}/jobs"
    jb = f"https://{HOST}/en-US/{st}"
    hits, seen = [], set()
    for q in ("designer", "brand", "packaging", "graphic", "experience"):
        try:
            posts = cj.post(base, json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q},
                            headers={"Content-Type": "application/json"}).json().get("jobPostings", [])
        except Exception:
            posts = []
        for p in posts:
            path = p.get("externalPath") or ""
            if path in seen:
                continue
            seen.add(path)
            t = p.get("title") or ""
            if BX.search(t):
                hits.append((t, p.get("locationsText") or "", jb + path))
    line(f"\nLEGO BX 자리 {len(hits)}개:")
    for t, l, u in hits[:25]:
        line(f"  • {t} — {l}")

line("\n==================== LEGO PROBE DONE ====================")
