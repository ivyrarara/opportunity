"""일회용 캐나다 공공기관 ATS 탐지 (GitHub Actions 전용).

City of Toronto / York Region / Metrolinx / TTC 의 채용 시스템을 알아낸다.
각 careers 랜딩을 받아 ATS 시그널(njoyn+clid / workday / taleo / successfactors)과
공고 링크·디자인 제목을 스캔한다. Njoyn이면 clid를 뽑아 바로 붙일 수 있다.
검증 후 삭제.
"""

from __future__ import annotations

import re

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
client = httpx.Client(follow_redirects=True, timeout=25.0, headers={
    "User-Agent": UA, "Accept": "text/html,*/*;q=0.8", "Accept-Language": "en-CA,en;q=0.9"})

ORGS = {
    "City of Toronto": [
        "https://jobs.toronto.ca",
        "https://www.toronto.ca/city-government/jobs-employment/",
    ],
    "York Region": [
        "https://york.njoyn.com/cl4/xweb/xweb.asp?page=joblisting&clid=&lang=1",
        "https://www.york.ca/york-region/careers",
        "https://careers.york.ca",
    ],
    "Metrolinx": [
        "https://careers.metrolinx.com",
        "https://www.metrolinx.com/en/about-us/careers",
    ],
    "TTC": [
        "https://www.ttc.ca/about-the-ttc/careers",
        "https://ttccareers.ttc.ca",
    ],
}


def detect(html, final_url):
    sig = []
    low = html.lower()
    if "njoyn.com" in low:
        sig.append("NJOYN")
        m = re.search(r'njoyn\.com', low)
    if "myworkdayjobs" in low or "/wday/" in low:
        sig.append("WORKDAY")
    if "careersection" in low or "taleo" in low:
        sig.append("TALEO")
    if "successfactors" in low or "sfcareer" in low:
        sig.append("SUCCESSFACTORS")
    if "greenhouse.io" in low:
        sig.append("GREENHOUSE")
    if "icims" in low:
        sig.append("ICIMS")
    if "oraclecloud" in low or "/hcmui/" in low:
        sig.append("ORACLE")
    # njoyn clid
    clids = re.findall(r'clid=(\d+)', html)
    hosts = re.findall(r'([a-z0-9-]+)\.njoyn\.com', low)
    # job 링크류
    njoyn_jobs = len(re.findall(r'Page=JobDetails', html, re.I))
    return sig, sorted(set(clids)), sorted(set(hosts)), njoyn_jobs


for name, urls in ORGS.items():
    print(f"\n########## {name} ##########", flush=True)
    for url in urls:
        try:
            r = client.get(url)
        except Exception as e:
            print(f"  {url}\n    ERR {type(e).__name__}: {str(e)[:90]}", flush=True)
            continue
        sig, clids, hosts, njobs = detect(r.text, str(r.url))
        print(f"  {url}\n    HTTP {r.status_code} → {r.url}", flush=True)
        print(f"    ATS={sig or '?(JS렌더 가능)'} njoyn_hosts={hosts} clids={clids[:6]} JobDetails링크={njobs} len={len(r.text)}", flush=True)

print("\n==================== PUBLIC ATS PROBE DONE ====================", flush=True)
