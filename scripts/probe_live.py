"""일회용 통합 탐색 (GitHub Actions 전용).

A) Lululemon Avature: 초기 HTML엔 10개뿐(JS렌더) → AJAX/결과 엔드포인트를 찾는다.
B) 은행 5곳: Scotiabank/CIBC/BMO(Workday 후보), RBC/TD(ATS 탐지).
C) NUDESTIX: 소규모 뷰티 브랜드 ATS 탐지(Lever/Greenhouse/Workable/BambooHR).

검증 후 이 파일/probe.yml 삭제. 봇 targets 는 건드리지 않는다.
"""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
H_HTML = {"User-Agent": UA, "Accept": "text/html,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
H_XHR = {**H_HTML, "X-Requested-With": "XMLHttpRequest"}
H_JSON = {"User-Agent": UA, "Accept": "application/json"}
client = httpx.Client(follow_redirects=True, timeout=25.0)

try:
    from opmon.relevance import is_design_or_access
except Exception:
    def is_design_or_access(t):
        return "design" in (t or "").lower()

CA = ("toronto", "ontario", ", on", "vaughan", "markham", "canada", "vancouver",
      "british columbia", ", bc", "remote")


def line(*a):
    print(*a, flush=True)


def count_jobdetail(html):
    soup = BeautifulSoup(html, "html.parser")
    a = soup.find_all("a", href=re.compile(r"/JobDetail/|/careers/JobDetail/"))
    rows, seen = [], set()
    for x in a:
        m = re.search(r"/JobDetail/([^/]+)/(\d+)", x.get("href", ""))
        if not m or m.group(2) in seen:
            continue
        seen.add(m.group(2))
        rows.append((m.group(2), x.get_text(strip=True) or m.group(1).replace("-", " ")))
    return rows


# ---------------------------------------------------- A) Lululemon Avature AJAX
def avature():
    line("\n########## A) Lululemon Avature — AJAX/결과 엔드포인트 탐색 ##########")
    base = "https://careers.lululemon.com"
    cands = [
        (f"{base}/en_US/careers/SearchJobs?jobRecordsPerPage=200", H_XHR),
        (f"{base}/en_US/careers/JobResultList?jobRecordsPerPage=200", H_XHR),
        (f"{base}/en_US/careers/SearchJobs/?jobRecordsPerPage=200&folderRecordsSource=1", H_XHR),
        (f"{base}/en_US/careers/SearchJobs/ProcessSearch?jobRecordsPerPage=200", H_XHR),
        (f"{base}/en_US/careers/JobRss", H_HTML),
        (f"{base}/en_US/careers/SearchJobs/?keyword=designer&jobRecordsPerPage=200", H_XHR),
    ]
    for url, h in cands:
        try:
            r = client.get(url, headers=h)
        except Exception as e:
            line(f"  {url}\n    ERR {type(e).__name__}")
            continue
        rows = count_jobdetail(r.text) if "JobDetail" in r.text else []
        line(f"  {url}\n    HTTP {r.status_code} len={len(r.text)} JobDetail유니크={len(rows)}")
        if len(rows) > 10:
            des = [x for x in rows if is_design_or_access(x[1])]
            line(f"    ✅ 전체 목록! 디자인 제목 {len(des)}개: {[t for _, t in des][:15]}")


# ---------------------------------------------------- B) 은행
WD_BANKS = {
    "Scotiabank": ("scotiabank.wd3.myworkdayjobs.com", "scotiabank",
                   ["Scotiabank_Careers", "External", "scotia_external", "Careers"]),
    "CIBC": ("cibc.wd3.myworkdayjobs.com", "cibc",
             ["External", "CIBC_Careers", "cibc", "CIBC_External"]),
    "BMO": ("bmo.wd3.myworkdayjobs.com", "bmo",
            ["External", "BMO_External", "BMO_Careers", "External_Career_Site"]),
    "TD": ("td.wd3.myworkdayjobs.com", "td",
           ["External", "TD_External", "TD_Bank_Careers", "Careers"]),
    "RBC": ("rbc.wd3.myworkdayjobs.com", "rbc",
            ["External", "RBC_External", "Careers"]),
}


def wd_probe():
    line("\n########## B) 은행 — Workday 탐색 ##########")
    for name, (host, tenant, sites) in WD_BANKS.items():
        found = None
        for site in sites:
            url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
            try:
                r = client.post(url, json={"appliedFacets": {}, "limit": 20, "offset": 0,
                                           "searchText": "designer"}, headers={**H_JSON, "Content-Type": "application/json"})
            except Exception:
                continue
            if r.status_code == 200:
                try:
                    d = r.json()
                except Exception:
                    continue
                if isinstance(d, dict) and "jobPostings" in d:
                    found = (site, d)
                    break
        if not found:
            line(f"\n[{name}] ❌ Workday 못 찾음 (host={host})")
            continue
        site, d = found
        base = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        job_base = f"https://{host}/en-US/{site}"
        hits, seen = [], set()
        for q in ("designer", "graphic", "brand", "creative"):
            try:
                rr = client.post(base, json={"appliedFacets": {}, "limit": 20, "offset": 0,
                                             "searchText": q}, headers={**H_JSON, "Content-Type": "application/json"})
                posts = rr.json().get("jobPostings") or []
            except Exception:
                posts = []
            for p in posts:
                path = p.get("externalPath") or ""
                if path in seen:
                    continue
                seen.add(path)
                t, loc = p.get("title") or "", (p.get("locationsText") or "")
                if is_design_or_access(t) and any(k in loc.lower() for k in CA):
                    hits.append((t, loc, job_base + path))
        line(f"\n[{name}] ✅ Workday site='{site}' 디자인+GTA/캐나다/remote: {len(hits)}")
        for t, l, u in hits[:12]:
            line(f"    • {t}  —  {l}")


def rbc_td_alt():
    line("\n########## B2) RBC/TD 대체 ATS 탐지 ##########")
    for name, urls in {
        "RBC": ["https://jobs.rbc.com/api/jobs?keyword=designer&limit=20",
                "https://jobs.rbc.com/careers/SearchJobs/?keyword=designer"],
        "TD": ["https://jobs.td.com/api/jobs?keyword=designer",
               "https://jobs.td.com/en/search-jobs/results?ActiveFacetID=0&keyword=designer"],
    }.items():
        for url in urls:
            try:
                r = client.get(url, headers=H_HTML)
                ct = r.headers.get("content-type", "")
                mark = "JobDetail" if "JobDetail" in r.text else ("json" if "json" in ct else "")
                line(f"  [{name}] {url}\n    HTTP {r.status_code} ct={ct[:30]} len={len(r.text)} {mark}")
            except Exception as e:
                line(f"  [{name}] {url}\n    ERR {type(e).__name__}")


# ---------------------------------------------------- C) NUDESTIX
def nudestix():
    line("\n########## C) NUDESTIX — ATS 탐지 ##########")
    tries = [
        ("lever", "https://api.lever.co/v0/postings/nudestix?mode=json"),
        ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/nudestix/jobs"),
        ("greenhouse2", "https://boards-api.greenhouse.io/v1/boards/nudestixinc/jobs"),
        ("workable", "https://apply.workable.com/api/v3/accounts/nudestix/jobs"),
        ("workable2", "https://www.nudestix.com/careers"),
        ("bamboo", "https://nudestix.bamboohr.com/careers/list"),
        ("own", "https://www.nudestix.com/pages/careers"),
    ]
    for name, url in tries:
        try:
            r = client.get(url, headers=H_HTML)
        except Exception as e:
            line(f"  [{name}] {url}\n    ERR {type(e).__name__}")
            continue
        body = r.text[:120].replace("\n", " ")
        n = r.text.count("JobDetail") + r.text.lower().count('"title"') + r.text.count("/jobs/")
        line(f"  [{name}] HTTP {r.status_code} len={len(r.text)} hints={n}  {url}")


if __name__ == "__main__":
    avature()
    wd_probe()
    rbc_td_alt()
    nudestix()
    line("\n==================== PROBE DONE ====================")
