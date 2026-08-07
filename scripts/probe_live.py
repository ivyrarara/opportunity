"""일회용 Avature(Lululemon) 엔드포인트 탐색 (GitHub Actions 전용).

careers.lululemon.com 은 Avature 기반(URL: /en_US/careers/JobDetail/{slug}/{id}).
검색 페이지 후보를 쳐서 JobDetail 링크(공고)가 몇 개 잡히는지, 제목/위치 파싱이
되는지 확인한다. 확정되면 Avature 어댑터를 만든다. 검증 후 파일 삭제.
"""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
client = httpx.Client(follow_redirects=True, timeout=25.0, headers={
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})

BASE = "https://careers.lululemon.com"
URLS = [
    f"{BASE}/en_US/careers/SearchJobs",
    f"{BASE}/en_US/careers/SearchJobs/?jobRecordsPerPage=1000",
    f"{BASE}/en_US/careers/SearchJobs/?jobOffset=0&jobRecordsPerPage=1000",
    f"{BASE}/en_US/careers/SearchJobs/?keyword=designer",
]

try:
    from opmon.relevance import is_design_or_access
except Exception:
    def is_design_or_access(t):
        return "design" in (t or "").lower()


def line(*a):
    print(*a, flush=True)


def analyze(html: str):
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=re.compile(r"/careers/JobDetail/"))
    line(f"    JobDetail 앵커 수: {len(anchors)}")
    seen, rows = set(), []
    for a in anchors:
        href = a.get("href", "")
        m = re.search(r"/careers/JobDetail/([^/]+)/(\d+)", href)
        if not m:
            continue
        jid = m.group(2)
        if jid in seen:
            continue
        seen.add(jid)
        title = a.get_text(strip=True) or m.group(1).replace("-", " ")
        # 위치: 앵커 상위 컨테이너에서 흔한 위치 텍스트 탐색
        loc = ""
        parent = a.find_parent(["li", "div", "article", "tr"])
        if parent:
            ptxt = parent.get_text(" ", strip=True)
            lm = re.search(r"(Vancouver|Toronto|Ontario|British Columbia|Canada|Remote|New York|London|Seattle|California|Amsterdam|Shanghai|[A-Z][a-z]+,\s*[A-Z]{2})", ptxt)
            loc = lm.group(1) if lm else ""
        rows.append((jid, title, loc))
    line(f"    유니크 공고: {len(rows)}")
    design = [r for r in rows if is_design_or_access(r[1])]
    line(f"    디자인/접근성 제목: {len(design)}")
    for jid, title, loc in design[:20]:
        line(f"      • [{jid}] {title}  —  {loc}")
    # 위치 파싱이 됐는지 표본
    with_loc = [r for r in rows if r[2]]
    line(f"    위치 파싱된 표본: {len(with_loc)}/{len(rows)}  예: {with_loc[:3]}")


def main():
    for url in URLS:
        line(f"\n--- {url}")
        try:
            r = client.get(url)
        except Exception as e:
            line(f"    ERR {type(e).__name__}: {str(e)[:120]}")
            continue
        line(f"    HTTP {r.status_code}  content-type={r.headers.get('content-type','')}  len={len(r.text)}")
        if r.status_code != 200 or "JobDetail" not in r.text:
            if r.status_code == 200:
                line("    (JobDetail 링크 없음 — 아마 JS 렌더 또는 다른 경로)")
            continue
        analyze(r.text)


if __name__ == "__main__":
    main()
    line("\n==================== AVATURE PROBE DONE ====================")
