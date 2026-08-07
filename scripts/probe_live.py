"""일회용 SuccessFactors 목록 스크레이프 가능성 확인 (GitHub Actions 전용).

TTC(company=TTCPRODUCTION, host career17.sapsf.com)의 job_listing_summary가
HTML로 공고(career_job_req_id + 제목 + 위치)를 주는지 확인. City of Toronto의
SF host/company도 jobs.toronto.ca에서 추출 시도. 긁히면 SF 어댑터를 만든다.
검증 후 삭제.
"""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
client = httpx.Client(follow_redirects=True, timeout=25.0, headers={
    "User-Agent": UA, "Accept": "text/html,*/*;q=0.8", "Accept-Language": "en-CA,en;q=0.9"})


def summary_url(host, company):
    return (f"https://{host}/career?company={company}&career_ns=job_listing_summary"
            f"&navBarLevel=JOB_SEARCH&rcm_site_locale=en_US&selected_lang=en_US"
            f"&_s.crb=&sort_by=RELEVANCE")


def analyze(html):
    soup = BeautifulSoup(html, "html.parser")
    # SF 공고 링크: career_job_req_id=NNN
    anchors = soup.find_all("a", href=re.compile(r"career_job_req_id=\d+"))
    rows, seen = [], set()
    for a in anchors:
        m = re.search(r"career_job_req_id=(\d+)", a.get("href", ""))
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        title = a.get_text(strip=True)
        if title:
            rows.append((m.group(1), title))
    ids_raw = len(set(re.findall(r"career_job_req_id=(\d+)", html)))
    bot = "perfdrive" in html.lower() or "captcha" in html.lower() or "botmanager" in html.lower()
    return rows, ids_raw, bot


def probe(name, host, company):
    print(f"\n########## {name}  (host={host} company={company}) ##########", flush=True)
    try:
        r = client.get(summary_url(host, company))
    except Exception as e:
        print(f"    ERR {type(e).__name__}: {str(e)[:100]}", flush=True)
        return
    rows, ids_raw, bot = analyze(r.text)
    print(f"    HTTP {r.status_code} len={len(r.text)} 봇차단={bot} req_id링크={ids_raw} 파싱된공고={len(rows)}", flush=True)
    for jid, title in rows[:20]:
        print(f"      • [{jid}] {title}", flush=True)


# TTC
probe("TTC", "career17.sapsf.com", "TTCPRODUCTION")

# City of Toronto — jobs.toronto.ca 에서 SF host/company 추출
print("\n########## City of Toronto — SF 파라미터 추출 ##########", flush=True)
try:
    r = client.get("https://jobs.toronto.ca")
    html = r.text
    hosts = sorted(set(re.findall(r"(career\d+\.sapsf\.com)", html)))
    comps = sorted(set(re.findall(r"company=([A-Za-z0-9]+)", html)))
    print(f"    final={r.url} sapsf_hosts={hosts} company params={comps[:8]}", flush=True)
    if hosts and comps:
        probe("City of Toronto", hosts[0], comps[0])
except Exception as e:
    print(f"    ERR {type(e).__name__}: {str(e)[:100]}", flush=True)

print("\n==================== SF PROBE DONE ====================", flush=True)
