"""일회용 Disney/LEGO ATS 탐지 + BX 자리 라이브 체크 (GitHub Actions 전용).

두 회사의 채용 시스템을 알아내고, 닿으면 디자인/브랜드/패키지/experience 자리를
실제로 뽑는다. 검증 후 삭제.
"""

from __future__ import annotations

import json
import re

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
cj = httpx.Client(follow_redirects=True, timeout=25.0,
                  headers={"User-Agent": UA, "Accept": "application/json"})
ch = httpx.Client(follow_redirects=True, timeout=25.0,
                  headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8"})

BX = re.compile(r"design|brand|packag|graphic|visual|creative|experience|art director|illustrat|merchand", re.I)


def line(*a):
    print(*a, flush=True)


def detect(html):
    low = html.lower()
    sig = []
    for k, name in [("myworkdayjobs", "WORKDAY"), ("successfactors", "SUCCESSFACTORS"),
                    ("phenom", "PHENOM"), ("radancy", "RADANCY"), ("icims", "ICIMS"),
                    ("greenhouse.io", "GREENHOUSE"), ("eightfold", "EIGHTFOLD"),
                    ("avature", "AVATURE"), ("workablehr", "WORKABLE")]:
        if k in low:
            sig.append(name)
    bot = any(b in low for b in ("perfdrive", "captcha", "botmanager", "are you human"))
    return sig, bot


def try_workday(name, host, tenant, sites):
    for site in sites:
        url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
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
                return host, site, d
    return None


def workday_pull(name, host, tenant, site):
    base = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    jb = f"https://{host}/en-US/{site}"
    hits, seen = [], set()
    for q in ("designer", "brand", "packaging", "graphic", "experience design"):
        try:
            d = cj.post(base, json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q},
                        headers={"Content-Type": "application/json"}).json()
        except Exception:
            continue
        for p in d.get("jobPostings", []):
            path = p.get("externalPath") or ""
            if path in seen:
                continue
            seen.add(path)
            t = p.get("title") or ""
            if BX.search(t):
                hits.append((t, p.get("locationsText") or "", jb + path))
    line(f"   ✅ Workday {host} site='{site}' — BX 자리 {len(hits)}")
    for t, l, u in hits[:20]:
        line(f"      • {t} — {l}")


# ---------------- Disney ----------------
def disney():
    line("\n########## DISNEY ##########")
    wd = (try_workday("Disney", "disney.wd5.myworkdayjobs.com", "disney", ["disney", "External", "Professional"])
          or try_workday("Disney", "disney.wd1.myworkdayjobs.com", "disney", ["disney", "External"]))
    if wd:
        workday_pull("Disney", *wd)
    # 자체 careers API/landing 탐지
    for url in ("https://jobs.disneycareers.com/api/jobs?keyword=designer&limit=20",
                "https://jobs.disneycareers.com/search-jobs/results?ActiveFacetID=0&keyword=designer",
                "https://jobs.disneycareers.com"):
        try:
            r = ch.get(url)
        except Exception as e:
            line(f"   {url}\n     ERR {type(e).__name__}"); continue
        sig, bot = detect(r.text)
        njobs = len(re.findall(r'/job/|jobId|requisitionId', r.text))
        line(f"   {url}\n     HTTP {r.status_code} ATS={sig or '?'} bot={bot} len={len(r.text)} job신호={njobs}")


# ---------------- LEGO ----------------
def lego():
    line("\n########## LEGO ##########")
    wd = (try_workday("LEGO", "lego.wd3.myworkdayjobs.com", "lego", ["lego", "External", "LEGO_External"])
          or try_workday("LEGO", "legogroup.wd3.myworkdayjobs.com", "legogroup", ["External", "lego"]))
    if wd:
        workday_pull("LEGO", *wd)
    for url in ("https://www.lego.com/en-us/careers/job-openings",
                "https://www.lego.com/en-us/careers"):
        try:
            r = ch.get(url)
        except Exception as e:
            line(f"   {url}\n     ERR {type(e).__name__}"); continue
        sig, bot = detect(r.text)
        hosts = sorted(set(re.findall(r"([a-z0-9-]+\.myworkdayjobs\.com)", r.text.lower())))
        line(f"   {url}\n     HTTP {r.status_code} ATS={sig or '?'} bot={bot} len={len(r.text)} wd_hosts={hosts}")


disney()
lego()
line("\n==================== DISNEY/LEGO PROBE DONE ====================")
